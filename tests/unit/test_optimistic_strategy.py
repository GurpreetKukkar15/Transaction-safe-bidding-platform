from uuid import UUID

from bidding.db.strategies import OptimisticBidStrategy, _OptimisticMiss
from bidding.domain.models import BidCommand, BidRejectionReason


def test_optimistic_retries_are_bounded(monkeypatch) -> None:
    strategy = OptimisticBidStrategy(None, max_attempts=3)  # type: ignore[arg-type]
    command = BidCommand(
        request_id=UUID("00000000-0000-0000-0000-000000000001"),
        auction_id=UUID("00000000-0000-0000-0000-000000000002"),
        bidder_id="alice",
        amount_cents=10_000,
    )
    attempts: list[int] = []

    def always_miss(_command, *, attempt):
        attempts.append(attempt)
        raise _OptimisticMiss(attempt - 1)

    monkeypatch.setattr(strategy, "_attempt", always_miss)
    monkeypatch.setattr(
        strategy,
        "_classify_after_miss",
        lambda _command, *, attempt: None,
    )

    outcome = strategy.place_bid(command)

    assert attempts == [1, 2, 3]
    assert outcome.rejection_reason is BidRejectionReason.CONFLICT_RETRY_EXHAUSTED
    assert outcome.attempts == 3
    assert outcome.conflicts == 3
