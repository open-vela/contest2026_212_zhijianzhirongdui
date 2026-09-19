"""Automatic competition metrics derived from compact demo telemetry."""

from __future__ import annotations

from datetime import datetime
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import async_session_factory
from app.models.models import DemoMetricSnapshot
from app.services.demo_event_bus import demo_event_bus


METRIC_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {"key": "discovery", "name": "发现耗时", "unit": "ms", "target": 1000, "operator": "lte", "target_note": "≤ 1000 ms"},
    {"key": "connection", "name": "连接建立耗时", "unit": "ms", "target": 3000, "operator": "lte", "target_note": "≤ 3000 ms"},
    {"key": "reconnect", "name": "断连到重连耗时", "unit": "ms", "target": 5000, "operator": "lte", "target_note": "≤ 5000 ms"},
    {"key": "end_to_end", "name": "端到端延迟", "unit": "ms", "target": 500, "operator": "lte", "target_note": "≤ 500 ms"},
    {"key": "messages_sent", "name": "消息发送数", "unit": "条", "target": None, "operator": None, "target_note": "设备累计发送"},
    {"key": "messages_received", "name": "消息接收数", "unit": "条", "target": None, "operator": None, "target_note": "服务端累计接收"},
    {"key": "packet_loss", "name": "丢包率", "unit": "%", "target": 1, "operator": "lte", "target_note": "≤ 1%"},
    {"key": "reliability", "name": "消息可靠性", "unit": "%", "target": 99, "operator": "gte", "target_note": "≥ 99%"},
    {"key": "multi_device_sync", "name": "多节点同步误差", "unit": "ms", "target": 100, "operator": "lte", "target_note": "≤ 100 ms"},
    {"key": "service_owner", "name": "Service owner", "unit": "", "target": None, "operator": None, "target_note": "设备状态上报"},
    {"key": "active_node", "name": "Active 节点", "unit": "", "target": None, "operator": None, "target_note": "设备状态上报"},
    {"key": "backup_node", "name": "Backup 节点", "unit": "", "target": None, "operator": None, "target_note": "设备状态上报"},
    {"key": "service_switch", "name": "服务切换耗时", "unit": "ms", "target": 3000, "operator": "lte", "target_note": "≤ 3000 ms"},
    {"key": "interruption", "name": "业务中断时长", "unit": "ms", "target": 1000, "operator": "lte", "target_note": "≤ 1000 ms"},
    {"key": "service_migration", "name": "服务流转", "unit": "bool", "target": True, "operator": "eq", "target_note": "支持跨节点流转"},
    {"key": "cooperative_modalities", "name": "协同感知复杂度", "unit": "种", "target": 3, "operator": "gte", "target_note": "≥ 3 种模态"},
)


ALIASES: dict[str, tuple[str, ...]] = {
    "discovery": ("discovery_ms", "discovery_latency_ms"),
    "connection": ("connection_ms", "connection_latency_ms"),
    "reconnect": ("reconnect_ms", "reconnect_latency_ms"),
    "end_to_end": ("end_to_end_ms", "p95_latency_ms", "latency_ms"),
    "messages_sent": ("messages_sent", "sent_count", "tx_count"),
    "messages_received": ("messages_received", "received_count", "rx_count"),
    "packet_loss": ("packet_loss_percent", "packet_loss", "loss_percent"),
    "reliability": ("reliability_percent", "success_rate"),
    "multi_device_sync": ("multi_device_sync_ms", "sync_skew_ms"),
    "service_owner": ("service_owner", "owner_node"),
    "active_node": ("active_node",),
    "backup_node": ("backup_node",),
    "service_switch": ("service_switch_ms", "switch_ms", "migration_ms"),
    "interruption": ("interruption_ms", "downtime_ms"),
    "service_migration": ("service_migration", "migration_supported"),
    "cooperative_modalities": ("cooperative_modalities", "modality_count"),
}


