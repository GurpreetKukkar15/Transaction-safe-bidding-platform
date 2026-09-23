"""Transport-independent auction application service."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from bidding.db.repositories import AuctionRepository
from bidding.db.strategies import BidStrategy
from bidding.domain.models import (
    AcceptedBid,
    AuctionSnapshot,
    BidCommand,
    BidOutcome,
)


class BiddingService:
    def __init__(
        self,
        repository: AuctionRepository,
        bid_strategy: BidStrategy,
    ) -> None:
        self._repository = repository
        self._bid_strategy = bid_strategy

    def create_auction(
        self,
        *,
        title: str,
        starting_price_cents: int,
        minimum_increment_cents: int,
        starts_at: datetime,
        ends_at: datetime,
    ) -> AuctionSnapshot:
        return self._repository.create(
            title=title,
            starting_price_cents=starting_price_cents,
            minimum_increment_cents=minimum_increment_cents,
            starts_at=starts_at,
            ends_at=ends_at,
        )

    def get_auction(self, auction_id: UUID) -> AuctionSnapshot | None:
        return self._repository.get(auction_id)

    def list_bids(self, auction_id: UUID) -> list[AcceptedBid]:
        return self._repository.list_bids(auction_id)

    def place_bid(self, command: BidCommand) -> BidOutcome:
        return self._bid_strategy.place_bid(command)
