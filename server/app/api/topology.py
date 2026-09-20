"""Hub/Edge topology API and hub command channel (OPE-100).

Endpoints (all under /api):
  GET    /hubs                      list R528 hubs with bound edges
  POST   /hubs                      register a hub
  GET    /hubs/{hub_id}             hub detail
  DELETE /hubs/{hub_id}             deregister a hub (also unlinks edges)
  POST   /hubs/{hub_id}/heartbeat   hub heartbeat (vela version, cloud_link)
  POST   /hubs/{hub_id}/command     publish a command to hub/<id>/cmd
  POST   /hubs/{hub_id}/cloud-link  force online/offline (degrade demo/replay)

  GET    /edges                     list edge nodes (?hub_id=)
  POST   /edges                     register an edge node
  DELETE /edges/{edge_id}           deregister
  POST   /edges/{edge_id}/heartbeat edge heartbeat (caps + RSSI/heap/fps)

  GET    /topology                  full hubs+edges graph for the dashboard
  GET    /offline-queue             staged edge events while cloud is down
  POST   /offline-queue/replay      force replay now

Live updates (registration, heartbeats, cloud-link changes, replay) are
pushed over the existing WebSocket /ws/events?token=... as
``{"type": "topology", "data": {"event": ...}}``; decisions flow on the
same socket as ``{"type": "recognition", ...}``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.middleware.auth import get_current_user, require_permission
from app.models.database import get_db
from app.models.models import EdgeEventQueue, User as UserModel
from app.schemas.schemas import ResponseWrapper
from app.services.topology import topology

router = APIRouter(prefix="/api", tags=["topology"])


# ── Request models ────────────────────────────────────────────────────
class HubRegister(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = ""
    model: str = "Gemini-S1/R528"
    vela_version: str = ""
    firmware_ver: str = ""
    ip_address: str = ""
    capabilities: list[str] = Field(default_factory=list)


class HubHeartbeat(BaseModel):
    vela_version: str | None = None
    firmware_ver: str | None = None
    ip_address: str | None = None
    cloud_link: str | None = None
    capabilities: list[str] | None = None


class HubCommand(BaseModel):
    cmd: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)


class CloudLink(BaseModel):
    state: str = Field(pattern="^(online|offline|unknown)$")


class EdgeRegister(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    hub_id: str | None = None
    name: str = ""
    board_model: str = "XIAO_ESP32S3_SENSE"
    firmware_ver: str = ""
    capabilities: list[str] = Field(default_factory=list)


class EdgeHeartbeat(BaseModel):
    firmware_ver: str | None = None
    capabilities: list[str] | None = None
    rssi: float | None = None
    wifi_rssi: float | None = None
    free_heap: int | None = None
    fps: float | None = None
    light: float | None = None


# ── Hub ───────────────────────────────────────────────────────────────
@router.get("/hubs", response_model=ResponseWrapper[list[dict]])
async def list_hubs(
    user: UserModel = Depends(get_current_user),
    _=Depends(require_permission("device:read")),
):
    return ResponseWrapper(data=await topology.list_hubs(user.tenant_id))


@router.post("/hubs", response_model=ResponseWrapper[dict], status_code=201)
async def register_hub(
    body: HubRegister,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_permission("device:write")),
):
    hub = await topology.register_hub(body.model_dump())
    from app.services.topology import hub_to_dict
    return ResponseWrapper(data=hub_to_dict(hub))


@router.get("/hubs/{hub_id}", response_model=ResponseWrapper[dict])
async def get_hub(
    hub_id: str,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("device:read")),
):
    from app.models.models import EdgeNode, Hub
    from app.services.topology import hub_to_dict
    hub = await db.get(Hub, hub_id)
    if not hub or hub.tenant_id != user.tenant_id:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "中枢不存在"})
    edges = (await db.execute(
        select(EdgeNode).where(EdgeNode.hub_id == hub_id)
    )).scalars().all()
    return ResponseWrapper(data=hub_to_dict(hub, edges))


@router.delete("/hubs/{hub_id}", status_code=204)
async def deregister_hub(
    hub_id: str,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_permission("device:write")),
):
    if not await topology.deregister_hub(hub_id):
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "中枢不存在"})


@router.post("/hubs/{hub_id}/heartbeat", response_model=ResponseWrapper[dict])
async def hub_heartbeat(
    hub_id: str,
    body: HubHeartbeat,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_permission("device:write")),
):
    hub = await topology.hub_heartbeat(hub_id, body.model_dump(exclude_none=True))
    if body.cloud_link:
        await topology.set_cloud_link(hub_id, body.cloud_link)
    from app.services.topology import hub_to_dict
    return ResponseWrapper(data=hub_to_dict(hub))


@router.post("/hubs/{hub_id}/command", response_model=ResponseWrapper[dict])
async def hub_command(
    hub_id: str,
    body: HubCommand,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_permission("device:write")),
):
    """Publish a command to ``hub/<hub_id>/cmd`` for the R528 to execute."""
    from app.services.mqtt_client import mqtt_client

    # Hub command channel (hub/<id>/cmd); consumed by the R528 hub service).
    topic = f"hub/{hub_id}/cmd"
    envelope = {
        "hub_id": hub_id,
        "cmd": body.cmd,
        "params": body.params,
        "issued_by": user.username,
        "ts": datetime.utcnow().isoformat() + "Z",
    }
    mqtt_client.publish(topic, envelope)
    return ResponseWrapper(data={"status": "sent", "mqtt_topic": topic, **envelope})


@router.post("/hubs/{hub_id}/cloud-link", response_model=ResponseWrapper[dict])
async def set_hub_cloud_link(
    hub_id: str,
    body: CloudLink,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_permission("device:write")),
):
    """Force the hub↔cloud link state (used by the offline-degrade demo).

    Setting offline starts SQLite staging of edge events; setting back to
    online replays the staged events into the cloud outbox automatically.
    """
    from app.services.cloud_state import cloud_state

    cloud_state.force(hub_id, body.state)
    state = await topology.set_cloud_link(hub_id, body.state)
    if state is None:
        # Auto-create the hub so the demo script works without registration.
        await topology.hub_heartbeat(hub_id, {"cloud_link": body.state})
        cloud_state.force(hub_id, body.state)
        state = await topology.set_cloud_link(hub_id, body.state)
    return ResponseWrapper(data={"hub_id": hub_id, "cloud_link": state})


# ── Edge ──────────────────────────────────────────────────────────────
@router.get("/edges", response_model=ResponseWrapper[list[dict]])
async def list_edges(
    hub_id: str | None = Query(None),
    user: UserModel = Depends(get_current_user),
    _=Depends(require_permission("device:read")),
):
    return ResponseWrapper(data=await topology.list_edges(hub_id, user.tenant_id))


@router.post("/edges", response_model=ResponseWrapper[dict], status_code=201)
async def register_edge(
    body: EdgeRegister,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_permission("device:write")),
):
    data = body.model_dump()
    data["hub_id"] = data.pop("hub_id") or None
    edge = await topology.register_edge(data)
    from app.services.topology import edge_to_dict
    return ResponseWrapper(data=edge_to_dict(edge))


@router.delete("/edges/{edge_id}", status_code=204)
async def deregister_edge(
    edge_id: str,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_permission("device:write")),
):
    if not await topology.deregister_edge(edge_id):
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "边缘节点不存在"})


@router.post("/edges/{edge_id}/heartbeat", response_model=ResponseWrapper[dict])
async def edge_heartbeat(
    edge_id: str,
    body: EdgeHeartbeat,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_permission("device:write")),
):
    edge = await topology.edge_heartbeat(edge_id, body.model_dump(exclude_none=True))
    from app.services.topology import edge_to_dict
    return ResponseWrapper(data=edge_to_dict(edge))


# ── Topology graph + offline queue ────────────────────────────────────
@router.get("/topology", response_model=ResponseWrapper[dict])
async def get_topology(
    user: UserModel = Depends(get_current_user),
    _=Depends(require_permission("device:read")),
):
    hubs = await topology.list_hubs(user.tenant_id)
    from app.services.hub_offline import hub_offline
    queue_depth = await hub_offline.depth()
    return ResponseWrapper(data={
        "hubs": hubs,
        "hub_count": len(hubs),
        "edge_count": sum(len(h["edges"]) for h in hubs),
        "offline_queue_depth": queue_depth,
        "mqtt": {
            "mode": _mqtt_mode(),
            "broker": f"{settings.MQTT_BROKER}:{settings.MQTT_PORT}",
        },
    })


@router.get("/offline-queue", response_model=ResponseWrapper[dict])
async def offline_queue(
    hub_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("device:read")),
):
    query = select(EdgeEventQueue)
    if hub_id:
        query = query.where(EdgeEventQueue.hub_id == hub_id)
    rows = (await db.execute(
        query.order_by(EdgeEventQueue.created_at.desc()).limit(limit)
    )).scalars().all()
    queued = (await db.execute(
        select(func.count()).select_from(EdgeEventQueue).where(
            EdgeEventQueue.status == "queued"
        )
    )).scalar() or 0
    return ResponseWrapper(data={
        "queued_depth": queued,
        "items": [{
            "id": r.id,
            "hub_id": r.hub_id,
            "edge_id": r.edge_id,
            "channel": r.channel,
            "topic": r.topic,
            "status": r.status,
            "created_at": r.created_at.isoformat() + "Z",
            "delivered_at": r.delivered_at.isoformat() + "Z" if r.delivered_at else None,
        } for r in rows],
    })


@router.post("/offline-queue/replay", response_model=ResponseWrapper[dict])
async def replay_offline_queue(
    user: UserModel = Depends(get_current_user),
    _=Depends(require_permission("device:write")),
):
    from app.services.hub_offline import hub_offline
    replayed = await hub_offline.replay()
    return ResponseWrapper(data={"replayed": replayed})


def _mqtt_mode() -> str:
    try:
        from app.services.mqtt_client import mqtt_client
        return mqtt_client.mode
    except Exception:
        return "unknown"
