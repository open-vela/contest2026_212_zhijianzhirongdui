/* ble_scanner_stub.c — minimal BLE scanner stub for build verification
 * Replace with ble_scanner_nuttx.c when BLE driver is fully ready.
 */

#include <stdio.h>
#include <nuttx/config.h>

#ifdef CONFIG_ESP32S3_BLE

int ble_scanner_run(int duration_sec)
{
  printf("BLE: scanner stub — scan for %d sec (not yet implemented)\n", duration_sec);
  return 0;
}

#endif
