"""Edge MQTT ingress: edge/<id>/{face,gait,ble,motion,status} → hub pipeline.

Wires the OPE-100 hub contract end to end:

  edge/<edge_id>/face|gait|ble|motion|status
        │
        ├─ demo_telemetry  (compact SQLite evidence + demo WS feed)
        ├─ topology        (EdgeNode/Hub registry, heartbeats, WS graph)
        ├─ identity_engine (fusion → decision)
        └─ hub_offline     (staging while the cloud uplink is down)

The 2026-09-20 delivery profile is BLE beacon identity + camera
motion/presence: ``edge/<id>/motion`` carries {present, confidence}; a
status payload may carry the same fields (folded presence), and a gait
payload without identity but with ``present``/``motion`` is treated as
presence evidence too.

Legacy topics stay subscribed for deployed firmware (see TOPIC_MAP):
  vela/node/<id>/{face,silhouette,ble,status} and
  dominiscius/<id>/gait/result (handled by gait_adapter).
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.models.database import async_session_factory
from app.models.models import EdgeNode
from app.services.demo_telemetry import demo_telemetry
from app.services.topology import topology

logger = logging.getLogger("edge.ingress")

# New hub contract channels. "motion" is the delivery-profile camera
# presence channel (shipped firmware); face/gait remain for research.
EDGE_CHANNELS = ("face", "gait", "ble", "motion", "status")

# New channel -> legacy vela/node channel, used by the telemetry layer and
# documented in the README (firmware OPE-99 migrates to the new topics).
CHANNEL_MAP = {
    "face": "face",
    "gait": "gait",
    "ble": "ble",
    "motion": "motion",
    "status": "status",
}


def parse_edge_topic(topic: str) -> tuple[str | None, str | None]:
    """Parse ``edge/<id>/<channel>``; returns (edge_id, channel) or (None, None)."""
    parts = topic.split("/")
    if len(parts) >= 3 and parts[0] == settings.MQTT_EDGE_TOPIC_PREFIX:
        return parts[1], parts[2]
    return None, None


class EdgeIngress:
    """Routes edge MQTT messages into telemetry, topology and fusion."""

    def topic_patterns(self) -> list[str]:
        prefix = settings.MQTT_EDGE_TOPIC_PREFIX
        return [f"{prefix}/+/{channel}" for channel in EDGE_CHANNELS]

    async def dispatch(self, topic: str, payload: dict[str, Any]) -> None:
        edge_id, channel = parse_edge_topic(topic)
        if not edge_id or channel not in CHANNEL_MAP:
            return
        payload = dict(payload)
        payload.setdefault("node_id", edge_id)
        payload.setdefault("edge_id", edge_id)

        try:
            # 1) Compact durable evidence (same path as the legacy topics).
            await demo_telemetry.ingest(topic, payload, persist=True)
        except Exception:
            logger.exception("[Edge] telemetry ingest failed on %s", topic)

        try:
            # 2) Offline staging: every edge channel is staged while the hub
            #    reports its cloud link down. Local decisions still run.
            await self._maybe_stage(topic, edge_id, channel, payload)
        except Exception:
            logger.exception("[Edge] offline staging failed on %s", topic)

        # 3) Topology + fusion.
        handler = {
            "face": self._on_face,
            "gait": self._on_gait,
            "ble": self._on_ble,
            "motion": self._on_motion,
            "status": self._on_status,
        }[channel]
        try:
            await handler(edge_id, topic, payload)
        except Exception:
            logger.exception("[Edge] handler failed on %s", topic)

    # ── Channel handlers ──────────────────────────────────────────────

    async def _on_face(self, edge_id: str, topic: str, payload: dict[str, Any]) -> None:
        from app.services.identity_engine import identity_engine

        await self._touch_edge(edge_id, payload, ["face", "camera"])
        # A score without an embedding was computed on the hub/edge itself.
        if "embedding" not in payload and "emb" not in payload and "score" in payload:
            await identity_engine.on_face_score(
                edge_id,
                score=float(payload.get("score", 0)),
                person_id=payload.get("person_id"),
                person_name=payload.get("person_name", ""),
                person_type=payload.get("person_type", "employee"),
                context=payload,
            )
        else:
            await identity_engine.on_face(topic, payload)

    async def _on_motion(self, edge_id: str, topic: str, payload: dict[str, Any]) -> None:
        from app.services.identity_engine import identity_engine

        await self._touch_edge(edge_id, payload, ["camera"])
        # Delivery-profile camera presence: {present, confidence, ...}.
        await identity_engine.on_motion(edge_id, payload)

    async def _on_gait(self, edge_id: str, topic: str, payload: dict[str, Any]) -> None:
        from app.services.identity_engine import identity_engine

        await self._touch_edge(edge_id, payload, ["gait", "camera"])
        # A gait/silhouette frame without identity but with an explicit
        # presence flag is delivery-profile motion evidence, not research
        # gait evidence (shipped firmware has no gait identity model).
        presence_only = (
            "score" not in payload
            and "rle" not in payload
            and ("present" in payload or "motion" in payload)
        )
        if presence_only:
            await identity_engine.on_motion(edge_id, payload)
            return
        # edge gait payloads may carry an RLE silhouette (legacy firmware),
        # gait features, or a direct score/identity (research/offline mode).
        if "rle" not in payload and "features" not in payload and "score" in payload:
            await identity_engine.on_gait_score(
                edge_id,
                score=float(payload.get("score", 0)),
                person_id=payload.get("person_id"),
                person_name=payload.get("person_name", ""),
                person_type=payload.get("person_type", "employee"),
                context=payload,
            )
        else:
            payload.setdefault("rle", "")
            await identity_engine.on_silhouette(topic, payload)

    async def _on_ble(self, edge_id: str, topic: str, payload: dict[str, Any]) -> None:
        from app.services.identity_engine import identity_engine

        await self._touch_edge(edge_id, payload, ["ble"])
        # New contract may directly carry a matched identity from the edge.
        if payload.get("matched") is True and payload.get("score") is not None:
            await identity_engine.on_ble_score(
                edge_id,
                score=float(payload.get("score", 0)),
                person_id=payload.get("person_id"),
                person_name=payload.get("person_name", ""),
                mac=payload.get("mac", ""),
                person_type=payload.get("person_type", "employee"),
                context=payload,
            )
        else:
            await identity_engine.on_ble(topic, payload)

    async def _on_status(self, edge_id: str, topic: str, payload: dict[str, Any]) -> None:
        from app.services.identity_engine import identity_engine

        hub_id = payload.get("hub_id")
        # A status with role=hub is the R528 reporting its own heartbeat.
        if payload.get("role") == "hub":
            hid = hub_id or edge_id
            await topology.hub_heartbeat(hid, payload)
            if payload.get("cloud_link"):
                await topology.set_cloud_link(hid, str(payload["cloud_link"]))
            return

        await topology.edge_heartbeat(edge_id, payload, hub_id=hub_id)
        # A slave status may itself report the hub's cloud link state.
        if hub_id and payload.get("cloud_link"):
            await topology.set_cloud_link(hub_id, str(payload["cloud_link"]))
        # Folded presence: firmware may report camera motion detection in the
        # status frame itself. present=false explicitly clears presence.
        if "present" in payload or "motion" in payload:
            from app.services.identity_engine import identity_engine

            await identity_engine.on_motion(edge_id, payload)
        await identity_engine.on_status(topic, payload)

    # ── Helpers ───────────────────────────────────────────────────────

    async def _touch_edge(
        self, edge_id: str, payload: dict[str, Any], capabilities: list[str]
    ) -> None:
        """Register capability bits on first evidence; heartbeats own liveness."""
        async with async_session_factory() as db:
            exists = (await db.get(EdgeNode, edge_id)) is not None
        if not exists:
            await topology.register_edge({
                "id": edge_id,
                "hub_id": payload.get("hub_id"),
                "firmware_ver": payload.get("firmware_ver"),
                "capabilities": capabilities,
            })

    async def _maybe_stage(
        self, topic: str, edge_id: str, channel: str, payload: dict[str, Any]
    ) -> None:
        from app.services.cloud_state import cloud_state
        from app.services.hub_offline import hub_offline

        hub_id = await topology.hub_for_edge(edge_id)
        if cloud_state.is_offline(hub_id):
            await hub_offline.enqueue(
                hub_id=hub_id, edge_id=edge_id, channel=channel,
                topic=topic, payload=payload,
            )


edge_ingress = EdgeIngress()
