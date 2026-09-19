"""Events API router: recognition event query, stats, recent."""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user, require_permission
from app.models.database import get_db
from app.models.models import Alert, Device, Event
from app.models.models import User as UserModel
from app.schemas.schemas import (
    EventResponse,
    EventStats,
    PaginatedResponse,
    Pagination,
    RecognitionResponse,
    ResponseWrapper,
)

router = APIRouter(prefix="/api/events", tags=["events"])
recognition_router = APIRouter(prefix="/api/recognitions", tags=["recognitions"])


def _event_response(e: Event) -> EventResponse:
    return EventResponse(
        id=e.id, person_id=e.person_id, person_name=e.person_name or "",
        node_id=e.node_id or "", device_name="", face_conf=e.face_conf or 0,
        gait_conf=e.gait_conf or 0, ble_conf=e.ble_conf or 0,
        fusion_conf=e.fusion_conf or 0, modality_count=e.modality_count or 0,
        decision=e.decision or "unknown", explain_text=e.explain_text or "",
        is_alert=e.is_alert or False, created_at=e.created_at,
    )


@router.get("", response_model=PaginatedResponse[EventResponse])
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    person_id: Optional[int] = Query(None),
    node_id: Optional[str] = Query(None),
    decision: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    min_confidence: Optional[float] = Query(None, ge=0, le=1),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("event:read")),
):
    query = select(Event).where(Event.tenant_id == user.tenant_id)

    if person_id:
        query = query.where(Event.person_id == person_id)
    if node_id:
        query = query.where(Event.node_id == node_id)
    if decision:
        query = query.where(Event.decision == decision)
    if date_from:
        query = query.where(Event.created_at >= date_from)
    if date_to:
        query = query.where(Event.created_at <= date_to)
    if min_confidence is not None:
        query = query.where(Event.fusion_conf >= min_confidence)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    sort_col = getattr(Event, sort_by, Event.created_at)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    events = result.scalars().all()

    # Enrich with device names
    data = []
    for e in events:
        resp = _event_response(e)
        if e.device_id:
            device = await db.get(Device, e.device_id)
            if device:
                resp.device_name = device.name or device.node_id
        data.append(resp)

    return PaginatedResponse(
        data=data,
        pagination=Pagination(page=page, page_size=page_size, total=total,
                               total_pages=(total + page_size - 1) // page_size),
    )


@router.get("/stats", response_model=ResponseWrapper[EventStats])
async def get_event_stats(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("event:read")),
):
    query = select(Event).where(Event.tenant_id == user.tenant_id)
    if date_from:
        query = query.where(Event.created_at >= date_from)
    if date_to:
        query = query.where(Event.created_at <= date_to)

    result = await db.execute(query)
    events = result.scalars().all()

    total = len(events)
    granted = sum(1 for e in events if e.decision == "granted")
    denied = sum(1 for e in events if e.decision == "denied")
    unknown = total - granted - denied

    stats = EventStats(
        total_events=total,
        granted_count=granted,
        denied_count=denied,
        unknown_count=unknown,
        grant_rate=round(granted / total, 3) if total > 0 else 0,
        by_hour={},
        top_persons=[],
    )
    return ResponseWrapper(data=stats)


@router.get("/recent", response_model=ResponseWrapper[list[EventResponse]])
async def get_recent_events(
    limit: int = Query(20, ge=1, le=50),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("event:read")),
):
    query = select(Event).where(
        Event.tenant_id == user.tenant_id
    ).order_by(Event.created_at.desc()).limit(limit)
    result = await db.execute(query)
    events = result.scalars().all()

    data = []
    for e in events:
        resp = _event_response(e)
        if e.device_id:
            device = await db.get(Device, e.device_id)
            if device:
                resp.device_name = device.name or device.node_id
        data.append(resp)

    return ResponseWrapper(data=data)


def _recognition_response(e: Event) -> RecognitionResponse:
    return RecognitionResponse(
        id=e.id,
        person_id=e.person_id,
        person_name=e.person_name or "",
        node_id=e.node_id or "",
        device_name="",
        face_conf=e.face_conf or 0,
        fusion_conf=e.fusion_conf or 0,
        decision=e.decision or "unknown",
        is_alert=e.is_alert or False,
        created_at=e.created_at,
    )


@recognition_router.get("", response_model=PaginatedResponse[RecognitionResponse])
async def list_recognitions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    person_id: Optional[int] = Query(None),
    node_id: Optional[str] = Query(None),
    decision: Optional[str] = Query(None),
    person_name: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("event:read")),
):
    query = select(Event).where(
        Event.tenant_id == user.tenant_id,
        Event.decision.in_(["granted", "denied"]),
    )

    if person_id:
        query = query.where(Event.person_id == person_id)
    if node_id:
        query = query.where(Event.node_id == node_id)
    if decision:
        query = query.where(Event.decision == decision)
    if person_name:
        query = query.where(Event.person_name.like(f"%{person_name}%"))
    if date_from:
        query = query.where(Event.created_at >= date_from)
    if date_to:
        query = query.where(Event.created_at <= date_to)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    sort_col = getattr(Event, sort_by, Event.created_at)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    events = result.scalars().all()

    data = []
    for e in events:
        resp = _recognition_response(e)
        if e.device_id:
            device = await db.get(Device, e.device_id)
            if device:
                resp.device_name = device.name or device.node_id
        data.append(resp)

    return PaginatedResponse(
        data=data,
        pagination=Pagination(page=page, page_size=page_size, total=total,
                               total_pages=(total + page_size - 1) // page_size),
    )
