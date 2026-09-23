from bidding.benchmark.cli import build_trial_schedule, parse_positive_int_csv
from bidding.benchmark.models import RequestObservation, TrialResult, percentile_ns
from bidding.benchmark.report import render_markdown


def test_percentile_uses_nearest_rank() -> None:
    samples = list(range(1, 101))

    assert percentile_ns(samples, 50) == 50
    assert percentile_ns(samples, 95) == 95
    assert percentile_ns(samples, 99) == 99


def test_concurrency_levels_are_parsed_and_validated() -> None:
    assert parse_positive_int_csv("1, 8,32") == [1, 8, 32]


def test_randomized_trial_schedule_is_complete_and_reproducible() -> None:
    arguments = {
        "strategies": ["pessimistic", "optimistic"],
        "workloads": ["unique_prices"],
        "concurrency_levels": [32],
        "repetitions": 5,
        "random_seed": 42,
        "randomized": True,
    }

    first = build_trial_schedule(**arguments)
    second = build_trial_schedule(**arguments)

    assert first == second
    assert len(first) == 10
    assert set(first) == {
        (strategy, "unique_prices", 32, repetition)
        for strategy in ("pessimistic", "optimistic")
        for repetition in range(1, 6)
    }
    assert first != sorted(first)


def test_trial_summary_preserves_raw_observations() -> None:
    observations = [
        RequestObservation(0, "auction", 100, 1_000_000, "accepted", None, 1, 0),
        RequestObservation(1, "auction", 100, 3_000_000, "rejected", "low", 2, 1),
    ]

    result = TrialResult.summarize(
        strategy="optimistic",
        workload="same_price",
        concurrency=2,
        repetition=1,
        wall_time_ns=4_000_000,
        observations=observations,
        invariant_violations=[],
    )

    assert result.throughput_requests_per_second == 500
    assert result.p50_latency_ms == 1
    assert result.p95_latency_ms == 3
    assert result.outcome_counts == {"accepted": 1, "rejected": 1}
    assert result.total_optimistic_attempts == 3
    assert result.total_optimistic_conflicts == 1
    assert result.requests == observations


def test_markdown_report_aggregates_repetitions() -> None:
    trial = {
        "strategy": "pessimistic",
        "workload": "same_price",
        "concurrency": 8,
        "throughput_requests_per_second": 1000.0,
        "p50_latency_ms": 2.0,
        "p95_latency_ms": 5.0,
        "p99_latency_ms": 7.0,
        "outcome_counts": {"accepted": 1, "rejected": 9},
        "total_optimistic_conflicts": 0,
        "invariant_valid": True,
    }
    document = {
        "metadata": {
            "recorded_at": "2026-09-22T00:00:00+00:00",
            "platform": "test-platform",
            "postgresql": {"version": "PostgreSQL test"},
        },
        "trials": [trial, trial, trial],
    }

    report = render_markdown(document, source_name="raw.json")

    assert "| pessimistic | same_price | 8 | 1000.0" in report
    assert "3/3" in report
    assert "unsafe strategy" not in report


def test_summary_only_report_labels_its_source_accurately() -> None:
    trial = {
        "strategy": "optimistic",
        "workload": "unique_prices",
        "concurrency": 32,
        "throughput_requests_per_second": 1000.0,
        "p50_latency_ms": 2.0,
        "p95_latency_ms": 5.0,
        "p99_latency_ms": 7.0,
        "outcome_counts": {"accepted": 1, "rejected": 9},
        "total_optimistic_conflicts": 1,
        "invariant_valid": True,
    }
    document = {
        "metadata": {
            "recorded_at": "2026-09-23T00:00:00+00:00",
            "platform": "test-platform",
            "postgresql": {"version": "PostgreSQL test"},
            "configuration": {"request_observations": "omitted"},
        },
        "trials": [trial, trial, trial],
    }

    report = render_markdown(document, source_name="summary.json")

    assert "Summary source: `summary.json`" in report
