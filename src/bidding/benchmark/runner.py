"""Repository-level workload generation with no artificial race widening."""

from __future__ import annotations

import platform
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from time import perf_counter_ns
from typing import Any
from uuid import UUID, uuid4

from psycopg_pool import ConnectionPool

from bidding.benchmark.models import RequestObservation, TrialResult
from bidding.db.repositories import AuctionRepository
from bidding.db.strategies import strategy_from_name
from bidding.domain.models import BidCommand
from bidding.verification.invariants import check_auction_invariants

WORKLOADS = frozenset({"same_price", "unique_prices", "low_contention"})


def reset_experiment_data(pool: ConnectionPool) -> None:
    with pool.connection() as connection:
        connection.execute("TRUNCATE TABLE bids, auctions CASCADE")


def postgres_metadata(pool: ConnectionPool) -> dict[str, str]:
    with pool.connection() as connection:
        row = connection.execute(
            """
            SELECT
                version() AS version,
                current_setting('transaction_isolation') AS isolation,
                current_setting('TimeZone') AS timezone
            """
        ).fetchone()
    assert row is not None
    return dict(row)


def environment_metadata(pool: ConnectionPool, *, random_seed: int) -> dict[str, Any]:
    return {
        "recorded_at": datetime.now(UTC).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "machine": platform.machine(),
        "random_seed": random_seed,
        "postgresql": postgres_metadata(pool),
        "clock": "time.perf_counter_ns",
    }


def seed_commands(
    pool: ConnectionPool,
    *,
    workload: str,
    request_count: int,
    random_seed: int,
) -> tuple[list[BidCommand], list[UUID]]:
    if workload not in WORKLOADS:
        raise ValueError(f"unknown workload: {workload}")
    if request_count <= 0:
        raise ValueError("request_count must be positive")

    repository = AuctionRepository(pool)
    now = datetime.now(UTC)

    def create_auction():
        return repository.create(
            title=f"Benchmark auction {uuid4()}",
            starting_price_cents=10_000,
            minimum_increment_cents=100,
            starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(minutes=30),
        )

    if workload == "low_contention":
        auctions = [create_auction() for _ in range(request_count)]
        commands = [
            BidCommand(uuid4(), auction.id, f"bidder-{index}", 10_000)
            for index, auction in enumerate(auctions)
        ]
        return commands, [auction.id for auction in auctions]

    auction = create_auction()
    if workload == "same_price":
        amounts = [10_000] * request_count
    else:
        amounts = [10_000 + index * 100 for index in range(request_count)]
        random.Random(random_seed).shuffle(amounts)
    commands = [
        BidCommand(uuid4(), auction.id, f"bidder-{index}", amount)
        for index, amount in enumerate(amounts)
    ]
    return commands, [auction.id]


def run_trial(
    pool: ConnectionPool,
    *,
    strategy_name: str,
    workload: str,
    concurrency: int,
    request_count: int,
    repetition: int,
    random_seed: int,
    optimistic_max_attempts: int,
) -> TrialResult:
    if concurrency <= 0:
        raise ValueError("concurrency must be positive")
    reset_experiment_data(pool)
    commands, auction_ids = seed_commands(
        pool,
        workload=workload,
        request_count=request_count,
        random_seed=random_seed,
    )
    strategy = strategy_from_name(
        strategy_name,
        pool,
        optimistic_max_attempts=optimistic_max_attempts,
    )

    def execute(item: tuple[int, BidCommand]) -> RequestObservation:
        index, command = item
        started = perf_counter_ns()
        try:
            outcome = strategy.place_bid(command)
            status = outcome.status.value
            reason = (
                None
                if outcome.rejection_reason is None
                else outcome.rejection_reason.value
            )
            attempts = outcome.attempts
            conflicts = outcome.conflicts
        except Exception as exc:
            status = "system_error"
            reason = type(exc).__name__
            attempts = 1
            conflicts = 0
        elapsed = perf_counter_ns() - started
        return RequestObservation(
            request_index=index,
            auction_id=str(command.auction_id),
            amount_cents=command.amount_cents,
            latency_ns=elapsed,
            status=status,
            reason=reason,
            attempts=attempts,
            conflicts=conflicts,
        )

    wall_started = perf_counter_ns()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        observations = list(executor.map(execute, enumerate(commands)))
    wall_time = perf_counter_ns() - wall_started

    violations: list[dict[str, str]] = []
    for auction_id in auction_ids:
        report = check_auction_invariants(pool, auction_id)
        violations.extend(asdict(violation) for violation in report.violations)
    return TrialResult.summarize(
        strategy=strategy_name,
        workload=workload,
        concurrency=concurrency,
        repetition=repetition,
        wall_time_ns=wall_time,
        observations=observations,
        invariant_violations=violations,
    )


def run_warmup(
    pool: ConnectionPool,
    *,
    strategy_name: str,
    concurrency: int,
    request_count: int,
    random_seed: int,
    optimistic_max_attempts: int,
) -> None:
    run_trial(
        pool,
        strategy_name=strategy_name,
        workload="low_contention",
        concurrency=concurrency,
        request_count=request_count,
        repetition=0,
        random_seed=random_seed,
        optimistic_max_attempts=optimistic_max_attempts,
    )
