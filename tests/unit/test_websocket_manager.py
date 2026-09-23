import asyncio
from uuid import UUID

from bidding.api.websockets import AuctionConnectionManager


class FailingWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.send_calls = 0

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload) -> None:
        self.send_calls += 1
        raise RuntimeError("disconnected")


def test_failed_websocket_is_removed_after_broadcast() -> None:
    async def scenario() -> None:
        auction_id = UUID("00000000-0000-0000-0000-000000000001")
        websocket = FailingWebSocket()
        manager = AuctionConnectionManager(send_timeout_seconds=0.1)

        await manager.connect(auction_id, websocket)  # type: ignore[arg-type]
        await manager.broadcast(auction_id, {"version": 1})
        await manager.broadcast(auction_id, {"version": 2})

        assert websocket.accepted is True
        assert websocket.send_calls == 1

    asyncio.run(scenario())
