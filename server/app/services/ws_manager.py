"""WebSocket connection manager for real-time event broadcasting."""

import json
import logging
import time
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("ws")


class WebSocketManager:
    """Manages WebSocket connections and broadcasts events to clients."""

    def __init__(self):
        self.connections: dict[str, WebSocket] = {}  # client_id → websocket

    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.connections[client_id] = websocket
        logger.info(f"WS client connected: {client_id} (total: {len(self.connections)})")

    async def disconnect(self, client_id: str):
        """Remove a disconnected client."""
        self.connections.pop(client_id, None)
        logger.info(f"WS client disconnected: {client_id} (total: {len(self.connections)})")

    async def broadcast(self, event_type: str, data: dict[str, Any]):
        """Broadcast an event to all connected clients."""
        message = json.dumps({
            "type": event_type,
            "data": data,
            "ts": time.time(),
        }, ensure_ascii=False, default=str)
        dead = []
        for cid, ws in self.connections.items():
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(cid)
        for cid in dead:
            await self.disconnect(cid)

    async def send_to(self, client_id: str, event_type: str, data: dict[str, Any]):
        """Send an event to a specific client."""
        ws = self.connections.get(client_id)
        if ws:
            try:
                await ws.send_text(json.dumps({
                    "type": event_type,
                    "data": data,
                    "ts": time.time(),
                }, ensure_ascii=False, default=str))
            except Exception:
                await self.disconnect(client_id)

    @property
    def count(self) -> int:
        return len(self.connections)


# Singleton
ws_manager = WebSocketManager()
