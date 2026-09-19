# Gait Frontend Adapter (OPE-73 -> OPE-86)

协议适配层：把 ESP32 步态识别结果（OPE-73）从 MQTT 接入 OPE-86 演示前端。

本任务只做协议适配，**不重构系统**：不修改 ESP32 MQTT topic、不修改 BLE 协议、不做 Face/BLE 融合、不做 Cloud MQTT、不改模型、不改 ESP32 固件。

## 数据链路

```
ESP32 (gait pipeline)
   │  publishes recognition result
   ▼
MQTT broker  (topic: dominiscius/<node_id>/gait/result)
   │
   ▼
Backend  GaitAdapter  (server/app/services/gait_adapter.py)
   │  1. parse topic -> node_id
   │  2. transform payload -> unified event
   │  3. persist via demo_telemetry (channel="gait")  -> SQLite
   │  4. publish "gait_result" event via demo_event_bus
   ▼
WebSocket  /ws/demo-events   (authenticated)
   │  { "type": "gait_result", "data": <unified payload>, "tenant_id", "ts" }
   ▼
Frontend  /admin/demo  (OPE-73 section, gait card)
   │  WebSocket message triggers REST refresh of GET /api/demo/ope73/gait
   ▼
评委可见：识别身份、置信度、方向、耗时、top3、收包 topic、来源 provenance
```

## 1. MQTT 输入（ESP32，不可修改）

- **Topic**: `dominiscius/+/gait/result`
  - `+` = node_id（ESP32 个体标识）
  - root 为 `dominiscius`，与 OpenVela 的 `vela/node/+/+` 命名空间相互独立
- **Payload**:

```json
{
  "session_id": "sess-2026-0001",
  "direction": "forward",
  "top3": [
    { "identity": "张三", "score": 0.8721 },
    { "identity": "李四", "score": 0.7289 },
    { "identity": "王五", "score": 0.6410 }
  ],
  "cosine": 0.8721,
  "margin": 0.1432,
  "timing": { "total_ms": 128 }
}
```

字段说明：

| 字段 | 类型 | 含义 |
|---|---|---|
| `session_id` | string | 本次识别会话 id |
| `direction` | string | 步行方向（forward / back / left / right …） |
| `top3` | array | top-3 候选匹配，每项含 `identity` 与 `score` |
| `cosine` | number | top-1 余弦相似度 |
| `margin` | number | top-1 与 top-2 的间距 |
| `timing` | number \| object | 推理耗时；标量按 ms 处理，对象取 `total_ms`/`latency_ms`/`inference_ms` 等 |

适配器对字段名做了容错：`top3` 条目里的身份键也接受 `label`/`name`/`id`/`person_name`，分数键也接受 `similarity`/`cosine`/`confidence`；`top3` 缺失或为标量 dict 时会退化为 top-1。`cosine` 顶层字段在 `top3[0]` 没有分数时作为分数兜底。

## 2. 统一事件（Backend -> Frontend）

适配器把上面的设备 payload 转成前端统一事件，经 `demo_event_bus.publish("gait_result", ...)` 推送到 `/ws/demo-events`：

```json
{
  "type": "gait_result",
  "data": {
    "identity": "张三",
    "score": 0.8721,
    "direction": "forward",
    "source": "gait",
    "session_id": "sess-2026-0001",
    "latency": 128.0,
    "node_id": "idf-gait-01",
    "cosine": 0.8721,
    "margin": 0.1432,
    "top3": [
      { "identity": "张三", "score": 0.8721 },
      { "identity": "李四", "score": 0.7289 },
      { "identity": "王五", "score": 0.641 }
    ]
  },
  "tenant_id": 1,
  "ts": "2026-08-10T18:20:00.000000Z"
}
```

> 说明：issue 里的契约写作 `{ "type": "gait_result", "payload": {...} }`。本仓库的 `demo_event_bus` 对所有事件统一使用 `data` 字段承载（与 `telemetry`、`cloud`、`snapshot`、`heartbeat` 一致），因此这里的 `data` 即契约中的 `payload`，字段完全相同。前端沿用现有「收到任意非 heartbeat 事件即刷新 REST」的模式，无需为 gait 单独改 WebSocket 解析。

