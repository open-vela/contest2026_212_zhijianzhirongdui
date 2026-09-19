/****************************************************************************
 * ble_employee_scanner.h — BLE 员工检测模块 (ESP32-S3)
 * v8.6 — 被动扫描 + RSSI 距离分级 + IRK 解析
 *
 * 原理: ESP32-S3 被动扫描周围 BLE 广播包，匹配预注册的员工设备。
 * 无需 App、无需配对、零用户操作。
 *
 * 集成方式: 在 network_init() 后调用 ble_scanner_init() + ble_scanner_start()
 * 检测结果通过回调上报到融合引擎。
 ****************************************************************************/

#ifndef __BLE_EMPLOYEE_SCANNER_H
#define __BLE_EMPLOYEE_SCANNER_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---- RSSI 距离分级 ---- */
typedef enum {
    BLE_PROX_IMMEDIATE = 0,  /* < 0.5m, RSSI > -45  */
    BLE_PROX_NEAR,           /* 0.5-2m, RSSI -45~-65 */
    BLE_PROX_MID,            /* 2-5m,   RSSI -65~-75 */
    BLE_PROX_FAR,            /* 5-10m,  RSSI -75~-85 */
    BLE_PROX_UNKNOWN         /* > 10m or invalid       */
} ble_proximity_t;

/* ---- 检测结果 ---- */
typedef struct {
    int    employee_id;       /* 员工索引 */
    int    rssi;              /* 当前 RSSI (EMA 平滑后) */
    float  distance_m;        /* 估算距离 (米) */
    ble_proximity_t proximity;/* 距离等级 */
    bool   present;           /* 当前是否在检测范围内 */
} ble_detection_t;

/* ---- 回调: 检测到员工设备 ---- */
typedef void (*ble_detection_cb_t)(const ble_detection_t *det);

/* ---- API ---- */

/* 初始化 BLE 扫描器 (需在 WiFi 就绪后调用) */
int  ble_scanner_init(void);

/* 注册员工 BLE 设备
 * name: 员工姓名
 * identity_addr: 6字节 MAC (静态地址或 Identity Address)
 * irk: 16字节 IRK (可选, 用于解析随机MAC; 传 NULL 则按静态 MAC 匹配)
 * tx_power: 1米处 RSSI 校准值 (典型 -62)
 * 返回: 员工索引 (>=0), 失败 -1 */
int  ble_register_employee(const char *name, const uint8_t identity_addr[6],
                           const uint8_t irk[16], int tx_power);

/* 启动连续扫描 (可重复调用以更新参数)
 * interval_ms: 扫描间隔 (0=连续)
 * window_ms:   扫描窗口 (建议 100ms, 平衡功耗和实时性) */
int  ble_scanner_start(uint32_t interval_ms, uint32_t window_ms);

/* 停止扫描 */
void ble_scanner_stop(void);

/* 设置检测回调 */
void ble_set_detection_callback(ble_detection_cb_t cb);

/* 获取当前最大员工数 */
int  ble_get_max_employees(void);

#ifdef __cplusplus
}
#endif

#endif /* __BLE_EMPLOYEE_SCANNER_H */
