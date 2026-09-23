from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from time import sleep
from uuid import uuid4

import psycopg
import pytest

from bidding.config import Settings
from bidding.db.pool import create_pool
from bidding.db.repositories import AuctionRepository
from bidding.db.strategies import (
    OptimisticBidStrategy,
    PessimisticBidStrategy,
    StrategyBusyError,
    UnsafeBidStrategy,
)
from bidding.domain.models import (
    BidCommand,
    BidOutcomeStatus,
    BidRejectionReason,
)
from bidding.verification.invariants import check_auction_invariants

pytestmark = pytest.mark.integration


def create_open_auction(db_pool):
    now = datetime.now(UTC)
    return AuctionRepository(db_pool).create(
        title="Concurrent systems auction",
        starting_price_cents=10_000,
        minimum_increment_cents=1_500,
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(hours=1),
    )


def commands(auction_id):
    return (
        BidCommand(uuid4(), auction_id, "alice", 13_000),
        BidCommand(uuid4(), auction_id, "bob", 15_000),
    )


def run_together(strategy, bid_commands):
    start = Barrier(len(bid_commands))

    def place(command):
        start.wait(timeout=5)
        return strategy.place_bid(command)

    with ThreadPoolExecutor(max_workers=len(bid_commands)) as executor:
        futures = [executor.submit(place, command) for command in bid_commands]
        return [future.result(timeout=10) for future in futures]


def test_unsafe_strategy_reproduces_lost_update(db_pool, clean_database) -> None:
    auction = create_open_auction(db_pool)
    overlap = Barrier(2)
    strategy = UnsafeBidStrategy(
        db_pool,
        after_read_hook=lambda: overlap.wait(timeout=5),
    )

    outcomes = run_together(strategy, commands(auction.id))
    report = check_auction_invariants(db_pool, auction.id)

    assert [outcome.status for outcome in outcomes].count(
        BidOutcomeStatus.ACCEPTED
    ) == 2
    assert report.valid is False
    assert {violation.code for violation in report.violations} >= {
        "version_sequence",
        "auction_version",
    }


@pytest.mark.parametrize(
    "strategy_factory",
    [
        lambda pool: PessimisticBidStrategy(pool),
        lambda pool: OptimisticBidStrategy(pool, max_attempts=5),
    ],
    ids=["pessimistic", "optimistic"],
)
def test_safe_strategies_preserve_invariants(
    db_pool, clean_database, strategy_factory
) -> None:
    auction = create_open_auction(db_pool)
    strategy = strategy_factory(db_pool)

    outcomes = run_together(strategy, commands(auction.id))
    report = check_auction_invariants(db_pool, auction.id)

    assert any(outcome.status is BidOutcomeStatus.ACCEPTED for outcome in outcomes)
    assert report.valid, report.violations


@pytest.mark.parametrize(
    "strategy_factory",
    [
        lambda pool: PessimisticBidStrategy(pool),
        lambda pool: OptimisticBidStrategy(pool, max_attempts=5),
    ],
    ids=["pessimistic", "optimistic"],
)
def test_concurrent_duplicate_request_is_committed_once(
    db_pool, clean_database, strategy_factory
) -> None:
    auction = create_open_auction(db_pool)
    request_id = uuid4()
    first = BidCommand(request_id, auction.id, "alice", 10_000)
    second = BidCommand(request_id, auction.id, "alice", 10_000)

    outcomes = run_together(strategy_factory(db_pool), (first, second))
    bids = AuctionRepository(db_pool).list_bids(auction.id)

    assert {outcome.status for outcome in outcomes} == {
        BidOutcomeStatus.ACCEPTED,
        BidOutcomeStatus.REPLAYED,
    }
    assert len(bids) == 1


