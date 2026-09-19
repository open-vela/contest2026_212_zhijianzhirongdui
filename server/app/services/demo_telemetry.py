"""Live MQTT evidence cache and compact SQLite persistence for the demo UI."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from app.models.database import async_session_factory
from app.models.models import DemoTelemetry
from app.services.demo_event_bus import demo_event_bus
from app.services.ws_manager import ws_manager

logger = logging.getLogger("demo.telemetry")

_HEAVY_FIELDS = {"embedding", "emb", "rle", "image", "image_b64", "frame"}
DEFAULT_TENANT_ID = 1


def _as_utc_naive(value: Any) -> datetime | None:
    """Parse common device timestamp formats into a naive UTC datetime."""
    try:
        if isinstance(value, (int, float)):
            seconds = float(value)
            if seconds > 10_000_000_000:  # milliseconds
                seconds /= 1000
            return datetime.utcfromtimestamp(seconds)
        if isinstance(value, str) and value:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
    except (OverflowError, TypeError, ValueError):
        return None
    return None


def _compact(value: Any, *, depth: int = 0) -> Any:
    """Keep useful scalar evidence while preventing large MQTT blobs in SQLite."""
    if depth > 4:
        return "[depth-limited]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, child in list(value.items())[:80]:
            key = str(raw_key)
            if key in _HEAVY_FIELDS:
                try:
                    result[f"{key}_length"] = len(child)
                except TypeError:
                    result[f"{key}_present"] = child is not None
                continue
            result[key] = _compact(child, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_compact(child, depth=depth + 1) for child in value[:50]]
    if isinstance(value, bytes):
        return {"bytes_length": len(value)}
    if isinstance(value, str) and len(value) > 512:
        return f"{value[:509]}..."
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class DemoTelemetryService:
    """Tracks the latest evidence per node/channel and fans out live updates."""

    PERSIST_MIN_INTERVAL_SECONDS = 1.0

    def __init__(self) -> None:
        self._latest: dict[tuple[int, str, str], dict[str, Any]] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=200)
        self._subscribers: set[asyncio.Queue] = set()
        self._last_persisted: dict[tuple[int, str, str], float] = {}
        self._sequence = 0

    async def on_message(self, topic: str, payload: dict[str, Any]) -> None:
        """MQTT callback registered against ``vela/node/+/+``."""
        await self.ingest(topic, payload, persist=True)

    async def ingest(
        self,
        topic: str,
        payload: dict[str, Any],
        *,
        persist: bool = True,
        provenance: str = "real",
    ) -> dict[str, Any]:
        parts = topic.split("/")
        topic_node = parts[2] if len(parts) >= 4 and parts[1] == "node" else "unknown"
        topic_channel = parts[3] if len(parts) >= 4 and parts[1] == "node" else parts[-1]
        node_id = str(payload.get("node_id") or topic_node)
        channel = str(payload.get("channel") or topic_channel)
        tenant_id = DEFAULT_TENANT_ID
        provenance = provenance if provenance in {"real", "mock"} else "pending_real"
        received_at = datetime.utcnow()
        device_at = _as_utc_naive(payload.get("ts") or payload.get("timestamp"))
        compact_payload = _compact(payload)

        self._sequence += 1
        record = {
            "event_id": self._sequence,
            "tenant_id": tenant_id,
            "node_id": node_id,
            "channel": channel,
            "topic": topic,
            "payload": compact_payload,
            "device_at": device_at.isoformat() + "Z" if device_at else None,
            "received_at": received_at.isoformat() + "Z",
            "provenance": provenance,
        }
        key = (tenant_id, node_id, channel)
        self._latest[key] = record
        self._events.appendleft(record)

        if persist and self._should_persist(key):
            try:
                async with async_session_factory() as db:
                    db.add(DemoTelemetry(
                        tenant_id=tenant_id,
                        node_id=node_id,
                        channel=channel,
                        topic=topic,
                        payload_json=compact_payload,
                        provenance=provenance,
                        received_at=received_at,
                    ))
                    await db.commit()
            except Exception:
                logger.exception("Failed to persist demo telemetry from %s", topic)

        # Calculated metrics deliberately consume the same compact record used
        # for real MQTT messages and software simulations.
        from app.services.demo_metrics import demo_metrics
        await demo_metrics.ingest(record, persist=persist)
        await self._fan_out(record)
        return record

    def _should_persist(self, key: tuple[int, str, str]) -> bool:
        now = time.monotonic()
        previous = self._last_persisted.get(key, 0.0)
        if now - previous < self.PERSIST_MIN_INTERVAL_SECONDS:
            return False
        self._last_persisted[key] = now
        return True

    async def _fan_out(self, record: dict[str, Any]) -> None:
        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(record)
        await ws_manager.broadcast("demo_event", record)
        await demo_event_bus.publish("telemetry", record, tenant_id=record["tenant_id"])

    def latest(
        self,
        channel: str,
        node_id: str | None = None,
        tenant_id: int = DEFAULT_TENANT_ID,
    ) -> dict[str, Any] | None:
        candidates = [
            record
            for (record_tenant, record_node, record_channel), record in self._latest.items()
            if record_tenant == tenant_id
            and record_channel == channel
            and (node_id is None or record_node == node_id)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item["received_at"])

    def records(self, tenant_id: int | None = None) -> list[dict[str, Any]]:
        records = list(self._latest.values())
        return records if tenant_id is None else [item for item in records if item["tenant_id"] == tenant_id]

    def recent_events(self, limit: int = 50, tenant_id: int | None = None) -> list[dict[str, Any]]:
        events = list(self._events)
        if tenant_id is not None:
            events = [item for item in events if item["tenant_id"] == tenant_id]
        return events[:limit]

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def clear(self) -> None:
        """Reset process-local state (primarily useful for deterministic tests)."""
        self._latest.clear()
        self._events.clear()
        self._last_persisted.clear()
        self._sequence = 0


demo_telemetry = DemoTelemetryService()
