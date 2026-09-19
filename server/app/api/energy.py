"""Energy API router: energy data query, summary, per-area breakdown."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user, require_permission
from app.models.database import get_db
from app.models.models import EnergyLog, Space
from app.models.models import User as UserModel
from app.schemas.schemas import (
    EnergyByAreaItem,
    EnergyResponse,
    EnergySummary,
    PaginatedResponse,
    Pagination,
    ResponseWrapper,
)

router = APIRouter(prefix="/api/energy", tags=["energy"])


@router.get("", response_model=PaginatedResponse[EnergyResponse])
async def list_energy_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    device_id: Optional[int] = Query(None),
    space_id: Optional[int] = Query(None),
    metric: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    sort_by: str = Query("recorded_at"),
    sort_order: str = Query("desc"),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("energy:read")),
):
    query = select(EnergyLog).where(EnergyLog.tenant_id == user.tenant_id)

    if device_id:
        query = query.where(EnergyLog.device_id == device_id)
    if space_id:
        query = query.where(EnergyLog.space_id == space_id)
    if metric:
        query = query.where(EnergyLog.metric == metric)
    if date_from:
        query = query.where(EnergyLog.recorded_at >= date_from)
    if date_to:
        query = query.where(EnergyLog.recorded_at <= date_to)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    sort_col = getattr(EnergyLog, sort_by, EnergyLog.recorded_at)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    logs = result.scalars().all()

    return PaginatedResponse(
        data=[
            EnergyResponse(
                id=log.id, device_id=log.device_id, space_id=log.space_id,
                metric=log.metric, value=log.value, unit=log.unit or "",
                source=log.source or "device", recorded_at=log.recorded_at,
            )
            for log in logs
        ],
        pagination=Pagination(page=page, page_size=page_size, total=total,
                               total_pages=(total + page_size - 1) // page_size),
    )


@router.get("/summary", response_model=ResponseWrapper[EnergySummary])
async def get_energy_summary(
    space_id: Optional[int] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    granularity: str = Query("daily"),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("energy:read")),
):
    query = select(EnergyLog).where(
        EnergyLog.tenant_id == user.tenant_id,
        EnergyLog.metric == "power",
    )
    if space_id:
        query = query.where(EnergyLog.space_id == space_id)
    if date_from:
        query = query.where(EnergyLog.recorded_at >= date_from)
    if date_to:
        query = query.where(EnergyLog.recorded_at <= date_to)

    result = await db.execute(query)
    logs = result.scalars().all()

    if not logs:
        return ResponseWrapper(data=EnergySummary(
            total_kwh=0, avg_power_w=0, peak_power_w=0,
        ))

    values = [log.value for log in logs if log.metric == "power" or log.metric == "energy"]

    summary = EnergySummary(
        total_kwh=round(sum(values) / 1000, 2) if values else 0,
        avg_power_w=round(sum(values) / len(values), 1) if values else 0,
        peak_power_w=round(max(values), 1) if values else 0,
    )
    return ResponseWrapper(data=summary)


@router.get("/by-area", response_model=ResponseWrapper[list[EnergyByAreaItem]])
async def get_energy_by_area(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("energy:read")),
):
    """Return energy consumption broken down by area/space."""
    # Query spaces at the area/room level (top-level spaces)
    spaces_q = select(Space).where(
        Space.tenant_id == user.tenant_id,
        Space.type.in_(["area", "room", "floor"]),
    )
    spaces_result = await db.execute(spaces_q)
    spaces = spaces_result.scalars().all()

    if not spaces:
        return ResponseWrapper(data=[])

    # Sum energy per space
    items = []
    total_energy = 0.0
    for space in spaces:
        energy_q = select(func.sum(EnergyLog.value)).where(
            EnergyLog.tenant_id == user.tenant_id,
            EnergyLog.space_id == space.id,
            EnergyLog.metric == "power",
        )
        if date_from:
            energy_q = energy_q.where(EnergyLog.recorded_at >= date_from)
        if date_to:
            energy_q = energy_q.where(EnergyLog.recorded_at <= date_to)
        val = (await db.execute(energy_q)).scalar() or 0.0
        kwh = round(val / 1000, 2)
        if kwh > 0:
            total_energy += kwh
            items.append(EnergyByAreaItem(
                space_id=space.id,
                space_name=space.name,
                energy_kwh=kwh,
                percentage=0.0,
            ))

    # Normalize percentages
    if total_energy > 0:
        for item in items:
            item.percentage = round(item.energy_kwh / total_energy * 100, 1)

    return ResponseWrapper(data=items)


@router.get("/trend", response_model=ResponseWrapper[list])
async def get_energy_trend(
    days: int = Query(30, ge=1, le=365),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("energy:read")),
):
    """Return daily energy consumption trend."""
    from datetime import timedelta
    since = datetime.utcnow() - timedelta(days=days)

    date_col = func.date(EnergyLog.recorded_at)
    q = select(
        date_col.label("day"),
        func.sum(EnergyLog.value).label("energy_value"),
    ).where(
        EnergyLog.tenant_id == user.tenant_id,
        EnergyLog.metric == "power",
        EnergyLog.recorded_at >= since,
    ).group_by(date_col).order_by(date_col)

    result = await db.execute(q)
    rows = result.fetchall()

    day_map = {}
    for row in rows:
        date_str = row[0] if isinstance(row[0], str) else row[0].strftime("%Y-%m-%d")
        day_map[date_str] = round(row[1] / 1000, 2)

    trend = []
    for i in range(days, 0, -1):
        d = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        trend.append({
            "date": d,
            "avg_power_kw": 0,
            "energy_kwh": day_map.get(d, 0),
        })

    return ResponseWrapper(data=trend)
