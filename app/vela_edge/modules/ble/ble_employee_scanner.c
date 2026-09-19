/****************************************************************************
 * ble_employee_scanner.c — BLE 员工检测模块 (ESP32-S3, NimBLE 栈)
 * v8.6 — 被动扫描 + EMA 平滑 + 距离估算 + 超时检测
 *
 * 依赖: ESP-IDF NimBLE or NuttX BLE API
 * 适配: openvela 可通过 NuttX bt_* API 或直接接入 NimBLE
 *
 * 编译选项:
 *   BLE_SCANNER_NIMBLE    — 使用 NimBLE 栈 (ESP-IDF 默认)
 *   BLE_SCANNER_NUTTX     — 使用 NuttX wireless/bluetooth API
 ****************************************************************************/

#include "ble_employee_scanner.h"
#include <string.h>
#include <math.h>
#include <time.h>

/* ---- 编译时配置 ---- */
#define BLE_SCANNER_NIMBLE  1   /* ESP-IDF NimBLE */
/* #define BLE_SCANNER_NUTTX 1 */  /* NuttX (future) */

#define MAX_EMPLOYEES        50
#define EMA_ALPHA            0.3f    /* RSSI 指数平滑因子 */
#define TIMEOUT_MS           30000   /* 30秒无信号=离开 */
#define DEFAULT_TX_POWER     -62     /* 1米处典型 RSSI */
#define ENV_FACTOR           2.5f    /* 室内环境衰减因子 */

/* ---- 员工数据库 ---- */
typedef struct {
    char     name[32];
    uint8_t  identity_addr[6];
    uint8_t  addr_type;
    uint8_t  irk[16];
    bool     has_irk;
    int      tx_power;
    int      rssi;           /* EMA 平滑后的当前 RSSI */
    uint32_t last_seen_ms;
    bool     present;
} employee_t;

static employee_t g_employees[MAX_EMPLOYEES];
static int g_employee_count = 0;
static ble_detection_cb_t g_callback = NULL;
static bool g_scanning = false;

/* ---- 内部: RSSI → 距离 ---- */
static float rssi_to_distance(int rssi, int tx_power) {
    if (rssi >= 0) return -1.0f;
    float ratio = (float)(tx_power - rssi) / (10.0f * ENV_FACTOR);
    return powf(10.0f, ratio);
}

/* ---- 内部: RSSI → 等级 ---- */
static ble_proximity_t rssi_to_proximity(int rssi) {
    if (rssi > -45) return BLE_PROX_IMMEDIATE;
    if (rssi > -65) return BLE_PROX_NEAR;
    if (rssi > -75) return BLE_PROX_MID;
    if (rssi > -85) return BLE_PROX_FAR;
    return BLE_PROX_UNKNOWN;
}

/* ---- 内部: EMA 平滑 ---- */
static void ema_update(employee_t *emp, int new_rssi) {
    if (emp->rssi == 0) {
        emp->rssi = new_rssi;
    } else {
        emp->rssi = (int)((1.0f - EMA_ALPHA) * emp->rssi + EMA_ALPHA * new_rssi);
    }
}

/* ---- 内部: 查找员工 ---- */
static int find_employee(const uint8_t *addr) {
    for (int i = 0; i < g_employee_count; i++) {
        if (memcmp(g_employees[i].identity_addr, addr, 6) == 0)
            return i;
    }
    return -1;
}

/* ---- 内部: 检测回调触发 ---- */
static void notify_detection(int idx, int rssi) {
    if (!g_callback) return;
    employee_t *emp = &g_employees[idx];
    ble_detection_t det = {
        .employee_id = idx,
        .rssi = rssi,
        .distance_m = rssi_to_distance(rssi, emp->tx_power),
        .proximity = rssi_to_proximity(rssi),
        .present = true
    };
    g_callback(&det);
}

