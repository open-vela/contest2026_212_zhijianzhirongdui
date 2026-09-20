# 枢络 VelaMesh · R528 中枢融合服务

分布式多模态无感感知与可解释访问控制系统的**服务端中枢**。运行在 PC/R528 侧，
FastAPI + EMQX/MQTT + SQLite（可平滑换 PostgreSQL），对下汇聚 ESP32-S3
边缘节点证据并做出可解释访问决策，对上通过 WebSocket/云端接口为 App 与
Dashboard 提供实时数据。

叙事定位：R528（Gemini-S1，openvela）为 **hub 中枢**，ESP32-S3 Sense 为绑定的
**edge 从节点**，构成显式主-从拓扑。

## 一键启动

```bash
cd server
./run.sh                 # 零配置：自动建 venv、装依赖、无 broker 时内置兜底
```

- 默认 `MQTT_MODE=auto`：先探测 `MQTT_BROKER:MQTT_PORT`，不可达时启动**进程内
  MQTT broker**（`127.0.0.1:11883`），无 EMQX/mosquitto 的演示笔记本也能一键起。
- 登录：`admin / admin123`（租户 default）；文档：`http://127.0.0.1:8000/docs`。
- 需要与实板固件共用 broker 时：`cp .env.example .env`，把 `MQTT_BROKER` /
  账号密码改成固件指向的 broker（固件默认 `10.6.40.22:1883`）。

## 模拟一条完整决策

```bash
# 服务已启动；内置 broker 在 11883
python scripts/simulate_edge.py --port 11883 --scenario allow   # 双证据放行
python scripts/simulate_edge.py --port 11883 --scenario deny    # 仅运动无信标 → 拒绝
python scripts/simulate_edge.py --port 11883 --scenario tailgate
python scripts/simulate_edge.py --port 11883 --scenario low_face  # 研究/离线降级
python scripts/simulate_edge.py --port 11883 --offline            # 断网暂存
python scripts/simulate_edge.py --port 11883 --online             # 恢复补传
```

脚本走真实 MQTT socket，打印服务端返回的完整决策 JSON，供 terminal 录屏使用。

## 决策 JSON（模板 3.3 契约）

```json
{
  "node_id": "esp32s3-edge-01",
  "hub_id": "r528-hub-01",
  "action": "allow",
  "policy_id": "EMPLOYEE-NORMAL",
  "explanation": "张伟，融合分 88.0%（BLE 信标 68%+在场轮廓 20%），策略:EMPLOYEE-NORMAL（信标身份+在场双证据一致，放行）",
  "confidence": 0.88,
  "weights_used": {"ble": 0.75, "motion": 0.25},
  "scenario": "front",
  "evidence_mode": "delivery",
  "contributions": {"ble": 0.675, "motion": 0.205},
  "event_id": 1
}
```

每个决策必含 `{action, policy_id, explanation, confidence, weights_used}`。

## 融合策略

| Policy id | 含义 | 动作 |
|---|---|---|
| `EMPLOYEE-NORMAL` | 信标/多模态正常命中 | allow |
| `DEGRADE-FACE-1` | 人脸置信度 <0.3，权重转给轮廓+BLE | allow（降级） |
| `TAILGATE-DETECT` | 检测到尾随 | alert（不自动开门，转复核） |
| `VISITOR-TEMP` | 访客在有效预约窗口内 | allow（限时） |
| `UNKNOWN-DENY` | 无身份/证据不足，默认拒绝 | deny |

优先级：**DENY > ALERT > DEGRADE > ALLOW**。阈值：正常 `0.65`、人脸降级
`0.55`（可用 `VELAMESH_FUSION_THRESHOLD*` 调整）。

### 两种证据模式（2026-09-20 范围修订）

- **delivery 交付路径**：交付固件的端侧证据为 **BLE 信标身份（主）+ 摄像头
  运动/轮廓在场（辅）**。权重随场景变化：默认 `ble 0.75 / motion 0.25`，拥挤
  `0.85/0.15`，低光 `0.80/0.20`。安全规则：**仅检测到在场、BLE 扫描无允许
  信标时立即 UNKNOWN-DENY**（扫描结果已返回）；扫描尚未返回则窗口短暂挂起，
  超时拒绝。
