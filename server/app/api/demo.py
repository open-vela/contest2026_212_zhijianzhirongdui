"""Competition demo API backed by MQTT evidence and a local SQLite outbox."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.middleware.auth import decode_token, get_current_user, require_permission
from app.models.database import get_db
from app.models.models import CloudTransferEvent, DemoMetricSnapshot, DemoTelemetry, Device
from app.models.models import User as UserModel
from app.schemas.schemas import ResponseWrapper
from app.services.demo_telemetry import demo_telemetry
from app.services.demo_event_bus import demo_event_bus
from app.services.demo_metrics import demo_metrics
from app.services.cloud_outbox import cloud_outbox
from app.services.mqtt_client import mqtt_client

router = APIRouter(prefix="/api/demo", tags=["demo"])
cloud_router = APIRouter(prefix="/api/cloud", tags=["cloud-demo"])
ws_router = APIRouter(tags=["demo-websocket"])


class CloudUploadRequest(BaseModel):
    event_type: str = Field("demo_snapshot", min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(None, min_length=1, max_length=128)


class CloudReceiveRequest(BaseModel):
    event_type: str = Field("cloud_receipt", min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    provider: str = Field("generic_http", min_length=1, max_length=32)


class MetricSimulationRequest(BaseModel):
    node_prefix: str = Field("software-sim", min_length=1, max_length=32)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def _from_row(row: DemoTelemetry | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "event_id": row.id,
        "node_id": row.node_id,
        "channel": row.channel,
        "topic": row.topic,
        "payload": row.payload_json or {},
        "device_at": None,
        "received_at": _iso(row.received_at),
        "provenance": row.provenance or "real",
    }


async def _latest_record(
    db: AsyncSession,
    tenant_id: int,
    channel: str,
    node_id: str | None = None,
) -> dict[str, Any] | None:
    cached = demo_telemetry.latest(channel, node_id, tenant_id)
    if cached:
        return cached
    query = select(DemoTelemetry).where(
        DemoTelemetry.tenant_id == tenant_id,
        DemoTelemetry.channel == channel,
    )
    if node_id:
        query = query.where(DemoTelemetry.node_id == node_id)
    row = (await db.execute(
        query.order_by(DemoTelemetry.received_at.desc()).limit(1)
    )).scalar_one_or_none()
    return _from_row(row)


def _payload(record: dict[str, Any] | None) -> dict[str, Any]:
    value = record.get("payload") if record else None
    return value if isinstance(value, dict) else {}


def _first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def _coalesce(primary: Any, fallback: Any) -> Any:
    return fallback if primary is None else primary


def _cloud_event(item: CloudTransferEvent) -> dict[str, Any]:
    return {
        "request_id": item.request_id,
        "idempotency_key": item.idempotency_key,
        "direction": item.direction,
        "event_type": item.event_type,
        "status": item.status,
        "provider": item.provider,
        "transport": item.transport,
        "error_code": item.error_code,
        "error_message": item.error_message,
        "response_status": item.response_status,
        "retry_count": item.retry_count,
        "max_retries": item.max_retries,
        "next_attempt_at": _iso(item.next_attempt_at),
        "last_attempt_at": _iso(item.last_attempt_at),
        "delivered_at": _iso(item.delivered_at),
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
        "provenance": item.provenance,
    }


async def _node_items(db: AsyncSession, tenant_id: int) -> list[dict[str, Any]]:
    devices = (await db.execute(
        select(Device).where(Device.tenant_id == tenant_id).order_by(Device.node_id)
    )).scalars().all()
    device_map = {device.node_id: device for device in devices}

    records_by_node: dict[str, list[dict[str, Any]]] = {}
    for record in demo_telemetry.records(tenant_id):
        records_by_node.setdefault(record["node_id"], []).append(record)

    node_ids = sorted(set(device_map) | set(records_by_node))
    now = datetime.utcnow()
    result: list[dict[str, Any]] = []
    for node_id in node_ids:
        device = device_map.get(node_id)
        records = records_by_node.get(node_id, [])
        latest = max(records, key=lambda item: item["received_at"]) if records else None
        last_seen = None
        if latest:
            try:
                last_seen = datetime.fromisoformat(latest["received_at"].replace("Z", "+00:00")).replace(tzinfo=None)
            except (TypeError, ValueError):
                last_seen = None
        elif device:
            last_seen = device.last_seen

        age_seconds = (now - last_seen).total_seconds() if last_seen else None
        online = age_seconds is not None and age_seconds <= settings.DEMO_NODE_ONLINE_SECONDS
        channels = sorted({record["channel"] for record in records})
        latest_payload = _payload(latest)
        config = device.config_json if device and isinstance(device.config_json, dict) else {}
        result.append({
            "node_id": node_id,
            "name": device.name if device else f"Node-{node_id}",
            "role": latest_payload.get("role") or config.get("role") or "edge_node",
            "capabilities": sorted(set(config.get("capabilities", [])) | set(channels)),
            "ip": _first(latest_payload, "ip", "ip_address") or (device.ip_address if device else ""),
            "broker": f"{settings.MQTT_BROKER}:{settings.MQTT_PORT}",
            "online": online,
            "last_heartbeat": _iso(last_seen),
            "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
            "channels": channels,
            "provenance": latest.get("provenance", "real") if latest else "pending_real",
        })
    return result


@router.get("/overview", response_model=ResponseWrapper[dict])
async def demo_overview(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:view")),
):
    nodes = await _node_items(db, user.tenant_id)
    channel_sources: dict[str, set[str]] = {}
    for record in demo_telemetry.records(user.tenant_id):
        channel_sources.setdefault(record["channel"], set()).add(record.get("provenance", "real"))
    persisted_evidence = (await db.execute(
        select(DemoTelemetry.channel, DemoTelemetry.provenance).where(
            DemoTelemetry.tenant_id == user.tenant_id
        ).distinct()
    )).all()
    for channel, provenance in persisted_evidence:
        channel_sources.setdefault(channel, set()).add(provenance or "real")

    def coverage_for(required: set[str]) -> str:
        if not required.issubset(channel_sources):
            return "pending_real"
        return "real" if all("real" in channel_sources[channel] for channel in required) else "mock"
    persisted_count = (await db.execute(
        select(func.count()).select_from(DemoTelemetry).where(
            DemoTelemetry.tenant_id == user.tenant_id
        )
    )).scalar() or 0
    queue_depth = (await db.execute(
        select(func.count()).select_from(CloudTransferEvent).where(
            CloudTransferEvent.tenant_id == user.tenant_id,
            CloudTransferEvent.status.in_(("pending", "sending", "retrying")),
        )
    )).scalar() or 0
    delivered_cloud = (await db.execute(
        select(CloudTransferEvent.provenance).where(
            CloudTransferEvent.tenant_id == user.tenant_id,
            CloudTransferEvent.direction == "upload",
            CloudTransferEvent.status == "delivered",
        ).order_by(CloudTransferEvent.delivered_at.desc()).limit(1)
    )).scalar_one_or_none()
    if delivered_cloud in {"real", "mock"}:
        cloud_coverage = delivered_cloud
    elif cloud_outbox.mode == "disabled":
        cloud_coverage = "reserved"
    else:
        cloud_coverage = "pending_real" if cloud_outbox.mode == "http" else "mock"
    telemetry_provenances = {source for sources in channel_sources.values() for source in sources}
    metric_sources = set((await db.execute(
        select(DemoMetricSnapshot.provenance).where(
            DemoMetricSnapshot.tenant_id == user.tenant_id
        ).distinct()
    )).scalars().all())
    metric_sources |= demo_metrics.provenances(user.tenant_id)
    metric_coverage = "real" if "real" in metric_sources else ("mock" if "mock" in metric_sources else "pending_real")
    return ResponseWrapper(data={
        "mode": "local_mqtt",
        "updated_at": _iso(datetime.utcnow()),
        "node_count": len(nodes),
        "online_node_count": sum(1 for node in nodes if node["online"]),
        "telemetry_count": persisted_count,
        "topic_root": f"{settings.MQTT_TOPIC_PREFIX}/node/+/+",
        "services": {
            "api": {"status": "connected", "provenance": "real"},
            "database": {"status": "connected", "engine": "sqlite", "provenance": "real"},
            "mqtt": {
                "status": "connected" if mqtt_client.is_connected else "disconnected",
                "broker": f"{settings.MQTT_BROKER}:{settings.MQTT_PORT}",
                "provenance": "real",
            },
            "cloud": {
                "status": {
                    "disabled": "disabled",
                    "mock": "local_mock",
                    "http": "configured",
                }.get(cloud_outbox.mode, "disabled"),
                "queue_depth": queue_depth,
                "provenance": cloud_coverage,
            },
        },
        "coverage": {
            "ope73_silhouette": coverage_for({"silhouette"}),
            "ope75_connectivity": coverage_for({"status", "ble"}),
            "xiaomi_metrics": metric_coverage,
            "seeed_evidence": "pending_real",
            "cloud_roundtrip": cloud_coverage,
        },
        "provenance": "real" if "real" in telemetry_provenances else ("mock" if "mock" in telemetry_provenances else "pending_real"),
    })


@router.get("/nodes", response_model=ResponseWrapper[list[dict]])
async def demo_nodes(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:view")),
):
    return ResponseWrapper(data=await _node_items(db, user.tenant_id))


@router.get("/ope73/silhouette", response_model=ResponseWrapper[dict])
async def demo_silhouette(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:view")),
):
    record = await _latest_record(db, user.tenant_id, "silhouette")
    payload = _payload(record)
    window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
    upload = payload.get("upload_stats") if isinstance(payload.get("upload_stats"), dict) else {}
    if not record:
        return ResponseWrapper(data={
            "node_id": None,
            "frame_seq": None,
            "foreground_pixels": None,
            "window": {"seq_start": None, "seq_end": None},
            "upload_stats": {"uploaded": None, "skipped_empty": None, "suppressed_empty": None},
            "server_receive": {
                "last_topic": f"{settings.MQTT_TOPIC_PREFIX}/node/<node_id>/silhouette",
                "received_at": None,
                "provenance": "pending_real",
            },
            "device_log_evidence": {"note": "等待 OPE-73 实机剪影上报", "provenance": "pending_real"},
            "provenance": "pending_real",
        })
    return ResponseWrapper(data={
        "node_id": record["node_id"],
        "frame_seq": _first(payload, "frame_seq", "seq"),
        "foreground_pixels": _first(payload, "foreground_pixels", "pixel_count", "area"),
        "width": payload.get("width"),
        "height": payload.get("height"),
        "window": {
            "seq_start": _coalesce(_first(window, "seq_start", "start"), payload.get("seq_start")),
            "seq_end": _coalesce(_first(window, "seq_end", "end"), payload.get("seq_end")),
        },
        "upload_stats": {
            "uploaded": _coalesce(_first(upload, "uploaded", "sent"), payload.get("uploaded")),
            "skipped_empty": upload.get("skipped_empty", payload.get("skipped_empty")),
            "suppressed_empty": upload.get("suppressed_empty", payload.get("suppressed_empty")),
        },
        "server_receive": {
            "last_topic": record["topic"],
            "received_at": record["received_at"],
            "provenance": record.get("provenance", "real"),
        },
        "device_log_evidence": {
            "note": payload.get("device_log") or "服务器已真实收包；串口日志仍待现场留证",
            "provenance": record.get("provenance", "real") if payload.get("device_log") else "pending_real",
        },
        "provenance": record.get("provenance", "real"),
    })


@router.get("/ope73/gait", response_model=ResponseWrapper[dict])
async def demo_gait(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:view")),
):
    """Latest OPE-73 gait recognition result from the ``dominiscius/+/gait/result`` topic.

    The ESP32 publishes ``{session_id, direction, top3, cosine, margin, timing}``;
    the gait adapter normalizes it into the unified event
    ``{identity, score, direction, source, session_id, latency}`` and persists it
    on the ``gait`` telemetry channel. This endpoint exposes the latest record.
    """
    record = await _latest_record(db, user.tenant_id, "gait")
    payload = _payload(record)
    if not record:
        return ResponseWrapper(data={
            "node_id": None,
            "identity": None,
            "score": None,
            "direction": None,
            "source": "gait",
            "session_id": None,
            "latency": None,
            "cosine": None,
            "margin": None,
            "top3": [],
            "server_receive": {
                "last_topic": "dominiscius/<node_id>/gait/result",
                "received_at": None,
                "provenance": "pending_real",
            },
            "provenance": "pending_real",
        })
    top3 = payload.get("top3")
    if not isinstance(top3, list):
        top3 = []
    return ResponseWrapper(data={
        "node_id": record["node_id"],
        "identity": payload.get("identity"),
        "score": payload.get("score"),
        "direction": payload.get("direction"),
        "source": payload.get("source", "gait"),
        "session_id": payload.get("session_id"),
        "latency": payload.get("latency"),
        "cosine": payload.get("cosine"),
        "margin": payload.get("margin"),
        "top3": top3,
        "server_receive": {
            "last_topic": record["topic"],
            "received_at": record["received_at"],
            "provenance": record.get("provenance", "real"),
        },
        "provenance": record.get("provenance", "real"),
    })


@router.get("/ope75/connectivity", response_model=ResponseWrapper[dict])
async def demo_connectivity(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:view")),
):
    ble_record = await _latest_record(db, user.tenant_id, "ble")
    status_record = await _latest_record(
        db,
        user.tenant_id,
        "status",
        ble_record["node_id"] if ble_record else None,
    )
    status_payload = _payload(status_record)
    ble_payload = _payload(ble_record)
    raw_devices = ble_payload.get("devices")
    if not isinstance(raw_devices, list):
        raw_devices = [ble_payload] if ble_record else []
    ble_devices = []
    for item in raw_devices:
        if not isinstance(item, dict):
            continue
        device_id = _first(item, "device_id", "mac", "address")
        if not device_id:
            continue
        ble_devices.append({
            "device_id": device_id,
            "rssi": item.get("rssi"),
            "seen": item.get("seen", True),
            "last_seen": _coalesce(_first(item, "last_seen", "timestamp", "ts"), (ble_record or {}).get("received_at")),
            "scan_seq": _coalesce(_first(item, "scan_seq", "seq"), ble_payload.get("scan_seq")),
            "publish_status": item.get("publish_status", "received"),
            "provenance": ble_record.get("provenance", "real") if ble_record else "pending_real",
        })
    evidence_sources = {
        record.get("provenance", "real")
        for record in (status_record, ble_record)
        if record
    }
    provenance = "real" if "real" in evidence_sources else ("mock" if "mock" in evidence_sources else "pending_real")
    return ResponseWrapper(data={
        "node_id": (status_record or ble_record or {}).get("node_id"),
        "wifi": {
            "connected": _first(status_payload, "wifi_connected", "wifi") if status_record else None,
            "ip": _first(status_payload, "ip", "ip_address"),
            "rssi": _first(status_payload, "wifi_rssi", "rssi"),
            "provenance": status_record.get("provenance", "real") if status_record else "pending_real",
        },
        "mqtt": {
            "server_connected": mqtt_client.is_connected,
            "node_connected": status_payload.get("mqtt_connected") if status_record else None,
            "broker": f"{settings.MQTT_BROKER}:{settings.MQTT_PORT}",
            "provenance": "real",
        },
        "ble_devices": ble_devices,
        "topics": {
            channel: f"{settings.MQTT_TOPIC_PREFIX}/node/<node_id>/{channel}"
            for channel in ("status", "ble", "silhouette", "face", "metrics")
        },
        "reconnect_evidence": {
            "count": _first(status_payload, "reconnect_count", "mqtt_reconnect_count"),
            "last_reconnect_ms": _first(status_payload, "reconnect_ms", "reconnect_latency_ms"),
            "provenance": status_record.get("provenance", "real") if status_record and _first(status_payload, "reconnect_count", "reconnect_ms") is not None else "pending_real",
        },
        "last_received_at": (status_record or ble_record or {}).get("received_at"),
        "provenance": provenance,
    })


@router.get("/metrics", response_model=ResponseWrapper[list[dict]])
async def demo_metric_items(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:view")),
):
    return ResponseWrapper(data=await demo_metrics.metric_items(db, user.tenant_id))


@router.post("/simulate/metrics", response_model=ResponseWrapper[dict])
async def simulate_metrics(
    body: MetricSimulationRequest,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_permission("dashboard:view")),
):
    """Feed a local Mock scenario through the exact telemetry/metrics path.

    It is disabled by default and every generated record is permanently marked
    ``mock`` so it cannot become a real competition score.
    """
    if not settings.DEMO_SIMULATION_ENABLED:
        raise HTTPException(status_code=403, detail="Software simulation is disabled")
    now = datetime.utcnow()
    node_id = f"{body.node_prefix}-gateway"
    events = [
        (
            f"{settings.MQTT_TOPIC_PREFIX}/node/{node_id}/status",
            {"node_id": node_id, "mqtt_connected": True, "wifi_connected": True, "ip": "127.0.0.1", "ts": now.timestamp()},
        ),
        (
            f"{settings.MQTT_TOPIC_PREFIX}/node/{node_id}/metrics",
            {
                "node_id": node_id,
                "metrics": {
                    "discovery_ms": 420,
                    "connection_ms": 780,
                    "reconnect_ms": 640,
                    "end_to_end_ms": 72,
                    "sent_count": 1000,
                    "received_count": 996,
                    "sync_skew_ms": 38,
                    "modality_count": 3,
                },
            },
        ),
        (
            f"{settings.MQTT_TOPIC_PREFIX}/node/{node_id}/service",
            {
                "node_id": node_id,
                "service_owner": node_id,
                "active_node": node_id,
                "backup_node": f"{body.node_prefix}-backup",
                "switch_started_at": (now - timedelta(milliseconds=540)).isoformat() + "Z",
                "switched_at": now.isoformat() + "Z",
                "interruption_ms": 120,
            },
        ),
    ]
    for topic, payload in events:
        await demo_telemetry.ingest(topic, payload, persist=True, provenance="mock")
    return ResponseWrapper(data={
        "records": len(events),
        "node_id": node_id,
        "provenance": "mock",
    }, message="Mock events traversed the production telemetry and metrics pipeline")


@router.get("/seeed-miniaturization", response_model=ResponseWrapper[dict])
async def seeed_miniaturization(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:view")),
):
    edge_rows = (await db.execute(
        select(DemoTelemetry.channel, DemoTelemetry.provenance).where(
            DemoTelemetry.tenant_id == user.tenant_id,
            DemoTelemetry.channel.in_(("face", "silhouette", "status", "ble")),
        )
    )).all()
    edge_real_count = sum(1 for channel, provenance in edge_rows if channel in {"face", "silhouette"} and provenance == "real")
    edge_mock_count = sum(1 for channel, provenance in edge_rows if channel in {"face", "silhouette"} and provenance == "mock")
    edge_count = edge_real_count or edge_mock_count
    edge_provenance = "real" if edge_real_count else ("mock" if edge_mock_count else "pending_real")
    real_protocol_channels = {channel for channel, provenance in edge_rows if provenance == "real"}
    mock_protocol_channels = {channel for channel, provenance in edge_rows if provenance == "mock"}
    if {"status", "ble"}.issubset(real_protocol_channels):
        protocol_provenance = "real"
    elif {"status", "ble"}.issubset(real_protocol_channels | mock_protocol_channels):
        protocol_provenance = "mock"
    else:
        protocol_provenance = "pending_real"
    return ResponseWrapper(data={
        "claimed_dimensions_mm": [45, 22, 8],
        "claimed_volume_cm3": 7.9,
        "claimed_weight_g": 5.3,
        "power_ratio": 15.5,
        "physical_verification": "待现场称重、卡尺和功耗计复核",
        "evidence": [
            {
                "name": "端侧 AI",
                "status": "software_ready" if edge_count else "awaiting_hardware",
                "note": f"SQLite 已保留 {edge_count} 条端侧 AI 证据" if edge_count else "等待节点上报剪影/人脸数据",
                "provenance": edge_provenance,
            },
            {"name": "多协议融合", "status": "interface_ready", "note": "WiFi + MQTT + BLE 软件接口已接通；真实链路仍以实机收包为准", "provenance": protocol_provenance},
            {"name": "小型化实物", "status": "awaiting_measurement", "note": "申报值已录入，现场测量前不判定达标", "provenance": "pending_real"},
            {"name": "复现文档", "status": "reserved", "note": "需补最终接线、启动和故障切换实录", "provenance": "reserved"},
            {"name": "演示视频", "status": "awaiting_recording", "note": "待硬件闭环后录制", "provenance": "pending_real"},
        ],
        "provenance": "pending_real",
    })


@cloud_router.get("/status", response_model=ResponseWrapper[dict])
async def cloud_status(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:view")),
):
    queue_depth = (await db.execute(
        select(func.count()).select_from(CloudTransferEvent).where(
            CloudTransferEvent.tenant_id == user.tenant_id,
            CloudTransferEvent.direction == "upload",
            CloudTransferEvent.status.in_(("pending", "sending", "retrying")),
        )
    )).scalar() or 0
    retry_count = (await db.execute(
        select(func.coalesce(func.sum(CloudTransferEvent.retry_count), 0)).where(
            CloudTransferEvent.tenant_id == user.tenant_id
        )
    )).scalar() or 0
    latest_upload = (await db.execute(
        select(CloudTransferEvent).where(
            CloudTransferEvent.tenant_id == user.tenant_id,
            CloudTransferEvent.direction == "upload",
        ).order_by(CloudTransferEvent.updated_at.desc()).limit(1)
    )).scalar_one_or_none()
    latest_receive = (await db.execute(
        select(CloudTransferEvent).where(
            CloudTransferEvent.tenant_id == user.tenant_id,
            CloudTransferEvent.direction == "receive",
        ).order_by(CloudTransferEvent.updated_at.desc()).limit(1)
    )).scalar_one_or_none()
    latest_error = (await db.execute(
        select(CloudTransferEvent).where(
            CloudTransferEvent.tenant_id == user.tenant_id,
            CloudTransferEvent.error_code.is_not(None),
        ).order_by(CloudTransferEvent.updated_at.desc()).limit(1)
    )).scalar_one_or_none()
    if latest_upload and latest_upload.status == "delivered":
        provenance = latest_upload.provenance
    elif cloud_outbox.mode == "mock":
        provenance = "mock"
    elif cloud_outbox.mode == "http":
        provenance = "pending_real"
    else:
        provenance = "reserved"
    ingest = {
        "disabled": "disabled",
        "mock": "local_mock",
        "http": "ready" if settings.DEMO_CLOUD_ENDPOINT else "misconfigured",
    }.get(cloud_outbox.mode, "disabled")
    return ResponseWrapper(data={
        "ingest": ingest,
        "mode": cloud_outbox.mode,
        "provider": cloud_outbox.provider,
        "endpoint_configured": cloud_outbox.mode == "http" and bool(settings.DEMO_CLOUD_ENDPOINT),
        "delivery_worker": "running" if cloud_outbox.is_running else ("disabled" if cloud_outbox.mode == "disabled" else "manual_test"),
        "error_code": latest_error.error_code if latest_error else None,
        "error_message": latest_error.error_message if latest_error else None,
        "retry_count": retry_count,
        "queue_depth": queue_depth,
        "last_upload_at": _iso(latest_upload.updated_at) if latest_upload else None,
        "last_receive_at": _iso(latest_receive.updated_at) if latest_receive else None,
        "last_upload_status": latest_upload.status if latest_upload else None,
        "provenance": provenance,
    })


@cloud_router.post("/upload", response_model=ResponseWrapper[dict], status_code=status.HTTP_202_ACCEPTED)
async def cloud_upload(
    body: CloudUploadRequest,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:view")),
):
    if len(json.dumps(body.payload, ensure_ascii=False).encode("utf-8")) > 256 * 1024:
        raise HTTPException(status_code=413, detail="Demo snapshot must not exceed 256 KiB")
    idempotency_key = body.idempotency_key or uuid.uuid4().hex
    existing = (await db.execute(
        select(CloudTransferEvent).where(
            CloudTransferEvent.tenant_id == user.tenant_id,
            CloudTransferEvent.idempotency_key == idempotency_key,
            CloudTransferEvent.direction == "upload",
        ).limit(1)
    )).scalar_one_or_none()
    if existing:
        return ResponseWrapper(
            data={
                "request_id": existing.request_id,
                "idempotency_key": existing.idempotency_key,
                "status": existing.status,
                "cloud_delivered": existing.status == "delivered",
                "endpoint_configured": cloud_outbox.mode == "http" and bool(settings.DEMO_CLOUD_ENDPOINT),
                "provenance": existing.provenance,
                "duplicate": True,
            },
            message="Idempotency key already exists; original outbox item returned",
        )
    request_id = uuid.uuid4().hex
    provenance = "mock" if cloud_outbox.mode == "mock" else ("pending_real" if cloud_outbox.mode == "http" else "reserved")
    event = CloudTransferEvent(
        tenant_id=user.tenant_id,
        request_id=request_id,
        idempotency_key=idempotency_key,
        direction="upload",
        event_type=body.event_type,
        status="pending",
        payload_json=body.payload,
        provider=cloud_outbox.provider,
        transport=cloud_outbox.mode,
        provenance=provenance,
        error_code="CLOUD_DISABLED" if cloud_outbox.mode == "disabled" else None,
        error_message="Cloud delivery is disabled; item is safely stored locally." if cloud_outbox.mode == "disabled" else None,
        max_retries=settings.DEMO_CLOUD_MAX_RETRIES,
        next_attempt_at=datetime.utcnow(),
    )
    db.add(event)
    try:
        await db.commit()
    except IntegrityError:
        # The database index is the final guard when two identical requests
        # arrive between the optimistic lookup and commit.
        await db.rollback()
        existing = (await db.execute(
            select(CloudTransferEvent).where(
                CloudTransferEvent.tenant_id == user.tenant_id,
                CloudTransferEvent.idempotency_key == idempotency_key,
                CloudTransferEvent.direction == "upload",
            ).limit(1)
        )).scalar_one_or_none()
        if not existing:
            raise
        return ResponseWrapper(
            data={
                "request_id": existing.request_id,
                "idempotency_key": existing.idempotency_key,
                "status": existing.status,
                "cloud_delivered": existing.status == "delivered",
                "endpoint_configured": cloud_outbox.mode == "http" and bool(settings.DEMO_CLOUD_ENDPOINT),
                "provenance": existing.provenance,
                "duplicate": True,
            },
            message="Idempotency race resolved; original outbox item returned",
        )
    cloud_outbox.wake()
    return ResponseWrapper(
        data={
            "request_id": request_id,
            "idempotency_key": idempotency_key,
            "status": "pending",
            "cloud_delivered": False,
            "endpoint_configured": cloud_outbox.mode == "http" and bool(settings.DEMO_CLOUD_ENDPOINT),
            "provenance": provenance,
            "duplicate": False,
        },
        message="Stored in the durable SQLite outbox",
    )


@cloud_router.post("/receive", response_model=ResponseWrapper[dict], status_code=status.HTTP_202_ACCEPTED)
async def cloud_receive(
    body: CloudReceiveRequest,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:view")),
):
    """Record a generic inbound cloud event with idempotency protection."""
    existing = (await db.execute(
        select(CloudTransferEvent).where(
            CloudTransferEvent.tenant_id == user.tenant_id,
            CloudTransferEvent.idempotency_key == body.idempotency_key,
            CloudTransferEvent.direction == "receive",
        ).limit(1)
    )).scalar_one_or_none()
    if existing:
        return ResponseWrapper(data={**_cloud_event(existing), "duplicate": True})
    if cloud_outbox.mode == "mock" or body.provider == "local_mock":
        provenance = "mock"
    elif cloud_outbox.mode == "http" and bool(settings.DEMO_CLOUD_ENDPOINT):
        provenance = "real"
    else:
        # A manually posted local callback proves the receive API works, but
        # without a configured HTTP cloud path it is not public-cloud proof.
        provenance = "pending_real"
    event = CloudTransferEvent(
        tenant_id=user.tenant_id,
        request_id=uuid.uuid4().hex,
        idempotency_key=body.idempotency_key,
        direction="receive",
        event_type=body.event_type,
        status="delivered",
        payload_json=body.payload,
        provider=body.provider,
        transport="http",
        provenance=provenance,
        max_retries=0,
        delivered_at=datetime.utcnow(),
    )
    db.add(event)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (await db.execute(
            select(CloudTransferEvent).where(
                CloudTransferEvent.tenant_id == user.tenant_id,
                CloudTransferEvent.idempotency_key == body.idempotency_key,
                CloudTransferEvent.direction == "receive",
            ).limit(1)
        )).scalar_one_or_none()
        if not existing:
            raise
        return ResponseWrapper(data={**_cloud_event(existing), "duplicate": True})
    payload = _cloud_event(event)
    await demo_event_bus.publish("cloud", payload, tenant_id=user.tenant_id)
    return ResponseWrapper(data={**payload, "duplicate": False})


@cloud_router.get("/events", response_model=ResponseWrapper[list[dict]])
async def cloud_events(
    limit: int = Query(20, ge=1, le=100),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:view")),
):
    events = (await db.execute(
        select(CloudTransferEvent).where(
            CloudTransferEvent.tenant_id == user.tenant_id
        ).order_by(CloudTransferEvent.created_at.desc()).limit(limit)
    )).scalars().all()
    return ResponseWrapper(data=[_cloud_event(item) for item in events])


@ws_router.websocket("/ws/demo-events")
async def demo_events_socket(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    """Authenticated live feed of compact MQTT evidence for the demo page."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        claims = decode_token(token)
        user_id = int(claims.get("sub", 0))
        user = await db.get(UserModel, user_id)
        if not user or not user.is_active:
            raise ValueError("inactive user")
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    queue = demo_event_bus.subscribe()
    try:
        await websocket.send_json({
            "type": "snapshot",
            "data": demo_telemetry.recent_events(20, user.tenant_id),
            "ts": datetime.utcnow().timestamp(),
        })
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=20)
                if event["tenant_id"] != user.tenant_id:
                    continue
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat", "ts": datetime.utcnow().timestamp()})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        demo_event_bus.unsubscribe(queue)
