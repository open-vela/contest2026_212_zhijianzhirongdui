/* ble_scanner_nuttx.c — NuttX native BLE scanner using IOCTL API
 * Replaces ESP-IDF NimBLE code. Uses bt_ioctl.h for scan start/get/stop.
 * Reports RSSI+MAC+distance via MQTT.
 *
 * Pattern: follows btsak_scan.c — socket + ioctl directly, NO bind needed.
 */

#include <sys/socket.h>
#include <sys/ioctl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <math.h>

#include <nuttx/wireless/bluetooth/bt_ioctl.h>
#include <netpacket/bluetooth.h>
#include "xiaosense_network.h"

/* Forward declaration — bring up Bluetooth netdev */
int netlib_ifup(const char *ifname);

#define SCAN_PERIOD_MS   3000
#define MAX_SCAN_RESULTS 10
#define TX_POWER_1M     -62    /* RSSI at 1 meter (device-dependent) */
#define ENV_FACTOR       2.5f   /* indoor path loss exponent */

/* Estimate distance in meters from RSSI */
static float rssi_to_distance(int rssi)
{
  if (rssi >= TX_POWER_1M) return 0.3f;
  float ratio = (TX_POWER_1M - rssi) / (10.0f * ENV_FACTOR);
  return powf(10.0f, ratio);
}

int ble_scanner_run(int duration_sec)
{
  struct btreq_s btreq;
  struct bt_scanresponse_s results[MAX_SCAN_RESULTS];
  int sockfd;
  int ret;
  int scans;

  /* Bring up bnep0 interface (required for ioctl to work) */
  printf("BLE: bringing up bnep0...\n");
  netlib_ifup("bnep0");
  usleep(500000);

  /* Create Bluetooth socket — NO bind needed (like btsak) */
  sockfd = socket(PF_BLUETOOTH, SOCK_RAW, BTPROTO_L2CAP);
  if (sockfd < 0) {
    printf("BLE: socket failed (err=%d)\n", errno);
    return -1;
  }

  /* Start scanning */
  memset(&btreq, 0, sizeof(btreq));
  strlcpy(btreq.btr_name, "bnep0", IFNAMSIZ);
  btreq.btr_dupenable = false;

  ret = ioctl(sockfd, SIOCBTSCANSTART, (unsigned long)&btreq);
  if (ret < 0) {
    printf("BLE: scan start failed (err=%d)\n", errno);
    close(sockfd);
    return -1;
  }
  puts("BLE: scan started");

  /* Scan loop */
  int max_scans = duration_sec * 1000 / SCAN_PERIOD_MS;
  if (max_scans < 1) max_scans = 1;

  for (scans = 0; scans < max_scans; scans++) {
    usleep(SCAN_PERIOD_MS * 1000);

    memset(&btreq, 0, sizeof(btreq));
    strlcpy(btreq.btr_name, "bnep0", IFNAMSIZ);
    btreq.btr_nrsp = MAX_SCAN_RESULTS;
    btreq.btr_rsp  = results;

    ret = ioctl(sockfd, SIOCBTSCANGET, (unsigned long)&btreq);
    if (ret < 0) {
      printf("BLE: scan get failed (err=%d)\n", errno);
      continue;
    }

    int nrsp = btreq.btr_nrsp;
    printf("BLE: found %d devices\n", nrsp);

    for (int i = 0; i < nrsp; i++) {
      struct bt_scanresponse_s *r = &results[i];
      float dist = rssi_to_distance(r->sr_rssi);

      printf("BLE: %02x:%02x:%02x:%02x:%02x:%02x RSSI=%d dist=%.1fm\n",
             r->sr_addr.val[5], r->sr_addr.val[4], r->sr_addr.val[3],
             r->sr_addr.val[2], r->sr_addr.val[1], r->sr_addr.val[0],
             r->sr_rssi, dist);

      /* Publish via MQTT (JSON) */
      char json[256];
      snprintf(json, sizeof(json),
        "{\"type\":\"ble\",\"mac\":\"%02x:%02x:%02x:%02x:%02x:%02x\","
        "\"rssi\":%d,\"dist\":%.1f}",
        r->sr_addr.val[0], r->sr_addr.val[1], r->sr_addr.val[2],
        r->sr_addr.val[3], r->sr_addr.val[4], r->sr_addr.val[5],
        r->sr_rssi, dist);
      network_send_json(json, strlen(json));
    }
  }

  /* Stop scanning */
  memset(&btreq, 0, sizeof(btreq));
  strlcpy(btreq.btr_name, "bnep0", IFNAMSIZ);
  ioctl(sockfd, SIOCBTSCANSTOP, (unsigned long)&btreq);
  close(sockfd);
  puts("BLE: scan complete");
  return 0;
}
