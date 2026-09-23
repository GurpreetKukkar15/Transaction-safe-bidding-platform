"""Command-line entry point for reproducible repository contention trials."""

from __future__ import annotations

import argparse
import json
import random
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bidding.benchmark.runner import (
    WORKLOADS,
    environment_metadata,
    run_trial,
    run_warmup,
)
from bidding.config import VALID_STRATEGIES, Settings
from bidding.db.migrations import migrate
from bidding.db.pool import create_pool


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_positive_int_csv(value: str) -> list[int]:
    try:
        numbers = [int(item) for item in parse_csv(value)]
    except ValueError as exc:
        raise ValueError("concurrency levels must be integers") from exc
    if not numbers or any(number <= 0 for number in numbers):
        raise ValueError("concurrency levels must be positive")
    return numbers


def build_trial_schedule(
    *,
    strategies: list[str],
    workloads: list[str],
    concurrency_levels: list[int],
    repetitions: int,
    random_seed: int,
    randomized: bool,
) -> list[tuple[str, str, int, int]]:
    """Build a complete, reproducible trial schedule."""
    schedule = [
        (strategy, workload, concurrency, repetition)
        for strategy in strategies
        for concurrency in concurrency_levels
        for workload in workloads
        for repetition in range(1, repetitions + 1)
    ]
    if randomized:
        random.Random(random_seed).shuffle(schedule)
    return schedule


def git_metadata() -> dict[str, Any]:
    """Capture the exact source revision used for a benchmark run."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {"git_commit": None, "git_dirty": None}
    return {"git_commit": commit, "git_dirty": dirty}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark PostgreSQL bid concurrency strategies"
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument(
        "--strategies",
        default="unsafe,pessimistic,optimistic",
        help="comma-separated strategy names",
    )
    parser.add_argument(
        "--workloads",
        default="same_price,unique_prices,low_contention",
        help="comma-separated workload names",
    )
    parser.add_argument(
        "--concurrencies",
        default="1,8,32",
        help="comma-separated concurrency levels",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="single-level override, primarily for smoke tests",
    )
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--warmup-requests", type=int, default=20)
    parser.add_argument("--random-seed", type=int, default=20260922)
    parser.add_argument(
        "--trial-order",
        choices=("fixed", "randomized"),
        default="fixed",
        help="execution order for measured trials",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="omit per-request observations from output for long benchmark runs",
    )
    parser.add_argument("--output", type=Path, default=None)
    arguments = parser.parse_args()

    strategies = parse_csv(arguments.strategies)
    workloads = parse_csv(arguments.workloads)
    unknown_strategies = set(strategies) - VALID_STRATEGIES
    unknown_workloads = set(workloads) - WORKLOADS
    if unknown_strategies:
        parser.error(f"unknown strategies: {sorted(unknown_strategies)}")
    if unknown_workloads:
        parser.error(f"unknown workloads: {sorted(unknown_workloads)}")
    try:
        concurrency_levels = (
            [arguments.concurrency]
            if arguments.concurrency is not None
            else parse_positive_int_csv(arguments.concurrencies)
        )
    except ValueError as exc:
        parser.error(str(exc))
    if arguments.requests <= 0:
        parser.error("requests must be positive")
    if arguments.repetitions < 3:
        parser.error("at least three repetitions are required")

    base_settings = Settings.from_env()
    settings = Settings(
        database_url=arguments.database_url or base_settings.database_url,
        bid_strategy=base_settings.bid_strategy,
        pool_min_size=min(4, max(concurrency_levels)),
        pool_max_size=max(base_settings.pool_max_size, max(concurrency_levels)),
        pool_timeout_seconds=base_settings.pool_timeout_seconds,
        lock_timeout_ms=base_settings.lock_timeout_ms,
        statement_timeout_ms=base_settings.statement_timeout_ms,
        optimistic_max_attempts=base_settings.optimistic_max_attempts,
    )
    pool = create_pool(settings, name="benchmark-db")
    pool.open(wait=True, timeout=30)
    try:
        with pool.connection() as connection:
            migrate(connection)
        metadata = environment_metadata(pool, random_seed=arguments.random_seed)
        metadata["source"] = git_metadata()
        metadata["configuration"] = {
            "strategies": strategies,
            "workloads": workloads,
            "concurrency_levels": concurrency_levels,
            "requests": arguments.requests,
            "repetitions": arguments.repetitions,
            "warmup_requests": arguments.warmup_requests,
            "pool_min_size": settings.pool_min_size,
            "pool_max_size": settings.pool_max_size,
            "lock_timeout_ms": settings.lock_timeout_ms,
            "statement_timeout_ms": settings.statement_timeout_ms,
            "optimistic_max_attempts": settings.optimistic_max_attempts,
            "trial_order": arguments.trial_order,
            "request_observations": (
                "omitted" if arguments.summary_only else "preserved"
            ),
        }

        results = []
        for strategy in strategies:
            for concurrency in concurrency_levels:
                run_warmup(
                    pool,
                    strategy_name=strategy,
                    concurrency=concurrency,
                    request_count=arguments.warmup_requests,
                    random_seed=arguments.random_seed,
                    optimistic_max_attempts=settings.optimistic_max_attempts,
                )

        schedule = build_trial_schedule(
            strategies=strategies,
            workloads=workloads,
            concurrency_levels=concurrency_levels,
            repetitions=arguments.repetitions,
            random_seed=arguments.random_seed,
            randomized=arguments.trial_order == "randomized",
        )
        for strategy, workload, concurrency, repetition in schedule:
            result = run_trial(
                pool,
                strategy_name=strategy,
                workload=workload,
                concurrency=concurrency,
                request_count=arguments.requests,
                repetition=repetition,
                random_seed=arguments.random_seed + repetition,
                optimistic_max_attempts=settings.optimistic_max_attempts,
            )
            serialized_result = result.to_dict()
            if arguments.summary_only:
                serialized_result.pop("requests")
            results.append(serialized_result)
            print(
                f"{strategy:11} {workload:15} c={concurrency:2} "
                f"rep={repetition} "
                f"throughput="
                f"{result.throughput_requests_per_second:.1f}/s "
                f"p95={result.p95_latency_ms:.2f}ms "
                f"valid={result.invariant_valid}"
            )

        output = arguments.output
        if output is None:
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            output = Path("benchmark-results") / f"repository-{timestamp}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"metadata": metadata, "trials": results}, indent=2),
            encoding="utf-8",
        )
        print(f"Raw benchmark written to {output}")
    finally:
        pool.close()


if __name__ == "__main__":
    main()
