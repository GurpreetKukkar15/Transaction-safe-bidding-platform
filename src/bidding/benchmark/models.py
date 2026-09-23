"""Serializable benchmark observations and summaries."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any


def percentile_ns(samples: list[int], percentile: float) -> int:
    if not samples:
        raise ValueError("at least one latency sample is required")
    if not 0 < percentile <= 100:
        raise ValueError("percentile must be in (0, 100]")
    ordered = sorted(samples)
    index = max(0, math.ceil(percentile / 100 * len(ordered)) - 1)
    return ordered[index]


@dataclass(frozen=True, slots=True)
class RequestObservation:
    request_index: int
    auction_id: str
    amount_cents: int
    latency_ns: int
    status: str
    reason: str | None
    attempts: int
    conflicts: int


@dataclass(frozen=True, slots=True)
class TrialResult:
    strategy: str
    workload: str
    concurrency: int
    request_count: int
    repetition: int
    wall_time_ns: int
    throughput_requests_per_second: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    outcome_counts: dict[str, int]
    total_optimistic_attempts: int
    total_optimistic_conflicts: int
    invariant_valid: bool
    invariant_violations: list[dict[str, str]]
    requests: list[RequestObservation]

    @classmethod
    def summarize(
        cls,
        *,
        strategy: str,
        workload: str,
        concurrency: int,
        repetition: int,
        wall_time_ns: int,
        observations: list[RequestObservation],
        invariant_violations: list[dict[str, str]],
    ) -> TrialResult:
        latencies = [observation.latency_ns for observation in observations]
        counts = Counter(observation.status for observation in observations)
        throughput = len(observations) / (wall_time_ns / 1_000_000_000)
        return cls(
            strategy=strategy,
            workload=workload,
            concurrency=concurrency,
            request_count=len(observations),
            repetition=repetition,
            wall_time_ns=wall_time_ns,
            throughput_requests_per_second=throughput,
            p50_latency_ms=percentile_ns(latencies, 50) / 1_000_000,
            p95_latency_ms=percentile_ns(latencies, 95) / 1_000_000,
            p99_latency_ms=percentile_ns(latencies, 99) / 1_000_000,
            outcome_counts=dict(sorted(counts.items())),
            total_optimistic_attempts=sum(
                observation.attempts for observation in observations
            ),
            total_optimistic_conflicts=sum(
                observation.conflicts for observation in observations
            ),
            invariant_valid=not invariant_violations,
            invariant_violations=invariant_violations,
            requests=observations,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
