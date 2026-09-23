# Primary Source Ledger

Last reviewed: 2026-09-22

This file records the sources that govern implementation decisions. Before a
phase begins, review the relevant source again because library behavior and
recommended APIs can change.

## Source policy

- Prefer official product and language documentation.
- Use articles and repositories only as secondary examples, never as the sole
  authority for transaction or delivery guarantees.
- Keep abstract compatibility ranges in `pyproject.toml`, resolved versions in
  `requirements/*.lock`, and exact container tags in `Dockerfile` and
  `compose.yaml`.
- Record important design choices under `docs/decisions/` as short architecture
  decision records.
- Confirm every important guarantee with an automated test. Documentation tells
  us intended behavior; the test verifies our configuration and code use it
  correctly.

## PostgreSQL

### Transaction isolation

Source: [PostgreSQL transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html)

Use it to:

- understand snapshots and visibility at `READ COMMITTED`;
- explain how successive statements can observe different committed data;
- design the unsafe lost-update experiment;
- avoid comparing strategies under accidentally different isolation levels;
- identify errors that require whole-transaction retries at stronger levels.

Project decision: the primary locking comparison explicitly uses
`READ COMMITTED`. A later optional experiment may compare `SERIALIZABLE`, but it
must not be mixed into the main results.

### Explicit row locking

