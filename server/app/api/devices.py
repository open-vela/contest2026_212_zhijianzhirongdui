"""Devices API router: CRUD + command + status history."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user, require_permission
from app.models.database import get_db
from app.models.models import Device
from app.models.models import User as UserModel
from app.schemas.schemas import (
    DeviceCommand,
    DeviceCreate,
    DeviceResponse,
    DeviceUpdate,
    PaginatedResponse,
    Pagination,
    ResponseWrapper,
)

router = APIRouter(prefix="/api/devices", tags=["devices"])


def _device_response(d: Device) -> DeviceResponse:
    return DeviceResponse(
        id=d.id, node_id=d.node_id, name=d.name or "", location=d.location or "",
        device_type=d.device_type or "camera", board_model=d.board_model or "",
        firmware_ver=d.firmware_ver or "", ip_address=d.ip_address or "",
        is_online=d.is_online, last_seen=d.last_seen,
        config_json=d.config_json or {}, created_at=d.created_at,
    )


@router.get("", response_model=PaginatedResponse[DeviceResponse])
async def list_devices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    device_type: Optional[str] = Query(None),
    is_online: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: str = Query("last_seen"),
    sort_order: str = Query("desc"),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("device:read")),
):
    query = select(Device).where(Device.tenant_id == user.tenant_id)

    if search:
        like = f"%{search}%"
        query = query.where(Device.name.like(like) | Device.node_id.like(like) | Device.location.like(like))
    if device_type:
        query = query.where(Device.device_type == device_type)
    if is_online is not None:
        query = query.where(Device.is_online == is_online)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    sort_col = getattr(Device, sort_by, Device.last_seen)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    devices = result.scalars().all()
    return PaginatedResponse(
        data=[_device_response(d) for d in devices],
        pagination=Pagination(page=page, page_size=page_size, total=total,
                               total_pages=(total + page_size - 1) // page_size),
    )


@router.post("", response_model=ResponseWrapper[DeviceResponse], status_code=201)
async def create_device(
    body: DeviceCreate,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("device:write")),
):
    existing = await db.execute(
        select(Device).where(Device.tenant_id == user.tenant_id, Device.node_id == body.node_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, detail={"code": "CONFLICT", "message": f"节点 {body.node_id} 已注册"})

    device = Device(tenant_id=user.tenant_id, **body.model_dump())
    db.add(device)
    await db.flush()
    return ResponseWrapper(data=_device_response(device))


@router.get("/{device_id}", response_model=ResponseWrapper[DeviceResponse])
async def get_device(
    device_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("device:read")),
):
    device = await db.get(Device, device_id)
    if not device or device.tenant_id != user.tenant_id:
        raise HTTPException(404)
    return ResponseWrapper(data=_device_response(device))


@router.put("/{device_id}", response_model=ResponseWrapper[DeviceResponse])
async def update_device(
    device_id: int,
    body: DeviceUpdate,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("device:write")),
):
    device = await db.get(Device, device_id)
    if not device or device.tenant_id != user.tenant_id:
        raise HTTPException(404)

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(device, key, value)
    await db.flush()
    return ResponseWrapper(data=_device_response(device))


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("device:write")),
):
    device = await db.get(Device, device_id)
    if not device or device.tenant_id != user.tenant_id:
        raise HTTPException(404)
    await db.delete(device)


@router.post("/{device_id}/command", response_model=ResponseWrapper[dict])
async def send_command(
    device_id: int,
    body: DeviceCommand,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("device:write")),
):
    device = await db.get(Device, device_id)
    if not device or device.tenant_id != user.tenant_id:
        raise HTTPException(404)

    from app.config import settings
    from app.services.mqtt_client import mqtt_client

    topic = f"{settings.MQTT_TOPIC_PREFIX}/server/command/{device.node_id}"
    mqtt_client.publish(topic, {
        "cmd": body.command,
        "params": body.params,
        "ts": datetime.utcnow().isoformat(),
    })

    return ResponseWrapper(data={
        "status": "sent",
        "mqtt_topic": topic,
        "command": body.command,
    })


@router.get("/{device_id}/status/history", response_model=ResponseWrapper[list])
async def get_device_status_history(
    device_id: int,
    limit: int = Query(100, ge=1, le=1000),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("device:read")),
):
    # Status history stored in events table with node_id reference
    from app.models.models import Event
    device = await db.get(Device, device_id)
    if not device or device.tenant_id != user.tenant_id:
        raise HTTPException(404)

    query = select(Event).where(
        Event.node_id == device.node_id, Event.decision == "status"
    ).order_by(Event.created_at.desc()).limit(limit)
    result = await db.execute(query)
    events = result.scalars().all()

    return ResponseWrapper(data=[
        {
            "timestamp": e.created_at.isoformat(),
            "free_heap": e.raw_data_json.get("free_heap", 0) if e.raw_data_json else 0,
            "wifi_rssi": e.raw_data_json.get("wifi_rssi", 0) if e.raw_data_json else 0,
            "fps": e.raw_data_json.get("fps", 0) if e.raw_data_json else 0,
            "temp": e.raw_data_json.get("temp", 0) if e.raw_data_json else 0,
        }
        for e in events
    ])
