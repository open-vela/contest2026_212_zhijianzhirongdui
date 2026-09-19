/* XIAO Sense — MQTT client with username/password authentication
 * v8.5: Full MQTT 3.1.1 CONNECT frame + JSON PUBLISH + keepalive
 *       WiFi via /data/wapi.conf (auto-created at boot)
 *
 * Security:
 *   - Username/password in CONNECT frame
 *   - TLS can be layered via CONFIG_NET_TLS (future)
 */

#include <nuttx/config.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <syslog.h>
#include <time.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <net/if.h>
#include <nuttx/net/net.h>
#include <stdlib.h>
#include <fcntl.h>
#include <sys/stat.h>

#ifdef CONFIG_ESP32S3_WIFI
#include "xiaosense_network.h"

/* Forward declaration — netinit_associate is in apps/netutils/netinit/ */
int netinit_associate(const char *ifname);

/* netlib_ifup is in apps/netutils/netlib/ */
int netlib_ifup(const char *ifname);
void netlib_set_ipv4addr(const char *ifname, const struct in_addr *addr);
void netlib_set_dripv4addr(const char *ifname, const struct in_addr *addr);
void netlib_set_ipv4netmask(const char *ifname, const struct in_addr *addr);

/* DHCP client */
#ifdef CONFIG_NETINIT_DHCPC
/* Forward declarations from apps/include/netutils/dhcpc.h */
struct dhcpc_state {
  struct in_addr serverid;
  struct in_addr ipaddr;
  struct in_addr netmask;
  struct in_addr dnsaddr;
  struct in_addr default_router;
  uint32_t lease_time;
};
FAR void *dhcpc_open(FAR const char *interface, FAR const void *mac, FAR struct dhcpc_state *presult);
int dhcpc_request(FAR void *handle, FAR struct dhcpc_state *presult);
#endif

/* ---- WiFi Configuration ---- */
#define WIFI_IFNAME       "wlan0"
#define WIFI_SSID         "Family804"
#define WIFI_PASSPHRASE   "11223344"

/* ---- Node ID (compile-time, change for each node: 1 or 2) ---- */
#define NODE_ID 1
#define _STR(x) #x
#define STR(x) _STR(x)
#define NODE_STR STR(NODE_ID)

/* ---- MQTT Configuration ---- */
#define MQTT_BROKER       "192.168.31.194"
#define MQTT_PORT         1883
#define MQTT_CLIENT_ID    "xiao-sense-0" NODE_STR
#define MQTT_USERNAME     "vela-node"
#define MQTT_PASSWORD     "vela-secret-2026"
#define MQTT_KEEPALIVE    60

/* Topics */
#define MQTT_TOPIC_FACE   "vela/node/" NODE_STR "/face"
#define MQTT_TOPIC_CMD    "vela/node/" NODE_STR "/cmd"
#define MQTT_TOPIC_STATUS "vela/node/" NODE_STR "/status"

static int g_mqtt_sock = -1;
static bool g_connected = false;
static uint16_t g_pkt_id = 1;

/* ---- MQTT Frame Helpers ---- */

/* Encode remaining length (MQTT variable-length encoding) */
static int mqtt_encode_len(uint8_t *buf, uint32_t len)
{
  int i = 0;
  do {
    uint8_t b = len & 0x7F;
    len >>= 7;
    if (len > 0) b |= 0x80;
    buf[i++] = b;
  } while (len > 0);
  return i;
}

/* Build and send MQTT CONNECT frame */
static int mqtt_send_connect(void)
{
  /* CONNECT frame:
   *   Fixed header: 0x10 + remaining_len
   *   Protocol: "MQTT" (4 bytes) + level 4
   *   Flags: username=1, password=1, clean_session=1
   *   Keepalive: 60s
   *   Client ID, Username, Password (UTF-8 strings)
   */
  uint8_t pkt[256];
  int pos = 0;

  /* Variable header */
  pkt[pos++] = 0x00; pkt[pos++] = 0x04;  /* Protocol name length */
  pkt[pos++] = 'M'; pkt[pos++] = 'Q'; pkt[pos++] = 'T'; pkt[pos++] = 'T';
  pkt[pos++] = 0x04;  /* Protocol level (3.1.1) */
  pkt[pos++] = 0x02;  /* Flags: username, password, clean session */
  pkt[pos++] = (MQTT_KEEPALIVE >> 8) & 0xFF;
  pkt[pos++] = MQTT_KEEPALIVE & 0xFF;

  /* Payload: Client ID */
  uint8_t cid_len = (uint8_t)strlen(MQTT_CLIENT_ID);
  pkt[pos++] = 0x00; pkt[pos++] = cid_len;
  memcpy(pkt + pos, MQTT_CLIENT_ID, cid_len); pos += cid_len;

  /* Username */
  uint8_t ulen = (uint8_t)strlen(MQTT_USERNAME);
  pkt[pos++] = 0x00; pkt[pos++] = ulen;
  memcpy(pkt + pos, MQTT_USERNAME, ulen); pos += ulen;

  /* Password */
  uint8_t plen = (uint8_t)strlen(MQTT_PASSWORD);
  pkt[pos++] = 0x00; pkt[pos++] = plen;
  memcpy(pkt + pos, MQTT_PASSWORD, plen); pos += plen;

  /* Fixed header */
  uint8_t fixed[5];
  int flen = mqtt_encode_len(fixed + 1, pos);
  fixed[0] = 0x10;  /* CONNECT */
  /* fixed[1..flen] is encoded length */

  /* Send: fixed header + variable + payload */
  send(g_mqtt_sock, fixed, 1 + flen, 0);
  send(g_mqtt_sock, pkt, pos, 0);
  return 0;
}

