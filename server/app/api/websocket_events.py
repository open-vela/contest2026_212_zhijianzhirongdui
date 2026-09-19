"""WebSocket endpoint for real-time event streaming."""

import json
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import decode_token
from app.models.database import get_db
from app.models.models import Alert, Device, Event, Person, User
from app.schemas.schemas import RealtimeOverview
from app.services.ws_manager import ws_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    """WebSocket endpoint for real-time event streaming.

    Clients must pass JWT token as a query parameter: /ws/events?token=<TOKEN>
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Validate token
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub", 0))
        user = await db.get(User, user_id)
        if not user or not user.is_active:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    client_id = f"user_{user_id}_{uuid.uuid4().hex[:8]}"
    await ws_manager.connect(websocket, client_id)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except (WebSocketDisconnect, json.JSONDecodeError):
        pass
    finally:
        await ws_manager.disconnect(client_id)


@router.get("/api/realtime/overview")
async def realtime_overview(db: AsyncSession = Depends(get_db)):
    """Return dashboard overview data."""
    from datetime import datetime, timedelta

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Device counts
    online = await db.execute(select(Device).where(Device.is_online == True))  # noqa: E712
    offline = await db.execute(select(Device).where(Device.is_online == False))  # noqa: E712

    # Person count
    person_count = (await db.execute(select(Person))).scalars().all()

    # Today events
    today_events_q = select(Event).where(Event.created_at >= today_start)
    today_events = (await db.execute(today_events_q)).scalars().all()

    # Today alerts
    today_alerts_q = select(Alert).where(Alert.created_at >= today_start)
    today_alerts = (await db.execute(today_alerts_q)).scalars().all()

    # Recent events
    recent_q = select(Event).where(
        Event.created_at >= today_start
    ).order_by(Event.created_at.desc()).limit(10)
    recent_events = (await db.execute(recent_q)).scalars().all()

    # Recent alerts
    recent_a_q = select(Alert).order_by(Alert.created_at.desc()).limit(5)
    recent_alerts = (await db.execute(recent_a_q)).scalars().all()

    return {
        "data": RealtimeOverview(
            online_devices=len(online.scalars().all()),
            offline_devices=len(offline.scalars().all()),
            total_persons=len(person_count),
            today_events=len(today_events),
            today_granted=sum(1 for e in today_events if e.decision == "granted"),
            today_alerts=len(today_alerts),
            recent_events=[{
                "id": e.id, "person_name": e.person_name or "未知",
                "node_id": e.node_id, "decision": e.decision,
                "fusion_conf": e.fusion_conf, "created_at": e.created_at.isoformat(),
            } for e in recent_events],
            recent_alerts=[{
                "id": a.id, "level": a.level, "title": a.title,
                "created_at": a.created_at.isoformat(),
            } for a in recent_alerts],
        )
    }