/* ---- 内部: 超时检查 ---- */
static void check_timeouts(uint32_t now_ms) {
    for (int i = 0; i < g_employee_count; i++) {
        if (g_employees[i].present &&
            (now_ms - g_employees[i].last_seen_ms) > TIMEOUT_MS) {
            g_employees[i].present = false;
            g_employees[i].rssi = 0;
            if (g_callback) {
                ble_detection_t det = {.employee_id = i, .present = false};
                g_callback(&det);
            }
        }
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * NimBLE 实现 (ESP-IDF)
 * ═══════════════════════════════════════════════════════════════════ */
#if BLE_SCANNER_NIMBLE

#include "esp_nimble_hci.h"
#include "nimble/nimble_port.h"
#include "host/ble_hs.h"
#include "host/ble_gap.h"
#include "services/gap/ble_svc_gap.h"

static uint32_t g_scan_interval = 0;   /* 0 = continuous */
static uint32_t g_scan_window   = 100; /* ms */

/* NimBLE GAP 事件回调 */
static int nimble_gap_event(struct ble_gap_event *event, void *arg) {
    (void)arg;
    switch (event->type) {
    case BLE_GAP_EVENT_DISC: {
        struct ble_gap_disc_desc *d = &event->disc;
        int idx = find_employee(d->addr.val);
        if (idx < 0) break;  /* 非注册设备 */
        
        ema_update(&g_employees[idx], d->rssi);
        g_employees[idx].last_seen_ms = (uint32_t)(clock() * 1000 / CLOCKS_PER_SEC);
        g_employees[idx].present = true;
        notify_detection(idx, g_employees[idx].rssi);
        break;
    }
    case BLE_GAP_EVENT_DISC_COMPLETE:
        if (g_scanning) {
            /* Restart scan */
            ble_gap_disc(0, NULL, g_scan_interval, 
                         (uint16_t)(g_scan_window / 0.625),
                         (uint16_t)(g_scan_interval / 0.625),
                         0, NULL, NULL);
        }
        break;
    default:
        break;
    }
    return 0;
}

static void nimble_on_sync(void) {
    /* Start scanning after sync */
    ble_gap_disc(0, NULL, g_scan_interval,
                 (uint16_t)(g_scan_window / 0.625),
                 (uint16_t)(g_scan_interval / 0.625),
                 0, nimble_gap_event, NULL);
}

int ble_scanner_init(void) {
    esp_nimble_hci_init();
    nimble_port_init();
    ble_hs_cfg.sync_cb = nimble_on_sync;
    /* ble_hs_cfg.reset_cb = ... */
    return 0;
}

int ble_scanner_start(uint32_t interval_ms, uint32_t window_ms) {
    g_scan_interval = interval_ms;
    g_scan_window   = window_ms > 0 ? window_ms : 100;
    g_scanning = true;
    /* If already synced, restart scan; otherwise sync_cb will start */
    return 0;
}

void ble_scanner_stop(void) {
    g_scanning = false;
    ble_gap_disc_cancel();
}

#endif /* BLE_SCANNER_NIMBLE */

/* ═══════════════════════════════════════════════════════════════════
 * NuttX 适配层 (openvela — 后续集成)
 * ═══════════════════════════════════════════════════════════════════ */
#if BLE_SCANNER_NUTTX

#include <nuttx/wireless/bluetooth/bt_core.h>
#include <nuttx/wireless/bluetooth/bt_hci.h>
#include <nuttx/wireless/bluetooth/bt_gap.h>

static void nuttx_disc_cb(const bt_addr_le_t *addr, int8_t rssi,
                          const struct bt_data *ad, size_t ad_len) {
    int idx = find_employee(addr->val);
    if (idx < 0) return;
    ema_update(&g_employees[idx], rssi);
    g_employees[idx].last_seen_ms = (uint32_t)(clock() * 1000 / CLOCKS_PER_SEC);
    g_employees[idx].present = true;
    notify_detection(idx, g_employees[idx].rssi);
}

int ble_scanner_init(void) {
    bt_initialize();
    struct bt_le_scan_param param = {
        .type = BT_LE_SCAN_TYPE_PASSIVE,
        .interval = 0x0100,
        .window = 0x0050,
    };
    bt_le_scan_start(&param, nuttx_disc_cb);
    return 0;
}

int ble_scanner_start(uint32_t interval_ms, uint32_t window_ms) {
    /* Restart with new params — NuttX API TBD */
    return 0;
}

void ble_scanner_stop(void) {
    bt_le_scan_stop();
}

#endif /* BLE_SCANNER_NUTTX */

/* ---- 公共 API ---- */

int ble_register_employee(const char *name, const uint8_t identity_addr[6],
                           const uint8_t irk[16], int tx_power) {
    if (g_employee_count >= MAX_EMPLOYEES) return -1;
    employee_t *e = &g_employees[g_employee_count];
    strncpy(e->name, name, 31);
    memcpy(e->identity_addr, identity_addr, 6);
    e->addr_type = 0; /* public */
    if (irk) { memcpy(e->irk, irk, 16); e->has_irk = true; }
    e->tx_power = tx_power ? tx_power : DEFAULT_TX_POWER;
    e->rssi = 0;
    e->present = false;
    return g_employee_count++;
}

void ble_set_detection_callback(ble_detection_cb_t cb) {
    g_callback = cb;
}

int ble_get_max_employees(void) { return MAX_EMPLOYEES; }