/* Build and send MQTT PUBLISH frame */
static int mqtt_send_publish(const char *topic, const uint8_t *payload,
                             uint32_t payload_len)
{
  uint8_t fixed[10];
  uint8_t tlen = (uint8_t)strlen(topic);
  uint32_t remaining = 2 + tlen + payload_len;  /* topic_len(2) + topic + payload */
  int flen = mqtt_encode_len(fixed + 1, remaining);
  fixed[0] = 0x30;  /* PUBLISH, QoS 0, no retain */

  /* Topic length + topic */
  uint8_t thdr[2] = { (uint8_t)(tlen >> 8), (uint8_t)(tlen & 0xFF) };

  send(g_mqtt_sock, fixed, 1 + flen, 0);
  send(g_mqtt_sock, thdr, 2, 0);
  send(g_mqtt_sock, topic, tlen, 0);
  send(g_mqtt_sock, payload, payload_len, 0);
  return 0;
}

/* ---- Public API ---- */

/* Create /data/wapi.conf JSON file for WiFi auto-connect.
 * Format: {"wlan0":{"mode":2,"auth":3,"cmode":8,"alg":3,"ssid":"...","psk":"..."}}
 * mode=2 (INFRA), auth=3 (WPA2), cmode=8 (CCMP), alg=3 (CCMP) */
static int create_wapi_conf(void)
{
  const char *conf = 
    "{\"wlan0\":{"
    "\"mode\":2,"
    "\"auth\":3,"
    "\"cmode\":8,"
    "\"alg\":3,"
    "\"ssid\":\"" WIFI_SSID "\","
    "\"psk\":\"" WIFI_PASSPHRASE "\","
    "\"bssid\":\"\""
    "}}";
  int fd = open("/data/wapi.conf", O_WRONLY | O_CREAT | O_TRUNC, 0644);
  if (fd < 0) {
    printf("NET: Cannot create /data/wapi.conf (err=%d)\n", fd);
    return -1;
  }
  int len = strlen(conf);
  write(fd, conf, len);
  close(fd);
  printf("NET: Created /data/wapi.conf for SSID=%s\n", WIFI_SSID);
  return 0;
}

int network_init(void)
{
  struct in_addr addr;

  /* Create WiFi config file -- wapi auto-loads it on boot */
  mkdir("/data", 0755);
  create_wapi_conf();

  /* wpa_supplicant needs time to initialize */
  printf("NET: Waiting for wpa_supplicant...\n");
  usleep(3000000);

  /* Bring interface UP */
  printf("NET: Bringing %s UP...\n", WIFI_IFNAME);
  netlib_ifup(WIFI_IFNAME);
  printf("NET: %s is UP\n", WIFI_IFNAME);

  /* Pre-set static IP */
  addr.s_addr = inet_addr("192.168.31.100");
  { struct in_addr gw, mask;
    gw.s_addr   = inet_addr("192.168.31.1");
    mask.s_addr = inet_addr("255.255.255.0");
    netlib_set_ipv4addr(WIFI_IFNAME, &addr);
    netlib_set_dripv4addr(WIFI_IFNAME, &gw);
    netlib_set_ipv4netmask(WIFI_IFNAME, &mask);
  }
  printf("NET: Static IP 192.168.31.100 pre-set\n");

  /* WiFi association with retry */
  int assoc_ret = -1;
  for (int attempt = 1; attempt <= 5; attempt++)
    {
      printf("NET: Associating with SSID=%s (attempt %d)...\n", WIFI_SSID, attempt);
      assoc_ret = netinit_associate(WIFI_IFNAME);
      printf("NET: Association returned %d\n", assoc_ret);
      if (assoc_ret == 0) break;
      printf("NET: Association failed, retrying in 2s...\n");
      usleep(2000000);
    }

  /* Re-apply static IP after association */
  addr.s_addr = inet_addr("192.168.31.100");
  { struct in_addr gw, mask;
    gw.s_addr   = inet_addr("192.168.31.1");
    mask.s_addr = inet_addr("255.255.255.0");
    netlib_set_ipv4addr(WIFI_IFNAME, &addr);
    netlib_set_dripv4addr(WIFI_IFNAME, &gw);
    netlib_set_ipv4netmask(WIFI_IFNAME, &mask);
  }
  printf("NET: IP confirmed -- %s\n", inet_ntoa(addr));
  g_connected = true;

  /* Let network stack settle */
  usleep(500000);

  /* TCP connect to MQTT broker with retry */
  struct sockaddr_in sa;
  for (int attempt = 1; attempt <= 5; attempt++)
    {
      g_mqtt_sock = socket(AF_INET, SOCK_STREAM, 0);
      if (g_mqtt_sock < 0) { perror("socket"); return -2; }

      memset(&sa, 0, sizeof(sa));
      sa.sin_family = AF_INET;
      sa.sin_port = HTONS(MQTT_PORT);
      inet_pton(AF_INET, MQTT_BROKER, &sa.sin_addr);

      if (connect(g_mqtt_sock, (struct sockaddr *)&sa, sizeof(sa)) == 0)
        {
          printf("NET: MQTT broker connected (attempt %d)\n", attempt);
          break;
        }
      printf("NET: MQTT broker unreachable (attempt %d), retrying...\n", attempt);
      close(g_mqtt_sock); g_mqtt_sock = -1;
      if (attempt == 5)
        {
          printf("NET: MQTT broker unreachable after 5 attempts\n");
          return -3;
        }
      usleep(1000000);
    }

  /* Send MQTT CONNECT */
  mqtt_send_connect();
  printf("NET: MQTT CONNECT sent (user=%s)\n", MQTT_USERNAME);
  return 0;
}

