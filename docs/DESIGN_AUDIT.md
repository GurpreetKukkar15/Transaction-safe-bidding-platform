# Pre-Implementation Design Audit

Audit date: 2026-09-22

No application code existed when this audit was performed. The purpose was to
remove ambiguous guarantees and experiment-design mistakes before they became
implementation bugs.

## Findings and resolutions

### 1. The first valid bid was ambiguous

Problem: saying every bid must exceed the current price by the minimum
increment leaves unclear whether the first bid must exceed the starting price.

Resolution: the first bid must be at least the starting price. Every later bid
must be at least the accepted current price plus the minimum increment.

### 2. Stored status could disagree with timestamps

Problem: an auction could say `OPEN` after `ends_at`, or `CLOSED` before it.

Resolution: derive `SCHEDULED`, `OPEN`, and `CLOSED` from `starts_at`, `ends_at`,
and the database clock. Do not store a second core status truth.

### 3. Application time and transaction-start time were unsafe boundaries

Problem: application clocks can differ from the database. PostgreSQL
`CURRENT_TIMESTAMP` is fixed at transaction start and can be stale after a
long row-lock wait.

Resolution: use the database's actual clock at the point of validation and test
exactly at `ends_at` and after a deliberately delayed lock acquisition.

### 4. Winner identity was duplicated

Problem: storing only `winner_bidder_id` permits it to disagree with the actual
winning bid.

Resolution: store a nullable `winning_bid_id`, require it to belong to the same
auction, and obtain the bidder from that bid.

### 5. The no-bid price invariant was false

Problem: "current price equals highest accepted bid" has no meaning before any
bid exists.

Resolution: current price and winning bid are null before the first acceptance;
starting price remains a separate field.

### 6. Isolation-level drift could invalidate the experiment

Problem: changing PostgreSQL defaults or running one strategy at a different
isolation level would make results incomparable. `SERIALIZABLE` could abort an
unsafe interleaving instead of exposing it.

Resolution: explicitly configure and verify `READ COMMITTED` for the main
comparison. Treat stronger isolation as a separate optional experiment.

### 7. A helpful unique constraint could hide the intended bug

Problem: unique `(auction_id, auction_version)` would cause a conflicting
unsafe transaction to abort, preventing the lost-update demonstration.

Resolution: omit that constraint deliberately and document the trade-off. Use
the same schema for every strategy and let the invariant checker detect
duplicate or non-monotonic versions.

### 8. Optimistic zero-row updates were underspecified

Problem: an affected-row count of zero might mean a version conflict, a closed
auction, an invalid price, or a missing auction.

Resolution: re-read and classify the outcome before retrying. Retry only true
version conflicts, and use a bounded retry count.

### 9. WebSocket delivery was overstated

Problem: sending only after commit prevents phantom notifications, but the
process can still crash between commit and send. In-memory connection lists are
also single-process, and Redis Pub/Sub is at-most-once.

Resolution: call notifications best-effort state-change hints, include the
auction version, and require clients to re-read PostgreSQL state after a gap or
reconnect. A transactional outbox is optional only if reliable event delivery
becomes an explicit goal.

### 10. Retry behavior after a lost HTTP response was missing

Problem: the client may not know whether its bid committed.

Resolution: accepted bids carry a client request ID. Replaying the same ID and
same payload returns the accepted result; conflicting reuse is rejected. The
initial guarantee does not persist rejected attempts, and documentation will
say so explicitly.

### 11. The pessimistic test expected the wrong number of accepted bids

Problem: two simultaneous increasing bids do not always imply exactly one
acceptance. If the smaller bid locks and commits first, the larger can validly
commit afterward.

Resolution: assert invariants and the final winning state, not a fixed accepted
count unless the test's proposed amounts make that count deterministic.

### 12. The benchmark could accidentally favor one strategy

Problem: an artificial sleep used to reproduce the unsafe race, different
pool sizes, different accepted-work counts, or different schemas would make
throughput comparisons misleading.

Resolution: separate deterministic correctness tests from performance tests;
use identical environment limits; define same-price, unique-price, and
low-contention workloads; save raw outcomes; repeat every configuration; and
run the invariant checker after every trial.

## Why this is not an API-wrapper project

FastAPI exposes the work but is not the technical contribution. The main work
is designing transaction boundaries and SQL, reproducing and explaining an
anomaly, implementing two correctness strategies, building an invariant
oracle, and performing a controlled experiment. PostgreSQL supplies concurrency
primitives; this project demonstrates when and how to combine them correctly.

The project would become wrapper-level if it stopped at CRUD routes, a
WebSocket broadcast, or a call to `SELECT FOR UPDATE` without a failing
baseline, transaction-level tests, invariants, and measured comparison.
