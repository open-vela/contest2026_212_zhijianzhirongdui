/****************************************************************************
 * VelaMesh (枢络) — vela_edge slave node application
 *
 * Runs on the XIAO ESP32S3 Sense edge node. Production pipeline (integrated
 * in later contest tasks, sources under modules/):
 *
 *   camera DMA (OV2640/OV3660)
 *     -> gait silhouette pre-filter (modules/gait)
 *     -> MobileFaceNet embedding via TFLite Micro (modules/inference)
 *   BLE passive scan (modules/ble)
 *     -> WiFi/MQTT uplink to the R528 hub (modules/net)
 *
 * This main is the stage-1 stub: it builds into the openvela image as an
 * NSH command ("vela_edge") and exercises the planned init/loop contract so
 * bring-up and CI can verify the linkfile wiring end to end.
 ****************************************************************************/

#include <nuttx/config.h>

#include <stdio.h>
#include <unistd.h>

#define VELA_EDGE_STUB_PERIOD_SEC  5
#define VELA_EDGE_STUB_ITERATIONS  3

/****************************************************************************
 * Public Functions
 ****************************************************************************/

int main(int argc, char *argv[])
{
  int i;

  printf("\n");
  printf("==================================================\n");
  printf("  VelaMesh (shu-luo) edge node  [stage-1 stub]\n");
  printf("  XIAO ESP32S3 Sense: camera + BLE + MQTT uplink\n");
  printf("==================================================\n");
  printf("[vela_edge] planned modules (integrated in later tasks):\n");
  printf("            camera DMA -> gait filter -> face embedding\n");
  printf("            BLE proximity scan -> MQTT uplink to hub\n");

  for (i = 0; i < VELA_EDGE_STUB_ITERATIONS; i++)
    {
      printf("[vela_edge] loop %d/%d: stub tick, sensors idle\n",
             i + 1, VELA_EDGE_STUB_ITERATIONS);
      sleep(VELA_EDGE_STUB_PERIOD_SEC);
    }

  printf("[vela_edge] stub run complete.\n");
  return 0;
}
