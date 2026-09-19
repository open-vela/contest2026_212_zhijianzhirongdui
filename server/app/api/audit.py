"""Audit API router: security audit log query, alert management."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user, require_permission
from app.models.database import get_db
from app.models.models import Alert
from app.models.models import AuditLog
from app.models.models import User as UserModel
from app.schemas.schemas import (
    AlertResolve,
    AlertResponse,
    AuditLogResponse,
    PaginatedResponse,
    Pagination,
    ResponseWrapper,
)

router = APIRouter(prefix="/api/audit", tags=["audit"])


# ── Audit Logs ───────────────────────────────────────────────────────

@router.get("/logs", response_model=PaginatedResponse[AuditLogResponse])
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("audit:read")),
):
    query = select(AuditLog).where(AuditLog.tenant_id == current_user.tenant_id)

    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if date_from:
        query = query.where(AuditLog.created_at >= date_from)
    if date_to:
        query = query.where(AuditLog.created_at <= date_to)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    sort_col = getattr(AuditLog, sort_by, AuditLog.created_at)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    logs = result.scalars().all()

    return PaginatedResponse(
        data=[
            AuditLogResponse(
                id=log.id, user_id=log.user_id,
                username=str(log.user_id),
                action=log.action, resource_type=log.resource_type,
                resource_id=log.resource_id or "",
                detail_json=log.detail_json or {},
                ip_address=log.ip_address or "",
                created_at=log.created_at,
            )
            for log in logs
        ],
        pagination=Pagination(page=page, page_size=page_size, total=total,
                               total_pages=(total + page_size - 1) // page_size),
    )


# ── Alerts ───────────────────────────────────────────────────────────

def _alert_response(a: Alert) -> AlertResponse:
    return AlertResponse(
        id=a.id,
        level=a.level or "info",
        type=a.type or "",
        title=a.title or "",
        message=a.message or "",
        related_event_id=a.related_event_id,
        related_person_id=a.related_person_id,
        related_device_id=a.related_device_id,
        is_resolved=a.resolved_at is not None,
        resolved_by=a.resolved_by,
        resolved_at=a.resolved_at,
        created_at=a.created_at,
    )


@router.get("/alerts", response_model=PaginatedResponse[AlertResponse])
async def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    level: Optional[str] = Query(None),
    is_resolved: Optional[bool] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("audit:read")),
):
    query = select(Alert).where(Alert.tenant_id == current_user.tenant_id)

    if level:
        query = query.where(Alert.level == level)
    if is_resolved is not None:
        if is_resolved:
            query = query.where(Alert.resolved_at != None)  # noqa: E711
        else:
            query = query.where(Alert.resolved_at == None)  # noqa: E711
    if date_from:
        query = query.where(Alert.created_at >= date_from)
    if date_to:
        query = query.where(Alert.created_at <= date_to)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    sort_col = getattr(Alert, sort_by, Alert.created_at)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    alerts = result.scalars().all()

    return PaginatedResponse(
        data=[_alert_response(a) for a in alerts],
        pagination=Pagination(page=page, page_size=page_size, total=total,
                               total_pages=(total + page_size - 1) // page_size),
    )


@router.patch("/alerts/{alert_id}/resolve", response_model=ResponseWrapper[AlertResponse])
async def resolve_alert(
    alert_id: int,
    body: AlertResolve,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("audit:write")),
):
    alert = await db.get(Alert, alert_id)
    if not alert or alert.tenant_id != current_user.tenant_id:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "告警不存在"})
    if alert.resolved_at is not None:
        raise HTTPException(400, detail={"code": "ALREADY_RESOLVED", "message": "告警已被处理"})

    alert.resolved_by = body.resolved_by or current_user.id
    alert.resolved_at = datetime.utcnow()
    await db.flush()
    return ResponseWrapper(data=_alert_response(alert))