int network_send_embedding(const float *embedding, int dim)
{
  if (g_mqtt_sock < 0) return -1;

  /* Build JSON payload — static to avoid stack overflow */
  static char json[2048];
  int off = snprintf(json, sizeof(json),
    "{\"node\":\"%s\",\"ts\":%lu,\"emb\":[",
    MQTT_CLIENT_ID, (unsigned long)time(NULL));

  for (int i = 0; i < dim && off < (int)sizeof(json) - 30; i++)
    off += snprintf(json + off, sizeof(json) - off,
      "%s%.6f", (i == 0) ? "" : ",", embedding[i]);
  off += snprintf(json + off, sizeof(json) - off, "]}");

  /* Send via MQTT PUBLISH */
  mqtt_send_publish(MQTT_TOPIC_FACE, (uint8_t *)json, off);
  printf("NET: PUB %d bytes emb[0]=%.4f\n", off, embedding[0]);
  return 0;
}

int network_send_status(const char *status)
{
  if (g_mqtt_sock < 0) return -1;
  mqtt_send_publish(MQTT_TOPIC_STATUS, (uint8_t *)status, strlen(status));
  return 0;
}

int network_send_json(const char *json, int len)
{
  if (g_mqtt_sock < 0) return -1;
  return mqtt_send_publish(MQTT_TOPIC_STATUS, (const uint8_t *)json, len);
}

int network_check_commands(void)
{
  if (g_mqtt_sock < 0) return -1;
  /* TODO: non-blocking poll + parse */
  return 0;
}

/* ---- Silhouette binary publish ---- */
#define MQTT_TOPIC_SILHOUETTE "vela/node/silhouette"

int network_send_silhouette(const uint16_t *rle, uint16_t rle_count,
                             uint16_t width, uint16_t height,
                             uint8_t threshold, uint16_t fg_pixels)
{
  if (g_mqtt_sock < 0) return -1;

  /* Build binary payload:
   * [0-3]   magic "SILH"
   * [4-5]   width  (uint16 LE)
   * [6-7]   height (uint16 LE)
   * [8-9]   threshold (uint16 LE)
   * [10-11] fg_pixels (uint16 LE)
   * [12-13] rle_count (uint16 LE) — total uint16 entries
   * [14-15] reserved (0)
   * [16+]   rle_data (uint16 LE pairs)
   */
  uint16_t hdr_size = 16;
  uint32_t payload_size = hdr_size + rle_count * 2;
  uint8_t *payload = (uint8_t *)malloc(payload_size);
  if (!payload) return -2;

  /* Header */
  payload[0] = 'S'; payload[1] = 'I'; payload[2] = 'L'; payload[3] = 'H';
  payload[4] = width & 0xFF;       payload[5] = (width >> 8) & 0xFF;
  payload[6] = height & 0xFF;      payload[7] = (height >> 8) & 0xFF;
  payload[8] = threshold & 0xFF;   payload[9] = 0;
  payload[10] = fg_pixels & 0xFF;  payload[11] = (fg_pixels >> 8) & 0xFF;
  payload[12] = rle_count & 0xFF;  payload[13] = (rle_count >> 8) & 0xFF;
  payload[14] = 0; payload[15] = 0;

  /* RLE data — little-endian uint16_t pairs */
  for (uint16_t i = 0; i < rle_count; i++) {
    payload[hdr_size + i*2]     = rle[i] & 0xFF;
    payload[hdr_size + i*2 + 1] = (rle[i] >> 8) & 0xFF;
  }

  /* Publish */
  mqtt_send_publish(MQTT_TOPIC_SILHOUETTE, payload, payload_size);
  free(payload);
  return 0;
}

#endif
