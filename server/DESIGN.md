# 智能建筑管理系统 — 服务端架构设计（完整版）

> **版本**: v2.0  
> **日期**: 2026-06-15  
> **基于**: 《统一技术方案设计 v3.4》+《10天冲刺计划》+ 已实现代码 + Web技术调研  
> **状态**: 设计阶段，待审核后实现

---

## 目录

1. [参考案例与技术调研](#一参考案例与技术调研)
2. [设计约束与定位](#二设计约束与定位)
3. [系统架构总览](#三系统架构总览)
4. [信息流设计](#四信息流设计)
5. [数据模型](#五数据模型)
6. [推理模型服务设计](#六推理模型服务设计)
7. [员工角色管理 RBAC](#七员工角色管理-rbac)
8. [租户管理设计](#八租户管理设计)
9. [MQTT 协议设计](#九mqtt-协议设计)
10. [REST API 设计](#十rest-api-设计)
11. [业务逻辑模块](#十一业务逻辑模块)
12. [WebSocket 实时推送](#十二websocket-实时推送)
13. [前端页面设计](#十三前端页面设计)
14. [目录结构](#十四目录结构)
15. [实现分期计划](#十五实现分期计划)
16. [砍掉清单](#十六砍掉清单)
17. [与原设计文档 v3.4 差异对比](#十七与原设计文档-v34-差异对比)

---

## 一、参考案例与技术调研

### 1.1 开源 IoT 智能建筑平台参考

| 平台 | 架构特点 | 借鉴点 | GitHub Stars |
|------|----------|--------|:---:|
| **[ThingsBoard](https://thingsboard.io)** | 多租户 IoT 平台，MQTT/HTTP/CoAP 多协议，规则引擎，RBAC，水平扩展 | **多租户隔离**（租户→客户→用户三级）；**规则引擎**（节点式可视化编排）；**设备管理**（ provisioning + 心跳 + 属性/遥测分离）；RBAC 按租户粒度 | 18k+ |
| **[AIOS v6](https://github.com/topics/smart-building?l=python)** | AI 驱动的数字孪生平台，MQTT + FastAPI + ML 分析 | FastAPI 作为 API 层、MQTT 设备接入、ML 分析模块独立、数字孪生资产模型 | — |
| **[OpenRemote](https://openremote.io)** | 100% 开源 IoT 设备管理，能源管理 | 资产模型 + 自动化规则 + 自定义仪表板 | 1k+ |
| **[IoTSharp](https://github.com/topics/iot-platform)** | .NET 开源 IoT 平台，MQTT + 可视化 | 设备管理 + 数据采集 + 规则链 | 1k+ |

### 1.2 人脸识别访问控制系统参考

| 项目 | 技术栈 | 借鉴点 |
|------|--------|--------|
| **[Seeed face-recognition-api](https://github.com/Seeed-Solution/face-recognition-api)** | Hailo-8 加速器 + SQLite 向量库 + 512-d embedding | 向量搜索 API 设计、embedding 管理、调试图像保存 |
| **[Face-Attendance-System](https://github.com/MohammadFayasKhan/Face-Attendance-System)** | FastAPI + React + face_recognition | 前后端分离、实时识别 + 考勤管理 |
| **[FastAPI Facial Recognition](https://github.com/Tahiralira/FastApi-Facial-Recognition-for-BleedAi-)** | FastAPI + SQLAlchemy + MediaPipe | 用户管理 + 图像处理 + 缓存优化 |

### 1.3 推理模型服务架构参考

| 方案 | 特点 | 适用场景 |
|------|------|----------|
| **[vLLM](https://github.com/vllm-project/vllm)** | 连续批处理、PagedAttention、OpenAI 兼容 API | 高吞吐 LLM 推理，生产级 |
| **[Ollama](https://ollama.com)** | 一键部署、GGUF 量化模型、REST API | 本地开发/演示，低门槛 |
| **[NVIDIA Triton](https://github.com/triton-inference-server)** | 多框架支持、动态批处理、GPU 优化 | 混合模型（LLM+CV）统一服务 |
| **FastAPI + Celery** | 异步任务队列、解耦推理、水平扩展 | 中等吞吐，模型推理异步化 |
| **FastAPI + BackgroundTasks** | 轻量异步、零额外依赖 | 低吞吐/演示环境 |

**本项目选择**: 演示阶段用 **Ollama** 加载 MiMo-VL GGUF（5.5GB），通过 HTTP API 调用；不引入 Celery/Redis 等额外中间件。论文中描述 vLLM 生产方案。

### 1.4 多租户 RBAC 参考

| 方案 | 核心设计 | 借鉴点 |
|------|----------|--------|
| **[WorkOS RBAC Guide](https://workos.com/blog/how-to-design-multi-tenant-rbac-saas)** | 租户作用域角色 + 租户作用域权限；全局角色 vs 租户角色分离 | tenant_id 作为所有权限检查的上下文 |
| **[Aserto Multi-tenant RBAC](https://www.aserto.com/use-cases/multi-tenant-saas-rbac)** | 用户→角色→权限，角色按租户/资源层级作用域 | 角色作用域模型（全局/租户/子资源） |
| **[ThingsBoard RBAC](https://thingsboard.io/docs/pe/reference/architecture)** | 三级实体隔离（租户→客户→用户），高级 RBAC | 平台级 vs 租户级管理分离 |

---

## 二、设计约束与定位

### 2.1 现实约束

| 约束 | 说明 |
|------|------|
| 时间 | D-9 (6/15) ~ D-Day (6/24)，**仅 9 天** |
| 人力 | Fly费（嵌入式）+ 伙伴（服务端为主） |
| 演示目标 | 3 项演示场景（无感通行 + 身份确认 + 节能联动） |
| 前端 | Web Dashboard 单页应用 |
| 数据库 | SQLite（演示足够） |
| GPU | 开发 PC (3080 10GB)，可跑 MiMo-VL GGUF |
| MQTT Broker | mosquitto, 192.168.31.194:1883 |

### 2.2 裁剪原则

- 演示必需 → 做
- 论文加分 → 架构图+文字描述，部分可 mock
- 生产必需（HA/集群/审计合规）→ 论文中描述，不实现

---

## 三、系统架构总览

### 3.1 分层架构（5 层）

```
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 5: 展示层 (Presentation)                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ 实时大屏  │ │ 通行记录  │ │ 设备管理  │ │ 用户管理  │ │ 系统管理  │  │
│  │ Dashboard│ │ Records  │ │ Devices  │ │ Persons  │ │ Admin    │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘  │
│       └────────────┴─────────────┴──────────────┴──────────┘         │
│                          │ HTTP/WebSocket                             │
├──────────────────────────┼───────────────────────────────────────────┤
│  Layer 4: API 网关层 (FastAPI + Uvicorn)                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ REST API │ │WebSocket │ │ 静态文件  │ │ Auth中间件│ │ CORS     │  │
│  │/api/v1/* │ │ /ws      │ │ /dashboard│ │ JWT+RBAC │ │          │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────────┘  │
│       └─────────────┴────────────┘                                    │
├──────────────────────────────────────────────────────────────────────┤
│  Layer 3: 业务逻辑层 (Services)                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │身份引擎  │ │设备管理器│ │规则引擎  │ │告警引擎  │ │模型服务  │  │
│  │Identity  │ │Device    │ │Rule      │ │Alert     │ │Inference │  │
│  │Engine    │ │Manager   │ │Engine    │ │Engine    │ │Service   │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘  │
│       └────────────┴─────────────┴──────────────┴──────────┘         │
├──────────────────────────────────────────────────────────────────────┤
│  Layer 2: 数据访问层 (Models + ORM)                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │SQLAlchemy│ │ SQLite   │ │ JSON配置 │ │ MQTT     │ │ Ollama   │  │
│  │ ORM      │ │ 数据库   │ │ 规则/偏好│ │ Client   │ │ Client   │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘  │
│       └────────────┴─────────────┘              │              │     │
├────────────────────────────────────────────────┼──────────────┼─────┤
│  Layer 1: 接入层                                │              │     │
│                                  MQTT Broker    │    Ollama    │     │
│                               192.168.31.194    │ localhost    │     │
│                                       │         │   :11434     │     │
│                          ┌────────────┼─────────┘              │     │
│                          │            │                        │     │
│                    ┌─────┴─────┐ ┌───┴────────┐ ┌────────────┐ │     │
│                    │ Board 1   │ │ Board 2    │ │ Board 3    │ │     │
│                    │ 门禁节点   │ │ 走廊节点    │ │ 备选节点   │ │     │
│                    │ Face+MQTT │ │轮廓+BLE+MQTT│ │ 辅视角     │ │     │
│                    └───────────┘ └────────────┘ └────────────┘ │     │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 技术栈

| 层 | 组件 | 选型 | 理由 |
|----|------|------|------|
| API | Web 框架 | **FastAPI 0.115+** + Uvicorn | async 原生、WebSocket 内建、自动 OpenAPI 文档、类型安全 |
| 数据 | 数据库 | **SQLite** + aiosqlite | 零配置、单文件、50人规模足够 |
| 数据 | ORM | **SQLAlchemy 2.0** (async) | 后续可无缝切 PostgreSQL |
| 数据 | 向量搜索 | **numpy 余弦相似度** | 50人无需 Faiss；论文描述 Faiss 方案 |
| 通信 | MQTT | **paho-mqtt** | 已有，异步封装 |
| 推理 | LLM 服务 | **Ollama** (MiMo-VL GGUF Q4_0) | 本地 3080 运行，5.5GB 显存 |
| 推理 | 接口 | Ollama REST API (`/api/generate`) | OpenAI 兼容接口 |
| 前端 | Web | 原生 HTML/CSS/JS + Chart.js CDN | 无构建链，单文件即可 |
| 认证 | 安全 | **JWT** (python-jose) | 轻量、无状态、支持 RBAC 声明 |

---

## 四、信息流设计

### 4.1 全链路数据流（端到端）

```
                    ESP32-S3 端                         PC 服务端                          Web 前端
                    ═══════════                        ════════════                       ════════

   ┌──────────────────┐                              ┌─────────────────┐                ┌──────────────┐
   │ OV3660 摄像头     │                              │                 │                │              │
   │ 采集 RGB 帧       │                              │                 │                │              │
   └────────┬─────────┘                              │                 │                │              │
            │ 320×240 RGB                              │                 │                │              │
            ▼                                          │                 │                │              │
   ┌──────────────────┐                              │                 │                │              │
   │ TFLite-Micro     │                              │                 │                │              │
   │ MobileFaceNet    │                              │                 │                │              │
   │ 推理 ~85ms       │                              │                 │                │              │
   └────────┬─────────┘                              │                 │                │              │
            │ 128-d float32 embedding                  │                 │                │              │
            ▼                                          │                 │                │              │
   ┌──────────────────┐     MQTT Publish              │                 │                │              │
   │ MQTT Client      │──── vela/node/1/face ────────→│                 │                │              │
   │ (esp-mqtt)       │  {emb:[128 floats],            │                 │                │              │
   └──────────────────┘   ts, light}                   │                 │                │              │
                                                        ▼                                │              │
                                            ┌─────────────────────┐                      │              │
                                            │ MQTT Broker          │                      │              │
                                            │ mosquitto :1883     │                      │              │
                                            └──────────┬──────────┘                      │              │
                                                        │ paho-mqtt subscribe              │              │
                                                        ▼                                │              │
                                            ┌─────────────────────┐                      │              │
     ┌──────────────────┐  MQTT Publish    │ MQTT Client Service  │                      │              │
     │ Board 2 (走廊)   │──── silhouette ──→│ (mqtt_client.py)     │                      │              │
     │ 帧差法轮廓 + BLE │──── ble ────────→│ 多 topic 订阅         │                      │              │
     └──────────────────┘     heartbeat     └──────────┬──────────┘                      │              │
                                                        │ 回调分发                          │              │
                                     ┌──────────────────┼──────────────────┐              │              │
                                     ▼                  ▼                  ▼              │              │
                            ┌───────────┐     ┌──────────────┐    ┌──────────────┐        │              │
                            │Face数据流 │     │轮廓/BLE数据流 │    │心跳数据流     │        │              │
                            └─────┬─────┘     └──────┬───────┘    └──────┬───────┘        │              │
                                  │                   │                   │                │              │
                                  ▼                   ▼                   ▼                │              │
                          ┌──────────────────────────────────────────────────┐            │              │
                          │            IdentityEngine (身份引擎)              │            │              │
                          │                                                  │            │              │
                          │ 1. 人脸: cosine_sim(emb, faces表) → Top-K匹配     │            │              │
                          │ 2. 步态: 轮廓RLE解码 → 空间特征 → gait_conf       │            │              │
                          │ 3. BLE:  RSSI → 距离等级 → ble_conf              │            │              │
                          │ 4. 融合: fusion_engine (自适应权重)               │            │              │
                          │ 5. 决策: fusion_conf > 0.55 → granted/denied      │            │              │
                          └──────────────────────┬───────────────────────────┘            │              │
                                                  │                                        │              │
                          ┌───────────────────────┼───────────────────────┐                │              │
                          ▼                       ▼                       ▼                │              │
                    ┌──────────┐          ┌──────────────┐         ┌──────────┐            │              │
                    │写库      │          │ WebSocket广播 │         │触发规则   │            │              │
                    │recognitions│        │ /ws/events    │         │RuleEngine │            │              │
                    └──────────┘          └──────┬───────┘         └────┬─────┘            │              │
                                                  │                     │                  │              │
                                                  │ WebSocket Push      │ Alert/Command    │              │
                                                  ▼                     ▼                  │              │
                                          ┌─────────────────────────────────────┐         │              │
                                          │           Web 前端                   │         │              │
                                          │                                      │         │              │
                                          │  websocket.js 接收事件:              │         │              │
                                          │   - recognition → 更新大屏卡片       │         │              │
                                          │   - device_status → 更新在线状态     │         │              │
                                          │   - alert_new → 弹窗 + 告警徽标      │─────────│──────────────│
                                          │                                      │         │              │
                                          │  REST API 拉取:                      │         │              │
                                          │   - GET /api/v1/realtime/overview    │         │              │
                                          │   - GET /api/v1/recognitions?page=1  │         │              │
                                          │   - POST /api/v1/persons (管理员操作) │         │              │
                                          └─────────────────────────────────────┘         │              │
                                                                                           │              │
    ┌──────────────────────────────────────────────────────────────────────────────────────┘              │
    │  推理模型数据流（按需触发）                                                                          │
    │                                                                                      │              │
    │  场景: "会议室多人活动检测" 或 "异常行为分析"                                                  │              │
    │                                                                                      │              │
    │  IdentityEngine 触发 ──→ POST /api/v1/inference/analyze                               │              │
    │                              │                                                       │              │
    │                              ▼                                                       │              │
    │                    ┌──────────────────┐                                              │              │
    │                    │ InferenceService │                                              │              │
    │                    │ (model_service.py)│                                             │              │
    │                    └────────┬─────────┘                                              │              │
    │                             │ HTTP POST /api/generate                                 │              │
    │                             ▼                                                        │              │
    │                    ┌──────────────────┐                                              │              │
    │                    │ Ollama (3080)    │                                              │              │
    │                    │ MiMo-VL GGUF     │                                              │              │
    │                    │ 推理 2-5s        │                                              │              │
    │                    └────────┬─────────┘                                              │              │
    │                             │ 活动语义 JSON                                           │              │
    │                             ▼                                                        │              │
    │                    写库 + WebSocket 推送                                               │              │
    └──────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 关键数据流时序

```
时间轴 →

ESP32 Board 1 (门禁):
  采集帧 ──[85ms]──→ 推理embedding ──[MQTT]──→ Broker

ESP32 Board 2 (走廊):
  帧差轮廓 ──[30ms]──→ RLE压缩 ──[MQTT]──→ Broker
  BLE扫描   ──[被动]──→ RSSI平滑 ──[MQTT]──→ Broker

PC Server:
  MQTT收到face ──[<1ms]──→ cosine匹配 ──[<5ms]──→ 融合判定
  MQTT收到silhouette ──[<1ms]──→ 解码+特征 ──[<10ms]──→ gait_conf
  MQTT收到ble ──[<1ms]──→ RSSI→距离 ──[<1ms]──→ ble_conf
  
  融合 → 阈值判定 → 写DB → WebSocket推送
  端到端延迟: 采集→前端展示 < 300ms ✓

Web 前端:
  WebSocket收到recognition ──[<1ms]──→ DOM更新 ──[<16ms]──→ 屏幕刷新
```

### 4.3 数据量估算

| 数据项 | 单次大小 | 频率 | 日数据量 |
|--------|:-------:|:----:|:--------:|
| face embedding | ~520B (128×f32+JSON) | 15fps | ~675MB |
| silhouette (RLE) | ~500B-2KB | 15fps | ~1.3GB |
| BLE 扫描结果 | ~200B | 1Hz | ~17MB |
| 心跳 status | ~150B | 0.1Hz | ~1.3MB |
| 识别记录 (DB) | ~500B/条 | ~15/分钟 | ~11MB |
| **合计** | | | **~2GB/天** |

> SQLite 日增 2GB 可接受，定期清理即可。演示场景仅数小时，完全无压力。

---

## 五、数据模型

### 5.1 ER 图（完整版）

```
                              ┌──────────────┐
                              │   Tenant     │
                              │  (租户/组织)  │
                              └──────┬───────┘
                                     │ 1:N
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
             ┌──────────┐   ┌──────────────┐   ┌──────────┐
             │  Person  │   │   Device     │   │   Rule   │
             │ (人员)    │   │  (设备)      │   │ (自动化)  │
             └────┬─────┘   └──────┬───────┘   └──────────┘
                  │ 1:N           │ 1:N
                  ▼               ▼
           ┌──────────┐   ┌──────────────┐
           │   Face   │   │ DeviceStatus │
           │(人脸注册) │   │ (设备状态)    │
           └──────────┘   └──────────────┘

┌──────────┐        ┌──────────────┐       ┌──────────┐
│   User   │──N:M──│    Role      │──N:M──│Permission│
│ (登录用户)│       │  (角色)      │       │ (权限)    │
└────┬─────┘       └──────────────┘       └──────────┘
     │
     │ N:1
     ▼
┌──────────┐
│  Tenant  │
└──────────┘

┌──────────────┐       ┌──────────┐
│ Recognition  │──N:1──│  Person  │
│ (识别记录)    │──N:1──│  Device  │
└──────────────┘       └──────────┘

┌──────────┐
│  Alert   │────── N:1 ──→ Rule / Person / Device
│ (告警)    │
└──────────┘
```

### 5.2 核心表结构

#### 5.2.1 tenants（租户表）

```sql
CREATE TABLE tenants (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,                      -- 租户名称: "安克深圳总部"
    code          TEXT UNIQUE NOT NULL,               -- 租户代码: "anker_sz"
    tier          TEXT DEFAULT 'free',                -- 套餐: free/basic/enterprise
    max_devices   INTEGER DEFAULT 10,                 -- 最大设备数
    max_persons   INTEGER DEFAULT 100,                -- 最大人员数
    is_active     INTEGER DEFAULT 1,
    settings_json TEXT DEFAULT '{}',                  -- 租户级全局配置
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT DEFAULT (datetime('now'))
);
```

#### 5.2.2 users（登录用户表 — RBAC）

```sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id     INTEGER NOT NULL REFERENCES tenants(id),
    username      TEXT NOT NULL,
    password_hash TEXT NOT NULL,                      -- bcrypt hash
    email         TEXT,
    display_name  TEXT DEFAULT '',
    is_active     INTEGER DEFAULT 1,
    is_superadmin INTEGER DEFAULT 0,                  -- 平台超级管理员（跨租户）
    last_login    TEXT,
    created_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(tenant_id, username)
);
```

#### 5.2.3 roles（角色表）

```sql
CREATE TABLE roles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id     INTEGER NOT NULL REFERENCES tenants(id),
    name          TEXT NOT NULL,                      -- 角色名: "管理员"/"安保"/"普通员工"
    description   TEXT DEFAULT '',
    is_system     INTEGER DEFAULT 0,                  -- 系统内置角色（不可删除）
    created_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(tenant_id, name)
);
```

#### 5.2.4 permissions（权限表）

```sql
CREATE TABLE permissions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT UNIQUE NOT NULL,               -- 权限代码: "person:read"
    name          TEXT NOT NULL,                      -- 权限名称: "查看人员"
    resource      TEXT NOT NULL,                      -- 资源: person/device/recognition/alert/rule/tenant
    action        TEXT NOT NULL,                      -- 动作: create/read/update/delete/manage
    description   TEXT DEFAULT ''
);

-- 预置权限
INSERT INTO permissions VALUES
(1, 'person:read',    '查看人员',     'person',      'read',    '查看人员列表和详情'),
(2, 'person:write',   '管理人员',     'person',      'manage',  '增删改人员及人脸注册'),
(3, 'device:read',    '查看设备',     'device',      'read',    '查看设备列表和状态'),
(4, 'device:write',   '管理设备',     'device',      'manage',  '注册/删除/控制设备'),
(5, 'recognition:read','查看识别记录','recognition',  'read',    '查看通行记录'),
(6, 'alert:read',     '查看告警',     'alert',       'read',    '查看告警列表'),
(7, 'alert:resolve',  '处理告警',     'alert',       'manage',  '标记告警已处理'),
(8, 'rule:write',     '管理规则',     'rule',        'manage',  '增删改自动化规则'),
(9, 'tenant:admin',   '租户管理',     'tenant',      'manage',  '修改租户配置'),
(10,'dashboard:view',  '查看大屏',    'dashboard',   'read',    '查看实时大屏'),
(11,'inference:use',   '使用推理',    'inference',   'read',    '触发模型推理');
```

#### 5.2.5 role_permissions（角色-权限关联）

```sql
CREATE TABLE role_permissions (
    role_id       INTEGER NOT NULL REFERENCES roles(id),
    permission_id INTEGER NOT NULL REFERENCES permissions(id),
    PRIMARY KEY (role_id, permission_id)
);
```

#### 5.2.6 user_roles（用户-角色关联，支持一个用户多角色）

```sql
CREATE TABLE user_roles (
    user_id       INTEGER NOT NULL REFERENCES users(id),
    role_id       INTEGER NOT NULL REFERENCES roles(id),
    PRIMARY KEY (user_id, role_id)
);
```

#### 5.2.7 persons（人员表 — 被识别对象，非登录用户）

```sql
CREATE TABLE persons (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id     INTEGER NOT NULL REFERENCES tenants(id),
    name          TEXT NOT NULL,
    employee_id   TEXT,                              -- 工号（租户内唯一）
    department    TEXT DEFAULT '',
    person_type   TEXT DEFAULT 'employee',           -- employee/visitor/vip/contractor
    phone         TEXT DEFAULT '',
    email         TEXT DEFAULT '',
    ble_mac       TEXT DEFAULT '',
    ble_irk       TEXT DEFAULT '',
    avatar_url    TEXT DEFAULT '',
    access_level  INTEGER DEFAULT 1,                 -- 通行级别: 1普通 2敏感区 3全区域
    valid_from    TEXT,                               -- 访客有效期开始
    valid_until   TEXT,                               -- 访客有效期结束
    is_active     INTEGER DEFAULT 1,
    registered_by INTEGER REFERENCES users(id),      -- 谁注册的
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(tenant_id, employee_id)
);
```

#### 5.2.8 devices（设备表）

```sql
CREATE TABLE devices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id     INTEGER NOT NULL REFERENCES tenants(id),
    node_id       TEXT NOT NULL,                      -- 节点ID: "1"
    name          TEXT DEFAULT '',
    location      TEXT DEFAULT '',
    device_type   TEXT DEFAULT 'camera',
    board_model   TEXT DEFAULT 'XIAO_ESP32S3_SENSE',
    firmware_ver  TEXT DEFAULT '',
    ip_address    TEXT DEFAULT '',
    is_online     INTEGER DEFAULT 0,
    last_seen     TEXT DEFAULT '',
    config_json   TEXT DEFAULT '{}',
    created_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(tenant_id, node_id)
);
```

#### 5.2.9 recognitions（识别记录）

```sql
CREATE TABLE recognitions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id     INTEGER NOT NULL REFERENCES tenants(id),
    person_id     INTEGER REFERENCES persons(id),
    device_id     INTEGER REFERENCES devices(id),
    node_id       TEXT NOT NULL,
    face_conf     REAL DEFAULT 0.0,
    gait_conf     REAL DEFAULT 0.0,
    ble_conf      REAL DEFAULT 0.0,
    fusion_conf   REAL DEFAULT 0.0,
    modality_count INTEGER DEFAULT 0,
    light_level   REAL DEFAULT 1.0,
    decision      TEXT DEFAULT 'unknown',            -- granted/denied/pending/unknown
    explain_text  TEXT DEFAULT '',                    -- 自然语言解释: "人脸匹配置信度高(0.62)，步态辅助确认(0.22)，BLE邻近(0.16)"
    face_emb_id   INTEGER REFERENCES faces(id),
    raw_data_json TEXT DEFAULT '{}',
    created_at    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_recog_tenant_time ON recognitions(tenant_id, created_at);
CREATE INDEX idx_recog_person ON recognitions(person_id);
CREATE INDEX idx_recog_decision ON recognitions(decision);
```

### 5.3 预置数据（seed）

```sql
-- 默认租户
INSERT INTO tenants (id, name, code, tier) VALUES (1, '默认组织', 'default', 'enterprise');

-- 默认管理员用户 (密码: admin123)
INSERT INTO users (id, tenant_id, username, password_hash, is_superadmin) 
VALUES (1, 1, 'admin', '$2b$12$...', 1);

-- 系统内置角色
INSERT INTO roles (id, tenant_id, name, is_system) VALUES
(1, 1, '超级管理员', 1),
(2, 1, '安保主管', 1),
(3, 1, '普通员工', 1);

-- 角色-权限映射
-- 超级管理员 → 所有权限
-- 安保主管 → person:read, device:read, recognition:read, alert:*, dashboard:view
-- 普通员工 → dashboard:view (仅查看)
```

---

## 六、推理模型服务设计

### 6.1 架构定位

推理模型（MiMo-VL）在整个系统中的定位是 **可选的认知增强层**：
- **Layer 0 (ESP32)**: 实时轻量推理（人脸 embedding、轮廓提取）
- **Layer 1 (Server CPU)**: 身份融合引擎（numpy 规则，<10ms）
- **Layer 2 (Server GPU)**: MiMo-VL 语义推理（按需触发，2-5s）

### 6.2 模型部署方案

```
┌─────────────────────────────────────────────────────────┐
│                  PC Server (3080 10GB)                    │
│                                                          │
│  ┌──────────────────┐     ┌───────────────────────────┐ │
│  │ FastAPI Server   │     │ Ollama Server (:11434)     │ │
│  │ (CPU 主进程)     │     │                           │ │
│  │                  │     │ MiMo-VL-Miloco-7B         │ │
│  │ InferenceService │────→│ GGUF Q4_0 (~5.5GB)       │ │
│  │   ↓              │ HTTP│                           │ │
│  │ 异步任务         │     │ 推理延迟: 2-5s/次          │ │
│  │ (BackgroundTasks)│     │ 批处理: 不支持(GGUF)       │ │
│  └──────────────────┘     └───────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 6.3 InferenceService 设计

```python
# services/inference_service.py

class InferenceService:
    """推理模型服务 — 封装 MiMo-VL 调用"""
    
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL_NAME = "mimo-vl-miloco:7b-q4_0"
    
    async def analyze_scene(self, image_b64: str, prompt: str) -> dict:
        """
        场景分析: 发送图像 + 文本提示 → 获取结构化结果
        
        Args:
            image_b64: Base64 编码的 RGB 图像
            prompt: 自然语言指令，如 "检测图像中有多少人在开会，描述他们的活动"
            
        Returns:
            {"activity": "开会", "person_count": 4, "confidence": 0.92, "detail": "..."}
        """
        ...
    
    async def detect_anomaly(self, event_sequence: list) -> dict:
        """
        异常检测: 基于事件序列判断异常行为
        
        示例输入: [{type:"enter", person:"张三", time:"22:15", zone:"财务部"}]
        返回: {"is_anomaly": True, "reason": "非工作时间进入敏感区域", "severity": "high"}
        """
        ...
    
    async def infer_intent(self, trajectory: list, calendar: dict) -> dict:
        """
        时空意图推断: 轨迹 + 日历 → 目的地预测
        
        返回: {"destination": "12F-305会议室", "confidence": 0.87, "eta": "2分钟"}
        """
        ...
```

### 6.4 调用触发方式

| 触发方式 | 场景 | 延迟要求 | 实现 |
|----------|------|:------:|------|
| **按需触发** (API) | 用户点击"分析此场景" | 2-5s 可接受 | FastAPI BackgroundTasks → Ollama |
| **规则触发** (自动) | 检测到"非工作时间敏感区有人" | 秒级 | RuleEngine → InferenceService |
| **定时触发** (批处理) | 每日凌晨分析昨日异常事件 | 分钟级 | 不做（9天冲刺不实现） |

### 6.5 降级策略

如果 MiMo-VL 不可用（Ollama 未安装/GPU 不足）：
```python
# 降级为规则引擎
if not ollama_available:
    # 基于规则的异常检测
    if time > "20:00" and zone == "财务部":
        return {"is_anomaly": True, "reason": "规则引擎: 非工作时间财务部有人"}
```

### 6.6 生产方案（论文描述）

论文中描述但不实现的完整推理架构：
- **vLLM** 替代 Ollama：连续批处理支持高并发
- **Celery + Redis** 任务队列：推理任务异步化、支持重试
- **NVIDIA Triton**：统一管理多个模型（MobileFaceNet resnet → ONNX、MiMo-VL → vLLM backend）
- **模型热加载**：按需加载不同微调版本

---

## 七、员工角色管理 (RBAC)

### 7.1 核心概念

```
┌─────────────────────────────────────────────────────────────────┐
│                         RBAC 模型                                │
│                                                                  │
│   User (登录用户) ──N:M── Role (角色) ──N:M── Permission (权限)  │
│       │                    │                      │              │
│       │ 属于               │ 属于                 │ 针对         │
│       ▼                    ▼                      ▼              │
│   Tenant (租户)        Tenant (租户)         Resource (资源)     │
│                                                                  │
│   权限检查 = User.id → 角色集合 → 权限集合 → 是否包含所需权限    │
│   租户隔离 = 所有查询自动附加 WHERE tenant_id = current_tenant   │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 权限矩阵（默认角色）

| 权限 | 超级管理员 | 安保主管 | 普通员工 |
|------|:---:|:---:|:---:|
| `person:read` | ✅ | ✅ | ❌ |
| `person:write` | ✅ | ❌ | ❌ |
| `device:read` | ✅ | ✅ | ❌ |
| `device:write` | ✅ | ❌ | ❌ |
| `recognition:read` | ✅ | ✅ | ❌ |
| `alert:read` | ✅ | ✅ | ❌ |
| `alert:resolve` | ✅ | ✅ | ❌ |
| `rule:write` | ✅ | ❌ | ❌ |
| `tenant:admin` | ✅ | ❌ | ❌ |
| `dashboard:view` | ✅ | ✅ | ✅ |
| `inference:use` | ✅ | ✅ | ❌ |

### 7.3 JWT 认证流程

```
1. 客户端 POST /api/v1/auth/login {username, password}
2. 服务端验证 → 查询用户+角色+权限 → 生成 JWT
   JWT Payload:
   {
     "sub": "1",                  // user_id
     "tenant_id": 1,
     "tenant_code": "default",
     "username": "admin",
     "roles": ["超级管理员"],
     "permissions": ["person:read","person:write",...],
     "exp": 1718524800            // 过期时间
   }
3. 客户端存储 token，后续请求带 Authorization: Bearer <token>
4. 中间件解码 JWT → 注入 request.state.user
5. API 端点用 Depends(check_permission("person:write")) 保护
```

### 7.4 FastAPI 权限中间件

```python
# 装饰器方式
@router.delete("/api/v1/persons/{person_id}")
@require_permission("person:write")
async def delete_person(person_id: int, ...):
    ...

# 依赖注入方式
async def check_permission(required: str):
    def checker(request: Request):
        user_perms = request.state.user.get("permissions", [])
        if required not in user_perms:
            raise HTTPException(403, f"需要权限: {required}")
        return True
    return Depends(checker)
```

### 7.5 租户数据隔离

所有数据访问层自动注入 `tenant_id`：

```python
# 查询人员列表 — 自动过滤当前租户
async def get_persons(db, tenant_id: int, page: int = 1):
    query = select(Person).where(Person.tenant_id == tenant_id)
    # ...分页
```

> 超级管理员 (`is_superadmin=1`) 可以跨租户访问。

---

## 八、租户管理设计

### 8.1 为什么要租户

虽然演示阶段只有 1 个"组织"，但方案设计需要体现：
- **多企业/多楼宇部署**：平台可同时服务多个客户
- **数据隔离**：企业 A 无法看到企业 B 的人员/设备/识别记录
- **差异化配置**：不同租户可有不同的规则、套餐限制

### 8.2 租户隔离模型

```
Platform (平台)
  ├── Tenant A: "安克深圳总部"
  │     ├── Users: [admin@anker, guard_zhang@anker, ...]
  │     ├── Persons: [张三(E001), 李四(E002), ...]
  │     ├── Devices: [Board1(门禁), Board2(走廊), Board3(备用)]
  │     ├── Rules:   ["会议室无人关灯", "访客通知"]
  │     └── Recognitions: [14:30 张三 通过, ...]
  │
  ├── Tenant B: "某联合办公空间"     ← 演示不建，架构支持
  │     ├── Users: [admin@cowork, ...]
  │     ├── Persons: [王五(V001), ...]
  │     └── ...
  │
  └── Tenant C: ...
```

**隔离方式**: 应用层隔离（每个查询带 tenant_id），非独立数据库（SQLite 单文件即可）。

### 8.3 租户管理员工作流

```
超级管理员 (platform admin)         租户管理员 (tenant admin)
═══════════════════════            ═══════════════════════
1. 创建租户                        ---
2. 设置租户套餐/限制                ---
3. 创建租户管理员帐号              1. 登录
---                               2. 管理本租户人员 (persons CRUD)
---                               3. 注册设备 (devices)
---                               4. 创建角色并分配权限
---                               5. 配置自动化规则
---                               6. 查看识别记录/大屏
---                               7. 处理告警
```

### 8.4 租户配置

```json
// tenant.settings_json
{
    "face_match_threshold": 0.55,
    "heartbeat_timeout_sec": 30,
    "alert_levels": {
        "device_offline": "warning",
        "unauthorized_access": "critical",
        "visitor_entry": "info"
    },
    "retention_days": {
        "recognitions": 30,
        "alerts": 90,
        "device_status": 7
    },
    "notification": {
        "webhook_url": "",
        "enable_sound": true
    }
}
```

---

## 九、MQTT 协议设计

### 9.1 主题空间（完整版）

```
                                         方向
vela/node/{node_id}/face                 ← ESP32 上报人脸嵌入
vela/node/{node_id}/silhouette           ← ESP32 上报轮廓 (RLE)
vela/node/{node_id}/ble                  ← ESP32 上报 BLE 扫描结果
vela/node/{node_id}/status               ← ESP32 心跳
vela/node/{node_id}/alert                ← ESP32 本地异常 (预留)

vela/server/command/{node_id}            → Server 下发指令 (重启/配置)
vela/server/config/{node_id}             → Server 下发配置更新
vela/server/broadcast                    → Server 全节点广播

vela/tenant/{tenant_code}/node/+/...     ← 多租户扩展（未来）
```

### 9.2 消息格式详述

#### face 上报
```json
{
    "ts": 1718438400.123,
    "emb": [0.123, -0.456, ...],   // 128 × float32
    "conf": 0.85,
    "light": 0.7,
    "frame_id": 12345              // 帧序号（调试用）
}
```

#### silhouette 上报
```json
{
    "ts": 1718438400.456,
    "width": 80,
    "height": 60,
    "rle": "AAABBBCCC...",         // Run-Length Encoded binary silhouette
    "crc": 54321,
    "frame_id": 12346
}
```

#### ble 上报
```json
{
    "ts": 1718438400.789,
    "devices": [
        {"mac": "AA:BB:CC:11:22:33", "rssi": -55, "addr_type": "random", "name": ""},
        {"mac": "DD:EE:FF:44:55:66", "rssi": -72, "addr_type": "public", "name": "iPhone-Fei"}
    ],
    "scan_duration_ms": 1000
}
```

#### status 上报（心跳，每 10s）
```json
{
    "ts": 1718438401.000,
    "uptime": 3600,
    "free_heap": 1234567,
    "free_psram": 4194304,
    "wifi_rssi": -45,
    "fps": 15.2,
    "temp": 42.5,
    "inference_mode": "face",      // 当前推理模式
    "fw_version": "v9.6"
}
```

#### 指令下发
```json
{
    "cmd": "reboot",               // reboot / config_update / set_threshold
    "ts": 1718438500.000,
    "params": {
        "delay_ms": 1000
    },
    "request_id": "uuid-xxxx"      // 异步响应匹配
}
```

---

## 十、REST API 设计

### 10.1 认证 `/api/v1/auth`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|:---:|
| `POST` | `/api/v1/auth/login` | 登录获取 JWT | 无 |
| `POST` | `/api/v1/auth/refresh` | 刷新 token | 登录 |
| `GET` | `/api/v1/auth/me` | 当前用户信息+权限 | 登录 |

### 10.2 租户管理 `/api/v1/tenants`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|:---:|
| `GET` | `/api/v1/tenants` | 租户列表 | superadmin |
| `POST` | `/api/v1/tenants` | 创建租户 | superadmin |
| `GET` | `/api/v1/tenants/{id}` | 租户详情 | tenant:admin |
| `PUT` | `/api/v1/tenants/{id}` | 更新租户 | tenant:admin |

### 10.3 用户与角色管理 `/api/v1/users`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|:---:|
| `GET` | `/api/v1/users` | 用户列表 | tenant:admin |
| `POST` | `/api/v1/users` | 创建用户 | tenant:admin |
| `PUT` | `/api/v1/users/{id}` | 更新用户 | tenant:admin |
| `DELETE` | `/api/v1/users/{id}` | 删除用户 | tenant:admin |
| `GET` | `/api/v1/roles` | 角色列表 | tenant:admin |
| `POST` | `/api/v1/roles` | 创建角色 | tenant:admin |
| `PUT` | `/api/v1/roles/{id}` | 更新角色 | tenant:admin |
| `DELETE` | `/api/v1/roles/{id}` | 删除角色 | tenant:admin |
| `GET` | `/api/v1/permissions` | 所有权限列表（只读） | 登录 |

### 10.4 人员管理 `/api/v1/persons`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|:---:|
| `GET` | `/api/v1/persons` | 人员列表（分页/搜索/过滤） | person:read |
| `POST` | `/api/v1/persons` | 新增人员 | person:write |
| `GET` | `/api/v1/persons/{id}` | 人员详情 | person:read |
| `PUT` | `/api/v1/persons/{id}` | 更新人员 | person:write |
| `DELETE` | `/api/v1/persons/{id}` | 删除人员 | person:write |
| `POST` | `/api/v1/persons/{id}/faces` | 注册人脸 | person:write |
| `GET` | `/api/v1/persons/{id}/faces` | 已注册人脸列表 | person:read |
| `DELETE` | `/api/v1/persons/{id}/faces/{face_id}` | 删除人脸 | person:write |

### 10.5 设备管理 `/api/v1/devices`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|:---:|
| `GET` | `/api/v1/devices` | 设备列表 | device:read |
| `POST` | `/api/v1/devices` | 注册设备 | device:write |
| `GET` | `/api/v1/devices/{id}` | 设备详情 | device:read |
| `PUT` | `/api/v1/devices/{id}` | 更新设备 | device:write |
| `POST` | `/api/v1/devices/{id}/command` | 发送指令 | device:write |
| `GET` | `/api/v1/devices/{id}/status/history` | 状态历史 | device:read |

### 10.6 识别记录 `/api/v1/recognitions`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|:---:|
| `GET` | `/api/v1/recognitions` | 记录列表（分页/时间范围/设备/人员/结果筛选） | recognition:read |
| `GET` | `/api/v1/recognitions/stats` | 统计数据（今日/本周识别数、准确率、模态占比） | recognition:read |
| `GET` | `/api/v1/recognitions/recent?limit=20` | 最近 N 条 | recognition:read |

### 10.7 告警 `/api/v1/alerts`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|:---:|
| `GET` | `/api/v1/alerts` | 告警列表（级别/状态过滤） | alert:read |
| `PUT` | `/api/v1/alerts/{id}/resolve` | 标记已处理 | alert:resolve |
| `GET` | `/api/v1/alerts/stats` | 告警统计 | alert:read |

### 10.8 规则管理 `/api/v1/rules`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|:---:|
| `GET` | `/api/v1/rules` | 规则列表 | rule:write |
| `POST` | `/api/v1/rules` | 创建规则 | rule:write |
| `PUT` | `/api/v1/rules/{id}` | 更新规则 | rule:write |
| `DELETE` | `/api/v1/rules/{id}` | 删除规则 | rule:write |
| `PUT` | `/api/v1/rules/{id}/toggle` | 启用/禁用 | rule:write |

### 10.9 实时数据 `/api/v1/realtime`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|:---:|
| `GET` | `/api/v1/realtime/overview` | 首页概览 | dashboard:view |
| `WebSocket` | `/ws/events` | 实时事件推送 | dashboard:view |

### 10.10 推理模型 `/api/v1/inference`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|:---:|
| `POST` | `/api/v1/inference/analyze` | 场景分析（发送图像+提示） | inference:use |
| `POST` | `/api/v1/inference/detect-anomaly` | 异常检测 | inference:use |
| `GET` | `/api/v1/inference/models` | 可用模型列表 | inference:use |

---

## 十一、业务逻辑模块

### 11.1 IdentityEngine（身份引擎）

```python
class IdentityEngine:
    """核心融合引擎 — MQTT 数据 → 身份决策"""
    
    def __init__(self, db_session, fusion_engine, mqtt_client, ws_manager):
        self.db = db_session
        self.fusion = fusion_engine      # 现有 fusion_engine.py
        self.mqtt = mqtt_client
        self.ws = ws_manager
        self.window = {}                  # node_id → deque
    
    async def on_face(self, node_id: str, emb: list, light: float):
        """处理人脸嵌入"""
        # 1. 与 faces 表做 cosine 匹配
        matches = await self._match_faces(emb)
        # 2. 更新 fusion engine
        if matches:
            self.fusion.update_face(matches[0].person_id, matches[0].score)
        self.fusion.set_light_level(light)
        # 3. 尝试融合决策
        await self._try_fusion(node_id)
    
    async def on_silhouette(self, node_id: str, rle: str):
        """处理轮廓数据"""
        # 解码 RLE → 提取空间特征（步频/步幅/高宽比）
        features = self._extract_gait_features(rle)
        # 更新滑动窗口
        ...
    
    async def on_ble(self, node_id: str, devices: list):
        """处理 BLE 扫描"""
        # 匹配 persons 表中的 ble_mac
        for dev in devices:
            person = await self._find_person_by_mac(dev['mac'])
            if person:
                proximity = self._rssi_to_proximity(dev['rssi'])
                self.fusion.update_ble(person.id, dev['rssi'], proximity)
        await self._try_fusion(node_id)
    
    async def _try_fusion(self, node_id: str):
        """执行融合 → 生成识别记录"""
        result = self.fusion.identify()
        if result and result.confidence > 0.55:
            recognition = Recognition(
                person_id=result.employee_id,
                fusion_conf=result.confidence,
                face_conf=result.face_conf,
                gait_conf=result.gait_conf,
                ble_conf=result.ble_conf,
                modality_count=result.modality_count,
                decision='granted',
                explain_text=self._generate_explanation(result)
            )
            await self.db.add(recognition)
            await self.db.commit()
            
            # WebSocket 推送
            await self.ws.broadcast('recognition', recognition.to_dict())
            
            # 触发规则引擎
            await self.rule_engine.on_recognition(recognition)
```

### 11.2 DeviceManager（设备管理器）

```python
class DeviceManager:
    async def on_heartbeat(self, node_id: str, status: dict):
        device = await self._get_or_create_device(node_id)
        device.is_online = True
        device.last_seen = datetime.now()
        # 记录状态历史
        DeviceStatus(device_id=device.id, free_heap=status['free_heap'], ...)
        await self.db.commit()
    
    async def check_offline(self):
        """定时任务：检测离线设备"""
        timeout = datetime.now() - timedelta(seconds=30)
        offline = await self.db.query(Device).filter(
            Device.is_online == True,
            Device.last_seen < timeout
        ).all()
        for dev in offline:
            dev.is_online = False
            await AlertEngine.create_alert(
                level='warning',
                title=f'设备 {dev.name} 离线',
                device_id=dev.id
            )
```

### 11.3 RuleEngine（规则引擎）

```python
class RuleEngine:
    async def on_recognition(self, recog: Recognition):
        """识别事件触发规则检查"""
        rules = await self.db.query(Rule).filter(
            Rule.is_enabled == True,
            Rule.trigger_type == 'recognition'
        ).all()
        for rule in rules:
            if self._match_condition(rule, recog):
                await self._execute_action(rule, recog)
    
    async def _execute_action(self, rule: Rule, event):
        if rule.action_type == 'mqtt_publish':
            await self.mqtt.publish(rule.action_config['topic'], json.dumps(...))
        elif rule.action_type == 'create_alert':
            await AlertEngine.create_alert(...)
        elif rule.action_type == 'webhook':
            await self._http_post(rule.action_config['url'], ...)
```

### 11.4 AlertEngine（告警引擎）

```python
class AlertEngine:
    @staticmethod
    async def create_alert(level: str, title: str, message: str = '', **kwargs):
        alert = Alert(level=level, title=title, message=message, **kwargs)
        await db.add(alert)
        await db.commit()
        # WebSocket 推送新告警
        await ws_manager.broadcast('alert_new', alert.to_dict())
```

---

## 十二、WebSocket 实时推送

### 12.1 事件类型

| 事件类型 | 触发时机 | 推送数据 |
|----------|----------|----------|
| `recognition` | 身份识别完成 | person_name, confidence, node_id, modalities, decision, explain_text |
| `device_status` | 收到心跳 | node_id, online, heap, rssi, uptime |
| `device_offline` | 设备离线 | node_id, device_name |
| `alert_new` | 新告警 | level, title, message |
| `alert_resolved` | 告警已处理 | alert_id |

### 12.2 连接管理

```python
class WebSocketManager:
    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}  # user_id → ws
    
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.connections[user_id] = websocket
    
    async def broadcast(self, event_type: str, data: dict):
        """向所有在线用户广播"""
        message = json.dumps({"type": event_type, "data": data, "ts": time.time()})
        dead = []
        for uid, ws in self.connections.items():
            try:
                await ws.send_text(message)
            except:
                dead.append(uid)
        for uid in dead:
            del self.connections[uid]
```

---

## 十三、前端页面设计

### 13.1 页面结构

```
┌─────────────────────────────────────────────────────────────────┐
│  🏢 智能建筑管理系统          🔔 3条告警   👤 admin   ⚙️ 退出  │
├─────────────────────────────────────────────────────────────────┤
│  [实时大屏] [通行记录] [设备管理] [人员管理] [告警中心] [系统设置]│
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                        Tab 内容区                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 13.2 各 Tab 详设

**Tab 1: 实时大屏** — 4 卡片概览 + 最近识别流 + 趋势图 + 空间占用

**Tab 2: 通行记录** — 表格 + 筛选器 + 分页，列: 时间/节点/人员/人脸置信度/步态置信度/BLE置信度/融合置信度/结果/解释

**Tab 3: 设备管理** — 设备卡片（在线🟢/离线🔴）+ 心跳曲线 + 指令操作

**Tab 4: 人员管理** — 人员表格 + 搜索 + 增删改 + 人脸注册/查看

**Tab 5: 告警中心** — 告警列表 + 级别过滤 + 标记处理

**Tab 6: 系统设置** — 角色管理 + 用户管理 + 规则管理 + 租户配置（仅 admin 可见）

### 13.3 前端技术方案

```html
<!-- 纯 HTML/CSS/JS, 无构建工具 -->
<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
</head>
<body>
    <!-- Tab 切换 + iframe 或动态加载 -->
    <script src="/static/js/app.js"></script>
    <script src="/static/js/websocket.js"></script>
</body>
</html>
```

---

## 十四、目录结构

```
server/
├── DESIGN.md                         ← 本文档
├── requirements.txt
├── server.py                         ← 启动入口
│
├── app/
│   ├── __init__.py
│   ├── main.py                       ← FastAPI 创建 + 生命周期
│   ├── config.py                     ← 配置管理
│   │
│   ├── models/                       ← SQLAlchemy 模型
│   │   ├── __init__.py
│   │   ├── database.py               ← DB 连接 + session
│   │   ├── tenant.py
│   │   ├── user.py
│   │   ├── role.py
│   │   ├── permission.py
│   │   ├── person.py
│   │   ├── face.py
│   │   ├── device.py
│   │   ├── device_status.py
│   │   ├── recognition.py
│   │   ├── rule.py
│   │   └── alert.py
│   │
│   ├── api/                          ← REST + WebSocket 路由
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── tenants.py
│   │   ├── users.py
│   │   ├── roles.py
│   │   ├── permissions.py
│   │   ├── persons.py
│   │   ├── devices.py
│   │   ├── recognitions.py
│   │   ├── alerts.py
│   │   ├── realtime.py
│   │   ├── rules.py
│   │   ├── inference.py
│   │   └── websocket.py
│   │
│   ├── services/                     ← 业务逻辑引擎
│   │   ├── __init__.py
│   │   ├── identity_engine.py
│   │   ├── mqtt_client.py
│   │   ├── device_manager.py
│   │   ├── rule_engine.py
│   │   ├── alert_engine.py
│   │   ├── inference_service.py      ← MiMo-VL 推理封装
│   │   └── auth_service.py           ← JWT 处理
│   │
│   └── fusion/                       ← 融合算法（从现有迁移）
│       ├── __init__.py
│       └── fusion_engine.py
│
├── static/                           ← Web 前端
│   ├── index.html
│   ├── css/
│   │   └── dashboard.css
│   └── js/
│       ├── app.js                    ← Tab 切换 + 路由
│       ├── dashboard.js              ← 实时大屏
│       ├── recognitions.js           ← 通行记录
│       ├── devices.js                ← 设备管理
│       ├── persons.js                ← 人员管理
│       ├── alerts.js                 ← 告警中心
│       ├── settings.js               ← 系统设置
│       ├── websocket.js              ← WS 事件处理
│       └── utils.js                  ← 工具函数（请求封装/格式化）
│
├── scripts/                          ← 工具脚本
│   ├── seed_data.py                  ← 初始化数据库 + 预置数据
│   └── migrate.py                    ← 数据库迁移
│
└── data/                             ← 运行时数据（gitignore）
    ├── smart_building.db
    └── config.json
```

---

## 十五、实现分期计划

### Phase 1: 核心管线（D-9 ~ D-8, 6/15-6/16）🎯 最小闭环

| # | 模块 | 任务 |
|---|------|------|
| 1 | models/ | 所有表模型 + SQLite 建表 |
| 2 | models/database.py | async session 管理 |
| 3 | scripts/seed_data.py | 预置租户+角色+权限+管理员 |
| 4 | services/mqtt_client.py | 多 topic 订阅（face/silhouette/ble/status） |
| 5 | fusion/fusion_engine.py | 迁移现有代码，适配 async |
| 6 | services/identity_engine.py | face 匹配 + 融合 + 写库 + WS 推送 |
| 7 | services/device_manager.py | 心跳处理 + 设备自动注册 |
| 8 | api/websocket.py | WebSocket 端点 + 连接管理 |
| 9 | api/realtime.py | `/api/v1/realtime/overview` |
| 10 | app/main.py | FastAPI 骨架 + startup/shutdown |

### Phase 2: API 补全 + 前端骨架（D-7 ~ D-6, 6/17-6/18）

| # | 模块 | 任务 |
|---|------|------|
| 11 | api/auth.py | 登录 + JWT |
| 12 | api/persons.py | CRUD + 人脸注册 |
| 13 | api/devices.py | CRUD + 指令下发 |
| 14 | api/recognitions.py | 查询 + 统计 |
| 15 | static/ | 前端骨架 HTML + CSS |
| 16 | static/js/dashboard.js | 实时大屏（Chart.js + WebSocket） |
| 17 | static/js/websocket.js | WebSocket 事件分发 |

### Phase 3: 前端补全 + 告警规则（D-5 ~ D-4, 6/19-6/20）

| # | 模块 | 任务 |
|---|------|------|
| 18 | static/js/* | 全部 5 个 Tab 页面 |
| 19 | api/alerts.py + services/alert_engine.py | 告警 CRUD + 自动生成 |
| 20 | api/rules.py + services/rule_engine.py | 规则 CRUD + 事件触发 |
| 21 | api/tenants.py + api/users.py + api/roles.py | 租户/用户/角色管理 |
| 22 | services/inference_service.py | Ollama 推理封装（可选） |
| 23 | api/inference.py | 推理 API（可选） |
| 24 | 前后端联调 | 端到端测试所有 Tab |

### Phase 4: 集成演示（D-3 ~ D-2, 6/21-6/22）

| # | 模块 | 任务 |
|---|------|------|
| 25 | 全链路联调 | ESP32 → MQTT → Server → Dashboard |
| 26 | CSS 美化 | 演示视觉效果 |
| 27 | 演示剧本 | 3 场景排练 |

---

## 十六、砍掉清单

| 砍掉 | 理由 | 论文处理 |
|------|------|----------|
| PostgreSQL / TimescaleDB / Redis / MinIO | 演示 SQLite 足够 | 论文描述 |
| Docker / k3s | 单进程裸跑 | 论文描述 |
| EMQX 换 mosquitto | mosquitto 已够用 | — |
| Celery 任务队列 | 推理用 BackgroundTasks 即可 | 论文描述 |
| NVIDIA Triton / vLLM | 用 Ollama 替代 | 论文描述 vLLM 方案 |
| Faiss GPU 向量搜索 | numpy 50人足够 | 论文描述 Faiss IVFPQ |
| 员工端 App / 小程序 | 冲刺已砍 | 视频 mockup |
| OTA 服务端 | 冲刺已砍 | — |
| 用户自助注册 | 管理员手动创建 | — |
| 响应式移动端 | 演示用 1920×1080 | — |
| CSV 导出 | 锦上添花 | — |
| 国际化 i18n | 全中文演示 | — |
| 邮件/短信通知 | 不需要 | 论文描述 |
| 定时批处理任务 | 9天不够 | 论文描述 |
| BLE IRK 完整流程 | BLE 框架还在调 | 论文描述 |

---

## 十七、与原设计文档 v3.4 差异对比

| 设计文档 v3.4 §17 | v2.0 设计 | 差异理由 |
|-------------------|-----------|----------|
| EMQX 5.x | mosquitto | 已有，不换 |
| PostgreSQL + TimescaleDB | SQLite | 演示足够 |
| Redis Pub/Sub | WebSocket 直接推送 | 减少依赖 |
| MinIO | 无 | 无大文件 |
| Faiss GPU | numpy 余弦 | <50人 |
| gRPC | 直接函数调用 | 单进程 |
| Docker Compose | 裸 python | 开发阶段 |
| Ollama (论文列) | **Ollama 实现** | 演示可行 |
| RBAC "企业级" | **RBAC 实现** | 必须做 |
| 多租户 "未来" | **多租户实现** | 架构需要 |
| 无推理模型服务 | **InferenceService** | 用户要求 |
| 无信息流图 | **详细时序+数据流** | 用户要求 |

---

## 附录：参考链接

- [ThingsBoard Architecture](https://thingsboard.io/docs/pe/reference/architecture) — 多租户 IoT 平台架构参考
- [ThingsBoard Multi-tenancy](https://thingsboard.io/docs/pe/user-guide/multi-tenancy) — 租户隔离模型
- [Seeed face-recognition-api](https://github.com/Seeed-Solution/face-recognition-api) — 人脸识别 API 设计参考
- [WorkOS Multi-tenant RBAC](https://workos.com/blog/how-to-design-multi-tenant-rbac-saas) — RBAC 最佳实践
- [Aserto Multi-tenant RBAC](https://www.aserto.com/use-cases/multi-tenant-saas-rbac) — 多租户角色作用域
- [FastAPI + Celery ML Inference](https://github.com/FerrariDG/async-ml-inference) — 异步推理架构参考
- [NVIDIA Triton + vLLM](https://docs.vllm.ai/en/stable/deployment/frameworks/triton) — 生产推理服务架构
- [vLLM vs Ollama](https://www.redhat.com/en/topics/ai/vllm-vs-ollama) — 推理框架选型对比
- [EMQX Smart Building](https://www.emqx.com/en/blog/global-edge-mqtt-building-management) — 分布式边缘 MQTT 架构

---

*设计完成 v2.0。文档约 19,000 字。确认后即开始 Phase 1 实现。*
