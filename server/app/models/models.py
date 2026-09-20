"""SQLAlchemy ORM models for all VelaMesh (枢络) entities."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.models.database import Base


# ── Enums ──────────────────────────────────────────────────────────────
class PersonType(str, Enum):
    employee = "employee"
    visitor = "visitor"
    vip = "vip"
    contractor = "contractor"


class VisitorStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    checked_in = "checked_in"
    checked_out = "checked_out"
    expired = "expired"


class DeviceType(str, Enum):
    camera = "camera"
    door_lock = "door_lock"
    sensor = "sensor"
    beacon = "beacon"


class SpaceType(str, Enum):
    area = "area"
    room = "room"
    floor = "floor"
    entrance = "entrance"
    elevator = "elevator"


class Decision(str, Enum):
    granted = "granted"
    denied = "denied"
    unknown = "unknown"


class TriggerType(str, Enum):
    recognition = "recognition"
    device_offline = "device_offline"
    schedule = "schedule"
    alert = "alert"


class ActionType(str, Enum):
    mqtt_publish = "mqtt_publish"
    create_alert = "create_alert"
    webhook = "webhook"
    energy_control = "energy_control"


class EnergyMetric(str, Enum):
    power = "power"
    energy = "energy"
    current = "current"
    voltage = "voltage"


class EnergySource(str, Enum):
    device = "device"
    rule = "rule"
    manual = "manual"


# ── Tenant ────────────────────────────────────────────────────────────
class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    code = Column(String(64), unique=True, nullable=False)
    tier = Column(String(32), default="free")
    max_devices = Column(Integer, default=10)
    max_persons = Column(Integer, default=100)
    is_active = Column(Boolean, default=True)
    settings_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    users = relationship("User", back_populates="tenant")
    persons = relationship("Person", back_populates="tenant")
    visitors = relationship("Visitor", back_populates="tenant")
    devices = relationship("Device", back_populates="tenant")
    spaces = relationship("Space", back_populates="tenant")
    events = relationship("Event", back_populates="tenant")
    rules = relationship("Rule", back_populates="tenant")
    energy_logs = relationship("EnergyLog", back_populates="tenant")
    audit_logs = relationship("AuditLog", back_populates="tenant")
    roles = relationship("Role", back_populates="tenant")
    demo_telemetry = relationship("DemoTelemetry", back_populates="tenant")
    demo_metric_snapshots = relationship("DemoMetricSnapshot", back_populates="tenant")
    cloud_transfers = relationship("CloudTransferEvent", back_populates="tenant")


# ── User (login user — RBAC) ─────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    username = Column(String(64), nullable=False)
    password_hash = Column(String(256), nullable=False)
    display_name = Column(String(128), default="")
    email = Column(String(128), default="")
    is_active = Column(Boolean, default=True)
    is_superadmin = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("tenant_id", "username"),)

    tenant = relationship("Tenant", back_populates="users")
    roles = relationship("Role", secondary="user_roles", back_populates="users")
    audit_logs = relationship("AuditLog", back_populates="user")


# ── Role ──────────────────────────────────────────────────────────────
class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    name = Column(String(64), nullable=False)
    description = Column(String(256), default="")
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    tenant = relationship("Tenant", back_populates="roles")
    users = relationship("User", secondary="user_roles", back_populates="roles")
    permissions = relationship("Permission", secondary="role_permissions", back_populates="roles")


# ── Permission ────────────────────────────────────────────────────────
class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False)
    name = Column(String(128), nullable=False)
    resource = Column(String(64), nullable=False)
    action = Column(String(32), nullable=False)
    description = Column(String(256), default="")

    roles = relationship("Role", secondary="role_permissions", back_populates="permissions")


# ── User-Role association ─────────────────────────────────────────────
class UserRole(Base):
    __tablename__ = "user_roles"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)


# ── Role-Permission association ───────────────────────────────────────
class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"), primary_key=True)


# ── Person (recognized subject, not login user) ──────────────────────
class Person(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    name = Column(String(64), nullable=False)
    employee_id = Column(String(64), nullable=True)
    department = Column(String(128), default="")
    person_type = Column(String(32), default="employee")
    phone = Column(String(32), default="")
    email = Column(String(128), default="")
    ble_mac = Column(String(32), default="")
    avatar_url = Column(String(256), default="")
    access_level = Column(Integer, default=1)
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("tenant_id", "employee_id"),)

    tenant = relationship("Tenant", back_populates="persons")
    faces = relationship("Face", back_populates="person", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="person")


# ── Face (registered face embedding) ──────────────────────────────────
class Face(Base):
    __tablename__ = "faces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    embedding = Column(JSON, nullable=False)  # 128-d float32 stored as list
    image_url = Column(String(256), default="")
    quality_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    person = relationship("Person", back_populates="faces")


# ── Visitor (appointment) ────────────────────────────────────────────
class Visitor(Base):
    __tablename__ = "visitors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    name = Column(String(64), nullable=False)
    phone = Column(String(32), nullable=False)
    id_card = Column(String(32), default="")
    host_person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    purpose = Column(String(256), default="")
    expected_at = Column(DateTime, nullable=False)
    valid_from = Column(DateTime, nullable=False)
    valid_until = Column(DateTime, nullable=False)
    status = Column(String(32), default="pending")
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    denied_reason = Column(String(256), default="")
    checked_in_at = Column(DateTime, nullable=True)
    checked_out_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="visitors")
    host_person = relationship("Person")


# ── Device (ESP32 node) ──────────────────────────────────────────────
class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    node_id = Column(String(64), nullable=False)
    name = Column(String(128), default="")
    location = Column(String(256), default="")
    device_type = Column(String(32), default="camera")
    board_model = Column(String(64), default="XIAO_ESP32S3_SENSE")
    firmware_ver = Column(String(32), default="")
    ip_address = Column(String(64), default="")
    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime, nullable=True)
    config_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("tenant_id", "node_id"),)

    tenant = relationship("Tenant", back_populates="devices")
    events = relationship("Event", back_populates="device")


# ── Hub (R528 / Gemini-S1 VelaMesh中枢节点) ──────────────────────────
class Hub(Base):
    """A R528 hub running openvela that owns a master-slave edge topology."""

    __tablename__ = "hubs"

    id = Column(String(64), primary_key=True)  # stable hub id, e.g. "r528-hub-01"
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    name = Column(String(128), default="")
    model = Column(String(64), default="Gemini-S1/R528")
    vela_version = Column(String(64), default="")
    firmware_ver = Column(String(32), default="")
    ip_address = Column(String(64), default="")
    is_online = Column(Boolean, default=False)
    last_heartbeat = Column(DateTime, nullable=True)
    # Cloud link state drives the offline-queue replay behaviour.
    cloud_link = Column(String(16), default="unknown")  # online | offline | unknown
    capabilities_json = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    edges = relationship("EdgeNode", back_populates="hub", cascade="all, delete-orphan")


# ── EdgeNode (ESP32-S3 从节点) ───────────────────────────────────────
class EdgeNode(Base):
    """An ESP32-S3 slave node bound to one R528 hub."""

    __tablename__ = "edge_nodes"

    id = Column(String(64), primary_key=True)  # edge node id (same as MQTT node id)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    hub_id = Column(String(64), ForeignKey("hubs.id"), nullable=True, index=True)
    name = Column(String(128), default="")
    board_model = Column(String(64), default="XIAO_ESP32S3_SENSE")
    firmware_ver = Column(String(32), default="")
    is_online = Column(Boolean, default=False)
    last_heartbeat = Column(DateTime, nullable=True)
    # Capability bits advertised by the edge firmware.
    cap_face = Column(Boolean, default=False)
    cap_gait = Column(Boolean, default=False)
    cap_ble = Column(Boolean, default=False)
    cap_camera = Column(Boolean, default=False)
    # Latest telemetry (free-form: rssi / free_heap / fps / light ...).
    telemetry_json = Column(JSON, default=dict)
    registered_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("tenant_id", "id"),)

    hub = relationship("Hub", back_populates="edges")


# ── EdgeEventQueue (断网本地暂存, 恢复补传) ───────────────────────────
class EdgeEventQueue(Base):
    """Durable per-hub staging of edge events while the cloud link is down.

    Local policy decisions are made regardless of cloud connectivity; this
    table only holds the evidence that must be replayed to the cloud/report
    pipeline after reconnect (status events at minimum).
    """

    __tablename__ = "edge_event_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    hub_id = Column(String(64), index=True, nullable=True)
    edge_id = Column(String(64), index=True, default="")
    channel = Column(String(32), default="status")
    topic = Column(String(256), default="")
    payload_json = Column(JSON, default=dict)
    status = Column(String(16), default="queued", nullable=False)  # queued | sent
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    delivered_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_edge_event_queue_hub_status_created", "hub_id", "status", "created_at"),
    )


# ── Space (area / room / floor / entrance) ──────────────────────────
class Space(Base):
    __tablename__ = "spaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    name = Column(String(128), nullable=False)
    code = Column(String(64), nullable=True)
    type = Column(String(32), nullable=False)
    parent_id = Column(Integer, ForeignKey("spaces.id"), nullable=True)
    floor = Column(String(16), default="")
    area = Column(Float, default=0.0)          # 面积 (m²)
    capacity = Column(Integer, default=0)       # 容量 (人数)
    occupancy = Column(Integer, default=0)      # 当前占用人数
    access_level = Column(Integer, default=1)
    settings_json = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="spaces")
    children = relationship("Space", backref="parent", remote_side=[id], cascade="all")


# ── Event (recognition event) ────────────────────────────────────────
class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    person_name = Column(String(64), default="")
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    node_id = Column(String(64), default="")
    face_conf = Column(Float, default=0.0)
    gait_conf = Column(Float, default=0.0)
    ble_conf = Column(Float, default=0.0)
    # Delivery profile (BLE beacon + camera presence): motion/presence score.
    motion_conf = Column(Float, default=0.0)
    fusion_conf = Column(Float, default=0.0)
    modality_count = Column(Integer, default=0)
    light_level = Column(Float, default=1.0)
    decision = Column(String(32), default="unknown")
    explain_text = Column(Text, default="")
    raw_data_json = Column(JSON, default=dict)
    # Hub-era explainable decision fields (OPE-100).
    policy_id = Column(String(32), default="")
    scenario = Column(String(32), default="")
    # "delivery" (BLE+motion shipped firmware) or "research" (face/gait/ble).
    evidence_mode = Column(String(16), default="research")
    weights_json = Column(JSON, default=dict)
    hub_id = Column(String(64), default="", index=True)
    is_alert = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="events")
    person = relationship("Person", back_populates="events")
    device = relationship("Device", back_populates="events")


# ── Demo telemetry (compact MQTT evidence) ───────────────────────────
class DemoTelemetry(Base):
    """Compact, durable evidence received from a node over MQTT.

    Large binary-like fields (face embeddings and silhouette RLE payloads) are
    stripped by ``demo_telemetry`` before records are written.  This table is
    intentionally separate from recognition events: it records transport and
    scoring evidence even when no identity decision is produced.
    """

    __tablename__ = "demo_telemetry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    node_id = Column(String(64), nullable=False)
    channel = Column(String(32), nullable=False)
    topic = Column(String(256), nullable=False)
    payload_json = Column(JSON, default=dict)
    provenance = Column(String(32), default="real", nullable=False)
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_demo_telemetry_tenant_channel_received", "tenant_id", "channel", "received_at"),
        Index("ix_demo_telemetry_tenant_node_received", "tenant_id", "node_id", "received_at"),
    )

    tenant = relationship("Tenant", back_populates="demo_telemetry")


class DemoMetricSnapshot(Base):
    """Durable metrics calculated from the same telemetry path as real devices."""

    __tablename__ = "demo_metric_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    node_id = Column(String(64), nullable=False)
    values_json = Column(JSON, default=dict, nullable=False)
    source_topic = Column(String(256), nullable=False)
    provenance = Column(String(32), default="real", nullable=False)
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_demo_metrics_tenant_calculated", "tenant_id", "calculated_at"),
        Index("ix_demo_metrics_tenant_node_calculated", "tenant_id", "node_id", "calculated_at"),
    )

    tenant = relationship("Tenant", back_populates="demo_metric_snapshots")


# ── Cloud transfer queue (local durable outbox) ──────────────────────
class CloudTransferEvent(Base):
    """A durable cloud upload request and its current delivery state."""

    __tablename__ = "cloud_transfer_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    request_id = Column(String(64), unique=True, nullable=False)
    direction = Column(String(16), default="upload", nullable=False)
    event_type = Column(String(64), default="demo_snapshot", nullable=False)
    status = Column(String(32), default="pending", nullable=False)
    payload_json = Column(JSON, default=dict)
    idempotency_key = Column(String(128), nullable=True)
    provider = Column(String(32), default="disabled", nullable=False)
    transport = Column(String(32), default="none", nullable=False)
    provenance = Column(String(32), default="reserved", nullable=False)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    response_status = Column(Integer, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=5, nullable=False)
    next_attempt_at = Column(DateTime, nullable=True)
    last_attempt_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    receipt_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_cloud_transfer_tenant_status_created", "tenant_id", "status", "created_at"),
        Index(
            "ux_cloud_transfer_tenant_direction_idempotency",
            "tenant_id", "direction", "idempotency_key",
            unique=True,
        ),
    )

    tenant = relationship("Tenant", back_populates="cloud_transfers")


class CloudTransferAttempt(Base):
    """Immutable audit row for every cloud delivery success or failure."""

    __tablename__ = "cloud_transfer_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    transfer_id = Column(Integer, ForeignKey("cloud_transfer_events.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False)
    response_status = Column(Integer, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    receipt_json = Column(JSON, default=dict)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_cloud_attempt_transfer_completed", "transfer_id", "completed_at"),
        Index("ix_cloud_attempt_tenant_completed", "tenant_id", "completed_at"),
    )


# ── Rule (policy/automation rule) ────────────────────────────────────
class Rule(Base):
    __tablename__ = "rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    trigger_type = Column(String(32), nullable=False)
    trigger_config = Column(JSON, nullable=False)
    condition_expr = Column(String(512), default="")
    action_type = Column(String(32), nullable=False)
    action_config = Column(JSON, nullable=False)
    priority = Column(Integer, default=2)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="rules")


# ── EnergyLog ─────────────────────────────────────────────────────────
class EnergyLog(Base):
    __tablename__ = "energy_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    space_id = Column(Integer, ForeignKey("spaces.id"), nullable=True)
    metric = Column(String(32), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(16), default="")
    source = Column(String(32), default="device")
    recorded_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="energy_logs")


# ── Alert ─────────────────────────────────────────────────────────────
class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    level = Column(String(16), default="info")
    type = Column(String(64), default="")
    title = Column(String(256), default="")
    message = Column(Text, default="")
    related_event_id = Column(Integer, nullable=True)
    related_person_id = Column(Integer, nullable=True)
    related_device_id = Column(Integer, nullable=True)
    resolved_by = Column(Integer, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant")


# ── AuditLog ──────────────────────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(64), nullable=False)
    resource_type = Column(String(64), nullable=False)
    resource_id = Column(String(64), default="")
    detail_json = Column(JSON, default=dict)
    ip_address = Column(String(64), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="audit_logs")
    user = relationship("User", back_populates="audit_logs")
