"""Dashboard API router: overview summary, trend, device status distribution."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user, require_permission
from app.models.database import get_db
from app.models.models import Alert, Device, EnergyLog, Event, Person
from app.models.models import Visitor
from app.models.models import User as UserModel
from app.schemas.schemas import (
    DashboardOverview,
    DashboardTrendItem,
    DeviceStatusDistribution,
    ResponseWrapper,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=ResponseWrapper[DashboardOverview])
async def dashboard_summary(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:view")),
):
    """Return aggregate dashboard overview for the current tenant."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Device counts
    total_dev_q = select(func.count()).select_from(
        select(Device).where(Device.tenant_id == user.tenant_id).subquery()
    )
    total_devices = (await db.execute(total_dev_q)).scalar() or 0

    online_dev_q = select(func.count()).select_from(
        select(Device).where(
            Device.tenant_id == user.tenant_id, Device.is_online == True  # noqa: E712
        ).subquery()
    )
    online_devices = (await db.execute(online_dev_q)).scalar() or 0

    # Today persons
    today_person_q = select(func.count()).select_from(
        select(Person).where(Person.tenant_id == user.tenant_id).subquery()
    )
    today_persons = (await db.execute(today_person_q)).scalar() or 0

    # Today events (recognition passes)
    today_event_q = select(func.count()).select_from(
        select(Event).where(
            Event.tenant_id == user.tenant_id,
            Event.created_at >= today_start,
        ).subquery()
    )
    today_events = (await db.execute(today_event_q)).scalar() or 0
    today_pass_q = select(func.count()).select_from(
        select(Event).where(
            Event.tenant_id == user.tenant_id,
            Event.created_at >= today_start,
            Event.decision == "granted",
        ).subquery()
    )
    today_pass = (await db.execute(today_pass_q)).scalar() or 0

    # Alert count
    alert_q = select(func.count()).select_from(
        select(Alert).where(
            Alert.tenant_id == user.tenant_id,
            Alert.resolved_at == None,  # noqa: E711
        ).subquery()
    )
    alert_count = (await db.execute(alert_q)).scalar() or 0

    # Today visitors
    today_visitor_q = select(func.count()).select_from(
        select(Visitor).where(
            Visitor.tenant_id == user.tenant_id,
            Visitor.expected_at >= today_start,
        ).subquery()
    )
    today_visitors = (await db.execute(today_visitor_q)).scalar() or 0

    return ResponseWrapper(data=DashboardOverview(
        today_person_count=today_persons,
        today_pass_count=today_pass,
        alert_count=alert_count,
        total_devices=total_devices,
        online_devices=online_devices,
        offline_devices=total_devices - online_devices,
        device_online_rate=round(online_devices / total_devices, 2) if total_devices > 0 else 0,
        today_visitor_count=today_visitors,
    ))


@router.get("/trend", response_model=ResponseWrapper[list[DashboardTrendItem]])
async def dashboard_trend(
    days: int = 7,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:view")),
):
    """Return daily pass-count trend for the last N days."""
    since = datetime.utcnow() - timedelta(days=days)
    # Query events grouped by date
    date_col = func.date(Event.created_at)
    q = select(
        date_col.label("day"),
        func.count().label("pass_count"),
    ).where(
        Event.tenant_id == user.tenant_id,
        Event.created_at >= since,
        Event.decision == "granted",
    ).group_by(date_col).order_by(date_col)

    result = await db.execute(q)
    rows = result.fetchall()
    day_map = {row[0]: row[1] for row in rows}

    trend = []
    for i in range(days - 1, -1, -1):
        d = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        trend.append(DashboardTrendItem(date=d, pass_count=day_map.get(d, 0)))

    return ResponseWrapper(data=trend)


@router.get("/device-status", response_model=ResponseWrapper[DeviceStatusDistribution])
async def dashboard_device_status(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:view")),
):
    """Return device online/offline/alert distribution."""
    total_dev_q = select(func.count()).select_from(
        select(Device).where(Device.tenant_id == user.tenant_id).subquery()
    )
    total = (await db.execute(total_dev_q)).scalar() or 0

    online_q = select(func.count()).select_from(
        select(Device).where(
            Device.tenant_id == user.tenant_id, Device.is_online == True  # noqa: E712
        ).subquery()
    )
    online = (await db.execute(online_q)).scalar() or 0

    alert_q = select(func.count()).select_from(
        select(Alert).where(
            Alert.tenant_id == user.tenant_id,
            Alert.resolved_at == None,  # noqa: E711
        ).subquery()
    )
    alerts = (await db.execute(alert_q)).scalar() or 0

    return ResponseWrapper(data=DeviceStatusDistribution(
        online_count=online,
        offline_count=total - online,
        alert_count=alerts,
    ))
