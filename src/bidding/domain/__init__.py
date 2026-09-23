"""Framework-independent auction rules and value objects."""

from bidding.domain.models import (
    AcceptedBid,
    AuctionSnapshot,
    AuctionState,
    BidCommand,
    BidEvaluation,
    BidOutcome,
    BidOutcomeStatus,
    BidRejectionReason,
)
from bidding.domain.rules import (
    apply_accepted_bid,
    derive_auction_state,
    evaluate_bid,
    minimum_acceptable_bid,
)

__all__ = [
    "AcceptedBid",
    "AuctionSnapshot",
    "AuctionState",
    "BidCommand",
    "BidEvaluation",
    "BidOutcome",
    "BidOutcomeStatus",
    "BidRejectionReason",
    "apply_accepted_bid",
    "derive_auction_state",
    "evaluate_bid",
    "minimum_acceptable_bid",
]
