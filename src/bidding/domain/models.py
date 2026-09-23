"""Immutable domain values shared by every concurrency strategy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

MAX_MONEY_CENTS = 9_000_000_000_000_000
MAX_TITLE_LENGTH = 200
MAX_BIDDER_ID_LENGTH = 128


class AuctionState(StrEnum):
    SCHEDULED = "scheduled"
    OPEN = "open"
    CLOSED = "closed"


class BidRejectionReason(StrEnum):
    AUCTION_NOT_FOUND = "auction_not_found"
    AUCTION_NOT_STARTED = "auction_not_started"
    AUCTION_CLOSED = "auction_closed"
    BID_TOO_LOW = "bid_too_low"
    REQUEST_ID_REUSED = "request_id_reused"
    CONFLICT_RETRY_EXHAUSTED = "conflict_retry_exhausted"


class BidOutcomeStatus(StrEnum):
    ACCEPTED = "accepted"
    REPLAYED = "replayed"
    REJECTED = "rejected"


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_money(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer number of cents")
    if not 0 < value <= MAX_MONEY_CENTS:
        raise ValueError(f"{field_name} must be between 1 and {MAX_MONEY_CENTS} cents")


@dataclass(frozen=True, slots=True)
class AuctionSnapshot:
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

    def __post_init__(self) -> None:
        title = self.title.strip()
        if not title or len(title) > MAX_TITLE_LENGTH:
            raise ValueError(
                f"title must contain 1 to {MAX_TITLE_LENGTH} non-whitespace characters"
            )
        _require_money(self.starting_price_cents, "starting_price_cents")
        _require_money(self.minimum_increment_cents, "minimum_increment_cents")
        for field_name, value in (
            ("starts_at", self.starts_at),
            ("ends_at", self.ends_at),
            ("created_at", self.created_at),
        ):
            _require_aware(value, field_name)
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        if isinstance(self.version, bool) or not isinstance(self.version, int):
            raise TypeError("version must be an integer")
        if self.version < 0:
            raise ValueError("version cannot be negative")

        has_price = self.current_price_cents is not None
        has_winner = self.winning_bid_id is not None
        if has_price != has_winner:
            raise ValueError("current price and winning bid must be set together")
        if not has_price and self.version != 0:
            raise ValueError("an auction without bids must have version zero")
        if has_price:
            _require_money(self.current_price_cents, "current_price_cents")
            if self.current_price_cents < self.starting_price_cents:
                raise ValueError("current price cannot be below the starting price")
            if self.version == 0:
                raise ValueError("an auction with a winning bid must have a version")


@dataclass(frozen=True, slots=True)
class BidCommand:
    request_id: UUID
    auction_id: UUID
    bidder_id: str
    amount_cents: int

    def __post_init__(self) -> None:
        bidder_id = self.bidder_id.strip()
        if not bidder_id or len(bidder_id) > MAX_BIDDER_ID_LENGTH:
            raise ValueError(
                "bidder_id must contain 1 to "
                f"{MAX_BIDDER_ID_LENGTH} non-whitespace characters"
            )
        _require_money(self.amount_cents, "amount_cents")


@dataclass(frozen=True, slots=True)
class BidEvaluation:
    accepted: bool
    state: AuctionState
    minimum_acceptable_cents: int
    rejection_reason: BidRejectionReason | None = None

    def __post_init__(self) -> None:
        if self.accepted == (self.rejection_reason is not None):
            raise ValueError(
                "accepted evaluations have no rejection reason; "
                "rejected ones require one"
            )


@dataclass(frozen=True, slots=True)
class AcceptedBid:
    id: UUID
    request_id: UUID
    auction_id: UUID
    bidder_id: str
    amount_cents: int
    auction_version: int
    accepted_at: datetime

    def __post_init__(self) -> None:
        _require_money(self.amount_cents, "amount_cents")
        if self.auction_version <= 0:
            raise ValueError("auction_version must be positive")
        _require_aware(self.accepted_at, "accepted_at")


@dataclass(frozen=True, slots=True)
class BidOutcome:
    status: BidOutcomeStatus
    bid: AcceptedBid | None = None
    rejection_reason: BidRejectionReason | None = None
    minimum_acceptable_cents: int | None = None
    attempts: int = 1
    conflicts: int = 0

    def __post_init__(self) -> None:
        if self.attempts <= 0:
            raise ValueError("attempts must be positive")
        if self.conflicts < 0:
            raise ValueError("conflicts cannot be negative")
        if self.status in {BidOutcomeStatus.ACCEPTED, BidOutcomeStatus.REPLAYED}:
            if self.bid is None or self.rejection_reason is not None:
                raise ValueError("accepted/replayed outcomes require a bid only")
        elif self.bid is not None or self.rejection_reason is None:
            raise ValueError("rejected outcomes require a reason and no bid")

    @classmethod
    def accepted(
        cls,
        bid: AcceptedBid,
        *,
        attempts: int = 1,
        conflicts: int = 0,
    ) -> BidOutcome:
        return cls(
            BidOutcomeStatus.ACCEPTED,
            bid=bid,
            attempts=attempts,
            conflicts=conflicts,
        )

    @classmethod
    def replayed(
        cls,
        bid: AcceptedBid,
        *,
        attempts: int = 1,
        conflicts: int = 0,
    ) -> BidOutcome:
        return cls(
            BidOutcomeStatus.REPLAYED,
            bid=bid,
            attempts=attempts,
            conflicts=conflicts,
        )

    @classmethod
    def rejected(
        cls,
        reason: BidRejectionReason,
        *,
        minimum_acceptable_cents: int | None = None,
        attempts: int = 1,
        conflicts: int = 0,
    ) -> BidOutcome:
        return cls(
            BidOutcomeStatus.REJECTED,
            rejection_reason=reason,
            minimum_acceptable_cents=minimum_acceptable_cents,
            attempts=attempts,
            conflicts=conflicts,
        )
