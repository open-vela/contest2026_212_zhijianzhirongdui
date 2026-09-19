# BLE 蓝牙无感身份识别 — 调研报告

> 2026-06-08 | ESP32-S3 + openvela | 作为人脸+步态的第三模态

## 核心方案：被动 BLE 扫描

ESP32-S3 在**被动扫描模式**下，无需配对即可检测员工手机/手表的 BLE 广播包（MAC、RSSI、设备名）。零 App、零用户操作。

## MAC 随机化应对

现代手机（iOS 14+/Android 10+）默认随机化 MAC。解决：
- **IRK 方案（推荐）**：提前配对获取 IRK → NimBLE 自动解析随机 MAC
- **专用 BLE 工牌**：静态 MAC，最可靠但需额外硬件（成本 ~¥15/个）
- **Service UUID 匹配**：匹配特定服务 UUID

## RSSI 距离分级

| 等级 | RSSI | 距离 | 置信度 |
|------|------|------|:--:|
| 贴身 | > -45 | <0.5m | 0.95 |
| 近距 | -45~-65 | 0.5-2m | 0.80 |
| 中距 | -65~-75 | 2-5m | 0.50 |
| 远距 | -75~-85 | 5-10m | 0.25 |

使用**指数移动平均 (α=0.3)** 平滑 RSSI 波动。

## NuttX/openvela BLE 现状

- NuttX 有 BLE 子系统（`include/nuttx/wireless/bt.h`），支持 `bt bnep0 scan`
- openvela 有 `frameworks_bluetooth` 仓库提供 BLE API
- ESP32-S3 NimBLE 驱动可用（VHCI 接口）
- 建议：ESP-IDF NimBLE 开发 → 预留 NuttX 适配层

## 推荐架构

```
ESP32 #1 (BLE扫描) ─┐
ESP32 #2 (人脸+步态) ─┼── MQTT ──→ 融合服务器 ──→ 身份决策
ESP32 #3 (BLE补充)  ─┘               │
                              权重: face(0.5)+gait(0.2)+BLE(0.15)+body(0.15)
```

## 待办

- [ ] ESP32-S3 BLE 扫描驱动适配到 openvela
- [ ] IRK 配对获取流程设计
- [ ] BLE RSSI → 置信度映射校准
- [ ] 多节点 BLE 三角定位（可选）
