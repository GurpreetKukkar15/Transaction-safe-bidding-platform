"""End-to-end HTTP benchmark for one running application strategy."""

from __future__ import annotations

import argparse
import json
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter_ns
from uuid import UUID, uuid4

import httpx2

from bidding.benchmark.models import RequestObservation, TrialResult
from bidding.benchmark.runner import (
    WORKLOADS,
    environment_metadata,
    reset_experiment_data,
)
from bidding.config import VALID_STRATEGIES, Settings
from bidding.db.migrations import migrate
from bidding.db.pool import create_pool
from bidding.verification.invariants import check_auction_invariants


def create_auction(client: httpx2.Client, index: int) -> UUID:
    now = datetime.now(UTC)
    response = client.post(
        "/auctions",
        json={
            "title": f"HTTP benchmark auction {index}",
            "starting_price_cents": 10_000,
            "minimum_increment_cents": 100,
            "starts_at": (now - timedelta(minutes=1)).isoformat(),
            "ends_at": (now + timedelta(minutes=30)).isoformat(),
        },
    )
    response.raise_for_status()
    return UUID(response.json()["id"])


def run_http_trial(
    client: httpx2.Client,
    pool,
    *,
    strategy_label: str,
    workload: str,
    concurrency: int,
    request_count: int,
    repetition: int,
    random_seed: int,
) -> TrialResult:
    reset_experiment_data(pool)
    if workload == "low_contention":
        auction_ids = [create_auction(client, index) for index in range(request_count)]
        amounts = [10_000] * request_count
    else:
        auction_ids = [create_auction(client, 0)]
        if workload == "same_price":
            amounts = [10_000] * request_count
        elif workload == "unique_prices":
            amounts = [10_000 + index * 100 for index in range(request_count)]
            random.Random(random_seed).shuffle(amounts)
        else:
            raise ValueError(f"unknown workload: {workload}")

    def execute(index: int) -> RequestObservation:
        auction_id = (
            auction_ids[index] if workload == "low_contention" else auction_ids[0]
        )
        amount = amounts[index]
        started = perf_counter_ns()
        try:
            response = client.post(
                f"/auctions/{auction_id}/bids",
                json={
                    "request_id": str(uuid4()),
                    "bidder_id": f"bidder-{index}",
                    "amount_cents": amount,
                },
            )
            body = response.json()
            if response.status_code == 200:
                status = body["status"]
                reason = None
                attempts = body["attempts"]
                conflicts = body["conflicts"]
            else:
                status = "rejected"
                reason = body.get("detail", {}).get(
                    "reason", f"http_{response.status_code}"
                )
                attempts = 1
                conflicts = 0
        except Exception as exc:
            status = "system_error"
            reason = type(exc).__name__
            attempts = 1
            conflicts = 0
        latency = perf_counter_ns() - started
        return RequestObservation(
            request_index=index,
            auction_id=str(auction_id),
            amount_cents=amount,
            latency_ns=latency,
            status=status,
            reason=reason,
            attempts=attempts,
            conflicts=conflicts,
        )

    wall_started = perf_counter_ns()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        observations = list(executor.map(execute, range(request_count)))
    wall_time = perf_counter_ns() - wall_started

    violations: list[dict[str, str]] = []
    for auction_id in auction_ids:
        report = check_auction_invariants(pool, auction_id)
        violations.extend(
            {"code": violation.code, "detail": violation.detail}
            for violation in report.violations
        )
    return TrialResult.summarize(
        strategy=strategy_label,
        workload=workload,
        concurrency=concurrency,
        repetition=repetition,
        wall_time_ns=wall_time,
        observations=observations,
        invariant_violations=violations,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the live HTTP API")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--strategy-label", required=True)
    parser.add_argument(
        "--workloads", default="same_price,unique_prices,low_contention"
    )
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--random-seed", type=int, default=20260922)
    parser.add_argument("--output", type=Path, default=None)
    arguments = parser.parse_args()
    workloads = [
        item.strip() for item in arguments.workloads.split(",") if item.strip()
    ]
    if not workloads or set(workloads) - WORKLOADS:
        parser.error("unknown workload")
    if arguments.strategy_label not in VALID_STRATEGIES:
        parser.error(f"unknown strategy label: {arguments.strategy_label}")
    if arguments.concurrency <= 0:
        parser.error("concurrency must be positive")
    if arguments.requests <= 0:
        parser.error("requests must be positive")
    if arguments.repetitions < 3:
        parser.error("at least three repetitions are required")

    base_settings = Settings.from_env()
    settings = Settings(
        database_url=arguments.database_url or base_settings.database_url,
        pool_min_size=2,
        pool_max_size=max(20, arguments.concurrency),
    )
    pool = create_pool(settings, name="http-benchmark-db")
    pool.open(wait=True, timeout=30)
    try:
        with pool.connection() as connection:
            migrate(connection)
        with httpx2.Client(
            base_url=arguments.base_url,
            timeout=10,
            limits=httpx2.Limits(
                max_connections=arguments.concurrency,
                max_keepalive_connections=arguments.concurrency,
            ),
        ) as client:
            health_response = client.get("/health")
            health_response.raise_for_status()
            running_strategy = health_response.json().get("bid_strategy")
            if running_strategy != arguments.strategy_label:
                parser.error(
                    "strategy label does not match the running application: "
                    f"expected {arguments.strategy_label!r}, got {running_strategy!r}"
                )
            results = []
            for workload in workloads:
                for repetition in range(1, arguments.repetitions + 1):
                    result = run_http_trial(
                        client,
                        pool,
                        strategy_label=arguments.strategy_label,
                        workload=workload,
                        concurrency=arguments.concurrency,
                        request_count=arguments.requests,
                        repetition=repetition,
                        random_seed=arguments.random_seed + repetition,
                    )
                    results.append(result.to_dict())
                    print(
                        f"http {arguments.strategy_label:11} {workload:15} "
                        f"rep={repetition} "
                        f"throughput={result.throughput_requests_per_second:.1f}/s "
                        f"p95={result.p95_latency_ms:.2f}ms "
                        f"valid={result.invariant_valid}"
                    )

        metadata = environment_metadata(pool, random_seed=arguments.random_seed)
        metadata["configuration"] = {
            "mode": "http",
            "base_url": arguments.base_url,
            "strategy_label": arguments.strategy_label,
            "workloads": workloads,
            "concurrency": arguments.concurrency,
            "requests": arguments.requests,
            "repetitions": arguments.repetitions,
        }
        output = arguments.output
        if output is None:
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            output = Path("benchmark-results") / f"http-{timestamp}.json"
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
