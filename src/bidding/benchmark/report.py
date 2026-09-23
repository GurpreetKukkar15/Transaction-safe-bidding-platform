"""Convert preserved benchmark JSON into a compact, auditable Markdown report."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import median, quantiles
from typing import Any


def render_markdown(document: dict[str, Any], *, source_name: str) -> str:
    metadata = document["metadata"]
    trials = document["trials"]
    mode = metadata.get("configuration", {}).get("mode", "repository")
    observations = metadata.get("configuration", {}).get(
        "request_observations", "preserved"
    )
    source_label = "Summary source" if observations == "omitted" else "Raw source"
    strategies = {trial["strategy"] for trial in trials}
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for trial in trials:
        grouped[(trial["strategy"], trial["workload"], trial["concurrency"])].append(
            trial
        )

    lines = [
        "# Benchmark Results",
        "",
        f"{source_label}: `{source_name}`",
        "",
        f"Recorded at: {metadata['recorded_at']}",
        "",
        f"Platform: `{metadata['platform']}`",
        "",
        f"PostgreSQL: `{metadata['postgresql']['version']}`",
        "",
        "Git commit: "
        f"`{metadata.get('source', {}).get('git_commit') or 'unavailable'}` "
        f"(dirty: `{metadata.get('source', {}).get('git_dirty')}`)",
        "",
        "All values below are medians across the recorded repetitions. "
        "IQR is the inclusive 25th-75th percentile interval. Correctness reports "
        "how many trials passed the invariant checker.",
        "",
        "| Strategy | Workload | Concurrency | Median throughput (req/s) | "
        "Throughput IQR | Throughput range | p50 (ms) | Median p95 (ms) | "
        "p95 IQR | p95 range | "
        "p99 (ms) | Accepted | Conflicts | System errors | Correct trials |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for (strategy, workload, concurrency), group in sorted(grouped.items()):
        throughput = median(trial["throughput_requests_per_second"] for trial in group)
        p50 = median(trial["p50_latency_ms"] for trial in group)
        p95 = median(trial["p95_latency_ms"] for trial in group)
        p99 = median(trial["p99_latency_ms"] for trial in group)
        throughput_values = [trial["throughput_requests_per_second"] for trial in group]
        p95_values = [trial["p95_latency_ms"] for trial in group]
        throughput_q1, _, throughput_q3 = quantiles(
            throughput_values, n=4, method="inclusive"
        )
        p95_q1, _, p95_q3 = quantiles(p95_values, n=4, method="inclusive")
        throughput_range = (
            min(throughput_values),
            max(throughput_values),
        )
        p95_range = (
            min(p95_values),
            max(p95_values),
        )
        accepted = median(trial["outcome_counts"].get("accepted", 0) for trial in group)
        conflicts = median(trial["total_optimistic_conflicts"] for trial in group)
        system_errors = sum(
            trial["outcome_counts"].get("system_error", 0) for trial in group
        )
        valid_count = sum(trial["invariant_valid"] for trial in group)
        lines.append(
            f"| {strategy} | {workload} | {concurrency} | {throughput:.1f} | "
            f"{throughput_q1:.1f}-{throughput_q3:.1f} | "
            f"{throughput_range[0]:.1f}-{throughput_range[1]:.1f} | "
            f"{p50:.2f} | {p95:.2f} | {p95_q1:.2f}-{p95_q3:.2f} | "
            f"{p95_range[0]:.2f}-{p95_range[1]:.2f} | "
            f"{p99:.2f} | {accepted:g} | {conflicts:g} | {system_errors} | "
            f"{valid_count}/{len(group)} |"
        )

    lines.extend(["", "## Interpretation limits", ""])
    lines.append(
        "- Results describe this machine, configuration, dataset, and workload; "
        "they are not production-capacity claims."
    )
    if observations == "omitted":
        lines.append(
            "- Per-request observations were omitted; the source preserves "
            "per-trial summaries, outcomes, errors, conflicts, and invariant results."
        )
    if mode == "http":
        lines.append(
            "- These end-to-end trials include HTTP, JSON validation, application "
            "thread-pool, connection-pool, and PostgreSQL time."
        )
        lines.append(
            "- This dataset measures only the strategy named in the report; use the "
            "repository experiment for controlled cross-strategy comparison."
        )
    elif "unsafe" in strategies:
        lines.append(
            "- The unsafe strategy is a deliberately incorrect experimental baseline. "
            "Its speed is not useful when invariants fail."
        )
    if mode != "http":
        lines.append(
            "- Repository-level trials exclude HTTP and JSON overhead. End-to-end HTTP "
            "results are reported separately."
        )
    if any(trial["workload"] == "unique_prices" for trial in trials):
        lines.append(
            "- Shuffled absolute bid values can become stale before execution; "
            "consider the accepted counts when interpreting this workload's throughput."
        )
    lines.extend(
        [
            "- No artificial sleep or barrier is present in performance trials; the "
            "deterministic barrier exists only in the correctness test suite.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render benchmark JSON as Markdown")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    document = json.loads(arguments.input.read_text(encoding="utf-8"))
    report = render_markdown(document, source_name=str(arguments.input))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(report, encoding="utf-8")
    print(f"Benchmark report written to {arguments.output}")


if __name__ == "__main__":
    main()
