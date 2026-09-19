# 统一竞赛 Demo 软件运行手册

现场只维护一套 Demo：`Vue → FastAPI → SQLite` 组成同源应用，Mosquitto 是第二个容器。三块开发板全部通过同一团队局域网向本地 broker 上报；浏览器只访问：

```text
http://127.0.0.1:8000/admin/demo
```

Seeed 的尺寸、重量和功耗仍必须由现场实物测量。Mock、local MQTT、cloud API 和 mixed 四种页面模式都保留来源标签，Mock 不参与实测达标判断。

## 1. 发布架构

```text
openvela / Arduino / IDF 节点
          │  vela/node/<node_id>/<channel>
          ▼
Mosquitto :1883 ──► FastAPI :8000 ──► SQLite data/app/dominiscius.db
                            │
                            ├─ /api/*
                            ├─ /ws/demo-events
                            └─ Vue production build (/admin/demo, /assets/*)
```

应用 Dockerfile 使用 Node 20 构建 Vue，再把 `client/dist` 复制到 Python 3.11/FastAPI 镜像。运行时不需要 Node、npm 或 Vite。Uvicorn 固定一个 worker，避免 MQTT 重复订阅和重复落库。

## 2. 有网环境生成离线包

在 Windows x64 的发布电脑上提前安装并启动 Docker Desktop/WSL2，然后：

1. 进入 `deploy\demo`；
2. 将 `.env.example` 复制为 `.env`，至少替换 `JWT_SECRET`；
3. 执行 `scripts\export-images.cmd`；
4. 确认生成 `images\dominiscius-demo-images.tar`；
5. 将整个 `deploy\demo` 目录复制到两台演练电脑；
6. 两台电脑断开公网，执行 `scripts\import-images.cmd` 和 `scripts\start-demo.cmd`；
7. 用 `scripts\smoke-test.cmd` 验证页面、API、JS Content-Type 和 favicon；
8. 执行一次 `scripts\backup-data.cmd`，再在备用目录测试恢复。

`export-images.cmd` 是发布准备脚本，可以构建应用并拉取固定版本 Mosquitto。现场的 `start-demo.cmd` 只允许本地 `docker load` 和 `docker compose up --no-build`，不会执行 `npm install`、`pip install`、`docker build` 或 `docker pull`。

## 3. 现场一键操作

所有命令均在 `deploy\demo` 下执行：

| 操作 | 命令 | 说明 |
|---|---|---|
| 启动 | `scripts\start-demo.cmd` | 检查 Docker，必要时从 tar 导入镜像，启动并 smoke test |
| 状态 | `scripts\status-demo.cmd` | 显示容器状态并检查页面/API/资源 |
| 停止 | `scripts\stop-demo.cmd` | 执行 `compose down`，不删除数据目录 |
| 备份 | `scripts\backup-data.cmd` | 短暂停服，压缩 `data/` 与 `logs/` 后恢复服务 |
| 恢复 | `scripts\restore-data.cmd <zip>` | 停服后覆盖恢复指定备份，再启动服务 |
| 导入镜像 | `scripts\import-images.cmd` | 从本地 tar 导入，不访问公网 |

严禁使用 `docker compose down -v`。当前发布使用绑定目录而不是 Docker 命名卷：

```text
deploy/demo/data/app/       SQLite
deploy/demo/data/mqtt/      Mosquitto persistence
deploy/demo/logs/app/       FastAPI rotating log
deploy/demo/logs/mqtt/      Mosquitto log
deploy/demo/backups/        数据备份 zip
deploy/demo/images/         离线镜像 tar
```

## 4. 云 transport 配置

所有上传先进入 SQLite outbox，然后由自动 worker 发送。`DEMO_CLOUD_MODE` 支持：

- `disabled`：只在本地排队，页面标记 `reserved`；
- `mock`：本地 Mock transport 自动确认并生成接收事件，页面标记 `mock`，不会声称已到公网；
- `http`：向 `DEMO_CLOUD_ENDPOINT` 发送通用 JSON，请求头携带 `Idempotency-Key`。

