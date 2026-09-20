# SmartAccess V77 —— 门区执行节点（Arduino 原型）

枢络 VelaMesh 的**门区执行节点**，与 openvela 边缘感知节点异构组网：openvela/XIAO 节点负责无感感知与证据上行，中枢负责融合决策；本节点负责物理执行（舵机门锁、状态显示、灯光）并保留独立的本地离线人脸通道。

- 平台：Seeed XIAO ESP32S3 Sense，Arduino IDE（esp32-arduino 2.0.x）
- 云下行：巴法云（bemfa.com:9501，TCP MQTT），订阅主题 `SmartDoor`，收到含 `open` 的消息即远程开门
- 本地通道：HC-SR04 超声波 50 cm 唤醒 → Edge Impulse 离线人脸分类（连续 2 帧、置信度 ≥70%）→ SG90 舵机开锁（125°）/闭锁（65°），超时自动落锁
- 交互：SSD1306 OLED 状态/倒计时、WS2812 补光与开门流水灯、和风天气信息显示
- 外壳：86 型 3D 打印面板（见 `board/forms/`）
- 五状态非阻塞状态机：SLEEP → WAKE/COLLECT → RECOGNIZING → OPEN → FAILED/ALERT

## 与中枢的关系（本期如实说明）

本节点通过巴法云接收"开门"指令（寒假练项目原有通道）；本期中枢服务端的决策下发走本地 MQTT（`hub/<id>/cmd`）。两条下行通道尚未在本期合并为同一 broker；演示可采用：中枢 ALLOW →（演示脚本/巴法云主题消息）→ 舵机执行。统一到本地 broker 为后续工作。

## 烧录

Arduino IDE 打开 `SmartAccess_V77.ino`，选 XIAO ESP32S3，安装依赖库：ESP32Servo、PubSubClient、SSD1306Wire(ESP8266_SSD1306)、Adafruit_NeoPixel、NewPing、edge-impulse-sdk。

> 上传前填入你自己的 WiFi SSID/密码与巴法云 Client ID（仓库版本已将真实值替换为占位符 `<YOUR_...>`）。本地演示用的原始文件不含在提交内，请勿把真实凭证推送到公开仓。

## 来源

基于 2026 寒假练项目《用 Seeed XIAO ESP32S3 Sense 实现智能门禁与报警系统》：https://www.eetree.cn/project/4938
