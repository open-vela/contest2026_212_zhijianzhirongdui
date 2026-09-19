"""Durable cloud outbox worker with recovery, retry, and idempotency."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update

from app.config import settings
from app.models.database import async_session_factory
from app.models.models import CloudTransferAttempt, CloudTransferEvent
from app.services.cloud_transport import CloudTransport, DeliveryResult, configured_cloud_transport
from app.services.demo_event_bus import demo_event_bus

logger = logging.getLogger("demo.cloud")


class CloudOutboxWorker:
    """Single-process delivery worker. Run one app worker for the demo image."""

    def __init__(self, transport: CloudTransport | None = None) -> None:
        self.transport = transport or configured_cloud_transport()
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._stopping = False
        self.last_error_code: str | None = None
        self.last_error_message: str | None = None
        self.last_delivery_at: datetime | None = None

    @property
    def mode(self) -> str:
        return self.transport.mode

    @property
    def provider(self) -> str:
        return self.transport.provider

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.is_running:
            return
        self._stopping = False
        await self.recover_stale()
        if self.mode == "disabled":
            logger.info("Cloud outbox worker disabled; pending items remain durable in SQLite")
            return
        self._task = asyncio.create_task(self._run(), name="cloud-outbox-worker")
        logger.info("Cloud outbox worker started (mode=%s, provider=%s)", self.mode, self.provider)

    async def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        task = self._task
        self._task = None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def wake(self) -> None:
        self._wake.set()

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self.process_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unhandled cloud outbox worker error")
            self._wake.clear()
            try:
                await asyncio.wait_for(
                    self._wake.wait(),
                    timeout=max(0.1, settings.DEMO_CLOUD_WORKER_INTERVAL_SECONDS),
                )
            except asyncio.TimeoutError:
                pass

    async def recover_stale(self) -> int:
        """Return interrupted sends to the retry queue after an app restart."""
        async with async_session_factory() as db:
            result = await db.execute(
                update(CloudTransferEvent).where(
                    CloudTransferEvent.status == "sending"
                ).values(
                    status="retrying",
                    next_attempt_at=datetime.utcnow(),
                    error_code="WORKER_RESTART",
                    error_message="Delivery was interrupted by an application restart.",
                )
            )
            await db.commit()
            return int(result.rowcount or 0)

    async def process_once(self, limit: int = 10) -> int:
        if self.mode == "disabled":
            return 0
        now = datetime.utcnow()
        async with async_session_factory() as db:
            events = (await db.execute(
                select(CloudTransferEvent).where(
                    CloudTransferEvent.direction == "upload",
                    CloudTransferEvent.status.in_(("pending", "retrying")),
                    or_(CloudTransferEvent.next_attempt_at.is_(None), CloudTransferEvent.next_attempt_at <= now),
                ).order_by(CloudTransferEvent.created_at).limit(limit)
            )).scalars().all()

        processed = 0
        for event in events:
            await self._deliver(event.id)
            processed += 1
        return processed

    async def _deliver(self, event_id: int) -> None:
        now = datetime.utcnow()
        async with async_session_factory() as db:
            event = await db.get(CloudTransferEvent, event_id)
            if not event or event.status not in {"pending", "retrying"}:
                return
            event.status = "sending"
            event.last_attempt_at = now
            event.provider = self.provider
            event.transport = self.mode
            event.error_code = None
            event.error_message = None
            await db.commit()
            envelope = self._envelope(event)

        try:
            result = await self.transport.deliver(envelope)
        except asyncio.CancelledError:
            # The durable row remains ``sending`` and is recovered to
            # ``retrying`` on the next application start.
            raise
        except Exception as exc:
            logger.exception("Cloud transport raised for transfer %s", event_id)
            result = DeliveryResult(
                delivered=False,
                error_code="TRANSPORT_EXCEPTION",
                error_message=str(exc)[:2048] or type(exc).__name__,
            )

        async with async_session_factory() as db:
            event = await db.get(CloudTransferEvent, event_id)
            if not event:
                return
            event.response_status = result.status_code
            event.receipt_json = result.receipt
            event.updated_at = datetime.utcnow()
            db.add(CloudTransferAttempt(
                tenant_id=event.tenant_id,
                transfer_id=event.id,
                attempt_number=event.retry_count + 1,
                status="delivered" if result.delivered else "failed",
                response_status=result.status_code,
                error_code=result.error_code,
                error_message=(result.error_message or "")[:2048] or None,
                receipt_json=result.receipt,
                started_at=event.last_attempt_at or now,
                completed_at=datetime.utcnow(),
            ))
            if result.delivered:
                event.status = "delivered"
                event.delivered_at = datetime.utcnow()
                event.next_attempt_at = None
                event.provenance = "mock" if self.mode == "mock" else "real"
                event.error_code = None
                event.error_message = None
                self.last_error_code = None
                self.last_error_message = None
                self.last_delivery_at = event.delivered_at
                await self._add_receipt(db, event, result.receipt)
            else:
                event.retry_count += 1
                event.error_code = result.error_code or "DELIVERY_FAILED"
                event.error_message = (result.error_message or "Cloud transport failed")[:2048]
                event.provenance = "mock" if self.mode == "mock" else "pending_real"
                self.last_error_code = event.error_code
                self.last_error_message = event.error_message
                if event.retry_count >= event.max_retries:
                    event.status = "failed"
                    event.next_attempt_at = None
                else:
                    event.status = "retrying"
                    event.next_attempt_at = datetime.utcnow() + timedelta(seconds=self._backoff(event.retry_count))
            payload = self._event_payload(event)
            tenant_id = event.tenant_id
            await db.commit()
        await demo_event_bus.publish("cloud", payload, tenant_id=tenant_id)

    async def _add_receipt(
        self,
        db,
        upload: CloudTransferEvent,
        receipt: dict[str, Any],
    ) -> None:
        request_id = f"{upload.request_id}-receipt"
        existing = (await db.execute(
            select(CloudTransferEvent.id).where(CloudTransferEvent.request_id == request_id)
        )).scalar_one_or_none()
        if existing:
            return
        db.add(CloudTransferEvent(
            tenant_id=upload.tenant_id,
            request_id=request_id,
            idempotency_key=f"{upload.idempotency_key}:receipt",
            direction="receive",
            event_type=f"{upload.event_type}_receipt",
            status="delivered",
            payload_json=receipt,
            provider=self.provider,
            transport=self.mode,
            provenance="mock" if self.mode == "mock" else "real",
            response_status=upload.response_status,
            max_retries=0,
            delivered_at=datetime.utcnow(),
        ))

    @staticmethod
    def _envelope(event: CloudTransferEvent) -> dict[str, Any]:
        return {
            "request_id": event.request_id,
            "idempotency_key": event.idempotency_key,
            "event_type": event.event_type,
            "payload": event.payload_json or {},
            "created_at": event.created_at.isoformat() + "Z",
        }

    @staticmethod
    def _event_payload(event: CloudTransferEvent) -> dict[str, Any]:
        return {
            "request_id": event.request_id,
            "direction": event.direction,
            "status": event.status,
            "retry_count": event.retry_count,
            "error_code": event.error_code,
            "error_message": event.error_message,
            "provenance": event.provenance,
        }

    @staticmethod
    def _backoff(retry_count: int) -> float:
        delay = settings.DEMO_CLOUD_BACKOFF_BASE_SECONDS * (2 ** max(0, retry_count - 1))
        return min(delay, settings.DEMO_CLOUD_BACKOFF_MAX_SECONDS)


cloud_outbox = CloudOutboxWorker()
