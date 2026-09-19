"""Process-local fan-out for telemetry, calculated metrics, and cloud events."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any


class DemoEventBus:
    """A bounded event bus used by the authenticated demo WebSocket."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    async def publish(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        tenant_id: int = 1,
    ) -> None:
        event = {
            "type": event_type,
            "tenant_id": tenant_id,
            "data": data,
            "ts": datetime.utcnow().isoformat() + "Z",
        }
        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)

    def clear(self) -> None:
        self._subscribers.clear()


demo_event_bus = DemoEventBus()
