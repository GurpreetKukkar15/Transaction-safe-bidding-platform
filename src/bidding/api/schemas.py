"""Validated HTTP payloads and response representations."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from bidding.domain.models import (
    MAX_BIDDER_ID_LENGTH,
    MAX_MONEY_CENTS,
    MAX_TITLE_LENGTH,
    AcceptedBid,
    AuctionSnapshot,
    BidOutcome,
    BidOutcomeStatus,
)

MoneyCents = Annotated[
    int,
    Field(strict=True, gt=0, le=MAX_MONEY_CENTS),
]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateAuctionRequest(StrictSchema):
    title: Annotated[str, Field(strict=True, min_length=1, max_length=MAX_TITLE_LENGTH)]
    starting_price_cents: MoneyCents
    minimum_increment_cents: MoneyCents
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @model_validator(mode="after")
    def validate_values(self) -> Self:
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("title cannot contain only whitespace")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class PlaceBidRequest(StrictSchema):
    request_id: UUID
    bidder_id: Annotated[
        str,
        Field(strict=True, min_length=1, max_length=MAX_BIDDER_ID_LENGTH),
    ]
    amount_cents: MoneyCents

    @model_validator(mode="after")
    def strip_bidder(self) -> Self:
        self.bidder_id = self.bidder_id.strip()
        if not self.bidder_id:
            raise ValueError("bidder_id cannot contain only whitespace")
        return self


class AuctionResponse(StrictSchema):
    id: UUID
    title: str
    starting_price_cents: int
    current_price_cents: int | None
    minimum_increment_cents: int
    winning_bid_id: UUID | None
    version: int
    starts_at: datetime
    ends_at: datetime
    created_at: datetime

    @classmethod
    def from_domain(cls, auction: AuctionSnapshot) -> AuctionResponse:
        return cls(**asdict(auction))


class BidResponse(StrictSchema):
    id: UUID
    request_id: UUID
    auction_id: UUID
    bidder_id: str
    amount_cents: int
    auction_version: int
    accepted_at: datetime

    @classmethod
    def from_domain(cls, bid: AcceptedBid) -> BidResponse:
        return cls(**asdict(bid))


class BidPlacementResponse(StrictSchema):
    status: BidOutcomeStatus
    bid: BidResponse
    attempts: int
    conflicts: int

    @classmethod
    def from_domain(cls, outcome: BidOutcome) -> BidPlacementResponse:
        if outcome.bid is None:
            raise ValueError("cannot serialize rejected outcome as success")
        return cls(
            status=outcome.status,
            bid=BidResponse.from_domain(outcome.bid),
            attempts=outcome.attempts,
            conflicts=outcome.conflicts,
        )


class AuctionStateEvent(StrictSchema):
    type: str = "auction.bid_accepted"
    auction_id: UUID
    version: int
    bid: BidResponse
