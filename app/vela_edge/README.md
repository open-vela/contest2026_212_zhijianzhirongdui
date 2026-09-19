# vela_edge — 枢络 VelaMesh 边缘从节点应用

XIAO ESP32S3 Sense 上的感知从节点，NSH 应用形态，经 manifest linkfile 映射到
openvela 工作树 `packages/demos/contest2026_212_vela_edge`。

## 职责

OV2640/OV3660 摄像头 DMA 采集 → 步态轮廓预过滤 → MobileFaceNet（TFLite Micro）
人脸嵌入 → BLE 无源近场扫描 → WiFi/MQTT 上行至 R528 主控融合节点（vela_hub）。

## 当前状态（Stage 1 基线）

- `vela_edge_main.c`：可编入、可在 NSH 中运行的 stub 主循环（打印规划中的
  模块链路并周期 tick），用于验证 manifest/linkfile 与构建接线。
- `modules/`：从项目原嵌入式工程移植的真实模块源码，供后续任务按 Kconfig
  特性开关（TFLITEMICRO / WiFi / BLE）逐步接入构建：

  | 目录 | 内容 |
  |---|---|
  | `modules/camera/` | OV2640/OV3660 DMA 采集、bringup 参考实现 |
  | `modules/gait/` | RGB565 帧差 + Otsu 步态轮廓 RLE 提取 |
  | `modules/inference/` | TFLM 封装、人脸嵌入、消息队列推理管线 |
  | `modules/ble/` | NuttX bt IOCTL 扫描器、员工 BLE 检测（含 stub） |
  | `modules/net/` | `xiaosense_network` MQTT 上行（CONNECT/PUBLISH） |
  | `modules/tools/` | MobileFaceNet 模型转换、VM 源码同步、WiFi 更新脚本 |

> `modules/` 中的文件保留移植时的原始 include/守卫，部分依赖板级驱动与
> TFLM 组件，尚未纳入当前 Makefile 编译；接入顺序与条件由后续任务处理。

## 启用

openvela 配置中打开 `CONFIG_LVX_USE_DEMO_CONTEST2026_212_VELA_EDGE=y`，烧录后
在 NSH 中执行 `vela_edge`。
