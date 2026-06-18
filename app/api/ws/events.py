"""WebSocket endpoint for real-time event streaming.

Clients connect and receive:
- Price updates from oracle feeds
- Trade execution confirmations
- Market state changes (new markets, settlements)
- Agent activity notifications
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("ax-server.ws")

ws_router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await ws.accept()
        self._connections.append(ws)
        logger.info("WS client connected (%d total)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a disconnected client."""
        self._connections.remove(ws)
        logger.info("WS client disconnected (%d remaining)", len(self._connections))

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Send an event to all connected clients.

        Silently drops clients that have disconnected.
        """
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)

    @property
    def client_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


@ws_router.websocket("/ws/events")
async def event_stream(ws: WebSocket):
    """Real-time event stream.

    After connecting, the client receives JSON events:
        {"type": "price_update", "data": {...}}
        {"type": "trade_executed", "data": {...}}
        {"type": "market_change", "data": {...}}

    The client can send subscription filters:
        {"subscribe": ["prices", "trades"]}
    """
    await manager.connect(ws)
    try:
        # Send welcome message
        await ws.send_json({
            "type": "connected",
            "data": {"message": "Connected to AthleteX event stream"},
        })

        while True:
            # Wait for client messages (subscription filters, pings)
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                # TODO: Handle subscription filters
                await ws.send_json({"type": "ack", "data": msg})
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "data": {"message": "Invalid JSON"}})

    except WebSocketDisconnect:
        manager.disconnect(ws)
