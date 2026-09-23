# Benchmark Results

Raw source: `docs/results/repository-2026-09-22.json`

Recorded at: 2026-09-22T07:26:25.964670+00:00

Platform: `macOS-26.6.2-arm64-arm-64bit`

PostgreSQL: `PostgreSQL 18.6 on aarch64-unknown-linux-musl, compiled by gcc (Alpine 15.2.0) 15.2.0, 64-bit`

All values below are medians across the recorded repetitions. Correctness reports how many trials passed the invariant checker.

| Strategy | Workload | Concurrency | Median throughput (req/s) | Throughput range | p50 (ms) | Median p95 (ms) | p95 range | p99 (ms) | Accepted | Conflicts | System errors | Correct trials |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| optimistic | low_contention | 1 | 772.3 | 762.3-806.7 | 1.24 | 1.50 | 1.38-1.50 | 1.58 | 200 | 0 | 0 | 3/3 |
| optimistic | low_contention | 8 | 2503.8 | 2494.6-2531.7 | 3.11 | 3.85 | 3.66-3.92 | 4.26 | 200 | 0 | 0 | 3/3 |
| optimistic | low_contention | 32 | 1948.1 | 1899.7-1970.7 | 15.01 | 20.73 | 20.29-20.98 | 23.15 | 200 | 0 | 0 | 3/3 |
| optimistic | same_price | 1 | 1309.8 | 1307.4-1322.2 | 0.71 | 0.91 | 0.90-0.91 | 1.79 | 1 | 0 | 0 | 3/3 |
| optimistic | same_price | 8 | 3503.2 | 3466.2-3532.2 | 2.07 | 3.09 | 3.09-3.25 | 6.47 | 1 | 7 | 0 | 3/3 |
| optimistic | same_price | 32 | 2374.1 | 2331.2-2473.7 | 11.16 | 26.14 | 23.22-26.17 | 31.48 | 1 | 19 | 0 | 3/3 |
| optimistic | unique_prices | 1 | 1287.8 | 1278.3-1290.0 | 0.71 | 0.93 | 0.91-0.93 | 1.67 | 7 | 0 | 0 | 3/3 |
| optimistic | unique_prices | 8 | 3482.8 | 3322.2-3627.2 | 1.98 | 3.39 | 2.75-3.68 | 7.96 | 5 | 7 | 0 | 3/3 |
| optimistic | unique_prices | 32 | 2385.6 | 2203.8-2510.6 | 10.14 | 30.86 | 22.65-32.88 | 38.15 | 5 | 19 | 0 | 3/3 |
| pessimistic | low_contention | 1 | 712.2 | 700.9-725.8 | 1.35 | 1.55 | 1.54-1.57 | 1.77 | 200 | 0 | 0 | 3/3 |
| pessimistic | low_contention | 8 | 2254.1 | 2253.1-2274.5 | 3.44 | 4.22 | 4.17-4.32 | 4.48 | 200 | 0 | 0 | 3/3 |
| pessimistic | low_contention | 32 | 1725.4 | 1724.8-1811.8 | 17.28 | 22.15 | 21.65-22.23 | 23.80 | 200 | 0 | 0 | 3/3 |
| pessimistic | same_price | 1 | 986.6 | 972.3-998.1 | 0.96 | 1.16 | 1.15-1.18 | 1.27 | 1 | 0 | 0 | 3/3 |
| pessimistic | same_price | 8 | 1720.1 | 1696.0-1745.9 | 4.46 | 5.11 | 4.84-5.67 | 5.75 | 1 | 0 | 0 | 3/3 |
| pessimistic | same_price | 32 | 1654.5 | 1390.9-1680.6 | 18.13 | 18.84 | 18.35-30.16 | 19.76 | 1 | 0 | 0 | 3/3 |
| pessimistic | unique_prices | 1 | 994.7 | 980.7-995.1 | 0.95 | 1.16 | 1.15-1.38 | 1.59 | 7 | 0 | 0 | 3/3 |
| pessimistic | unique_prices | 8 | 1695.4 | 1693.3-1696.8 | 4.46 | 5.45 | 5.37-5.53 | 6.39 | 8 | 0 | 0 | 3/3 |
| pessimistic | unique_prices | 32 | 1601.3 | 1600.7-1662.6 | 18.35 | 20.54 | 19.82-22.51 | 23.96 | 5 | 0 | 0 | 3/3 |
| unsafe | low_contention | 1 | 855.8 | 845.7-862.5 | 1.13 | 1.39 | 1.36-1.40 | 1.68 | 200 | 0 | 0 | 3/3 |
| unsafe | low_contention | 8 | 2628.4 | 2588.5-2672.0 | 2.96 | 3.61 | 3.59-3.65 | 3.92 | 200 | 0 | 0 | 3/3 |
| unsafe | low_contention | 32 | 2021.0 | 1964.6-2034.1 | 14.77 | 19.69 | 19.25-19.90 | 21.19 | 200 | 0 | 0 | 3/3 |
| unsafe | same_price | 1 | 1397.4 | 1364.7-1447.6 | 0.70 | 0.80 | 0.73-0.89 | 0.85 | 1 | 0 | 0 | 3/3 |
| unsafe | same_price | 8 | 3517.7 | 3459.4-3717.8 | 1.99 | 2.80 | 2.57-2.91 | 6.05 | 8 | 0 | 0 | 0/3 |
| unsafe | same_price | 32 | 2592.6 | 2537.2-2667.8 | 11.21 | 16.43 | 13.66-18.69 | 23.85 | 17 | 0 | 0 | 0/3 |
| unsafe | unique_prices | 1 | 1286.1 | 1278.7-1423.3 | 0.70 | 1.12 | 0.78-1.29 | 1.50 | 7 | 0 | 0 | 3/3 |
| unsafe | unique_prices | 8 | 3427.4 | 3259.6-3552.2 | 2.00 | 3.85 | 3.81-5.19 | 6.49 | 23 | 0 | 0 | 0/3 |
| unsafe | unique_prices | 32 | 2584.2 | 2382.9-2640.9 | 3.36 | 42.45 | 39.16-44.44 | 61.43 | 82 | 0 | 0 | 0/3 |

## Interpretation limits

- Results describe this machine, configuration, dataset, and workload; they are not production-capacity claims.
- The unsafe strategy is a deliberately incorrect experimental baseline. Its speed is not useful when invariants fail.
- Repository-level trials exclude HTTP and JSON overhead. End-to-end HTTP results are reported separately.
- No artificial sleep or barrier is present in performance trials; the deterministic barrier exists only in the correctness test suite.
