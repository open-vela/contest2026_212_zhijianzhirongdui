# 边缘节点注册

为枢络 VelaMesh 的 R528 hub 注册 ESP32-S3 边缘节点：生成节点身份与 MQTT topic/ACL，在人工确认物理连接后引导烧录，并用中文解释记录注册决策。

## 何时使用

当 Dashboard 或管理员声明“新增边缘节点”“注册边缘节点”，或某节点出现固件版本失配、反复重启时使用。
不要因一次离线自动触发烧录；先区分网络抖动、供电、固件不匹配与持续重启。

## 使用方法

1. 向管理员确认节点 ID、目标固件版本、部署位置和 MQTT broker。节点 ID 只使用字母、数字、点、
   下划线与连字符，且不能与现有注册表重复。
2. 先以 stub 后端运行仓内 `scripts/provision_demo.sh`，生成注册记录与最小权限 ACL。检查以下 topic：
   `edge/{id}/face`、`edge/{id}/gait`、`edge/{id}/ble`、`edge/{id}/status`。
3. 解释触发原因、风险和下一步；如果只是视频或无硬件演示，到此停止并明确标记 `stub`。
4. 真实烧录前再次取得人工确认，核对 ESP32-S3 物理连接、串口、节点 ID 和固件产物。调用开发机
   `esp32s3-flash-pipeline/scripts/flash.sh --port <设备> --confirm-flash`，不得静默猜测端口。
5. 烧录后让 hub 订阅四个上行 topic，等待 `status` 上线消息，再观察 face/gait/ble 数据。
6. 写入节点注册记录和中文解释日志。日志需区分“配置已生成”“烧录已完成”“节点已上线”三个阶段，
   不得用前一阶段代替后一阶段的证据。

## 输出

- `node-registration.json`：节点身份、固件版本、broker、topic 和后端类型。
- `mqtt-acl.conf`：该节点只能向自身四个上行 topic 发布。
- `explanation.log`：与 LLMAC-Lite 决策解释风格一致的中文原因、动作、风险与验证项。

## 失败处理

- 节点 ID 非法或冲突：停止并要求新 ID，不覆盖已有记录。
- 未确认物理连接、找不到串口或固件：只保留 stub/配置阶段结果，禁止宣称烧录成功。
- 固件版本失配：先记录当前与目标版本；只有管理员确认后才安排重刷。
- 反复重启：先保存 status/串口证据并检查供电；不要在证据不足时循环烧录。
- 上线超时：报告订阅到的最后状态、broker 与 topic，不伪造在线消息。

## 示例

管理员：“新增边缘节点 edge-lab-01，目标固件 0.1.0。”

→ 生成身份、`edge/edge-lab-01/{face,gait,ble,status}` 和 ACL  
→ 用 stub 演示注册并输出中文解释  
→ 询问并等待物理连接确认  
→ 获得确认后才调用烧录管线  
→ 收到 `edge/edge-lab-01/status` 上线消息后标记节点在线
