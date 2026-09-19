"""Pydantic schemas for request/response serialization."""

from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ── Generic response wrappers ─────────────────────────────────────────
class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class ResponseWrapper(BaseModel, Generic[T]):
    data: T
    message: str = "ok"


class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    pagination: Pagination


# ── Auth ──────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str
    tenant_code: str = "default"


class TokenData(BaseModel):
    user_id: int
    tenant_id: int
    username: str
    permissions: list[str]


class UserInfo(BaseModel):
    id: int
    username: str
    display_name: str
    email: str = ""
    roles: list[str]
    permissions: list[str]
    tenant_id: int
    tenant_code: str
    is_superadmin: bool = False


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: UserInfo


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


# ── Person ────────────────────────────────────────────────────────────
class PersonCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    employee_id: Optional[str] = None
    department: str = ""
    person_type: str = "employee"
    phone: str = ""
    email: str = ""
    ble_mac: str = ""
    access_level: int = 1
    is_active: bool = True
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    employee_id: Optional[str] = None
    department: Optional[str] = None
    person_type: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    ble_mac: Optional[str] = None
    access_level: Optional[int] = None
    is_active: Optional[bool] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class FaceInfo(BaseModel):
    id: int
    quality_score: float
    image_url: str = ""
    created_at: datetime


class EnrollFromNodeRequest(BaseModel):
    """Camera-based enrollment: capture the next embedding from this node."""
    node_id: str = Field(..., min_length=1, max_length=64)
    timeout_seconds: float = Field(30.0, ge=5.0, le=120.0)


class EnrollResult(BaseModel):
    person_id: int
    person_name: str
    node_id: str
    face_id: int
    embedding_len: int
    status: str = "captured"


class PersonResponse(BaseModel):
    id: int
    name: str
    employee_id: Optional[str]
    department: str
    person_type: str
    phone: str
    email: str
    ble_mac: str
    avatar_url: str
    access_level: int
    is_active: bool
    face_count: int = 0
    faces: list[FaceInfo] = []
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PersonListResponse(BaseModel):
    id: int
    name: str
    employee_id: Optional[str]
    department: str
    person_type: str
    phone: str
    email: str
    access_level: int
    is_active: bool
    face_count: int
    created_at: datetime
    updated_at: datetime


# ── Visitor ───────────────────────────────────────────────────────────
class VisitorCreate(BaseModel):
    name: str = Field(..., min_length=1)
    phone: str = Field(..., min_length=1)
    id_card: str = ""
    host_person_id: int
    purpose: str = ""
    expected_at: datetime
    valid_from: datetime
    valid_until: datetime


class VisitorUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    purpose: Optional[str] = None
    expected_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class VisitorResponse(BaseModel):
    id: int
    name: str
    phone: str
    id_card: str
    host_person_id: int
    host_name: str = ""
    purpose: str
    expected_at: datetime
    valid_from: datetime
    valid_until: datetime
    status: str
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    denied_reason: str = ""
    checked_in_at: Optional[datetime] = None
    checked_out_at: Optional[datetime] = None
    created_at: datetime


class VisitorApprove(BaseModel):
    approved_by: int


class VisitorDeny(BaseModel):
    reason: str = ""


# ── Device ────────────────────────────────────────────────────────────
class DeviceCreate(BaseModel):
    node_id: str = Field(..., min_length=1)
    name: str = ""
    location: str = ""
    device_type: str = "camera"
    board_model: str = "XIAO_ESP32S3_SENSE"
    config_json: dict = {}


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    device_type: Optional[str] = None
    firmware_ver: Optional[str] = None
    ip_address: Optional[str] = None
    config_json: Optional[dict] = None


class DeviceResponse(BaseModel):
    id: int
    node_id: str
    name: str
    location: str
    device_type: str
    board_model: str
    firmware_ver: str
    ip_address: str
    is_online: bool
    last_seen: Optional[datetime] = None
    config_json: dict = {}
    created_at: datetime


class DeviceCommand(BaseModel):
    command: str
    params: dict = {}


class DeviceStatusHistory(BaseModel):
    timestamp: datetime
    free_heap: int = 0
    free_psram: int = 0
    wifi_rssi: float = 0
    fps: float = 0
    temp: float = 0


# ── Space ─────────────────────────────────────────────────────────────
class SpaceCreate(BaseModel):
    name: str = Field(..., min_length=1)
    code: Optional[str] = None
    type: str = "area"
    parent_id: Optional[int] = None
    floor: str = ""
    area: float = 0.0
    capacity: int = 0
    access_level: int = 1
    settings_json: dict = {}


class SpaceUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    parent_id: Optional[int] = None
    floor: Optional[str] = None
    area: Optional[float] = None
    capacity: Optional[int] = None
    access_level: Optional[int] = None
    settings_json: Optional[dict] = None
    is_active: Optional[bool] = None


class SpaceResponse(BaseModel):
    id: int
    name: str
    code: Optional[str]
    type: str
    parent_id: Optional[int]
    floor: str
    area: float = 0.0
    capacity: int
    occupancy: int = 0
    access_level: int
    settings_json: dict = {}
    is_active: bool
    children: list["SpaceResponse"] = []
    created_at: datetime