字段映射：

| 统一事件字段 | 来源 |
|---|---|
| `identity` | `top3[0].identity`（兜底 `cosine` 顶层、`unknown`） |
| `score` | `top3[0].score`（兜底顶层 `cosine`） |
| `direction` | `direction` |
| `source` | 固定 `"gait"` |
| `session_id` | `session_id` |
| `latency` | `timing`（ms） |
| `node_id` | topic 的 `+` 段或 payload `node_id` |
| `cosine` | `cosine` |
| `margin` | `margin` |
| `top3` | `top3` 压缩为 `[{identity, score}]`（最多 3 项） |

## 3. 后端组件

| 文件 | 作用 |
|---|---|
| `server/app/services/gait_adapter.py` | `GaitAdapter`：订阅 `dominiscius/+/gait/result`，`transform()` 做字段映射，`on_message()` 持久化并推送事件。单例 `gait_adapter`。 |
| `server/app/main.py` | lifespan 中 `mqtt_client.subscribe(gait_adapter.topic_pattern, gait_adapter.on_message)`，与现有 face/silhouette/ble/status 订阅并列。 |
| `server/app/api/demo.py` | `GET /api/demo/ope73/gait` 返回最新一条 gait 记录（从 `demo_telemetry.latest("gait")`）。 |
| `server/app/services/demo_telemetry.py` | 复用既有 telemetry 路径：`ingest(channel="gait")` 落 SQLite、计入节点 channels、fan-out `telemetry` 事件。 |
| `server/app/services/demo_event_bus.py` | 复用既有事件总线，推送 `gait_result` 事件到 `/ws/demo-events`。 |

gait 消息**只**走 `gait_adapter`，不会被 `vela/node/+/+` 的 `demo_telemetry.on_message` 重复处理（topic root 不同），不会进 face/BLE 融合引擎。

## 4. 后端启动方式

```bash
# 1) 安装依赖（首次）
cd server
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# 2) 启动本地 MQTT broker（任选其一）
#    a) Docker:
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto
#    b) 本仓库 deploy/demo/docker-compose.yml 里已含 mosquitto

# 3) 启动后端（默认 127.0.0.1:8000，MQTT broker 127.0.0.1:1883）
#    Windows PowerShell:
$env:MQTT_BROKER="127.0.0.1"; $env:MQTT_PORT="1883"
uvicorn app.main:app --host 0.0.0.0 --port 8000
#    或: python -m uvicorn app.main:app --reload
```

环境变量（默认值见 `server/app/config.py`）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `MQTT_BROKER` | `127.0.0.1` | broker 地址 |
| `MQTT_PORT` | `1883` | broker 端口 |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | 空 | 若 broker 需要鉴权 |
| `MQTT_TOPIC_PREFIX` | `vela` | OpenVela 节点 topic 前缀；**不影响** gait topic（`dominiscius` 为固件写死） |

启动后访问 `http://127.0.0.1:8000/admin/demo`（登录 admin / admin123），切到「现场真实链路」模式即可看到步态卡片。

## 5. Mock gait event（无实机时验证）

无需 ESP32，用 mosquitto-cli 直接向 broker 发一条 gait/result，前端应实时刷新：

```bash
mosquitto_pub -h 127.0.0.1 -p 1883 \
  -t "dominiscius/idf-gait-01/gait/result" \
  -m '{"session_id":"sess-test-0001","direction":"forward","top3":[{"identity":"张三","score":0.8721},{"identity":"李四","score":0.7289},{"identity":"王五","score":0.6410}],"cosine":0.8721,"margin":0.1432,"timing":{"total_ms":128}}'
```

或在 Python 里（适合自动化测试）：

