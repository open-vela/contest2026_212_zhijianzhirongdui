"""Visitors API router: appointment, approval, check-in/out."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user, require_permission
from app.models.database import get_db
from app.models.models import User as UserModel
from app.models.models import Person, Visitor
from app.schemas.schemas import (
    PaginatedResponse,
    Pagination,
    ResponseWrapper,
    VisitorApprove,
    VisitorCreate,
    VisitorDeny,
    VisitorResponse,
    VisitorUpdate,
)

router = APIRouter(prefix="/api/visitors", tags=["visitors"])


def _visitor_to_response(v: Visitor) -> VisitorResponse:
    return VisitorResponse(
        id=v.id,
        name=v.name,
        phone=v.phone,
        id_card=v.id_card or "",
        host_person_id=v.host_person_id,
        purpose=v.purpose or "",
        expected_at=v.expected_at,
        valid_from=v.valid_from,
        valid_until=v.valid_until,
        status=v.status,
        approved_by=v.approved_by,
        approved_at=v.approved_at,
        denied_reason=v.denied_reason or "",
        checked_in_at=v.checked_in_at,
        checked_out_at=v.checked_out_at,
        created_at=v.created_at,
    )


@router.get("", response_model=PaginatedResponse[VisitorResponse])
async def list_visitors(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    sort_by: str = Query("expected_at"),
    sort_order: str = Query("desc"),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("visitor:read")),
):
    query = select(Visitor).where(Visitor.tenant_id == user.tenant_id)

    if search:
        like = f"%{search}%"
        query = query.where(Visitor.name.like(like) | Visitor.phone.like(like))
    if status_filter:
        query = query.where(Visitor.status == status_filter)
    if date_from:
        query = query.where(Visitor.expected_at >= date_from)
    if date_to:
        query = query.where(Visitor.expected_at <= date_to)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    sort_col = getattr(Visitor, sort_by, Visitor.expected_at)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    visitors = result.scalars().all()

    return PaginatedResponse(
        data=[_visitor_to_response(v) for v in visitors],
        pagination=Pagination(page=page, page_size=page_size, total=total,
                               total_pages=(total + page_size - 1) // page_size),
    )


@router.post("", response_model=ResponseWrapper[VisitorResponse], status_code=201)
async def create_visitor(
    body: VisitorCreate,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("visitor:write")),
):
    # Verify host person exists
    person = await db.get(Person, body.host_person_id)
    if not person or person.tenant_id != user.tenant_id:
        raise HTTPException(400, detail={"code": "INVALID_HOST", "message": "受访人不存在"})

    visitor = Visitor(tenant_id=user.tenant_id, status="pending", **body.model_dump())
    db.add(visitor)
    await db.flush()
    return ResponseWrapper(data=_visitor_to_response(visitor))


@router.get("/{visitor_id}", response_model=ResponseWrapper[VisitorResponse])
async def get_visitor(
    visitor_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("visitor:read")),
):
    visitor = await db.get(Visitor, visitor_id)
    if not visitor or visitor.tenant_id != user.tenant_id:
        raise HTTPException(404)
    return ResponseWrapper(data=_visitor_to_response(visitor))


@router.put("/{visitor_id}", response_model=ResponseWrapper[VisitorResponse])
async def update_visitor(
    visitor_id: int,
    body: VisitorUpdate,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("visitor:write")),
):
    visitor = await db.get(Visitor, visitor_id)
    if not visitor or visitor.tenant_id != user.tenant_id:
        raise HTTPException(404)
    if visitor.status not in ("pending",):
        raise HTTPException(400, detail={"code": "INVALID_STATUS", "message": "仅可修改待审批的预约"})

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(visitor, key, value)
    await db.flush()
    return ResponseWrapper(data=_visitor_to_response(visitor))


@router.delete("/{visitor_id}", status_code=204)
async def delete_visitor(
    visitor_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("visitor:write")),
):
    visitor = await db.get(Visitor, visitor_id)
    if not visitor or visitor.tenant_id != user.tenant_id:
        raise HTTPException(404)
    await db.delete(visitor)


@router.post("/{visitor_id}/approve", response_model=ResponseWrapper[VisitorResponse])
async def approve_visitor(
    visitor_id: int,
    body: VisitorApprove,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("visitor:approve")),
):
    visitor = await db.get(Visitor, visitor_id)
    if not visitor or visitor.tenant_id != user.tenant_id:
        raise HTTPException(404)
    if visitor.status != "pending":
        raise HTTPException(400, detail={"code": "INVALID_STATUS", "message": "仅可审批待审批的预约"})

    visitor.status = "approved"
    visitor.approved_by = body.approved_by
    visitor.approved_at = datetime.utcnow()
    await db.flush()
    return ResponseWrapper(data=_visitor_to_response(visitor))


@router.post("/{visitor_id}/deny", response_model=ResponseWrapper[VisitorResponse])
async def deny_visitor(
    visitor_id: int,
    body: VisitorDeny,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("visitor:approve")),
):
    visitor = await db.get(Visitor, visitor_id)
    if not visitor or visitor.tenant_id != user.tenant_id:
        raise HTTPException(404)
    if visitor.status != "pending":
        raise HTTPException(400, detail={"code": "INVALID_STATUS", "message": "仅可拒绝待审批的预约"})

    visitor.status = "denied"
    visitor.denied_reason = body.reason
    visitor.approved_by = body.approved_by if hasattr(body, 'approved_by') else None
    await db.flush()
    return ResponseWrapper(data=_visitor_to_response(visitor))


@router.post("/{visitor_id}/check-in", response_model=ResponseWrapper[VisitorResponse])
async def checkin_visitor(
    visitor_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("visitor:write")),
):
    visitor = await db.get(Visitor, visitor_id)
    if not visitor or visitor.tenant_id != user.tenant_id:
        raise HTTPException(404)
    if visitor.status != "approved":
        raise HTTPException(400, detail={"code": "INVALID_STATUS", "message": "仅已批准的预约可签到"})

    visitor.status = "checked_in"
    visitor.checked_in_at = datetime.utcnow()
    await db.flush()
    return ResponseWrapper(data=_visitor_to_response(visitor))


@router.post("/{visitor_id}/check-out", response_model=ResponseWrapper[VisitorResponse])
async def checkout_visitor(
    visitor_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("visitor:write")),
):
    visitor = await db.get(Visitor, visitor_id)
    if not visitor or visitor.tenant_id != user.tenant_id:
        raise HTTPException(404)
    if visitor.status != "checked_in":
        raise HTTPException(400, detail={"code": "INVALID_STATUS", "message": "仅已签到的访客可签退"})

    visitor.status = "checked_out"
    visitor.checked_out_at = datetime.utcnow()
    await db.flush()
    return ResponseWrapper(data=_visitor_to_response(visitor))