Source: [PostgreSQL explicit locking](https://www.postgresql.org/docs/current/explicit-locking.html)

Use it to:

- implement and explain `SELECT ... FOR UPDATE`;
- understand which concurrent writers and lockers are blocked;
- confirm that row locks last until transaction end;
- design lock-wait, rollback, timeout, and deadlock tests.

### Constraints

Source: [PostgreSQL data constraints](https://www.postgresql.org/docs/current/ddl-constraints.html)

Use it to:

- choose `NOT NULL`, `CHECK`, `UNIQUE`, and foreign-key constraints;
- understand what the database can enforce locally;
- document cross-table invariants that still need transactional logic and an
  invariant checker.

### `UPDATE`, `INSERT`, and `RETURNING`

Sources:

- [PostgreSQL UPDATE](https://www.postgresql.org/docs/current/sql-update.html)
- [PostgreSQL INSERT](https://www.postgresql.org/docs/current/sql-insert.html)

Use them to:

- implement the optimistic conditional update;
- inspect affected or returned rows instead of performing a blind write;
- handle unique request IDs and conflicts deliberately;
- keep the auction update and bid insertion in one transaction.

### Database time

Source: [PostgreSQL date/time functions](https://www.postgresql.org/docs/current/functions-datetime.html)

Use it to distinguish transaction-start time, statement-start time, and actual
clock time. `CURRENT_TIMESTAMP` is fixed at transaction start, so it is unsafe
for an expiry decision made after a long row-lock wait. The implementation will
check actual database time at the validation point and test the end-time
boundary.

### Query plans

Source: [PostgreSQL EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html)

Use it to inspect whether auction lookup and bid-history queries use intended
indexes. Remember that `EXPLAIN ANALYZE` executes the statement; modifying
statements must be tested inside a transaction that is rolled back.

## Python/PostgreSQL driver

### Psycopg transactions

Source: [Psycopg transaction management](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)

Use it to:

- create explicit transaction boundaries;
- guarantee rollback after exceptions;
- avoid connections remaining idle in a transaction;
- distinguish a transaction block from a nested savepoint;
- configure and verify isolation behavior.

### Psycopg connection pools

Source: [Psycopg connection pools](https://www.psycopg.org/psycopg3/docs/advanced/pool.html)

Use it to:

- bound database concurrency;
- ensure one concurrent transaction does not share a connection with another;
- measure pool-wait time separately when interpreting latency;
- reset transaction state before a connection returns to the pool.

Project decision: use Psycopg and explicit SQL. An ORM would not make the
project invalid, but it would hide the SQL and transaction mechanics that this
project exists to study.

## Python environment and packaging

### Virtual environments

Source: [Python virtual environments](https://docs.python.org/3.11/tutorial/venv.html)

Use a repository-local `.venv` to isolate this project's dependencies from the
system interpreter and other projects. The directory is generated state and is
therefore excluded from version control.

### Project metadata and `src` layout

Sources:

- [Packaging Python Projects](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
- [`src` layout versus flat layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)

Use `pyproject.toml` as the build and tool configuration file. The `src` layout
requires installing the package before import, which helps prevent tests from
silently importing an uninstalled working-tree copy.

Resolved on 2026-09-22 with Python 3.11.15. Runtime and test-tool versions are
recorded in `requirements/runtime.lock` and `requirements/dev.lock`; the
isolated package-build backend is pinned in `pyproject.toml`.

## FastAPI and WebSockets

### Concurrency model

Source: [FastAPI concurrency and async/await](https://fastapi.tiangolo.com/async/)

Use it to choose `def` for blocking database calls or `async def` for genuinely
awaitable libraries. Never call a blocking driver directly from an async route
and assume the endpoint remains non-blocking.

### WebSockets

Source: [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)

Use it for connection lifecycle and disconnect handling. FastAPI's simple
in-memory connection-list example works only in one process, so the initial
implementation will state that limitation explicitly.

### API tests

Source: [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/)

Use it for route-level tests through `TestClient`. Database concurrency tests
will still execute against real PostgreSQL because an HTTP test client or mock
database cannot demonstrate row-lock behavior.

The resolved FastAPI 0.141.1 installation uses Starlette 1.6.0, whose test
client declares HTTPX2. The development lock therefore uses `httpx2==2.13.0`
rather than the legacy `httpx` package.

## Redis - optional

Source: [Redis Pub/Sub delivery semantics](https://redis.io/docs/latest/develop/pubsub/)

Use it only if multi-process WebSocket fan-out is implemented. Redis Pub/Sub is
at-most-once: a disconnected subscriber can lose an event. Therefore it may
carry best-effort state-change hints, but it must not become the auction's
source of truth or be described as reliable delivery.

## Test and benchmark infrastructure

### Docker Compose readiness

Source: [Docker Compose startup order](https://docs.docker.com/compose/how-tos/startup-order/)

Use a PostgreSQL healthcheck and `service_healthy`. Container startup order
alone does not mean the database is ready to accept connections.

### Official container images

Sources:

- [Python official image](https://hub.docker.com/_/python)
- [PostgreSQL official image](https://hub.docker.com/_/postgres)

Resolved tags on 2026-09-22:

- application: `python:3.11.15-slim`;
- database: `postgres:18.6-alpine3.24`.

PostgreSQL's official image changed its versioned `PGDATA` and declared volume
for major version 18. The Compose volume is consequently mounted at
`/var/lib/postgresql`, as documented by the image, rather than the older
`/var/lib/postgresql/data` location.

### Deterministic concurrency

Source: [Python threading and barrier objects](https://docs.python.org/3/library/threading.html#barrier-objects)

Use a barrier only in the correctness experiment to make unsafe transactions
overlap reproducibly. Do not leave artificial pauses or barriers in throughput
benchmarks.

### PostgreSQL benchmark practice

Source: [PostgreSQL pgbench](https://www.postgresql.org/docs/current/pgbench.html)

Use its good-practice guidance to avoid presenting short, noisy runs as stable
performance results. Run longer trials, repeat them, preserve failures and
retry counts, report variability, and state the exact clients, workload,
machine, database, and source revision used. The project uses its own workload
harness rather than claiming that its numbers are pgbench results.

### Monotonic latency timing

Source: [Python `time.perf_counter_ns`](https://docs.python.org/3/library/time.html#time.perf_counter_ns)

Use the monotonic high-resolution performance counter for request duration.
Preserve raw nanosecond observations and derive percentile summaries from the
saved data.

### pytest fixtures

Source: [pytest fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html)

Use fixtures for isolated auction data and reliable cleanup. Do not let tests
depend on execution order or shared state left by a previous test.

## Per-phase reading map

| Phase | Read before implementation |
| --- | --- |
| 0-1 | PostgreSQL isolation overview; Python clock/test documentation |
| 2 | PostgreSQL constraints and time; Psycopg transactions/pools; Docker readiness |
| 3 | PostgreSQL `READ COMMITTED`; Python barriers |
| 4 | PostgreSQL explicit row locking and lock timeout behavior |
| 5 | PostgreSQL `UPDATE ... WHERE ... RETURNING`; transaction retry rules |
| 6 | FastAPI concurrency/testing; Psycopg pool behavior |
| 7 | FastAPI WebSockets; Redis semantics only if Redis is added |
| 8 | Python performance timing; PostgreSQL EXPLAIN; saved benchmark protocol |
| 9 | Re-read every source supporting a documented guarantee or published claim |
