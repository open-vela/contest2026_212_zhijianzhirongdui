# vela_hub — 枢络 VelaMesh 主控融合节点应用

R528 主控节点上的融合应用，NSH 应用形态，经 manifest linkfile 映射到
openvela 工作树 `packages/demos/contest2026_212_vela_hub`。

## 职责

1. MQTT 订阅各 XIAO ESP32S3 Sense 边缘节点（`vela_edge`）上行的人脸嵌入、
   步态轮廓、BLE 近场证据；
2. 多模态身份融合与可解释访问控制决策；
3. 触发 Skill（与服务端 FastAPI/智能体平台联动的动作占位）。

## 当前状态（Stage 1 基线）

`vela_hub_main.c` 为可编入、可在 NSH 中运行的 stub 主循环：打印将要订阅的
topic、融合 tick 与 Skill 触发占位。真实 MQTT 客户端、融合引擎与 Skill 调用
由后续任务填充，签名约定见源码中的 stub hook 注释。

## 启用

openvela 配置中打开 `CONFIG_LVX_USE_DEMO_CONTEST2026_212_VELA_HUB=y`，烧录后
在 NSH 中执行 `vela_hub`。