worker 状态为 `pending / sending / delivered / retrying / failed`，支持超时、指数退避、最大重试、幂等键、最近错误、成功回执和重启恢复。云端不可用不会影响 MQTT、SQLite、页面或本地识别链路。

通用 HTTP envelope：

```json
{
  "request_id": "...",
  "idempotency_key": "...",
  "event_type": "demo_snapshot",
  "payload": {},
  "created_at": "2026-08-10T00:00:00Z"
}
```

## 5. MQTT 合约与自动指标

| Channel | Topic | 软件用途 |
|---|---|---|
| 心跳 | `vela/node/<node_id>/status` | 在线、WiFi、MQTT、断连/重连 |
| BLE | `vela/node/<node_id>/ble` | device_id、RSSI、scan_seq |
| 剪影 | `vela/node/<node_id>/silhouette` | frame_seq、foreground_pixels、上传窗口 |
| 人脸 | `vela/node/<node_id>/face` | 身份融合；大 embedding 不写 Demo 表 |
| 指标 | `vela/node/<node_id>/metrics` | 显式计数/耗时，也进入统一计算器 |
| 服务 | `vela/node/<node_id>/service` | owner、active/backup、切换和中断 |

自动指标层从同一条 telemetry 路径计算或聚合：发现、连接、重连、端到端延迟、发送/接收数、丢包率、可靠性、多节点同步误差、service owner、active/backup、服务切换耗时与中断时长。设备可上报已测数值，也可上报开始/结束时间戳和计数器；两者使用同一 API 类型和 SQLite 快照。

软件模拟入口默认关闭。仅在排练环境将 `DEMO_SIMULATION_ENABLED=true` 后，可调用 `POST /api/demo/simulate/metrics`；生成记录永久标记为 `mock`。

## 6. 开发模式

开发时仍可分别运行后端与 Vite：

```bash
docker compose -f deploy/demo/docker-compose.yml up -d mqtt
cd server && ./run.sh
cd client && npm run dev -- --host 0.0.0.0
```

Vite 将 `/api` 和 `/ws` 同时代理到 `localhost:8000`。生产模式则由 FastAPI 直接提供 `/assets/*`、`/favicon.svg` 和 Vue history fallback；不存在的 API/静态资源保持 404，不会被错误替换成 `index.html`。

## 7. 本地验证

```bash
cd client
npm run typecheck
npm run build

cd ..
server/.venv/bin/python -m pytest -q

# 后端以生产构建运行时，使用 Firefox/WebDriver 审计两种视口和四种数据模式
node client/scripts/browser-audit.mjs
```

生产资源集成测试会验证 `/admin/demo` 直接访问/刷新、JS/CSS 状态码和 Content-Type、favicon、API 404 与缺失资源 404。Docker CLI 可用时再执行：

```bash
cd deploy/demo
copy .env.example .env
docker compose --env-file .env config
docker compose --env-file .env build app
docker compose --env-file .env up -d
scripts\smoke-test.cmd
```

## 8. 现场故障切换

- MQTT 不通：确认路由器、Windows 私有网络防火墙、PC 固定 IP、1883 和板子 broker 地址；
- 页面无数据：确认页面不是 Mock、订阅 `vela/node/#` 并核对 topic；
- WebSocket 断开：前端会采用有上限的指数退避重连，并保留 5 秒轮询；
- 云端不可用：outbox 自动重试或最终进入 `failed`，本地 Demo 继续工作；
- 单板离线：15 秒后显示待心跳，其他模块继续；
- 硬件临时不可用：切换明确标注的 Mock 模式讲解软件，但主动说明不作为实测得分；
- 主电脑故障：在已演练的备用电脑导入同一 tar，恢复最近备份后启动。

硬件烧录、三板真机联调、BLE 实扫、真实网络成绩、实机服务流转、尺寸重量功耗以及真实公网云交付仍属于现场/外部验收项。