# ── Event ─────────────────────────────────────────────────────────────
class EventResponse(BaseModel):
    id: int
    person_id: Optional[int] = None
    person_name: str
    node_id: str
    device_name: str = ""
    face_conf: float
    gait_conf: float
    ble_conf: float
    fusion_conf: float
    modality_count: int
    decision: str
    explain_text: str
    is_alert: bool
    created_at: datetime


class EventStats(BaseModel):
    total_events: int
    granted_count: int
    denied_count: int
    unknown_count: int
    grant_rate: float
    by_hour: dict[str, int] = {}
    top_persons: list[dict] = []


# ── Rule ──────────────────────────────────────────────────────────────
class RuleCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    trigger_type: str
    trigger_config: dict
    condition_expr: str = ""
    action_type: str
    action_config: dict
    priority: int = 2
    is_enabled: bool = True


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[dict] = None
    condition_expr: Optional[str] = None
    action_type: Optional[str] = None
    action_config: Optional[dict] = None
    priority: Optional[int] = None
    is_enabled: Optional[bool] = None


class RuleToggle(BaseModel):
    is_enabled: bool


class RuleResponse(BaseModel):
    id: int
    name: str
    description: str
    trigger_type: str
    trigger_config: dict
    condition_expr: str
    action_type: str
    action_config: dict
    priority: int
    is_enabled: bool
    created_at: datetime


# ── Energy ────────────────────────────────────────────────────────────
class EnergyResponse(BaseModel):
    id: int
    device_id: Optional[int] = None
    space_id: Optional[int] = None
    metric: str
    value: float
    unit: str
    source: str
    recorded_at: datetime


class EnergySummary(BaseModel):
    total_kwh: float
    avg_power_w: float
    peak_power_w: float
    by_space: list[dict] = []
    timeline: list[dict] = []


# ── Audit ─────────────────────────────────────────────────────────────
class AuditLogResponse(BaseModel):
    id: int
    user_id: int
    username: str = ""
    action: str
    resource_type: str
    resource_id: str
    detail_json: dict = {}
    ip_address: str
    created_at: datetime


# ── Alert ─────────────────────────────────────────────────────────────
class AlertResponse(BaseModel):
    id: int
    level: str = "info"
    type: str = ""
    title: str = ""
    message: str = ""
    related_event_id: Optional[int] = None
    related_person_id: Optional[int] = None
    related_device_id: Optional[int] = None
    is_resolved: bool = False
    resolved_by: Optional[int] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime


class AlertResolve(BaseModel):
    resolved_by: int = 0


# ── User management ───────────────────────────────────────────────────
class UserCreate(BaseModel):
    username: str = Field(..., min_length=2)
    password: str = Field(..., min_length=6)
    display_name: str = ""
    email: str = ""
    role_ids: list[int] = []


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    role_ids: Optional[list[int]] = None


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    email: str
    is_active: bool
    roles: list[str] = []
    last_login: Optional[datetime] = None
    created_at: datetime


class RoleCreate(BaseModel):
    name: str
    description: str = ""
    permission_ids: list[int] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permission_ids: Optional[list[int]] = None


class RoleResponse(BaseModel):
    id: int
    name: str
    description: str
    is_system: bool
    permissions: list[str] = []
    created_at: datetime


class PermissionResponse(BaseModel):
    id: int
    code: str
    name: str
    resource: str
    action: str
    description: str


# ── Realtime overview ─────────────────────────────────────────────────
class RealtimeOverview(BaseModel):
    online_devices: int
    offline_devices: int
    total_persons: int
    today_events: int
    today_granted: int
    today_alerts: int
    recent_events: list = []
    recent_alerts: list = []
    energy_today_kwh: float = 0


# ── Dashboard ─────────────────────────────────────────────────────────
class DashboardOverview(BaseModel):
    today_person_count: int = 0
    today_pass_count: int = 0
    alert_count: int = 0
    total_devices: int = 0
    online_devices: int = 0
    offline_devices: int = 0
    device_online_rate: float = 0.0
    today_visitor_count: int = 0


class DashboardTrendItem(BaseModel):
    date: str
    pass_count: int = 0


class DeviceStatusDistribution(BaseModel):
    online_count: int = 0
    offline_count: int = 0
    alert_count: int = 0


# ── Recognition ───────────────────────────────────────────────────────
class RecognitionResponse(BaseModel):
    id: int
    person_id: Optional[int] = None
    person_name: str = ""
    node_id: str = ""
    device_name: str = ""
    face_conf: float = 0.0
    fusion_conf: float = 0.0
    decision: str = "unknown"
    is_alert: bool = False
    created_at: datetime


# ── Energy by area ─────────────────────────────────────────────────
class EnergyByAreaItem(BaseModel):
    space_id: int
    space_name: str
    energy_kwh: float = 0.0
    percentage: float = 0.0


# ── Error ─────────────────────────────────────────────────────────────
class ErrorDetail(BaseModel):
    code: str = "VALIDATION_ERROR"
    message: str
    errors: list[dict] = []
