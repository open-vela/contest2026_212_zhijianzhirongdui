"""Hub/Edge master-slave topology service (OPE-100).

Owns the durable Hub (R528) and EdgeNode (ESP32-S3) registries, ingests
heartbeats, and fans topology changes out to WebSocket clients so the #6
dashboard can render the master-slave graph in real time.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.models.database import async_session_factory
from app.models.models import EdgeNode, Hub
from app.services.demo_event_bus import demo_event_bus
from app.services.ws_manager import ws_manager

logger = logging.getLogger("topology")

DEFAULT_TENANT_ID = 1
DEFAULT_HUB_ID = "r528-hub-01"

# Edge id -> hub id, cached from status traffic / DB bindings.
_hub_binding_cache: dict[str, str] = {}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def hub_to_dict(hub: Hub, edges: list[EdgeNode] | None = None) -> dict[str, Any]:
    return {
        "id": hub.id,
        "name": hub.name or hub.id,
        "model": hub.model or "Gemini-S1/R528",
        "vela_version": hub.vela_version or "",
        "firmware_ver": hub.firmware_ver or "",
        "ip_address": hub.ip_address or "",
        "is_online": bool(hub.is_online),
        "cloud_link": hub.cloud_link or "unknown",
        "last_heartbeat": _iso(hub.last_heartbeat),
        "capabilities": hub.capabilities_json or [],
        "edges": [edge_to_dict(e) for e in (edges or [])],
    }


def edge_to_dict(edge: EdgeNode) -> dict[str, Any]:
    return {
        "id": edge.id,
        "hub_id": edge.hub_id,
        "name": edge.name or edge.id,
        "board_model": edge.board_model or "XIAO_ESP32S3_SENSE",
        "firmware_ver": edge.firmware_ver or "",
        "is_online": bool(edge.is_online),
        "last_heartbeat": _iso(edge.last_heartbeat),
        "capabilities": _capabilities(edge),
        "telemetry": edge.telemetry_json or {},
        "registered_at": _iso(edge.registered_at),
    }


def _capabilities(edge: EdgeNode) -> list[str]:
    caps = []
    if edge.cap_face:
        caps.append("face")
    if edge.cap_gait:
        caps.append("gait")
    if edge.cap_ble:
        caps.append("ble")
    if edge.cap_camera:
        caps.append("camera")
    return caps


_CAP_KEYS = {
    "face": "cap_face",
    "gait": "cap_gait",
    "ble": "cap_ble",
    "camera": "cap_camera",
}


class TopologyService:
    """DB-backed hub/edge registry with live WS fan-out."""

    async def ensure_default_hub(self) -> Hub:
        async with async_session_factory() as db:
            hub = await db.get(Hub, DEFAULT_HUB_ID)
            if hub is None:
                hub = Hub(
                    id=DEFAULT_HUB_ID,
                    tenant_id=DEFAULT_TENANT_ID,
                    name="R528 中枢-01",
                    model="Gemini-S1/R528",
                )
                db.add(hub)
                await db.commit()
                await db.refresh(hub)
                logger.info("[Topology] auto-created default hub %s", DEFAULT_HUB_ID)
            return hub

    # ── Hub ───────────────────────────────────────────────────────────

    async def register_hub(self, data: dict[str, Any]) -> Hub:
        async with async_session_factory() as db:
            hub = await db.get(Hub, data["id"])
            if hub is None:
                hub = Hub(id=data["id"], tenant_id=DEFAULT_TENANT_ID)
                db.add(hub)
            hub.name = data.get("name") or hub.name or data["id"]
            hub.model = data.get("model") or hub.model or "Gemini-S1/R528"
            if data.get("vela_version") is not None:
                hub.vela_version = data["vela_version"]
            if data.get("firmware_ver") is not None:
                hub.firmware_ver = data["firmware_ver"]
            if data.get("ip_address"):
                hub.ip_address = data["ip_address"]
            if data.get("capabilities"):
                hub.capabilities_json = data["capabilities"]
            if data.get("is_online"):
                hub.is_online = True
                hub.last_heartbeat = datetime.utcnow()
            await db.commit()
            await db.refresh(hub)
            result = hub
        await self._broadcast_topology("hub_registered", hub_to_dict(result))
        return result

    async def deregister_hub(self, hub_id: str) -> bool:
        async with async_session_factory() as db:
            hub = await db.get(Hub, hub_id)
            if hub is None:
                return False
            await db.delete(hub)
            await db.commit()
        await self._broadcast_topology("hub_deregistered", {"id": hub_id})
        return True

    async def hub_heartbeat(
        self, hub_id: str, payload: dict[str, Any] | None = None
    ) -> Hub | None:
        payload = payload or {}
        async with async_session_factory() as db:
            hub = await db.get(Hub, hub_id)
            if hub is None:
                hub = Hub(id=hub_id, tenant_id=DEFAULT_TENANT_ID, name=f"R528 中枢-{hub_id}")
                db.add(hub)
            hub.is_online = True
            hub.last_heartbeat = datetime.utcnow()
            for key in ("vela_version", "firmware_ver", "ip_address", "cloud_link"):
                if payload.get(key) is not None:
                    setattr(hub, key, payload[key])
            if payload.get("capabilities"):
                hub.capabilities_json = payload["capabilities"]
            await db.commit()
            await db.refresh(hub)
            result = hub
        await self._broadcast_topology("hub_heartbeat", {"id": hub_id, "is_online": True})
        return result

    async def set_cloud_link(self, hub_id: str, state: str) -> str | None:
        """Record hub↔cloud link state and trigger offline replay on recovery."""
        if state not in ("online", "offline", "unknown"):
            state = "unknown"
        previous = None
        async with async_session_factory() as db:
            hub = await db.get(Hub, hub_id)
            if hub is None:
                return None
            previous = hub.cloud_link
            hub.cloud_link = state
            await db.commit()

        from app.services.cloud_state import cloud_state

        cloud_state.update(hub_id, state)
        logger.info("[Topology] hub %s cloud_link %s -> %s", hub_id, previous, state)
        await self._broadcast_topology(
            "cloud_link", {"hub_id": hub_id, "cloud_link": state}
        )
        if previous == "offline" and state == "online":
            from app.services.hub_offline import hub_offline

            replayed = await hub_offline.replay(hub_id)
            await self._broadcast_topology(
                "offline_replay", {"hub_id": hub_id, "replayed": replayed}
            )
        return state

    # ── Edge ──────────────────────────────────────────────────────────

    async def register_edge(self, data: dict[str, Any]) -> EdgeNode:
        hub_id = data.get("hub_id") or DEFAULT_HUB_ID
        async with async_session_factory() as db:
            hub = await db.get(Hub, hub_id)
            if hub is None:
                hub = Hub(
                    id=hub_id, tenant_id=DEFAULT_TENANT_ID,
                    name=f"R528 中枢-{hub_id}", model="Gemini-S1/R528",
                )
                db.add(hub)
            edge = await db.get(EdgeNode, data["id"])
            if edge is None:
                edge = EdgeNode(id=data["id"], tenant_id=DEFAULT_TENANT_ID)
                db.add(edge)
            edge.hub_id = hub_id
            edge.name = data.get("name") or edge.name or f"边缘节点-{data['id']}"
            if data.get("board_model"):
                edge.board_model = data["board_model"]
            if data.get("firmware_ver") is not None:
                edge.firmware_ver = data["firmware_ver"]
            caps = set(data.get("capabilities") or [])
            for cap, column in _CAP_KEYS.items():
                if cap in caps:
                    setattr(edge, column, True)
            if data.get("is_online"):
                edge.is_online = True
                edge.last_heartbeat = datetime.utcnow()
            await db.commit()
            await db.refresh(edge)
            result = edge
        _hub_binding_cache[data["id"]] = hub_id
        await self._broadcast_topology("edge_registered", edge_to_dict(result))
        return result

    async def deregister_edge(self, edge_id: str) -> bool:
        async with async_session_factory() as db:
            edge = await db.get(EdgeNode, edge_id)
            if edge is None:
                return False
            await db.delete(edge)
            await db.commit()
        _hub_binding_cache.pop(edge_id, None)
        await self._broadcast_topology("edge_deregistered", {"id": edge_id})
        return True

    async def edge_heartbeat(
        self,
        edge_id: str,
        payload: dict[str, Any] | None = None,
        *,
        hub_id: str | None = None,
        online: bool = True,
    ) -> EdgeNode:
        """Upsert an edge from a status message; never raises on bad payload."""
        payload = payload or {}
        hub_id = hub_id or payload.get("hub_id") or DEFAULT_HUB_ID
        telemetry = {
            key: payload[key]
            for key in (
                "rssi", "wifi_rssi", "free_heap", "mem_free", "fps",
                "light", "temperature", "ip", "battery",
            )
            if key in payload
        }
        caps = payload.get("capabilities") or payload.get("caps") or []
        async with async_session_factory() as db:
            hub = await db.get(Hub, hub_id)
            if hub is None:
                hub = Hub(
                    id=hub_id, tenant_id=DEFAULT_TENANT_ID,
                    name=f"R528 中枢-{hub_id}", model="Gemini-S1/R528",
                )
                db.add(hub)
                await db.flush()
            edge = await db.get(EdgeNode, edge_id)
            created = edge is None
            if created:
                edge = EdgeNode(id=edge_id, tenant_id=DEFAULT_TENANT_ID, name=f"边缘节点-{edge_id}")
                db.add(edge)
            edge.hub_id = hub_id
            edge.is_online = online
            edge.last_heartbeat = datetime.utcnow()
            if payload.get("firmware_ver") or payload.get("firmware"):
                edge.firmware_ver = payload.get("firmware_ver") or payload.get("firmware")
            if isinstance(caps, list):
                for cap, column in _CAP_KEYS.items():
                    if cap in caps:
                        setattr(edge, column, True)
            merged = dict(edge.telemetry_json or {})
            merged.update({k: v for k, v in telemetry.items() if v is not None})
            edge.telemetry_json = merged
            await db.commit()
            await db.refresh(edge)
            result = edge
        _hub_binding_cache[edge_id] = hub_id
        await self._broadcast_topology(
            "edge_heartbeat",
            {"id": edge_id, "hub_id": hub_id, "is_online": online, "telemetry": telemetry},
        )
        return result

    async def mark_edge_offline(self, edge_id: str) -> None:
        async with async_session_factory() as db:
            edge = await db.get(EdgeNode, edge_id)
            if edge and edge.is_online:
                edge.is_online = False
                await db.commit()
        await self._broadcast_topology("edge_heartbeat", {"id": edge_id, "is_online": False})

    async def hub_for_edge(self, edge_id: str) -> str:
        if edge_id in _hub_binding_cache:
            return _hub_binding_cache[edge_id]
        async with async_session_factory() as db:
            edge = await db.get(EdgeNode, edge_id)
            hub_id = edge.hub_id if edge and edge.hub_id else DEFAULT_HUB_ID
        _hub_binding_cache[edge_id] = hub_id
        return hub_id

    # ── Reads ─────────────────────────────────────────────────────────

    async def list_hubs(self, tenant_id: int = DEFAULT_TENANT_ID) -> list[dict[str, Any]]:
        async with async_session_factory() as db:
            hubs = (await db.execute(
                select(Hub).where(Hub.tenant_id == tenant_id).order_by(Hub.id)
            )).scalars().all()
            edges = (await db.execute(
                select(EdgeNode).where(EdgeNode.tenant_id == tenant_id).order_by(EdgeNode.id)
            )).scalars().all()
        edges_by_hub: dict[str, list[EdgeNode]] = {}
        for edge in edges:
            edges_by_hub.setdefault(edge.hub_id or DEFAULT_HUB_ID, []).append(edge)
        return [hub_to_dict(hub, edges_by_hub.get(hub.id, [])) for hub in hubs]

    async def list_edges(
        self, hub_id: str | None = None, tenant_id: int = DEFAULT_TENANT_ID
    ) -> list[dict[str, Any]]:
        async with async_session_factory() as db:
            query = select(EdgeNode).where(EdgeNode.tenant_id == tenant_id)
            if hub_id:
                query = query.where(EdgeNode.hub_id == hub_id)
            edges = (await db.execute(query.order_by(EdgeNode.id))).scalars().all()
        return [edge_to_dict(edge) for edge in edges]

    # ── Fan-out ───────────────────────────────────────────────────────

    async def _broadcast_topology(self, event_type: str, data: dict[str, Any]) -> None:
        # Global WS feed (/ws/events) used by the topology dashboard (#6).
        await ws_manager.broadcast("topology", {"event": event_type, **data})
        # Authenticated demo feed as well, so /ws/demo-events gets one stream.
        await demo_event_bus.publish("topology", {"event": event_type, **data})


topology = TopologyService()
