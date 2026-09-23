"""Single-process, best-effort auction WebSocket fan-out."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket


class AuctionConnectionManager:
    def __init__(self, *, send_timeout_seconds: float = 1.0) -> None:
        self._connections: dict[UUID, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._send_timeout_seconds = send_timeout_seconds

    async def connect(self, auction_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[auction_id].add(websocket)

    async def disconnect(self, auction_id: UUID, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections.get(auction_id)
            if connections is None:
                return
            connections.discard(websocket)
            if not connections:
                self._connections.pop(auction_id, None)

    async def broadcast(self, auction_id: UUID, payload: dict) -> None:
        async with self._lock:
            connections = tuple(self._connections.get(auction_id, ()))
        if not connections:
            return

        async def send(websocket: WebSocket) -> WebSocket | None:
            try:
                await asyncio.wait_for(
                    websocket.send_json(payload),
                    timeout=self._send_timeout_seconds,
                )
                return None
            except Exception:
                return websocket

        disconnected = await asyncio.gather(*(send(ws) for ws in connections))
        for websocket in disconnected:
            if websocket is not None:
                await self.disconnect(auction_id, websocket)
