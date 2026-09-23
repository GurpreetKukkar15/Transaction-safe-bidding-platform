# Transaction-Safe Real-Time Bidding Platform

A PostgreSQL concurrency-control lab exposed as a FastAPI auction backend. The
same bid operation is implemented as an intentionally unsafe read-check-write,
pessimistic row locking, and optimistic version checking. Deterministic tests
demonstrate the unsafe anomaly; repeatable benchmarks compare correctness,
throughput, tail latency, and optimistic conflicts.

Implementation status: complete and locally verified on 2026-09-22.

## Why this is not an API wrapper

FastAPI and Psycopg provide transport and database connectivity. This
repository implements and tests the engineering work being evaluated:

- immutable auction rules and integer-cent validation;
- a constrained relational schema with a same-auction winner foreign key;
- explicit transaction boundaries and three SQL concurrency strategies;
- deterministic lost-update reproduction;
- bounded lock waits and optimistic retries;
- accepted-request replay through database-enforced request IDs;
- an independent post-workload invariant checker;
- versioned post-commit WebSocket notifications;
- repository and end-to-end workload generators preserving raw measurements.

## Architecture

```text
client
  |
  v
FastAPI route + Pydantic schema
  |
  v
BiddingService
  |
  +--> unsafe / pessimistic / optimistic transaction strategy
  |                          |
  |                          v
  |                    PostgreSQL 18
  |                          |
  +<---------------- committed outcome
  |
  +--> best-effort versioned WebSocket event
```

PostgreSQL is the source of truth. WebSockets are single-process,
best-effort hints; reconnecting clients receive a snapshot and must resynchronize
after a version gap. See [architecture](docs/ARCHITECTURE.md) and
[transaction strategies](docs/TRANSACTIONS.md).

## Verified results

The controlled repository experiment ran:

- 3 strategies;
- 3 workloads;
- concurrency levels 1, 8, and 32;
- 3 repetitions;
- 200 measured requests per trial;
- 81 trials and 16,200 measured requests total.

All 54 pessimistic and optimistic trials passed invariant checking. The unsafe
strategy failed all 12 contended hot-row trials while passing sequential and
separate-auction controls, showing that the checker distinguishes contention
bugs from ordinary operation.

At 32-way contention on shuffled unique prices:

| Strategy | Median throughput | Median p95 | Median conflicts | Correct trials |
| --- | ---: | ---: | ---: | ---: |
| Unsafe | 2,584.2 req/s | 42.45 ms | 0 | 0/3 |
| Pessimistic | 1,601.3 req/s | 20.54 ms | 0 | 3/3 |
| Optimistic | 2,385.6 req/s | 30.86 ms | 19 | 3/3 |

The separate containerized HTTP run measured the pessimistic strategy at 16
clients. Its shuffled-price workload reached median 1,517.1 req/s with 14.01 ms
p95, with all three trials passing invariants.

These are local experimental measurements, not production-capacity claims.
Read the [methodology](docs/BENCHMARK_METHODOLOGY.md),
[repository results](docs/BENCHMARK_RESULTS.md),
[HTTP results](docs/HTTP_BENCHMARK_RESULTS.md), and raw JSON under
`docs/results/`.

## Quick start

Requirements: Docker Desktop, Docker Compose, and Python 3.11.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements/dev.lock
python -m pip install --no-deps -e .

docker compose up -d --wait db
TEST_DATABASE_URL=postgresql://bidding:bidding@localhost:54329/bidding_test \
  python -m pytest
```

Run the containerized service:

```bash
docker compose up -d --build --wait app
curl http://localhost:8000/health
```

OpenAPI documentation is available at `http://localhost:8000/docs`.
The health response includes the configured bid strategy so benchmark output
cannot be accidentally labeled as a different implementation.

## API

```text
POST /auctions
GET  /auctions/{auction_id}
POST /auctions/{auction_id}/bids
GET  /auctions/{auction_id}/bids
WS   /ws/auctions/{auction_id}
GET  /health
```

The client supplies a UUID `request_id` with every bid. Repeating the same ID
and payload returns the original accepted bid; conflicting reuse returns HTTP
409. Bid validation errors include a machine-readable reason and, where
applicable, the current minimum acceptable amount.

Choose one strategy at application startup:

```bash
BID_STRATEGY=optimistic docker compose up -d --build --force-recreate app
```

Valid values are `unsafe`, `pessimistic`, and `optimistic`. The unsafe option is
for experiments only.

## Tests and fault cases

```bash
make lint
make test-unit
make test-integration
make test
```

The 63-test suite covers domain boundaries, schema constraints, migration
checksums, rollback atomicity, deterministic lost updates, safe concurrent
execution, accepted-request deduplication, auction expiry while waiting for a
row lock, bounded lock timeout, HTTP error mapping, post-commit WebSocket
behavior, and failed-client cleanup.

## Reproduce benchmarks

Smoke matrix:

```bash
make benchmark-smoke
```

Full repository matrix:

```bash
bidding-benchmark \
  --database-url postgresql://bidding:bidding@localhost:54329/bidding_test \
  --concurrencies 1,8,32 \
  --requests 200 \
  --repetitions 3 \
  --output benchmark-results/repository.json
```

Focused, longer workload comparison:

```bash
bidding-benchmark \
  --database-url postgresql://bidding:bidding@localhost:54329/bidding_test \
  --strategies pessimistic,optimistic \
  --workloads unique_prices \
  --concurrency 32 \
  --requests 100000 \
  --repetitions 10 \
  --warmup-requests 1000 \
  --trial-order randomized \
  --summary-only \
  --output benchmark-results/focused.json
```

This focused run records 20 measured trials and two million requests. Summary
mode retains every trial's latency percentiles, outcome counts, conflicts,
errors, invariant result, configuration, environment, and Git revision while
omitting the very large per-request observation arrays. Use it only for the
named 32-client shuffled-price workload, not as a production-capacity claim.
The recorded result is in
[`docs/FOCUSED_BENCHMARK_RESULTS.md`](docs/FOCUSED_BENCHMARK_RESULTS.md), with its
compact source data under `docs/results/`.

End-to-end measurement against a running application:

```bash
bidding-http-benchmark \
  --base-url http://localhost:8000 \
  --database-url postgresql://bidding:bidding@localhost:54329/bidding \
  --strategy-label pessimistic \
  --concurrency 16 \
  --requests 200 \
  --repetitions 3 \
  --output benchmark-results/http.json
```

Every trial saves raw request latency, outcome, attempts, conflicts,
configuration, platform, and PostgreSQL metadata, then runs the invariant
checker. `--summary-only` deliberately omits the per-request arrays for long
runs while retaining the complete per-trial summaries.

## Deliberate limitations

- No authentication, authorization, payment, or anti-fraud system.
- One Uvicorn worker for the in-memory WebSocket connection manager.
- No guaranteed event delivery or transactional outbox.
- Accepted request IDs are deduplicated; rejected attempts are not persisted.
- The experimental schema omits one production-hardening unique constraint so
  the unsafe anomaly remains observable.
- Measurements apply only to the recorded local environment and workloads.

Primary documentation and reviewed implementation assumptions are recorded in
[the source ledger](docs/SOURCES.md). Design trade-offs are recorded as ADRs
under `docs/decisions/`.
