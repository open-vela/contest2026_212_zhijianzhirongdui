"""Hub offline/degrade handling: local staging + reconnect replay.

When the R528 hub loses its cloud uplink the system must keep making local
policy decisions. Edge evidence that would normally be forwarded upstream
(status events at minimum, all channels in the demo build) is staged in the
durable SQLite ``edge_event_queue`` table and replayed after the link
recovers. Replay currently re-enters the local cloud outbox
(``cloud_transfer_events``), so the existing retry/idempotency machinery is
reused instead of duplicated.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.config import settings
from app.models.database import async_session_factory
from app.models.models import EdgeEventQueue

logger = logging.getLogger("hub.offline")


class HubOfflineQueue:
    """Durable per-hub edge-event staging with replay-to-outbox."""

    async def enqueue(
        self,
        *,
        hub_id: str | None,
        edge_id: str,
        channel: str,
        topic: str,
        payload: dict[str, Any],
    ) -> EdgeEventQueue | None:
        """Stage an event while the cloud link is down.

        Returns the queued row, or None when the queue is full (oldest
        evidence is dropped with a logged warning — access decisions are
        never blocked by queue pressure).
        """
        async with async_session_factory() as db:
            count = (await db.execute(
                select(func.count()).select_from(EdgeEventQueue).where(
                    EdgeEventQueue.status == "queued"
                )
            )).scalar() or 0
            if count >= settings.HUB_OFFLINE_QUEUE_MAX:
                oldest = (await db.execute(
                    select(EdgeEventQueue).where(EdgeEventQueue.status == "queued")
                    .order_by(EdgeEventQueue.created_at).limit(1)
                )).scalar_one_or_none()
                if oldest:
                    await db.delete(oldest)
                    logger.warning("Offline queue full (%s); dropped oldest event", count)

            row = EdgeEventQueue(
                tenant_id=1,
                hub_id=hub_id,
                edge_id=edge_id,
                channel=channel,
                topic=topic,
                payload_json=payload,
                status="queued",
                created_at=datetime.utcnow(),
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return row

    async def depth(self, hub_id: str | None = None) -> int:
        async with async_session_factory() as db:
            query = select(func.count()).select_from(EdgeEventQueue).where(
                EdgeEventQueue.status == "queued"
            )
            if hub_id:
                query = query.where(EdgeEventQueue.hub_id == hub_id)
            return int((await db.execute(query)).scalar() or 0)

    async def replay(self, hub_id: str | None = None, limit: int = 500) -> int:
        """Replay queued events into the cloud outbox and mark them sent."""
        from app.services.cloud_outbox import cloud_outbox
        import uuid

        replayed = 0
        async with async_session_factory() as db:
            query = select(EdgeEventQueue).where(EdgeEventQueue.status == "queued")
            if hub_id:
                query = query.where(EdgeEventQueue.hub_id == hub_id)
            rows = (await db.execute(
                query.order_by(EdgeEventQueue.created_at).limit(limit)
            )).scalars().all()

            for row in rows:
                # Hand the evidence to the durable cloud outbox. In disabled
                # mode it stays durably stored there as well; nothing is lost.
                try:
                    from app.models.models import CloudTransferEvent

                    request_id = uuid.uuid4().hex
                    db.add(CloudTransferEvent(
                        tenant_id=row.tenant_id,
                        request_id=request_id,
                        idempotency_key=f"replay-{row.id}",
                        direction="upload",
                        event_type=f"edge_{row.channel}",
                        status="pending",
                        payload_json={
                            "hub_id": row.hub_id,
                            "edge_id": row.edge_id,
                            "topic": row.topic,
                            "edge_payload": row.payload_json,
                            "edge_created_at": row.created_at.isoformat() + "Z",
                            "replayed_at": datetime.utcnow().isoformat() + "Z",
                        },
                        provider=cloud_outbox.provider,
                        transport=cloud_outbox.mode,
                        provenance="reserved" if cloud_outbox.mode == "disabled" else "pending_real",
                        max_retries=settings.DEMO_CLOUD_MAX_RETRIES,
                        next_attempt_at=datetime.utcnow(),
                    ))
                    row.status = "sent"
                    row.delivered_at = datetime.utcnow()
                    replayed += 1
                except Exception:
                    logger.exception("Failed to replay offline queue row %s", row.id)
            await db.commit()

        if replayed:
            cloud_outbox.wake()
            logger.info("[Offline] replayed %s queued edge events for hub=%s", replayed, hub_id)
        return replayed


hub_offline = HubOfflineQueue()
