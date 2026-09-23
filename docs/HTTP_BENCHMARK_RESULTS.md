# Benchmark Results

Raw source: `docs/results/http-pessimistic-2026-09-22.json`

Recorded at: 2026-09-22T07:46:25.229280+00:00

Platform: `macOS-26.6.2-arm64-arm-64bit`

PostgreSQL: `PostgreSQL 18.6 on aarch64-unknown-linux-musl, compiled by gcc (Alpine 15.2.0) 15.2.0, 64-bit`

All values below are medians across the recorded repetitions. Correctness reports how many trials passed the invariant checker.

| Strategy | Workload | Concurrency | Median throughput (req/s) | Throughput range | p50 (ms) | Median p95 (ms) | p95 range | p99 (ms) | Accepted | Conflicts | System errors | Correct trials |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pessimistic | low_contention | 16 | 891.4 | 878.2-899.3 | 17.34 | 23.24 | 23.22-23.98 | 25.60 | 200 | 0 | 0 | 3/3 |
| pessimistic | same_price | 16 | 1503.9 | 1202.2-1550.1 | 10.89 | 13.37 | 12.37-23.95 | 18.69 | 1 | 0 | 0 | 3/3 |
| pessimistic | unique_prices | 16 | 1517.1 | 1442.0-1520.2 | 10.70 | 14.01 | 13.12-16.95 | 18.97 | 5 | 0 | 0 | 3/3 |

## Interpretation limits

- Results describe this machine, configuration, dataset, and workload; they are not production-capacity claims.
- These end-to-end trials include HTTP, JSON validation, application thread-pool, connection-pool, and PostgreSQL time.
- This dataset measures only the strategy named in the report; use the repository experiment for controlled cross-strategy comparison.
- No artificial sleep or barrier is present in performance trials; the deterministic barrier exists only in the correctness test suite.