def test_request_id_reuse_with_different_payload_is_rejected(
    db_pool, clean_database
) -> None:
    auction = create_open_auction(db_pool)
    strategy = PessimisticBidStrategy(db_pool)
    request_id = uuid4()

    accepted = strategy.place_bid(BidCommand(request_id, auction.id, "alice", 10_000))
    rejected = strategy.place_bid(BidCommand(request_id, auction.id, "bob", 12_000))

    assert accepted.status is BidOutcomeStatus.ACCEPTED
    assert rejected.status is BidOutcomeStatus.REJECTED
    assert rejected.rejection_reason is BidRejectionReason.REQUEST_ID_REUSED


def test_pessimistic_strategy_rejects_bid_against_new_committed_price(
    db_pool, clean_database
) -> None:
    auction = create_open_auction(db_pool)
    strategy = PessimisticBidStrategy(db_pool)

    first = strategy.place_bid(BidCommand(uuid4(), auction.id, "alice", 12_000))
    second = strategy.place_bid(BidCommand(uuid4(), auction.id, "bob", 13_000))

    assert first.status is BidOutcomeStatus.ACCEPTED
    assert second.status is BidOutcomeStatus.REJECTED
    assert second.rejection_reason is BidRejectionReason.BID_TOO_LOW
    assert second.minimum_acceptable_cents == 13_500


def test_pessimistic_strategy_checks_actual_time_after_lock_wait(
    db_pool, clean_database, integration_database_url
) -> None:
    now = datetime.now(UTC)
    auction = AuctionRepository(db_pool).create(
        title="Expiring while locked",
        starting_price_cents=10_000,
        minimum_increment_cents=1_500,
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(milliseconds=400),
    )
    strategy = PessimisticBidStrategy(db_pool)
    attempted = Event()

    def place_waiting_bid():
        attempted.set()
        return strategy.place_bid(BidCommand(uuid4(), auction.id, "alice", 10_000))

    with (
        ThreadPoolExecutor(max_workers=1) as executor,
        psycopg.connect(integration_database_url) as locking_connection,
        locking_connection.transaction(),
    ):
        locking_connection.execute(
            "SELECT id FROM auctions WHERE id = %s FOR UPDATE",
            (auction.id,),
        )
        future = executor.submit(place_waiting_bid)
        assert attempted.wait(timeout=1)
        sleep(0.6)
    outcome = future.result(timeout=5)

    assert outcome.status is BidOutcomeStatus.REJECTED
    assert outcome.rejection_reason is BidRejectionReason.AUCTION_CLOSED
    assert AuctionRepository(db_pool).list_bids(auction.id) == []


def test_rollback_releases_pessimistic_row_lock(
    db_pool, clean_database, integration_database_url
) -> None:
    auction = create_open_auction(db_pool)

    with (
        pytest.raises(RuntimeError, match="force rollback"),
        psycopg.connect(integration_database_url) as locking_connection,
        locking_connection.transaction(),
    ):
        locking_connection.execute(
            "SELECT id FROM auctions WHERE id = %s FOR UPDATE",
            (auction.id,),
        )
        raise RuntimeError("force rollback")

    outcome = PessimisticBidStrategy(db_pool).place_bid(
        BidCommand(uuid4(), auction.id, "alice", 10_000)
    )

    assert outcome.status is BidOutcomeStatus.ACCEPTED


def test_pessimistic_lock_wait_is_bounded(
    db_pool, clean_database, integration_database_url
) -> None:
    auction = create_open_auction(db_pool)
    short_settings = Settings(
        database_url=integration_database_url,
        pool_min_size=1,
        pool_max_size=2,
        lock_timeout_ms=100,
        statement_timeout_ms=2_000,
    )
    short_pool = create_pool(short_settings, name="short-lock-timeout")
    short_pool.open(wait=True, timeout=5)
    try:
        with (
            psycopg.connect(integration_database_url) as locking_connection,
            locking_connection.transaction(),
        ):
            locking_connection.execute(
                "SELECT id FROM auctions WHERE id = %s FOR UPDATE",
                (auction.id,),
            )
            with pytest.raises(StrategyBusyError, match="timeout"):
                PessimisticBidStrategy(short_pool).place_bid(
                    BidCommand(uuid4(), auction.id, "alice", 10_000)
                )
    finally:
        short_pool.close()
