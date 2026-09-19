# 枢络 VelaMesh — REST API 设计文档

> **版本**: v1.0  
> **日期**: 2026-06-18  
> **状态**: 设计阶段（Phase 1），待 A6 前端确认后进入 Phase 2 后端实现  
> **作者**: A3-全栈开发  
> **项目**: [OPE-8](mention://issue/b397d8e3-fe8f-4858-9189-6528156738c3)

---

## 目录

1. [概述](#一概述)
2. [数据模型定义](#二数据模型定义)
3. [REST API 端点清单](#三rest-api-端点清单)
4. [JWT 认证流程](#四jwt-认证流程)
5. [RBAC/ABAC 权限矩阵](#五rbacabac-权限矩阵)
6. [WebSocket 事件格式](#六websocket-事件格式)
7. [分页/过滤/排序规范](#七分页过滤排序规范)
8. [MQTT 主题规范](#八mqtt-主题规范)

---

## 一、概述

### 1.1 基础地址

```
开发环境: http://localhost:8000
Base Path: /api/v1
```

### 1.2 通用约定

| 项目 | 规范 |
|------|------|
| 编码 | UTF-8 |
| 请求体 | `application/json` |
| 响应体 | `application/json` |
| 认证方式 | `Authorization: Bearer <JWT>` |
| 时间格式 | ISO 8601 (`2026-06-18T10:30:00Z`) |
| 分页默认 | page=1, page_size=20 |
| 最大 page_size | 100 |

### 1.3 通用响应结构

**成功响应：**
```json
{
  "data": { ... },
  "message": "ok"
}
```

**分页响应：**
```json
{
  "data": [ ... ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 156,
    "total_pages": 8
  }
}
```

**错误响应：**
```json
{
  "detail": {
    "code": "VALIDATION_ERROR",
    "message": "具体错误描述",
    "errors": [
      { "field": "name", "message": "该字段是必填的" }
    ]
  }
}
```

### 1.4 HTTP 状态码使用规范

| 状态码 | 含义 | 使用场景 |
|--------|------|----------|
| 200 | OK | GET 请求成功、PUT/PATCH 更新成功 |
| 201 | Created | POST 创建资源成功 |
| 204 | No Content | DELETE 删除成功 |
| 400 | Bad Request | 请求参数校验失败 |
| 401 | Unauthorized | 未登录或 token 过期 |
| 403 | Forbidden | 已登录但权限不足 |
| 404 | Not Found | 资源不存在 |
| 409 | Conflict | 资源冲突（如重复的工号或设备ID） |
| 422 | Unprocessable Entity | 请求体 JSON 格式错误或语义错误 |
| 429 | Too Many Requests | 频率限制 |
| 500 | Internal Server Error | 服务端内部错误 |

---

## 二、数据模型定义

### 2.1 Person（人员）

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| id | integer | 自动 | 主键 |
| tenant_id | integer | 自动 | 租户隔离 |
| name | string | ✅ | 姓名 |
| employee_id | string | — | 工号（租户内唯一） |
| department | string | — | 部门 |
| person_type | enum | — | 类型: `employee` / `visitor` / `vip` / `contractor` |
| phone | string | — | 手机号 |
| email | string | — | 邮箱 |
| ble_mac | string | — | BLE MAC 地址 |
| avatar_url | string | — | 头像 URL |
| access_level | integer | — | 通行级别: 1-普通, 2-敏感区, 3-全区域 |
| is_active | boolean | — | 是否启用（默认 true） |
| valid_from | datetime | — | 有效期起始（访客） |
| valid_until | datetime | — | 有效期截止（访客） |
| created_at | datetime | 自动 | 创建时间 |
| updated_at | datetime | 自动 | 更新时间 |

### 2.2 Visitor（访客）

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| id | integer | 自动 | 主键 |
| tenant_id | integer | 自动 | 租户隔离 |
| name | string | ✅ | 访客姓名 |
| phone | string | ✅ | 手机号 |
| id_card | string | — | 身份证号（可选） |
| host_person_id | integer | ✅ | 受访人（Person.id） |
| purpose | string | ✅ | 来访事由 |
| expected_at | datetime | ✅ | 预约来访时间 |
| valid_from | datetime | ✅ | 授权有效期起始 |
| valid_until | datetime | ✅ | 授权有效期截止 |
| status | enum | — | 状态: `pending` / `approved` / `denied` / `checked_in` / `checked_out` / `expired` |
| approved_by | integer | — | 审批人（User.id） |
| approved_at | datetime | — | 审批时间 |
| checked_in_at | datetime | — | 签到时间 |
| checked_out_at | datetime | — | 签退时间 |
| denied_reason | string | — | 拒绝原因 |
| created_at | datetime | 自动 | 创建时间 |
| updated_at | datetime | 自动 | 更新时间 |

### 2.3 Device（设备/ESP32节点）

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| id | integer | 自动 | 主键 |
| tenant_id | integer | 自动 | 租户隔离 |
| node_id | string | ✅ | 节点 ID（租户内唯一） |
| name | string | — | 设备名称 |
| location | string | — | 安装位置描述 |
| device_type | enum | — | 类型: `camera` / `door_lock` / `sensor` / `beacon` |
| board_model | string | — | 板型: `XIAO_ESP32S3_SENSE` |
| firmware_ver | string | — | 固件版本 |
| ip_address | string | — | IP 地址 |
| is_online | boolean | — | 是否在线（自动检测） |
| last_seen | datetime | — | 最后心跳时间 |
| config_json | json | — | 设备级配置（JSON 对象） |
| created_at | datetime | 自动 | 创建时间 |

### 2.4 Space（区域/会议室）

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| id | integer | 自动 | 主键 |
| tenant_id | integer | 自动 | 租户隔离 |
| name | string | ✅ | 空间名称 |
| code | string | — | 空间代码（唯一） |
| type | enum | ✅ | 类型: `area` / `room` / `floor` / `entrance` / `elevator` |
| parent_id | integer | — | 父空间 ID（层级结构） |
| floor | string | — | 楼层 |
| capacity | integer | — | 容量（会议室） |
| device_ids | json | — | 关联设备 ID 列表 |
| access_level | integer | — | 所需通行级别 |
| settings_json | json | — | 空间配置（灯光联动规则等） |
| is_active | boolean | — | 是否启用 |
| created_at | datetime | 自动 | 创建时间 |
| updated_at | datetime | 自动 | 更新时间 |

### 2.5 Event（识别事件）

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| id | integer | 自动 | 主键 |
| tenant_id | integer | 自动 | 租户隔离 |
| person_id | integer | — | 关联人员（未识别则为 null） |
| person_name | string | — | 识别到的人员姓名（冗余，方便查询） |
| device_id | integer | — | 关联设备 |
| node_id | string | — | 来源节点 ID |
| face_conf | float | — | 人脸置信度 (0.0~1.0) |
| gait_conf | float | — | 步态置信度 (0.0~1.0) |
| ble_conf | float | — | BLE 置信度 (0.0~1.0) |
| fusion_conf | float | — | 融合置信度 (0.0~1.0) |
| modality_count | integer | — | 参与融合的模态数量 (1~3) |
| light_level | float | — | 环境光照 |
| decision | enum | — | 决策结果: `granted` / `denied` / `unknown` |
| explain_text | text | — | 决策解释文本 |
| raw_data_json | json | — | 原始数据快照 |
| is_alert | boolean | — | 是否触发告警 |
| created_at | datetime | 自动 | 事件发生时间 |

### 2.6 Rule（策略规则）

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| id | integer | 自动 | 主键 |
| tenant_id | integer | 自动 | 租户隔离 |
| name | string | ✅ | 规则名称 |
| description | text | — | 规则描述 |
| trigger_type | enum | ✅ | 触发类型: `recognition` / `device_offline` / `schedule` / `alert` |
| trigger_config | json | ✅ | 触发条件配置 |
| condition_expr | string | — | 条件表达式（可选） |
| action_type | enum | ✅ | 动作类型: `mqtt_publish` / `create_alert` / `webhook` / `energy_control` |
| action_config | json | ✅ | 动作参数配置 |
| priority | integer | — | 优先级: 1-高, 2-中, 3-低 |
| is_enabled | boolean | — | 是否启用（默认 true） |
| created_at | datetime | 自动 | 创建时间 |
| updated_at | datetime | 自动 | 更新时间 |

### 2.7 EnergyLog（能耗日志）

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| id | integer | 自动 | 主键 |
| tenant_id | integer | 自动 | 租户隔离 |
| device_id | integer | — | 关联设备 |
| space_id | integer | — | 关联空间 |
| metric | enum | ✅ | 指标类型: `power` / `energy` / `current` / `voltage` |
| value | float | ✅ | 数值 |
| unit | string | — | 单位: `W` / `kWh` / `A` / `V` |
| source | enum | — | 数据来源: `device` / `rule` / `manual` |
| recorded_at | datetime | ✅ | 记录时间 |

### 2.8 辅助模型

#### Face（人脸注册）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| person_id | integer | 关联人员 |
| embedding | blob | 128-d float32 向量 |
| image_url | string | 原始图片路径 |
| quality_score | float | 质量评分 |
| created_at | datetime | 创建时间 |

#### AuditLog（审计日志）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| tenant_id | integer | 租户隔离 |
| user_id | integer | 操作用户 |
| action | string | 操作动作（如 `person.create`） |
| resource_type | string | 资源类型 |
| resource_id | string | 资源 ID |
| detail_json | json | 操作详情 |
| ip_address | string | 客户端 IP |
| created_at | datetime | 操作时间 |

#### User（登录用户 - RBAC）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| tenant_id | integer | 租户隔离 |
| username | string | 用户名（租户内唯一） |
| password_hash | string | bcrypt 密码哈希 |
| display_name | string | 显示名称 |
| email | string | 邮箱 |
| is_active | boolean | 是否启用 |
| is_superadmin | boolean | 是否跨租户超级管理员 |
| last_login | datetime | 最后登录时间 |
| created_at | datetime | 创建时间 |

#### Role（角色）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| tenant_id | integer | 租户隔离 |
| name | string | 角色名（租户内唯一） |
| description | string | 描述 |
| is_system | boolean | 是否系统内置（不可删除） |

#### Permission（权限）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| code | string | 权限代码（全局唯一） |
| name | string | 权限名称 |
| resource | string | 所属资源 |
| action | string | 动作（create/read/update/delete/manage） |
| description | string | 描述 |

---

## 三、REST API 端点清单

### 3.1 认证 `/api/v1/auth`

#### POST `/api/v1/auth/login` — 用户登录

**请求体：**
```json
{
  "username": "admin",
  "password": "admin123",
  "tenant_code": "default"
}
```

**成功响应 (200)：**
```json
{
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 3600,
    "user": {
      "id": 1,
      "username": "admin",
      "display_name": "超级管理员",
      "roles": ["超级管理员"],
      "permissions": ["person:read", "person:write", "device:read", ...],
      "tenant_id": 1,
      "tenant_code": "default"
    }
  }
}
```

**错误响应：**
| 状态码 | 场景 |
|--------|------|
| 401 | 用户名或密码错误 |
| 403 | 账户已禁用 |

---

#### POST `/api/v1/auth/refresh` — 刷新 Token

**请求体：**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**成功响应 (200)：**
```json
{
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 3600
  }
}
```

**错误响应：**
| 状态码 | 场景 |
|--------|------|
| 401 | refresh_token 无效或已过期 |

---

#### GET `/api/v1/auth/me` — 获取当前用户信息

**请求头：** `Authorization: Bearer <token>`

**成功响应 (200)：**
```json
{
  "data": {
    "id": 1,
    "username": "admin",
    "display_name": "超级管理员",
    "email": "admin@example.com",
    "roles": ["超级管理员"],
    "permissions": ["person:read", "person:write", ...],
    "tenant_id": 1,
    "tenant_code": "default",
    "is_superadmin": true
  }
}
```

| 状态码 | 场景 |
|--------|------|
| 401 | Token 无效或已过期 |

---

### 3.2 人员管理 `/api/v1/persons`

#### GET `/api/v1/persons` — 人员列表

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| page | integer | 页码（默认 1） |
| page_size | integer | 每页条数（默认 20，最大 100） |
| search | string | 全局搜索（姓名/工号/手机号） |
| person_type | string | 人员类型过滤：`employee` / `visitor` / `vip` / `contractor` |
| department | string | 部门过滤 |
| is_active | boolean | 启用状态过滤 |
| sort_by | string | 排序字段（默认 `created_at`） |
| sort_order | string | 排序方向：`asc` / `desc`（默认 `desc`） |

**成功响应 (200)：**
```json
{
  "data": [
    {
      "id": 1,
      "name": "张三",
      "employee_id": "EMP001",
      "department": "研发部",
      "person_type": "employee",
      "phone": "13800138001",
      "email": "zhangsan@example.com",
      "access_level": 3,
      "is_active": true,
      "face_count": 2,
      "created_at": "2026-06-15T08:00:00Z",
      "updated_at": "2026-06-17T10:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 156,
    "total_pages": 8
  }
}
```

| 状态码 | 场景 |
|--------|------|
| 401 | 未认证 |
| 403 | 缺少 `person:read` 权限 |

---

#### POST `/api/v1/persons` — 新增人员

**请求体：**
```json
{
  "name": "李四",
  "employee_id": "EMP002",
  "department": "安保部",
  "person_type": "employee",
  "phone": "13800138002",
  "email": "lisi@example.com",
  "ble_mac": "AA:BB:CC:DD:EE:01",
  "access_level": 2,
  "is_active": true,
  "valid_from": null,
  "valid_until": null
}
```

**成功响应 (201)：**
```json
{
  "data": {
    "id": 2,
    "name": "李四",
    "employee_id": "EMP002",
    "department": "安保部",
    "person_type": "employee",
    "phone": "13800138002",
    "email": "lisi@example.com",
    "ble_mac": "AA:BB:CC:DD:EE:01",
    "access_level": 2,
    "is_active": true,
    "created_at": "2026-06-18T10:00:00Z"
  }
}
```

| 状态码 | 场景 |
|--------|------|
| 400 | 请求参数校验失败 |
| 401 | 未认证 |
| 403 | 缺少 `person:write` 权限 |
| 409 | 工号已存在 |

---

#### GET `/api/v1/persons/{id}` — 人员详情

**成功响应 (200)：**
```json
{
  "data": {
    "id": 1,
    "name": "张三",
    "employee_id": "EMP001",
    "department": "研发部",
    "person_type": "employee",
    "phone": "13800138001",
    "email": "zhangsan@example.com",
    "ble_mac": "AA:BB:CC:DD:EE:01",
    "access_level": 3,
    "avatar_url": "/static/avatars/1.jpg",
    "is_active": true,
    "valid_from": null,
    "valid_until": null,
    "face_count": 2,
    "faces": [
      { "id": 1, "quality_score": 0.92, "created_at": "..." },
      { "id": 2, "quality_score": 0.88, "created_at": "..." }
    ],
    "created_at": "2026-06-15T08:00:00Z",
    "updated_at": "2026-06-17T10:30:00Z"
  }
}
```

| 状态码 | 场景 |
|--------|------|
| 401 | 未认证 |
| 403 | 缺少 `person:read` 权限 |
| 404 | 人员不存在 |

---

#### PUT `/api/v1/persons/{id}` — 更新人员

**请求体：**（支持部分更新）
```json
{
  "name": "张三（更新后）",
  "department": "技术部",
  "phone": "13800138000"
}
```

**成功响应 (200)：** 返回更新后的完整人员对象。

| 状态码 | 场景 |
|--------|------|
| 400 | 参数校验失败 |
| 401 | 未认证 |
| 403 | 缺少 `person:write` 权限 |
| 404 | 人员不存在 |
| 409 | 工号被其他人员占用 |

---

#### DELETE `/api/v1/persons/{id}` — 删除人员

**成功响应 (204)：** 无返回体。

| 状态码 | 场景 |
|--------|------|
| 401 | 未认证 |
| 403 | 缺少 `person:write` 权限 |
| 404 | 人员不存在 |

---

#### POST `/api/v1/persons/{id}/faces` — 注册人脸

**请求体（multipart/form-data）：**
| 参数 | 类型 | 说明 |
|------|------|------|
| image | file | 人脸图片文件（JPEG/PNG） |
| label | string | 可选标注 |

**成功响应 (201)：**
```json
{
  "data": {
    "id": 3,
    "person_id": 1,
    "quality_score": 0.95,
    "image_url": "/data/faces/1_3.jpg",
    "embedding_length": 128,
    "created_at": "2026-06-18T10:05:00Z"
  }
}
```

| 状态码 | 场景 |
|--------|------|
| 400 | 图片中未检测到人脸 |
| 401 | 未认证 |
| 403 | 缺少 `person:write` 权限 |
| 404 | 人员不存在 |

---

#### GET `/api/v1/persons/{id}/faces` — 获取人脸列表

**成功响应 (200)：**
```json
{
  "data": [
    {
      "id": 1,
      "quality_score": 0.92,
      "image_url": "/data/faces/1_1.jpg",
      "created_at": "2026-06-15T09:00:00Z"
    }
  ]
}
```

---

#### DELETE `/api/v1/persons/{id}/faces/{face_id}` — 删除人脸

**成功响应 (204)：** 无返回体。

---

### 3.3 访客管理 `/api/v1/visitors`

#### GET `/api/v1/visitors` — 访客预约列表

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| page | integer | 页码 |
| page_size | integer | 每页条数 |
| status | string | 状态过滤：`pending` / `approved` / `denied` / `checked_in` / `checked_out` / `expired` |
| search | string | 搜索访客姓名/手机号 |
| date_from | string | 预约日期范围起始 |
| date_to | string | 预约日期范围截止 |
| sort_by | string | 排序字段（默认 `expected_at`） |
| sort_order | string | 排序方向 |

**成功响应 (200)：** 分页返回访客列表。

| 状态码 | 场景 |
|--------|------|
| 401 | 未认证 |
| 403 | 缺少 `visitor:read` 权限 |

---

#### POST `/api/v1/visitors` — 创建访客预约

**请求体：**
```json
{
  "name": "王五",
  "phone": "13900139001",
  "id_card": "110101199001011234",
  "host_person_id": 1,
  "purpose": "商务洽谈",
  "expected_at": "2026-06-20T14:00:00Z",
  "valid_from": "2026-06-20T14:00:00Z",
  "valid_until": "2026-06-20T17:00:00Z"
}
```

**成功响应 (201)：** 返回创建的访客对象（状态为 `pending`）。

| 状态码 | 场景 |
|--------|------|
| 400 | 参数校验失败（如受访人不存在） |
| 401 | 未认证 |
| 403 | 缺少 `visitor:write` 权限 |

---

#### GET `/api/v1/visitors/{id}` — 访客预约详情

**成功响应 (200)：** 返回完整访客信息。

---

#### PUT `/api/v1/visitors/{id}` — 更新访客预约

**请求体：** 支持部分更新。

**成功响应 (200)：** 返回更新后的访客对象。

---

#### DELETE `/api/v1/visitors/{id}` — 删除访客预约

**成功响应 (204)：** 仅可删除 `pending` 状态的预约。

---

#### POST `/api/v1/visitors/{id}/approve` — 审批通过

**请求体：**
```json
{
  "approved_by": 1
}
```

**成功响应 (200)：** 状态变更为 `approved`。

| 状态码 | 场景 |
|--------|------|
| 400 | 非 `pending` 状态不可审批 |
| 403 | 缺少 `visitor:approve` 权限 |

---

#### POST `/api/v1/visitors/{id}/deny` — 拒绝预约

**请求体：**
```json
{
  "reason": "受访人当天不在"
}
```

**成功响应 (200)：** 状态变更为 `denied`。

---

#### POST `/api/v1/visitors/{id}/check-in` — 访客签到

**成功响应 (200)：** 状态变更为 `checked_in`。

---

#### POST `/api/v1/visitors/{id}/check-out` — 访客签退

**成功响应 (200)：** 状态变更为 `checked_out`。

---

### 3.4 设备管理 `/api/v1/devices`

#### GET `/api/v1/devices` — 设备列表

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| page | integer | 页码 |
| page_size | integer | 每页条数 |
| device_type | string | 设备类型过滤 |
| is_online | boolean | 在线状态过滤 |
| search | string | 搜索名称/位置/节点ID |
| sort_by | string | 排序字段（默认 `last_seen`） |
| sort_order | string | 排序方向 |

**成功响应 (200)：**
```json
{
  "data": [
    {
      "id": 1,
      "node_id": "door-01",
      "name": "大门门禁",
      "location": "一楼大厅入口",
      "device_type": "camera",
      "is_online": true,
      "last_seen": "2026-06-18T10:05:00Z",
      "firmware_ver": "v1.2.0",
      "ip_address": "192.168.31.101"
    }
  ],
  "pagination": { ... }
}
```

| 状态码 | 场景 |
|--------|------|
| 401 | 未认证 |
| 403 | 缺少 `device:read` 权限 |

---

#### POST `/api/v1/devices` — 注册设备

**请求体：**
```json
{
  "node_id": "door-02",
  "name": "侧门门禁",
  "location": "一楼侧门",
  "device_type": "camera",
  "board_model": "XIAO_ESP32S3_SENSE",
  "config_json": {
    "face_threshold": 0.6,
    "led_brightness": 80
  }
}
```

**成功响应 (201)：** 返回注册的设备对象。

| 状态码 | 场景 |
|--------|------|
| 400 | 参数校验失败 |
| 401 | 未认证 |
| 403 | 缺少 `device:write` 权限 |
| 409 | node_id 已存在 |

---

#### GET `/api/v1/devices/{id}` — 设备详情

**成功响应 (200)：** 返回设备完整信息，包括当前配置。

---

#### PUT `/api/v1/devices/{id}` — 更新设备

**请求体：** 支持部分更新。

**成功响应 (200)：** 返回更新后的设备。

---

#### DELETE `/api/v1/devices/{id}` — 删除设备

**成功响应 (204)：** 删除设备注册信息。

---

#### POST `/api/v1/devices/{id}/command` — 发送指令

**请求体：**
```json
{
  "command": "reboot",
  "params": {
    "delay_ms": 1000
  }
}
```

**可用指令：** `reboot` / `config_update` / `set_threshold` / `set_led`

**成功响应 (200)：**
```json
{
  "data": {
    "status": "sent",
    "request_id": "uuid-xxxx",
    "mqtt_topic": "vela/server/command/door-02"
  }
}
```

| 状态码 | 场景 |
|--------|------|
| 400 | 不支持的指令类型 |
| 404 | 设备不在线（指令仍然会发送） |

---

#### GET `/api/v1/devices/{id}/status/history` — 设备状态历史

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| start_time | string | 起始时间 |
| end_time | string | 结束时间 |
| limit | integer | 返回条数（默认 100） |

**成功响应 (200)：**
```json
{
  "data": [
    {
      "timestamp": "2026-06-18T10:05:00Z",
      "free_heap": 1234567,
      "free_psram": 4194304,
      "wifi_rssi": -45,
      "fps": 15.2,
      "temp": 42.5
    }
  ]
}
```

---

### 3.5 区域/空间管理 `/api/v1/spaces`

#### GET `/api/v1/spaces` — 空间列表

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| type | string | 类型过滤：`area` / `room` / `floor` / `entrance` / `elevator` |
| floor | string | 楼层过滤 |
| parent_id | integer | 父空间过滤 |

**成功响应 (200)：**
```json
{
  "data": [
    {
      "id": 1,
      "name": "A栋一楼大厅",
      "type": "area",
      "floor": "1F",
      "parent_id": null,
      "children": [
        {
          "id": 2,
          "name": "大门入口",
          "type": "entrance",
          "floor": "1F",
          "parent_id": 1,
          "access_level": 1
        },
        {
          "id": 3,
          "name": "101会议室",
          "type": "room",
          "floor": "1F",
          "parent_id": 1,
          "capacity": 10,
          "access_level": 2
        }
      ]
    }
  ]
}
```

| 状态码 | 场景 |
|--------|------|
| 401 | 未认证 |
| 403 | 缺少 `space:read` 权限 |

---

#### POST `/api/v1/spaces` — 创建空间

**请求体：**
```json
{
  "name": "102会议室",
  "code": "RM-102",
  "type": "room",
  "parent_id": 1,
  "floor": "1F",
  "capacity": 20,
  "access_level": 1,
  "settings_json": {
    "auto_light": true,
    "auto_ac": true
  }
}
```

**成功响应 (201)：** 返回创建的空间对象。

| 状态码 | 场景 |
|--------|------|
| 409 | space code 已存在 |

---

#### GET `/api/v1/spaces/{id}` — 空间详情

---

#### PUT `/api/v1/spaces/{id}` — 更新空间

---

#### DELETE `/api/v1/spaces/{id}` — 删除空间

**成功响应 (204)：** 有子空间时不允许删除。

---

### 3.6 识别事件 `/api/v1/events`

#### GET `/api/v1/events` — 事件列表

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| page | integer | 页码 |
| page_size | integer | 每页条数 |
| person_id | integer | 人员 ID 过滤 |
| node_id | string | 节点 ID 过滤 |
| decision | string | 决策结果过滤：`granted` / `denied` / `unknown` |
| date_from | string | 时间范围起始 |
| date_to | string | 时间范围截止 |
| min_confidence | float | 最低融合置信度 |
| sort_by | string | 排序字段（默认 `created_at`） |
| sort_order | string | 排序方向 |

**成功响应 (200)：**
```json
{
  "data": [
    {
      "id": 1001,
      "person_id": 1,
      "person_name": "张三",
      "node_id": "door-01",
      "device_name": "大门门禁",
      "face_conf": 0.85,
      "gait_conf": 0.0,
      "ble_conf": 0.0,
      "fusion_conf": 0.85,
      "modality_count": 1,
      "decision": "granted",
      "explain_text": "人脸匹配张三（置信度 0.85），单一模态已达阈值",
      "is_alert": false,
      "created_at": "2026-06-18T09:30:00Z"
    }
  ],
  "pagination": { ... }
}
```

| 状态码 | 场景 |
|--------|------|
| 401 | 未认证 |
| 403 | 缺少 `event:read` 权限 |

---

#### GET `/api/v1/events/stats` — 事件统计概览

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| date_from | string | 统计起始时间 |
| date_to | string | 统计结束时间 |

**成功响应 (200)：**
```json
{
  "data": {
    "total_events": 1250,
    "granted_count": 1180,
    "denied_count": 45,
    "unknown_count": 25,
    "grant_rate": 0.944,
    "by_modality": {
      "face_only": 850,
      "multi_modal": 400
    },
    "by_hour": {
      "08": 120,
      "09": 245,
      "10": 180
    },
    "top_persons": [
      { "person_id": 1, "person_name": "张三", "count": 85 },
      { "person_id": 2, "person_name": "李四", "count": 72 }
    ]
  }
}
```

---

#### GET `/api/v1/events/recent` — 最近事件

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| limit | integer | 返回条数（默认 20，最大 50） |

**成功响应 (200)：** 返回时间倒序的最新事件列表（不分页）。

---

### 3.7 审计日志 `/api/v1/audit`

#### GET `/api/v1/audit` — 审计日志列表

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| page | integer | 页码 |
| page_size | integer | 每页条数 |
| user_id | integer | 操作用户 |
| action | string | 操作类型 |
| resource_type | string | 资源类型 |
| date_from | string | 时间范围起始 |
| date_to | string | 时间范围截止 |
| sort_by | string | 排序字段（默认 `created_at`） |
| sort_order | string | 排序方向 |

**成功响应 (200)：**
```json
{
  "data": [
    {
      "id": 1,
      "user_id": 1,
      "username": "admin",
      "action": "person.create",
      "resource_type": "person",
      "resource_id": "2",
      "detail_json": {
        "person_name": "李四",
        "department": "安保部"
      },
      "ip_address": "192.168.1.100",
      "created_at": "2026-06-18T10:00:00Z"
    }
  ],
  "pagination": { ... }
}
```

| 状态码 | 场景 |
|--------|------|
| 401 | 未认证 |
| 403 | 缺少 `audit:read` 权限 |

---

### 3.8 策略规则 `/api/v1/rules`

#### GET `/api/v1/rules` — 规则列表

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| trigger_type | string | 触发类型过滤 |
| is_enabled | boolean | 启用状态过滤 |

**成功响应 (200)：**
```json
{
  "data": [
    {
      "id": 1,
      "name": "非工作时间敏感区告警",
      "description": "20:00~08:00 期间检测到财务部有通行记录时触发告警",
      "trigger_type": "recognition",
      "trigger_config": {
        "time_range": ["20:00", "08:00"],
        "spaces": [5]
      },
      "action_type": "create_alert",
      "action_config": {
        "level": "critical",
        "title_template": "非工作时间敏感区域通行"
      },
      "priority": 1,
      "is_enabled": true,
      "created_at": "2026-06-15T10:00:00Z"
    }
  ]
}
```

| 状态码 | 场景 |
|--------|------|
| 401 | 未认证 |
| 403 | 缺少 `rule:read` 权限 |

---

#### POST `/api/v1/rules` — 创建规则

**请求体：**
```json
{
  "name": "会议室无人关灯",
  "description": "检测到会议室无人时，发送 MQTT 指令关闭灯光",
  "trigger_type": "recognition",
  "trigger_config": {
    "space_ids": [3, 4],
    "decision": "denied",
    "timeout_seconds": 600
  },
  "condition_expr": "",
  "action_type": "mqtt_publish",
  "action_config": {
    "topic": "vela/server/command/light-ctrl",
    "payload": {"cmd": "off", "space_id": "{space_id}"}
  },
  "priority": 2,
  "is_enabled": true
}
```

**成功响应 (201)：** 返回创建的规则对象。

---

#### PUT `/api/v1/rules/{id}` — 更新规则

---

#### DELETE `/api/v1/rules/{id}` — 删除规则

**成功响应 (204)：** 系统内置规则不可删除。

---

#### PUT `/api/v1/rules/{id}/toggle` — 启用/禁用规则

**请求体：**
```json
{
  "is_enabled": false
}
```

**成功响应 (200)：** 返回更新后的规则。

---

### 3.9 能耗数据 `/api/v1/energy`

#### GET `/api/v1/energy` — 能耗数据查询

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| page | integer | 页码 |
| page_size | integer | 每页条数 |
| device_id | integer | 设备过滤 |
| space_id | integer | 空间过滤 |
| metric | string | 指标类型：`power` / `energy` / `current` / `voltage` |
| date_from | string | 时间范围起始 |
| date_to | string | 时间范围截止 |
| sort_by | string | 排序字段（默认 `recorded_at`） |
| sort_order | string | 排序方向 |

**成功响应 (200)：**
```json
{
  "data": [
    {
      "id": 1,
      "device_id": 1,
      "device_name": "大门门禁",
      "space_id": 1,
      "metric": "power",
      "value": 12.5,
      "unit": "W",
      "source": "device",
      "recorded_at": "2026-06-18T10:00:00Z"
    }
  ],
  "pagination": { ... }
}
```

---

#### GET `/api/v1/energy/summary` — 能耗汇总

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| space_id | integer | 空间过滤 |
| date_from | string | 起始时间 |
| date_to | string | 结束时间 |
| granularity | string | 聚合粒度：`hourly` / `daily` / `weekly` |

**成功响应 (200)：**
```json
{
  "data": {
    "total_kwh": 45.2,
    "avg_power_w": 188.3,
    "peak_power_w": 350.0,
    "by_space": [
      { "space_id": 1, "space_name": "A栋1F", "kwh": 25.0 },
      { "space_id": 3, "space_name": "101会议室", "kwh": 20.2 }
    ],
    "timeline": [
      { "period": "2026-06-18T08:00", "kwh": 2.1 },
      { "period": "2026-06-18T09:00", "kwh": 2.8 }
    ]
  }
}
```

---

### 3.10 用户与角色管理 `/api/v1/users` / `/api/v1/roles`

#### GET `/api/v1/users` — 用户列表

| 状态码 | 场景 |
|--------|------|
| 403 | 需要 `tenant:admin` 权限 |

#### POST `/api/v1/users` — 创建用户

**请求体：**
```json
{
  "username": "guard_zhang",
  "password": "securepass123",
  "display_name": "张保安",
  "email": "guard@example.com",
  "role_ids": [2]
}
```

**成功响应 (201)。**

---

#### PUT `/api/v1/users/{id}` — 更新用户

---

#### DELETE `/api/v1/users/{id}` — 删除用户

---

#### GET `/api/v1/roles` — 角色列表

---

#### POST `/api/v1/roles` — 创建角色

**请求体：**
```json
{
  "name": "访客接待",
  "description": "前台人员，可管理访客预约",
  "permission_ids": [1, 10, 12, 13]
}
```

---

#### PUT `/api/v1/roles/{id}` — 更新角色

---

#### DELETE `/api/v1/roles/{id}` — 删除角色

**成功响应 (204)：** 系统内置角色不可删除。

---

#### GET `/api/v1/permissions` — 权限列表（只读）

**成功响应 (200)：**
```json
{
  "data": [
    { "id": 1, "code": "person:read", "name": "查看人员", "resource": "person", "action": "read" },
    { "id": 2, "code": "person:write", "name": "管理人员", "resource": "person", "action": "manage" }
  ]
}
```

---

### 3.11 实时数据

#### GET `/api/v1/realtime/overview` — 首页概览

**成功响应 (200)：**
```json
{
  "data": {
    "online_devices": 3,
    "offline_devices": 0,
    "total_persons": 156,
    "today_events": 245,
    "today_granted": 230,
    "today_alerts": 3,
    "recent_events": [ ... ],
    "recent_alerts": [ ... ],
    "energy_today_kwh": 12.5
  }
}
```

---

### 3.12 WebSocket — 实时推送

详见 [第六节 - WebSocket 事件格式](#六websocket-事件格式)

---

## 四、JWT 认证流程

### 4.1 完整流程

```
┌─────────┐          ┌──────────────┐          ┌──────────────┐
│ 客户端   │          │  FastAPI     │          │  SQLite DB   │
│ (前端)   │          │  服务端       │          │              │
└────┬─────┘          └──────┬───────┘          └──────┬───────┘
     │                       │                         │
     │  POST /auth/login     │                         │
     │  {username,password}  │                         │
     ├──────────────────────→│                         │
     │                       │  SELECT user WHERE      │
     │                       │  username=?             │
     │                       ├────────────────────────→│
     │                       │←────────────────────────┤
     │                       │                         │
     │                       │  bcrypt.verify()        │
     │                       │                         │
     │                       │  SELECT roles + perms   │
     │                       ├────────────────────────→│
     │                       │←────────────────────────┤
     │                       │                         │
     │                       │  Generate JWT:          │
     │                       │  sub=user_id            │
     │                       │  tenant_id=1            │
     │                       │  roles=[...]            │
     │                       │  permissions=[...]      │
     │                       │  exp=now+3600           │
     │                       │                         │
     │  200 {access_token,   │                         │
     │       refresh_token,  │                         │
     │       user}           │                         │
     │←──────────────────────┤                         │
     │                       │                         │
     │  ─── 后续请求 ──────  │                         │
     │                       │                         │
     │  GET /api/v1/...      │                         │
     │  Authorization:       │                         │
     │  Bearer <token>       │                         │
     ├──────────────────────→│                         │
     │                       │  JWT 中间件:             │
     │                       │  1. 解码 token          │
     │                       │  2. 验证签名 + 过期      │
     │                       │  3. 注入 request.user   │
     │                       │  4. RBAC 权限检查       │
     │                       │                         │
     │  200 {data}           │                         │
     │←──────────────────────┤                         │
```

### 4.2 JWT Payload 结构

```json
{
  "sub": "1",
  "tenant_id": 1,
  "tenant_code": "default",
  "username": "admin",
  "display_name": "超级管理员",
  "roles": ["超级管理员"],
  "permissions": ["person:read", "person:write", "device:read", ...],
  "is_superadmin": false,
  "iat": 1718611200,
  "exp": 1718614800
}
```

### 4.3 关键参数

| 参数 | 值 | 说明 |
|------|:---:|------|
| 签名算法 | HS256 | HMAC + SHA-256 |
| Access Token 有效期 | 3600s (1h) | 短时效，减少泄露风险 |
| Refresh Token 有效期 | 604800s (7d) | 用于静默续期 |
| 密钥 | 环境变量 `JWT_SECRET` | 生产环境需 32+ 字节随机串 |

### 4.4 Token 刷新机制

1. Access Token 过期后，客户端使用 Refresh Token 调用 `POST /api/v1/auth/refresh`
2. 服务端验证 Refresh Token 有效 → 签发新的 Access Token
3. Refresh Token 过期后，用户需重新登录
4. 前端应在 token 过期前（如剩余 5 分钟）主动刷新

### 4.5 安全性设计

| 防护措施 | 实现方式 |
|----------|----------|
| 密码存储 | bcrypt (12 rounds) |
| Token 签名 | HS256 + 环境变量密钥 |
| Token 过期 | 1h 自动过期，无手动吊销（演示阶段） |
| 传输安全 | HTTP（开发）/ HTTPS（生产） |
| 频率限制 | 登录端点 5次/分钟/IP |
| 租户隔离 | Token 内嵌 tenant_id，所有查询自动过滤 |

---

## 五、RBAC/ABAC 权限矩阵

### 5.1 预置角色

| 角色 | 说明 | 适用人员 |
|------|------|----------|
| `admin` | 超级管理员，拥有系统全部权限 | IT 管理员 |
| `hr` | 人事管理员，负责人事信息和人员管理 | HR 人员 |
| `it` | IT 运维，负责设备和系统配置 | 运维工程师 |
| `security` | 安保人员，可查看监控/识别记录/告警 | 安保主管/保安 |
| `reception` | 前台接待，负责访客管理 | 前台人员 |
| `employee` | 普通员工，仅可查看大屏和个人信息 | 全体员工 |

### 5.2 权限代码定义

| 权限代码 | 资源 | 动作 | 说明 |
|----------|------|:----:|------|
| `person:read` | person | read | 查看人员列表和详情 |
| `person:write` | person | manage | 增删改人员及人脸注册 |
| `visitor:read` | visitor | read | 查看访客预约 |
| `visitor:write` | visitor | manage | 创建/更新访客预约 |
| `visitor:approve` | visitor | approve | 审批访客预约 |
| `device:read` | device | read | 查看设备列表和状态 |
| `device:write` | device | manage | 注册/删除/控制设备 |
| `space:read` | space | read | 查看空间/区域定义 |
| `space:write` | space | manage | 管理空间配置 |
| `event:read` | event | read | 查看识别事件日志 |
| `audit:read` | audit | read | 查看审计日志 |
| `rule:read` | rule | read | 查看策略规则 |
| `rule:write` | rule | manage | 增删改策略规则 |
| `energy:read` | energy | read | 查看能耗数据 |
| `tenant:admin` | tenant | manage | 租户级管理（用户/角色） |
| `dashboard:view` | dashboard | read | 查看实时大屏 |
| `system:admin` | system | super | 跨租户超级管理（仅超级管理员） |

### 5.3 权限矩阵（角色 × 权限）

| 权限 | admin | hr | it | security | reception | employee |
|------|:-----:|:--:|:--:|:--------:|:---------:|:--------:|
| `person:read` | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ |
| `person:write` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `visitor:read` | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ |
| `visitor:write` | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `visitor:approve` | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| `device:read` | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| `device:write` | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| `space:read` | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| `space:write` | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| `event:read` | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| `audit:read` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `rule:read` | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| `rule:write` | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| `energy:read` | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| `tenant:admin` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `dashboard:view` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `system:admin` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

### 5.4 端点权限映射表

| 模块 | 端点 | 所需权限 |
|------|------|:--------:|
| **Auth** | `POST /api/v1/auth/login` | ❌ 无需认证 |
| | `POST /api/v1/auth/refresh` | ❌ 无需认证（需 refresh_token） |
| | `GET /api/v1/auth/me` | ✅ 登录即可 |
| **Persons** | `GET /api/v1/persons` | `person:read` |
| | `POST /api/v1/persons` | `person:write` |
| | `GET /api/v1/persons/{id}` | `person:read` |
| | `PUT /api/v1/persons/{id}` | `person:write` |
| | `DELETE /api/v1/persons/{id}` | `person:write` |
| | `POST /api/v1/persons/{id}/faces` | `person:write` |
| | `GET /api/v1/persons/{id}/faces` | `person:read` |
| | `DELETE /api/v1/persons/{id}/faces/{face_id}` | `person:write` |
| **Visitors** | `GET /api/v1/visitors` | `visitor:read` |
| | `POST /api/v1/visitors` | `visitor:write` |
| | `GET /api/v1/visitors/{id}` | `visitor:read` |
| | `PUT /api/v1/visitors/{id}` | `visitor:write` |
| | `DELETE /api/v1/visitors/{id}` | `visitor:write` |
| | `POST /api/v1/visitors/{id}/approve` | `visitor:approve` |
| | `POST /api/v1/visitors/{id}/deny` | `visitor:approve` |
| | `POST /api/v1/visitors/{id}/check-in` | `visitor:write` |
| | `POST /api/v1/visitors/{id}/check-out` | `visitor:write` |
| **Devices** | `GET /api/v1/devices` | `device:read` |
| | `POST /api/v1/devices` | `device:write` |
| | `GET /api/v1/devices/{id}` | `device:read` |
| | `PUT /api/v1/devices/{id}` | `device:write` |
| | `DELETE /api/v1/devices/{id}` | `device:write` |
| | `POST /api/v1/devices/{id}/command` | `device:write` |
| | `GET /api/v1/devices/{id}/status/history` | `device:read` |
| **Spaces** | `GET /api/v1/spaces` | `space:read` |
| | `POST /api/v1/spaces` | `space:write` |
| | `GET /api/v1/spaces/{id}` | `space:read` |
| | `PUT /api/v1/spaces/{id}` | `space:write` |
| | `DELETE /api/v1/spaces/{id}` | `space:write` |
| **Events** | `GET /api/v1/events` | `event:read` |
| | `GET /api/v1/events/stats` | `event:read` |
| | `GET /api/v1/events/recent` | `event:read` |
| **Audit** | `GET /api/v1/audit` | `audit:read` |
| **Rules** | `GET /api/v1/rules` | `rule:read` |
| | `POST /api/v1/rules` | `rule:write` |
| | `PUT /api/v1/rules/{id}` | `rule:write` |
| | `DELETE /api/v1/rules/{id}` | `rule:write` |
| | `PUT /api/v1/rules/{id}/toggle` | `rule:write` |
| **Energy** | `GET /api/v1/energy` | `energy:read` |
| | `GET /api/v1/energy/summary` | `energy:read` |
| **Users** | `GET /api/v1/users` | `tenant:admin` |
| | `POST /api/v1/users` | `tenant:admin` |
| | `PUT /api/v1/users/{id}` | `tenant:admin` |
| | `DELETE /api/v1/users/{id}` | `tenant:admin` |
| **Roles** | `GET /api/v1/roles` | `tenant:admin` |
| | `POST /api/v1/roles` | `tenant:admin` |
| | `PUT /api/v1/roles/{id}` | `tenant:admin` |
| | `DELETE /api/v1/roles/{id}` | `tenant:admin` |
| **Permissions** | `GET /api/v1/permissions` | 登录即可 |
| **Realtime** | `GET /api/v1/realtime/overview` | `dashboard:view` |
| | `WS /ws/events` | `dashboard:view` |

### 5.5 ABAC 属性检查扩展

在 RBAC 基础上，ABAC 增加以下属性维度检查（后续可逐步实现）：

| 属性维度 | 说明 | 检查方式 |
|----------|------|----------|
| **时间** | 非工作时间（20:00~08:00）部分操作受限 | `request.time` 与规则配置对比 |
| **空间** | 仅允许操作本空间及其下级空间 | `resource.space_id` 与用户授权空间范围对比 |
| **人员** | 普通员工仅可查看本人相关记录 | `resource.person_id == request.user.person_id` |
| **设备** | 仅允许查看本租户注册的设备 | 自动通过 `tenant_id` 隔离 |

**ABAC 检查伪代码：**
```python
async def abac_check(user: User, resource: str, resource_id: int, action: str) -> bool:
    # 1. RBAC 基础检查（是否有该权限）
    if not rbac_check(user, f"{resource}:{action}"):
        return False
    # 2. 超级管理员跳过 ABAC
    if user.is_superadmin:
        return True
    # 3. 租户隔离（自动）
    if not tenant_isolation_check(user, resource, resource_id):
        return False
    # 4. 时间约束
    if time_restriction_check(resource, action):
        return False
    # 5. 空间范围
    if not spatial_scope_check(user, resource, resource_id):
        return False
    return True
```

---

## 六、WebSocket 事件格式

### 6.1 连接

**端点：** `ws://localhost:8000/ws/events?token=<JWT>`

**连接流程：**
1. 客户端通过 URL 参数传递 JWT token
2. 服务端验证 token 有效性
3. 验证通过 → 建立 WebSocket 连接
4. 验证失败 → 返回 401 并关闭连接

### 6.2 通用消息格式

```json
{
  "type": "recognition",
  "data": { ... },
  "ts": 1718611200.123
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 事件类型标识 |
| `data` | object | 事件数据体 |
| `ts` | float | 服务端时间戳（Unix 秒.毫秒） |

### 6.3 事件类型及数据体

#### `recognition` — 身份识别完成

```json
{
  "type": "recognition",
  "data": {
    "id": 1001,
    "person_id": 1,
    "person_name": "张三",
    "person_type": "employee",
    "avatar_url": "/static/avatars/1.jpg",
    "node_id": "door-01",
    "device_name": "大门门禁",
    "face_conf": 0.85,
    "gait_conf": 0.0,
    "ble_conf": 0.0,
    "fusion_conf": 0.85,
    "modality_count": 1,
    "decision": "granted",
    "explain_text": "人脸匹配张三（置信度 0.85），单一模态已达阈值"
  },
  "ts": 1718611200.123
}
```

#### `device_status` — 设备状态更新（心跳）

```json
{
  "type": "device_status",
  "data": {
    "device_id": 1,
    "node_id": "door-01",
    "name": "大门门禁",
    "is_online": true,
    "free_heap": 1234567,
    "free_psram": 4194304,
    "wifi_rssi": -45,
    "fps": 15.2,
    "temp": 42.5,
    "uptime": 3600,
    "last_seen": "2026-06-18T10:05:00Z"
  },
  "ts": 1718611200.123
}
```

#### `device_offline` — 设备离线

```json
{
  "type": "device_offline",
  "data": {
    "device_id": 1,
    "node_id": "door-01",
    "name": "大门门禁",
    "last_seen": "2026-06-18T09:55:00Z",
    "offline_duration_sec": 600
  },
  "ts": 1718611200.123
}
```

#### `alert_new` — 新告警

```json
{
  "type": "alert_new",
  "data": {
    "alert_id": 5,
    "level": "critical",
    "type": "unauthorized_access",
    "title": "非工作时间敏感区域通行",
    "message": "2026-06-18 22:15:00 检测到财务部有通行记录",
    "related_event_id": 1005,
    "related_person_id": 3,
    "related_person_name": "赵六",
    "device_name": "财务部门禁",
    "created_at": "2026-06-18T22:15:00Z"
  },
  "ts": 1718611200.123
}
```

#### `alert_resolved` — 告警已处理

```json
{
  "type": "alert_resolved",
  "data": {
    "alert_id": 5,
    "resolved_by": "admin",
    "resolved_at": "2026-06-18T22:30:00Z"
  },
  "ts": 1718611200.123
}
```

#### `visitor_checkin` — 访客签到/签退

```json
{
  "type": "visitor_checkin",
  "data": {
    "visitor_id": 3,
    "name": "王五",
    "host_name": "张三",
    "status": "checked_in",
    "checked_in_at": "2026-06-18T14:05:00Z"
  },
  "ts": 1718611200.123
}
```

#### `energy_alert` — 能耗异常

```json
{
  "type": "energy_alert",
  "data": {
    "space_id": 3,
    "space_name": "101会议室",
    "metric": "power",
    "value": 2500.0,
    "threshold": 1000.0,
    "unit": "W",
    "message": "101会议室功率异常（2500W），超过阈值（1000W）"
  },
  "ts": 1718611200.123
}
```

### 6.4 客户端心跳

客户端应每 **30 秒** 发送心跳维持连接：

```json
{
  "type": "ping"
}
```

服务端回复：

```json
{
  "type": "pong"
}
```

### 6.5 重连策略

| 场景 | 行为 |
|------|------|
| 连接断开 | 客户端等待 1s → 3s → 5s → 10s → 30s（指数退避）后重连 |
| Token 过期 | 使用 refresh_token 获取新 token 后重连 |
| 服务端重启 | 客户端连续 5 次重连失败后停止，提示用户刷新页面 |

---

## 七、分页/过滤/排序规范

### 7.1 通用查询参数

所有列表端点统一使用以下查询参数：

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|:------:|:----:|------|
| `page` | integer | 1 | ≥1 | 页码 |
| `page_size` | integer | 20 | 1~100 | 每页条数 |
| `sort_by` | string | `created_at` | 见下方 | 排序字段 |
| `sort_order` | string | `desc` | `asc` / `desc` | 排序方向 |

### 7.2 分页响应

所有列表端点返回统一的 `pagination` 对象：

```json
{
  "data": [ ... ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 156,
    "total_pages": 8
  }
}
```

**客户端分页指引：**
- 首次请求不带 `page` 参数 → 默认第 1 页
- 后续翻页使用响应中的 `total_pages` 计算总页数
- 翻页超出 `total_pages` → 返回空数组 `[]`

### 7.3 常见模式

| 模式 | 说明 | 示例 |
|------|------|------|
| 翻页 | `?page=2&page_size=20` | 第 2 页，每页 20 条 |
| 排序 | `?sort_by=name&sort_order=asc` | 按名称升序 |
| 精确过滤 | `?decision=granted` | 仅显示 granted 的结果 |
| 时间范围 | `?date_from=2026-06-18T00:00:00Z&date_to=2026-06-18T23:59:59Z` | 指定日期范围 |
| 搜索 | `?search=张三` | 模糊搜索姓名/工号等 |
| 组合 | `?page=1&page_size=10&person_type=employee&department=研发部&sort_by=name&sort_order=asc` | 组合查询 |

### 7.4 每模块可用的排序字段

| 模块 | 可用的 `sort_by` 字段 |
|------|----------------------|
| persons | `name`, `employee_id`, `department`, `person_type`, `created_at`, `updated_at` |
| visitors | `name`, `expected_at`, `status`, `created_at` |
| devices | `name`, `node_id`, `device_type`, `last_seen`, `created_at` |
| spaces | `name`, `type`, `floor`, `created_at` |
| events | `fusion_conf`, `created_at`, `decision` |
| audit | `user_id`, `action`, `resource_type`, `created_at` |
| rules | `name`, `trigger_type`, `priority`, `created_at` |
| energy | `metric`, `value`, `recorded_at` |

### 7.5 搜索行为

- **全局搜索（单一 search 参数）**：跨多个字段模糊匹配，如 `search=张三` 同时匹配 `name`、`employee_id`、`phone` 等
- **精确过滤（独立参数）**：一对一精确匹配，如 `?department=研发部`
- **组合查询**：`search` 与独立过滤参数可同时使用，取交集
- **搜索字符编码**：URL 编码（中文需 UTF-8 编码）

---

## 八、MQTT 主题规范

### 8.1 主题定义

| 方向 | Topic | 发布者 | 频率 | 说明 |
|:----:|-------|:------:|:----:|------|
| ← | `vela/node/{node_id}/face` | ESP32 | ~15fps | 人脸嵌入 (128-d float32) |
| ← | `vela/node/{node_id}/silhouette` | ESP32 | ~15fps | 轮廓二值图 (RLE) |
| ← | `vela/node/{node_id}/ble` | ESP32 | 1Hz | BLE 扫描结果 (RSSI) |
| ← | `vela/node/{node_id}/status` | ESP32 | 0.1Hz | 设备心跳 |
| → | `vela/decision` | Server | 事件驱动 | 融合决策结果 |
| → | `vela/alert` | Server | 事件驱动 | 告警事件 |

### 8.2 消息 JSON 格式

**Node → vela/node/{node_id}/face:**
```json
{
  "node_id": "door-01",
  "embedding": [0.123, -0.456, ...],
  "timestamp": "2026-06-18T10:00:00Z"
}
```

**Node → vela/node/{node_id}/silhouette:**
```json
{
  "node_id": "door-01",
  "frames": 12345,
  "timestamp": "2026-06-18T10:00:00Z"
}
```

**Node → vela/node/{node_id}/ble:**
```json
{
  "node_id": "door-01",
  "rssi": -55,
  "mac": "AA:BB:CC:DD:EE:01",
  "timestamp": "2026-06-18T10:00:00Z"
}
```

**Server → vela/decision:**
```json
{
  "person_id": 1,
  "action": "granted",
  "explanation": "人脸匹配张三（置信度 0.85），单一模态已达阈值",
  "confidence": 0.85
}
```

**Server → vela/alert:**
```json
{
  "level": "critical",
  "type": "unauthorized_access",
  "message": "非工作时间敏感区域通行",
  "timestamp": "2026-06-18T22:15:00Z"
}
```

---

## 附录 A：完整端点速查表

| # | 方法 | 路径 | 模块 | 权限 |
|:-:|:----:|------|:----:|:----:|
| 1 | POST | `/api/v1/auth/login` | Auth | ❌ |
| 2 | POST | `/api/v1/auth/refresh` | Auth | ❌ |
| 3 | GET | `/api/v1/auth/me` | Auth | ✅ |
| 4 | GET | `/api/v1/persons` | Persons | person:read |
| 5 | POST | `/api/v1/persons` | Persons | person:write |
| 6 | GET | `/api/v1/persons/{id}` | Persons | person:read |
| 7 | PUT | `/api/v1/persons/{id}` | Persons | person:write |
| 8 | DELETE | `/api/v1/persons/{id}` | Persons | person:write |
| 9 | POST | `/api/v1/persons/{id}/faces` | Persons | person:write |
| 10 | GET | `/api/v1/persons/{id}/faces` | Persons | person:read |
| 11 | DELETE | `/api/v1/persons/{id}/faces/{face_id}` | Persons | person:write |
| 12 | GET | `/api/v1/visitors` | Visitors | visitor:read |
| 13 | POST | `/api/v1/visitors` | Visitors | visitor:write |
| 14 | GET | `/api/v1/visitors/{id}` | Visitors | visitor:read |
| 15 | PUT | `/api/v1/visitors/{id}` | Visitors | visitor:write |
| 16 | DELETE | `/api/v1/visitors/{id}` | Visitors | visitor:write |
| 17 | POST | `/api/v1/visitors/{id}/approve` | Visitors | visitor:approve |
| 18 | POST | `/api/v1/visitors/{id}/deny` | Visitors | visitor:approve |
| 19 | POST | `/api/v1/visitors/{id}/check-in` | Visitors | visitor:write |
| 20 | POST | `/api/v1/visitors/{id}/check-out` | Visitors | visitor:write |
| 21 | GET | `/api/v1/devices` | Devices | device:read |
| 22 | POST | `/api/v1/devices` | Devices | device:write |
| 23 | GET | `/api/v1/devices/{id}` | Devices | device:read |
| 24 | PUT | `/api/v1/devices/{id}` | Devices | device:write |
| 25 | DELETE | `/api/v1/devices/{id}` | Devices | device:write |
| 26 | POST | `/api/v1/devices/{id}/command` | Devices | device:write |
| 27 | GET | `/api/v1/devices/{id}/status/history` | Devices | device:read |
| 28 | GET | `/api/v1/spaces` | Spaces | space:read |
| 29 | POST | `/api/v1/spaces` | Spaces | space:write |
| 30 | GET | `/api/v1/spaces/{id}` | Spaces | space:read |
| 31 | PUT | `/api/v1/spaces/{id}` | Spaces | space:write |
| 32 | DELETE | `/api/v1/spaces/{id}` | Spaces | space:write |
| 33 | GET | `/api/v1/events` | Events | event:read |
| 34 | GET | `/api/v1/events/stats` | Events | event:read |
| 35 | GET | `/api/v1/events/recent` | Events | event:read |
| 36 | GET | `/api/v1/audit` | Audit | audit:read |
| 37 | GET | `/api/v1/rules` | Rules | rule:read |
| 38 | POST | `/api/v1/rules` | Rules | rule:write |
| 39 | PUT | `/api/v1/rules/{id}` | Rules | rule:write |
| 40 | DELETE | `/api/v1/rules/{id}` | Rules | rule:write |
| 41 | PUT | `/api/v1/rules/{id}/toggle` | Rules | rule:write |
| 42 | GET | `/api/v1/energy` | Energy | energy:read |
| 43 | GET | `/api/v1/energy/summary` | Energy | energy:read |
| 44 | GET | `/api/v1/users` | Users | tenant:admin |
| 45 | POST | `/api/v1/users` | Users | tenant:admin |
| 46 | PUT | `/api/v1/users/{id}` | Users | tenant:admin |
| 47 | DELETE | `/api/v1/users/{id}` | Users | tenant:admin |
| 48 | GET | `/api/v1/roles` | Roles | tenant:admin |
| 49 | POST | `/api/v1/roles` | Roles | tenant:admin |
| 50 | PUT | `/api/v1/roles/{id}` | Roles | tenant:admin |
| 51 | DELETE | `/api/v1/roles/{id}` | Roles | tenant:admin |
| 52 | GET | `/api/v1/permissions` | Permissions | ✅ |
| 53 | GET | `/api/v1/realtime/overview` | Realtime | dashboard:view |
| — | WS | `/ws/events` | Realtime | dashboard:view |

---

*— 文档结束 —*
