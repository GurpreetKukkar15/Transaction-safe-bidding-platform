# Architecture

## Purpose

The system is an auction backend and concurrency-control experiment. Its core
question is not how to expose CRUD endpoints. It asks how three implementations
of the same bid operation behave when requests contend for one PostgreSQL row.

## Component flow

```text
HTTP/WebSocket client
        |
        v
FastAPI schemas and routes
        |
        v
BiddingService
        |
        +-----------------------+
        |                       |
        v                       v
AuctionRepository       configured BidStrategy
                                |
                +---------------+---------------+
                |               |               |
                v               v               v
             unsafe        pessimistic      optimistic
                |               |               |
                +---------------+---------------+
                                |
                                v
                    Psycopg connection pool
                                |
                                v
                         PostgreSQL 18
                                |
                         committed result
                                |
                                v
                 best-effort WebSocket event
```

The domain package imports no FastAPI, Psycopg, or WebSocket code. This keeps
auction rules independently testable. The critical price, time, and version
conditions are repeated atomically in SQL where application-only checks would
be vulnerable to concurrent change.

## Request lifecycle

1. Pydantic rejects malformed transport input, including booleans supplied as
   integer money values and timezone-naive timestamps.
2. The route converts the request into a `BidCommand`.
3. FastAPI runs the blocking Psycopg operation in its worker thread pool rather
   than blocking the event loop.
4. The configured strategy obtains one connection for one transaction.
5. PostgreSQL either commits the bid row and auction update together or rolls
   both back.
6. Only an accepted, committed outcome produces a WebSocket hint.
7. A replay of an already accepted request returns the original bid but does
   not emit a duplicate event.

## Data model

```text
auctions                                  bids
----------------------------------        --------------------------------
id (PK)                             <---- auction_id (FK)
starting_price_cents                      id (PK)
current_price_cents                       request_id (UNIQUE)
minimum_increment_cents                   bidder_id
winning_bid_id -------------------------> amount_cents
version                                   auction_version
starts_at / ends_at                       accepted_at
```

The composite foreign key `(auctions.id, auctions.winning_bid_id)` references
`(bids.auction_id, bids.id)`. This prevents an auction from naming a bid from a
different auction as its winner. It is deferred until transaction commit so a
new bid can be inserted before the auction points to it.

There is deliberately no unique constraint on `(auction_id, auction_version)`.
Such a constraint would abort one unsafe transaction and hide the anomaly the
experiment is designed to observe. The independent invariant checker detects
duplicate or missing committed versions after every workload.

## Time model

Auction state is derived from the half-open interval `[starts_at, ends_at)`:

```text
database clock < starts_at             scheduled
starts_at <= database clock < ends_at  open
database clock >= ends_at              closed
```

The pessimistic strategy asks PostgreSQL for `clock_timestamp()` after it owns
the row lock. `CURRENT_TIMESTAMP` is unsuitable because PostgreSQL fixes it at
transaction start, which may precede a long lock wait.

## WebSocket delivery model

WebSocket messages are versioned, best-effort state-change hints. The initial
implementation intentionally runs one application worker and stores live
connections in memory. A process crash can occur after database commit and
before broadcast, and disconnected clients can miss messages. Therefore:

- PostgreSQL is always authoritative;
- clients receive a current snapshot on connection;
- every event includes the auction version;
- clients detecting a gap or reconnecting must fetch current HTTP state;
- Redis Pub/Sub and reliable delivery are not claimed.

## Deployment boundary

Docker Compose starts PostgreSQL with a health check. The application depends
on `service_healthy`, runs checksum-verified SQL migrations during lifespan
startup, uses one Uvicorn worker, and exposes its own `/health` check. The
container runs as a non-root user.

