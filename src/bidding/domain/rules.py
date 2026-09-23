"""Pure auction state, eligibility, and transition rules."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from bidding.domain.models import (
    MAX_MONEY_CENTS,
    AuctionSnapshot,
    AuctionState,
    BidEvaluation,
    BidRejectionReason,
)


def derive_auction_state(auction: AuctionSnapshot, now: datetime) -> AuctionState:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if now < auction.starts_at:
        return AuctionState.SCHEDULED
    if now >= auction.ends_at:
        return AuctionState.CLOSED
    return AuctionState.OPEN


def minimum_acceptable_bid(auction: AuctionSnapshot) -> int:
    if auction.current_price_cents is None:
        return auction.starting_price_cents
    minimum = auction.current_price_cents + auction.minimum_increment_cents
    if minimum > MAX_MONEY_CENTS:
        raise OverflowError("minimum acceptable bid exceeds the supported money range")
    return minimum


def evaluate_bid(
    auction: AuctionSnapshot,
    *,
    amount_cents: int,
    now: datetime,
) -> BidEvaluation:
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int):
        raise TypeError("amount_cents must be an integer number of cents")
    if not 0 < amount_cents <= MAX_MONEY_CENTS:
        raise ValueError(f"amount_cents must be between 1 and {MAX_MONEY_CENTS} cents")

    state = derive_auction_state(auction, now)
    minimum = minimum_acceptable_bid(auction)
    if state is AuctionState.SCHEDULED:
        return BidEvaluation(
            accepted=False,
            state=state,
            minimum_acceptable_cents=minimum,
            rejection_reason=BidRejectionReason.AUCTION_NOT_STARTED,
        )
    if state is AuctionState.CLOSED:
        return BidEvaluation(
            accepted=False,
            state=state,
            minimum_acceptable_cents=minimum,
            rejection_reason=BidRejectionReason.AUCTION_CLOSED,
        )
    if amount_cents < minimum:
        return BidEvaluation(
            accepted=False,
            state=state,
            minimum_acceptable_cents=minimum,
            rejection_reason=BidRejectionReason.BID_TOO_LOW,
        )
    return BidEvaluation(
        accepted=True,
        state=state,
        minimum_acceptable_cents=minimum,
    )


def apply_accepted_bid(
    auction: AuctionSnapshot,
    *,
    bid_id: UUID,
    amount_cents: int,
    now: datetime,
) -> AuctionSnapshot:
    evaluation = evaluate_bid(auction, amount_cents=amount_cents, now=now)
    if not evaluation.accepted:
        raise ValueError(f"bid rejected: {evaluation.rejection_reason}")
    return replace(
        auction,
        current_price_cents=amount_cents,
        winning_bid_id=bid_id,
        version=auction.version + 1,
    )
