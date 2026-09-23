# Benchmark Methodology

## Controlled question

How do unsafe read-check-write, pessimistic row locking, and optimistic version
checking differ in correctness and latency under increasing contention?

## Repository experiment

- PostgreSQL 18.6 in Docker on the same machine as the benchmark process.
- Explicit `READ COMMITTED` isolation and UTC database sessions.
- Identical schema, dataset rules, pool limits, and request count.
- Concurrency levels: 1, 8, and 32 workers.
- Workloads: same-price hot row, shuffled unique prices on a hot row, and
  separate-auction low-contention control.
- 200 measured requests per trial.
- Three repetitions for every strategy/workload/concurrency combination.
- One warm-up workload before each strategy/concurrency group.
- Latency measured with monotonic `time.perf_counter_ns()`.
- Nearest-rank p50, p95, and p99 calculated from preserved raw observations.
- Reports show medians plus throughput and p95 ranges across repetitions, and
  surface any system errors instead of treating a valid final state as proof
  that every request executed successfully.
- Invariant checker executed after every trial.

The complete matrix contains 81 trials and 16,200 measured requests. Artificial
race widening is prohibited in performance trials.

## End-to-end HTTP experiment

The separately reported HTTP run includes FastAPI routing, Pydantic validation,
JSON encoding/decoding, application worker scheduling, connection-pool waits,
and PostgreSQL. It uses the containerized pessimistic strategy, 16 clients, 200
requests per trial, three workloads, and three repetitions: 1,800 measured
requests total. Before measuring, the harness checks `/health` and refuses to
run if its strategy label differs from the application's configured strategy.

## Workload meanings

### Same price

Every client submits the same initially valid price to one auction. A correct
strategy can accept at most one bid. This isolates hot-row rejection behavior.

### Shuffled unique prices

Clients submit distinct absolute amounts in a deterministic shuffled order.
Which intermediate bids commit depends on scheduling, but every committed
sequence must remain monotonic and internally consistent.

### Low contention

Every request targets a separate auction. This control distinguishes ordinary
database/application overhead from one-row contention.

## Interpretation

The unsafe implementation is faster in some contended cases precisely because
it accepts mutually inconsistent work. Its throughput is not comparable as a
correct solution when its invariant report fails.

See [repository results](BENCHMARK_RESULTS.md),
[HTTP results](HTTP_BENCHMARK_RESULTS.md), and the raw JSON under
`docs/results/`.

## Focused long-run experiment

The small full matrix answers the broad correctness question but its trials are
too short for a strong performance statement. A separate focused comparison
uses only the two correct strategies, 32 workers, shuffled unique prices on one
auction, 100,000 requests per trial, and 10 repetitions per strategy. Its 20
trials are executed in a reproducibly randomized order to reduce systematic
warm-up or thermal-order bias.

The report includes the median, inclusive interquartile range, full range,
system errors, and invariant results. It also records the Git commit and dirty
state. Summary-only output omits individual request rows to keep two million
observations from producing an unnecessarily large artifact; the smaller
matrix remains available when per-request evidence is needed.

PostgreSQL's own benchmark guidance warns that short runs can produce
meaningless numbers and recommends longer, repeated runs. Even this focused
local experiment remains machine- and workload-specific; it is evidence for a
narrow comparison, not a production sizing claim.

See the recorded [focused result](FOCUSED_BENCHMARK_RESULTS.md) and its compact
source data under `docs/results/`.
