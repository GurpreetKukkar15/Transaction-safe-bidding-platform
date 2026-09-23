"""Thin HTTP and WebSocket routes around the application service."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from fastapi.concurrency import run_in_threadpool
from starlette.websockets import WebSocketDisconnect

from bidding.api.schemas import (
    AuctionResponse,
    AuctionStateEvent,
    BidPlacementResponse,
    BidResponse,
    CreateAuctionRequest,
    PlaceBidRequest,
)
from bidding.application.service import BiddingService
from bidding.db.strategies import StrategyBusyError
from bidding.domain.models import BidCommand, BidOutcomeStatus, BidRejectionReason

router = APIRouter()


def get_service(request: Request) -> BiddingService:
    return request.app.state.bidding_service


ServiceDependency = Annotated[BiddingService, Depends(get_service)]


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    def check_database() -> None:
        with request.app.state.db_pool.connection() as connection:
            connection.execute("SELECT 1")

    await run_in_threadpool(check_database)
    return {
        "status": "ok",
        "bid_strategy": request.app.state.settings.bid_strategy,
    }


@router.post("/auctions", response_model=AuctionResponse, status_code=201)
async def create_auction(
    body: CreateAuctionRequest,
    service: ServiceDependency,
) -> AuctionResponse:
    auction = await run_in_threadpool(
        service.create_auction,
        title=body.title,
        starting_price_cents=body.starting_price_cents,
        minimum_increment_cents=body.minimum_increment_cents,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
    )
    return AuctionResponse.from_domain(auction)


@router.get("/auctions/{auction_id}", response_model=AuctionResponse)
async def get_auction(
    auction_id: UUID,
    service: ServiceDependency,
) -> AuctionResponse:
    auction = await run_in_threadpool(service.get_auction, auction_id)
    if auction is None:
        raise HTTPException(status_code=404, detail={"reason": "auction_not_found"})
    return AuctionResponse.from_domain(auction)


@router.get("/auctions/{auction_id}/bids", response_model=list[BidResponse])
async def list_bids(
    auction_id: UUID,
    service: ServiceDependency,
) -> list[BidResponse]:
    auction = await run_in_threadpool(service.get_auction, auction_id)
    if auction is None:
        raise HTTPException(status_code=404, detail={"reason": "auction_not_found"})
    bids = await run_in_threadpool(service.list_bids, auction_id)
    return [BidResponse.from_domain(bid) for bid in bids]


@router.post("/auctions/{auction_id}/bids", response_model=BidPlacementResponse)
async def place_bid(
    auction_id: UUID,
    body: PlaceBidRequest,
    request: Request,
    service: ServiceDependency,
) -> BidPlacementResponse:
    command = BidCommand(
        request_id=body.request_id,
        auction_id=auction_id,
        bidder_id=body.bidder_id,
        amount_cents=body.amount_cents,
    )
    try:
        outcome = await run_in_threadpool(service.place_bid, command)
    except StrategyBusyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"reason": "database_busy"},
            headers={"Retry-After": "1"},
        ) from exc

    if outcome.status is BidOutcomeStatus.REJECTED:
        assert outcome.rejection_reason is not None
        status_code = _rejection_status(outcome.rejection_reason)
        detail: dict[str, str | int] = {"reason": outcome.rejection_reason.value}
        if outcome.minimum_acceptable_cents is not None:
            detail["minimum_acceptable_cents"] = outcome.minimum_acceptable_cents
        raise HTTPException(status_code=status_code, detail=detail)

    response = BidPlacementResponse.from_domain(outcome)
    if outcome.status is BidOutcomeStatus.ACCEPTED:
        assert outcome.bid is not None
        event = AuctionStateEvent(
            auction_id=auction_id,
            version=outcome.bid.auction_version,
            bid=BidResponse.from_domain(outcome.bid),
        )
        # The commit already succeeded. Broadcast failure cannot roll it back.
        await request.app.state.connection_manager.broadcast(
            auction_id,
            event.model_dump(mode="json"),
        )
    return response


def _rejection_status(reason: BidRejectionReason) -> int:
    if reason is BidRejectionReason.AUCTION_NOT_FOUND:
        return 404
    if reason is BidRejectionReason.CONFLICT_RETRY_EXHAUSTED:
        return 503
    return 409


@router.websocket("/ws/auctions/{auction_id}")
async def auction_websocket(websocket: WebSocket, auction_id: UUID) -> None:
    app = websocket.scope["app"]
    service: BiddingService = app.state.bidding_service
    manager = app.state.connection_manager
    auction = await run_in_threadpool(service.get_auction, auction_id)
    if auction is None:
        await websocket.close(code=4404, reason="auction not found")
        return

    await manager.connect(auction_id, websocket)
    try:
        await websocket.send_json(
            {
                "type": "auction.snapshot",
                "auction": AuctionResponse.from_domain(auction).model_dump(mode="json"),
            }
        )
        while True:
            # Client messages are heartbeats only; PostgreSQL state changes via HTTP.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(auction_id, websocket)
