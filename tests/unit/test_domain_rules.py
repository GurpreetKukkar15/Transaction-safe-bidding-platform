from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from bidding.domain.models import (
    MAX_MONEY_CENTS,
    AuctionSnapshot,
    AuctionState,
    BidRejectionReason,
)
from bidding.domain.rules import (
    apply_accepted_bid,
    derive_auction_state,
    evaluate_bid,
    minimum_acceptable_bid,
)

AUCTION_ID = UUID("00000000-0000-0000-0000-000000000001")
BID_ID = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def auction(**overrides: object) -> AuctionSnapshot:
    values: dict[str, object] = {
        "id": AUCTION_ID,
        "title": "Database Systems Textbook",
        "starting_price_cents": 10_000,
        "current_price_cents": None,
        "minimum_increment_cents": 1_500,
        "winning_bid_id": None,
        "version": 0,
        "starts_at": NOW - timedelta(hours=1),
        "ends_at": NOW + timedelta(hours=1),
        "created_at": NOW - timedelta(days=1),
    }
    values.update(overrides)
    return AuctionSnapshot(**values)  # type: ignore[arg-type]


def test_first_bid_minimum_is_starting_price() -> None:
    assert minimum_acceptable_bid(auction()) == 10_000


def test_later_bid_minimum_adds_increment() -> None:
    assert (
        minimum_acceptable_bid(
            auction(
                current_price_cents=12_000,
                winning_bid_id=BID_ID,
                version=1,
            )
        )
        == 13_500
    )


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        (NOW - timedelta(hours=2), AuctionState.SCHEDULED),
        (NOW - timedelta(hours=1), AuctionState.OPEN),
        (NOW, AuctionState.OPEN),
        (NOW + timedelta(hours=1), AuctionState.CLOSED),
    ],
)
def test_state_uses_half_open_time_interval(
    when: datetime, expected: AuctionState
) -> None:
    assert derive_auction_state(auction(), when) is expected


def test_bid_exactly_at_first_minimum_is_accepted() -> None:
    result = evaluate_bid(auction(), amount_cents=10_000, now=NOW)

    assert result.accepted is True
    assert result.rejection_reason is None
    assert result.minimum_acceptable_cents == 10_000


def test_bid_one_cent_below_minimum_is_rejected() -> None:
    result = evaluate_bid(auction(), amount_cents=9_999, now=NOW)

    assert result.accepted is False
    assert result.rejection_reason is BidRejectionReason.BID_TOO_LOW
    assert result.minimum_acceptable_cents == 10_000


def test_scheduled_auction_rejects_otherwise_valid_bid() -> None:
    result = evaluate_bid(
        auction(starts_at=NOW + timedelta(seconds=1)),
        amount_cents=10_000,
        now=NOW,
    )

    assert result.rejection_reason is BidRejectionReason.AUCTION_NOT_STARTED


def test_bid_at_exact_end_time_is_rejected() -> None:
    item = auction(ends_at=NOW)
    result = evaluate_bid(item, amount_cents=10_000, now=NOW)

    assert result.rejection_reason is BidRejectionReason.AUCTION_CLOSED


def test_rejection_does_not_mutate_auction() -> None:
    item = auction()

    evaluate_bid(item, amount_cents=9_999, now=NOW)

    assert item == auction()


def test_accepted_transition_increases_version_once() -> None:
    original = auction()

    updated = apply_accepted_bid(
        original,
        bid_id=BID_ID,
        amount_cents=10_000,
        now=NOW,
    )

    assert updated.current_price_cents == 10_000
    assert updated.winning_bid_id == BID_ID
    assert updated.version == 1
    assert original.current_price_cents is None


def test_current_price_cannot_be_constructed_below_starting_price() -> None:
    with pytest.raises(ValueError, match="below the starting price"):
        auction(current_price_cents=9_999, winning_bid_id=BID_ID, version=1)


def test_boolean_is_not_accepted_as_money() -> None:
    with pytest.raises(TypeError, match="integer number of cents"):
        evaluate_bid(auction(), amount_cents=True, now=NOW)


def test_minimum_overflow_is_rejected() -> None:
    item = auction(
        starting_price_cents=MAX_MONEY_CENTS,
        current_price_cents=MAX_MONEY_CENTS,
        minimum_increment_cents=1,
        winning_bid_id=BID_ID,
        version=1,
    )

    with pytest.raises(OverflowError, match="supported money range"):
        minimum_acceptable_bid(item)


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        derive_auction_state(auction(), NOW.replace(tzinfo=None))
