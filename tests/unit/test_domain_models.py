from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from bidding.domain.models import (
    AcceptedBid,
    AuctionSnapshot,
    BidCommand,
    BidOutcome,
    BidOutcomeStatus,
    BidRejectionReason,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
ID = UUID("00000000-0000-0000-0000-000000000001")


def test_bid_command_rejects_empty_bidder() -> None:
    with pytest.raises(ValueError, match="bidder_id"):
        BidCommand(ID, ID, "   ", 100)


def test_auction_requires_price_and_winner_together() -> None:
    with pytest.raises(ValueError, match="set together"):
        AuctionSnapshot(
            id=ID,
            title="Auction",
            starting_price_cents=100,
            current_price_cents=100,
            minimum_increment_cents=10,
            winning_bid_id=None,
            version=1,
            starts_at=NOW,
            ends_at=NOW + timedelta(hours=1),
            created_at=NOW,
        )


def test_accepted_outcome_requires_bid() -> None:
    with pytest.raises(ValueError, match="require a bid"):
        BidOutcome(BidOutcomeStatus.ACCEPTED)


def test_rejected_outcome_cannot_contain_bid() -> None:
    bid = AcceptedBid(ID, ID, ID, "bidder", 100, 1, NOW)

    with pytest.raises(ValueError, match="require a reason"):
        BidOutcome(
            BidOutcomeStatus.REJECTED,
            bid=bid,
            rejection_reason=BidRejectionReason.BID_TOO_LOW,
        )