- **research 研究/离线模式**：face + gait/silhouette + BLE 三模态按场景
  （正面/侧身/背对/拥挤/低光）动态加权。步态离线 Rank-1 86.7% 仅在竞赛报告中
  陈述，不由交付固件产生。模式按窗口证据自动选择（出现 face/gait 证据即进入
  research）。

## MQTT topic 契约

新契约（本服务端标准）与固件旧 topic **并行订阅**，映射如下：

| 方向 | 新契约 | 固件旧 topic |
|---|---|---|
| 边缘证据 | `edge/<id>/face` | `vela/node/<id>/face` |
| 轮廓/在场 | `edge/<id>/gait`、`edge/<id>/motion` | `vela/node/<id>/silhouette` |
| BLE | `edge/<id>/ble` | `vela/node/<id>/ble` |
| 心跳 | `edge/<id>/status` | `vela/node/<id>/status` |
| 步态结果 | — | `dominiscius/<id>/gait/result`（经 gait_adapter 归一，root 固件写死） |
| 中枢指令 | `hub/<id>/cmd` | — |
| 决策下发 | `edge/<id>/decision`、`vela/decision` | — |

BLE payload 兼容固件实际字段：`allowlist_hit`（设备端白名单命中）、
`ble_enabled`、`mac`、`rssi`；设备端白名单命中即使服务端人员表无对应行也
视为信标身份。

## 断网 / 弱网降级

hub↔云链路断开时（心跳 `cloud_link=offline`，或
`POST /api/hubs/{id}/cloud-link {"state":"offline"}` 演示开关）：

1. 本地策略**照常出决策**，门禁能力不依赖云端；
2. 边缘事件落 SQLite `edge_event_queue` 暂存（队列满丢最旧，不阻塞决策）；
3. 链路恢复后自动把暂存事件补进云端 outbox（复用既有重试/幂等），暂存队列清零。

## MiMo 云端模型接入面

模板 3.3 要求的两个增强调用已实现：`infer_intent`（意图推断）与
`explain_decision`（中文解释增强）。密钥**只从环境变量读**：
`VELAMESH_MIMO_API_KEY`（旧名 `DOMINISCIUS_MIMO_API_KEY` 仍兼容），key 不入仓。
未配置 key（当前演示默认）时全部走**确定性本地 mock**，`mode` 字段如实报
`mock`——报告不得宣称云端推理。

## 兼容标识（刻意保留，勿改名）

本代码库前身名为 Dominiscius，以下旧拼写保留以兼容既有部署/固件/数据：
SQLite 文件 `data/dominiscius.db`、client id `dominiscius-server`、日志
`dominiscius.log`、env 前缀 `DOMINISCIUS_`（每个 `VELAMESH_*` 变量同时接受
`DOMINISCIUS_*` 前缀）。

## 测试

```bash
python -m pytest -q
```

覆盖：API 全量、BLE+motion 交付融合（含仅运动无信标拒绝）、face/gait 研究
融合与降级、拓扑注册/心跳/遥测、断网暂存与补传、MiMo mock、内置 broker
真实 socket 收发。

## 目录

```
app/
  api/topology.py        # /hubs /edges /topology /offline-queue + hub 指令
  fusion/fusion_engine.py# 双证据/三模态融合、策略集、中文解释
  services/
    topology.py          # Hub/EdgeNode 注册表 + WS 拓扑推送
    edge_ingress.py      # edge/<id>/* 消息路由
    mqtt_client.py       # paho 封装 + auto/embedded/external
    embedded_broker.py   # 进程内 MQTT 3.1.1 broker（演示兜底）
    identity_engine.py   # MQTT → 融合 → 落库 → WS/决策下发
    hub_offline.py       # 断网暂存 + 恢复补传
    cloud_state.py       # 链路状态缓存/强制开关
    mimo_client.py       # MiMo 接入面（无 key 走 mock）
scripts/simulate_edge.py # 模拟边缘节点（录屏用）
```