```python
import paho.mqtt.client as mqtt, json
c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.connect("127.0.0.1", 1883)
c.publish("dominiscius/idf-gait-01/gait/result", json.dumps({
    "session_id": "sess-test-0001", "direction": "forward",
    "top3": [{"identity": "张三", "score": 0.8721}],
    "cosine": 0.8721, "margin": 0.1432, "timing": {"total_ms": 128},
}), qos=1)
c.disconnect()
```

也可直接调用适配器，绕过 broker 做单元验证：

```python
import asyncio
from app.services.gait_adapter import gait_adapter
event = gait_adapter.transform("dominiscius/idf-gait-01/gait/result", {
    "session_id": "sess-test-0001", "direction": "forward",
    "top3": [{"identity": "张三", "score": 0.8721}],
    "cosine": 0.8721, "margin": 0.1432, "timing": 128,
})
print(event["payload"])
# {'identity': '张三', 'score': 0.8721, 'direction': 'forward', 'source': 'gait',
#  'session_id': 'sess-test-0001', 'latency': 128.0, 'node_id': 'idf-gait-01',
#  'cosine': 0.8721, 'margin': 0.1432, 'top3': [{'identity': '张三', 'score': 0.8721}]}
```

## 6. WebSocket 示例

`/ws/demo-events` 需要登录 token（query 参数）。收到 gait 后会推送 `gait_result` 事件：

```javascript
// 浏览器控制台（先在 /admin/demo 登录拿到 token）
const token = localStorage.getItem('token')
const ws = new WebSocket(`ws://127.0.0.1:8000/ws/demo-events?token=${encodeURIComponent(token)}`)

ws.onmessage = (event) => {
  const message = JSON.parse(event.data)
  if (message.type === 'gait_result') {
    const g = message.data
    console.log('步态识别：', g.identity, '置信度', g.score,
                '方向', g.direction, '耗时', g.latency, 'ms', 'session', g.session_id)
  }
}
// 连接后先收到 { type: "snapshot", data: [...] }，之后每 20s 收到 heartbeat，
// ESP32 上报 gait 后即收到 { type: "gait_result", data: {...} }
```

等效 Python（测试用）：

```python
import asyncio, json, websockets
from app.services.auth_service import create_access_token

async def main():
    token = create_access_token({"sub": "1"})
    async with websockets.connect(f"ws://127.0.0.1:8000/ws/demo-events?token={token}") as ws:
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("type") == "gait_result":
                print("gait:", msg["data"])

asyncio.run(main())
```

前端 `/admin/demo` 现有实现：`connectDemoEvents()`（`client/src/api/demo.ts`）在收到任意非 heartbeat 消息时触发一次 REST 刷新，`GET /api/demo/ope73/gait` 的结果渲染到 OPE-73 区块的「步态识别结果」卡片。因此 gait 事件到达即刷新，无需改 WebSocket 解析逻辑。

## 7. 前端展示

`client/src/views/admin/demo/Index.vue` 的 02 区块（OPE-73 剪影 / 步态）新增「步态识别结果」卡片：

- 6 项指标：识别身份 / 置信度 / 方向 / 推理耗时 / margin / session
- Top-3 候选列表（最佳匹配打标）
- 服务器收包 topic、最后收包时间、来源协议链路
- `EvidenceBadge` 标注 provenance（real / mock / pending_real）

类型定义：`client/src/types/demo.ts` 的 `GaitEvidence`；mock 数据与 API client 在 `client/src/api/demo.ts`（`demoApi.gait()`，mock 模式返回演练样例）。

## 8. 不在本适配范围

- ESP32 MQTT topic、payload 字段（保持固件现状）
- BLE 协议、BLE 融合
- Face 融合
- Cloud MQTT
- 模型修改、ESP32 固件修改
- OpenVela `vela/node/+/+` 命名空间（gait 独立走 `dominiscius` root）

## 9. 验收

- `npm run typecheck` / `npm run build` 通过
- 后端 `pytest` 通过（含 `test_gait_adapter_*`）
- `mosquitto_pub` 一条 gait/result，`/admin/demo` 步态卡片实时显示真实身份、置信度、方向、耗时、top3，provenance=`real`
- 无实机时切 mock 模式可完整演练，provenance=`mock`
