# Benchmark Results

Summary source: `docs/results/focused-2026-09-23.json`

Recorded at: 2026-09-23T16:47:20.413859+00:00

Platform: `macOS-26.6.2-arm64-arm-64bit`

PostgreSQL: `PostgreSQL 18.6 on aarch64-unknown-linux-musl, compiled by gcc (Alpine 15.2.0) 15.2.0, 64-bit`

Git commit: `20978dcd55747e8f12e6efc397f083287db2e13e` (dirty: `False`)

All values below are medians across the recorded repetitions. IQR is the inclusive 25th-75th percentile interval. Correctness reports how many trials passed the invariant checker.

| Strategy | Workload | Concurrency | Median throughput (req/s) | Throughput IQR | Throughput range | p50 (ms) | Median p95 (ms) | p95 IQR | p95 range | p99 (ms) | Accepted | Conflicts | System errors | Correct trials |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| optimistic | unique_prices | 32 | 1920.7 | 1833.4-2136.1 | 1759.5-2181.1 | 16.09 | 23.92 | 21.37-25.13 | 21.05-26.37 | 28.05 | 14 | 54.5 | 0 | 10/10 |
| pessimistic | unique_prices | 32 | 1164.3 | 1127.8-1481.8 | 1074.4-1773.1 | 26.74 | 30.34 | 25.50-31.59 | 18.79-36.12 | 36.63 | 13 | 0 | 0 | 10/10 |

## Interpretation limits

- Results describe this machine, configuration, dataset, and workload; they are not production-capacity claims.
- Per-request observations were omitted; the source preserves per-trial summaries, outcomes, errors, conflicts, and invariant results.
- Repository-level trials exclude HTTP and JSON overhead. End-to-end HTTP results are reported separately.
- Shuffled absolute bid values can become stale before execution; consider the accepted counts when interpreting this workload's throughput.
- No artificial sleep or barrier is present in performance trials; the deterministic barrier exists only in the correctness test suite.