def _first(payload: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in payload and payload[name] is not None:
            return payload[name]
    return None


def _parse_time(value: Any) -> datetime | None:
    try:
        if isinstance(value, (int, float)):
            seconds = float(value)
            if seconds > 10_000_000_000:
                seconds /= 1000
            return datetime.utcfromtimestamp(seconds)
        if isinstance(value, str) and value:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except (OverflowError, TypeError, ValueError):
        return None
    return None


def _duration_ms(start: Any, end: Any) -> float | None:
    left = _parse_time(start)
    right = _parse_time(end)
    if not left or not right:
        return None
    value = (right - left).total_seconds() * 1000
    return round(value, 3) if 0 <= value <= 24 * 60 * 60 * 1000 else None


class DemoMetricsService:
    """Derive measurements while retaining their source and provenance."""

    def __init__(self) -> None:
        self._node_state: dict[tuple[int, str], dict[str, Any]] = {}
        self._device_times: dict[tuple[int, str], tuple[datetime, datetime]] = {}
        self._latest: dict[tuple[int, str], dict[str, Any]] = {}
        self._last_persisted: dict[tuple[int, str, str], float] = {}

    async def ingest(self, record: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
        tenant_id = int(record.get("tenant_id") or 1)
        node_id = str(record.get("node_id") or "unknown")
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        nested_metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        nested_service = payload.get("service") if isinstance(payload.get("service"), dict) else {}
        source = {**payload, **nested_metrics, **nested_service}
        received_at = _parse_time(record.get("received_at")) or datetime.utcnow()
        provenance = str(record.get("provenance") or "pending_real")
        state = self._node_state.setdefault((tenant_id, node_id), {"server_received": 0})
        state["server_received"] = int(state.get("server_received", 0)) + 1

        values: dict[str, Any] = {}
        for key, aliases in ALIASES.items():
            value = _first(source, aliases)
            if value is not None:
                values[key] = value

        # The server can always count what it actually receives. Total sent is
        # only known when the device reports its counter.
        if "messages_received" in values:
            state["reported_received"] = values["messages_received"]
        elif "reported_received" in state:
            values["messages_received"] = state["reported_received"]
        else:
            values["messages_received"] = state["server_received"]
        if "messages_sent" in values:
            state["sent"] = values["messages_sent"]
        elif "sent" in state:
            values["messages_sent"] = state["sent"]

        explicit_reliability = "reliability" in values
        explicit_packet_loss = "packet_loss" in values
        if explicit_reliability and isinstance(values["reliability"], (int, float)) and values["reliability"] <= 1:
            values["reliability"] = round(float(values["reliability"]) * 100, 3)
        if explicit_packet_loss and isinstance(values["packet_loss"], (int, float)) and values["packet_loss"] <= 1:
            values["packet_loss"] = round(float(values["packet_loss"]) * 100, 3)

        sent = values.get("messages_sent")
        received = values.get("messages_received")
        if isinstance(sent, (int, float)) and sent > 0 and isinstance(received, (int, float)):
            reliable = max(0.0, min(100.0, float(received) / float(sent) * 100.0))
            values.setdefault("reliability", round(reliable, 3))
            values.setdefault("packet_loss", round(100.0 - reliable, 3))

        # Timestamp pairs allow devices to provide lifecycle events without
        # pre-calculating their own score.
        for key, start_name, end_name in (
            ("discovery", "discovery_started_at", "discovered_at"),
            ("connection", "connection_started_at", "connected_at"),
            ("service_switch", "switch_started_at", "switched_at"),
            ("interruption", "interrupted_at", "resumed_at"),
        ):
            duration = _duration_ms(source.get(start_name), source.get(end_name))
            if duration is not None:
                values.setdefault(key, duration)

        mqtt_connected = source.get("mqtt_connected")
        if mqtt_connected is False:
            state["disconnected_at"] = received_at
        elif mqtt_connected is True and isinstance(state.get("disconnected_at"), datetime):
            reconnect_ms = (received_at - state.pop("disconnected_at")).total_seconds() * 1000
            if reconnect_ms >= 0:
                values.setdefault("reconnect", round(reconnect_ms, 3))
                values.setdefault("interruption", round(reconnect_ms, 3))

        device_at = _parse_time(record.get("device_at"))
        if device_at:
            latency_ms = (received_at - device_at).total_seconds() * 1000
            if 0 <= latency_ms <= 60_000:
                values.setdefault("end_to_end", round(latency_ms, 3))
            self._device_times[(tenant_id, node_id)] = (device_at, received_at)
            recent = [
                timestamp
                for (item_tenant, _), (timestamp, seen_at) in self._device_times.items()
                if item_tenant == tenant_id and abs((received_at - seen_at).total_seconds()) <= 5
            ]
            if len(recent) >= 2:
                values.setdefault("multi_device_sync", round((max(recent) - min(recent)).total_seconds() * 1000, 3))

        if values.get("service_switch") is not None:
            values.setdefault("service_migration", True)

        values = self._validated(values)
        if not values:
            return {}

        calculated_at = datetime.utcnow()
        for key, value in values.items():
            self._latest[(tenant_id, key)] = {
                "value": value,
                "node_id": node_id,
                "source_topic": record.get("topic"),
                "provenance": provenance,
                "updated_at": calculated_at,
            }

        channel = str(record.get("channel") or "unknown")
        persist_key = (tenant_id, node_id, channel)
        now_monotonic = time.monotonic()
        should_persist = now_monotonic - self._last_persisted.get(persist_key, 0.0) >= 1.0
        if persist and should_persist:
            self._last_persisted[persist_key] = now_monotonic
            async with async_session_factory() as db:
                db.add(DemoMetricSnapshot(
                    tenant_id=tenant_id,
                    node_id=node_id,
                    values_json=values,
                    source_topic=str(record.get("topic") or "software/derived"),
                    provenance=provenance,
                    calculated_at=calculated_at,
                ))
                await db.commit()

        await demo_event_bus.publish(
            "metrics",
            {"node_id": node_id, "values": values, "provenance": provenance},
            tenant_id=tenant_id,
        )
        return values

    async def metric_items(self, db: AsyncSession, tenant_id: int) -> list[dict[str, Any]]:
        snapshots = (await db.execute(
            select(DemoMetricSnapshot).where(
                DemoMetricSnapshot.tenant_id == tenant_id
            ).order_by(DemoMetricSnapshot.calculated_at.desc()).limit(500)
        )).scalars().all()

        latest: dict[str, dict[str, Any]] = {}
        for snapshot in snapshots:
            for key, value in (snapshot.values_json or {}).items():
                latest.setdefault(key, {
                    "value": value,
                    "node_id": snapshot.node_id,
                    "source_topic": snapshot.source_topic,
                    "provenance": snapshot.provenance,
                    "updated_at": snapshot.calculated_at,
                })
        for (item_tenant, key), item in self._latest.items():
            if item_tenant != tenant_id:
                continue
            previous = latest.get(key)
            if not previous or item["updated_at"] >= previous["updated_at"]:
                latest[key] = item

        result: list[dict[str, Any]] = []
        for definition in METRIC_DEFINITIONS:
            evidence = latest.get(definition["key"])
            value = evidence["value"] if evidence else None
            passed = self._passed(value, definition["target"], definition["operator"])
            result.append({
                **definition,
                "value": value,
                "passed": passed,
                "source_topic": evidence["source_topic"] if evidence else None,
                "source_node": evidence["node_id"] if evidence else None,
                "updated_at": evidence["updated_at"].isoformat() + "Z" if evidence else None,
                "provenance": evidence["provenance"] if evidence else "pending_real",
            })
        return result

    @staticmethod
    def _passed(value: Any, target: Any, operator: str | None) -> bool | None:
        if value is None or target is None or operator is None:
            return None
        try:
            if operator == "lte":
                return float(value) <= float(target)
            if operator == "gte":
                return float(value) >= float(target)
            if operator == "eq":
                return value == target
        except (TypeError, ValueError):
            return None
        return None

    @staticmethod
    def _validated(values: dict[str, Any]) -> dict[str, Any]:
        numeric_keys = {
            "discovery", "connection", "reconnect", "end_to_end",
            "messages_sent", "messages_received", "packet_loss", "reliability",
            "multi_device_sync", "service_switch", "interruption", "cooperative_modalities",
        }
        string_keys = {"service_owner", "active_node", "backup_node"}
        result: dict[str, Any] = {}
        for key, value in values.items():
            if value is None or key not in ALIASES:
                continue
            if key in numeric_keys:
                if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                    continue
                if key in {"packet_loss", "reliability"} and value > 100:
                    continue
            elif key in string_keys:
                if not isinstance(value, str) or not value.strip():
                    continue
                value = value.strip()[:128]
            elif key == "service_migration" and not isinstance(value, bool):
                continue
            result[key] = value
        return result

    def clear(self) -> None:
        self._node_state.clear()
        self._device_times.clear()
        self._latest.clear()
        self._last_persisted.clear()

    def provenances(self, tenant_id: int) -> set[str]:
        return {
            item["provenance"]
            for (item_tenant, _), item in self._latest.items()
            if item_tenant == tenant_id
        }


demo_metrics = DemoMetricsService()
