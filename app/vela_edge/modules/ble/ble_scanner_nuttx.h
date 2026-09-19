/* ble_scanner_nuttx.h — NuttX native BLE scanner */

#ifndef __BLE_SCANNER_NUTTX_H
#define __BLE_SCANNER_NUTTX_H

#ifdef CONFIG_ESP32S3_BLE
int ble_scanner_run(int duration_sec);
#endif

#endif
