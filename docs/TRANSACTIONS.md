# Transaction Strategies

All three strategies use the same schema, `READ COMMITTED` isolation level,
connection-pool limits, domain rules, and workloads. Only the concurrency
control changes.

## Unsafe baseline

```text
BEGIN
read auction without a lock
validate against observed price
insert accepted bid at observed version + 1
update auction without a version predicate
COMMIT
```

Two transactions can both observe version 0, both insert version-1 bids, and
then overwrite the auction row in commit order. The deterministic correctness
test uses a Python barrier after both reads. Performance benchmarks contain no
barrier or artificial delay.

This code is intentionally incorrect and is never presented as a production
option.

## Pessimistic row locking

```text
BEGIN
SELECT auction ... FOR UPDATE
wait until the row lock is owned
read clock_timestamp()
re-check accepted request ID
validate against locked state
insert bid
update auction
COMMIT (releases the row lock)
```

Concurrent writers serialize at the row lock. Validation happens after the
wait, so it uses the latest committed price and actual database time. A session
`lock_timeout` bounds waiting; expiration becomes `StrategyBusyError`, which
the API maps to HTTP 503 with `Retry-After: 1`.

## Optimistic version checking

```text
read auction and version V
validate candidate
BEGIN
insert tentative bid at V + 1
UPDATE auction
  WHERE version = V
    AND actual database time is inside the window
    AND amount satisfies the latest price rule
  RETURNING version
COMMIT on one returned row
ROLLBACK on zero rows
```

The update combines version, time, and price conditions atomically. A zero-row
result is not blindly called a conflict: the strategy re-reads state and
classifies missing auction, closed auction, newly invalid price, or a genuine
retryable version conflict. Retries are bounded. The response and benchmark
records include both attempts and observed conflicts.

## Accepted-request replay

Every bid carries a client-generated request UUID. Accepted request IDs are
unique in PostgreSQL.

- Same ID and same auction, bidder, and amount: return the original accepted
  bid as `replayed`.
- Same ID with a different payload: reject with `request_id_reused`.
- Concurrent duplicate IDs: the unique constraint is the final arbiter; at
  most one bid row commits.

This is deliberately narrower than “exactly once.” Rejected attempts are not
persisted, and the guarantee applies only while accepted bid history remains in
this database.

