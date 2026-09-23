# ADR 0001: Implement Domain Rules Before Framework Integration

## Status

Accepted

## Context

Auction correctness rules must behave identically whether they are called from
a unit test, an HTTP route, or a PostgreSQL transaction strategy. Embedding the
rules directly in FastAPI routes would couple business behavior to transport
code and make the concurrency implementations harder to compare.

## Decision

Implement monetary, auction-time, and bid-eligibility rules as pure Python
functions and value objects under `src/bidding/domain/`. Domain modules cannot
import FastAPI, Psycopg, or Redis.

## Consequences

- Domain rules can be tested without starting infrastructure.
- HTTP routes and database repositories remain adapters around the same rules.
- PostgreSQL conditions must still repeat critical checks atomically because a
  Python validation performed before a concurrent database update is not, by
  itself, sufficient for correctness.
