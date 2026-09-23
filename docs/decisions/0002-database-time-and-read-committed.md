# ADR 0002: Pin READ COMMITTED and Validate with Actual Database Time

## Status

Accepted

## Context

Different isolation levels can hide or change the anomaly being compared.
Application clocks may drift from PostgreSQL, and PostgreSQL
`CURRENT_TIMESTAMP` is fixed at transaction start even when a transaction
waits for a row lock.

## Decision

Configure every pooled session explicitly as `READ COMMITTED` and UTC. Use
`clock_timestamp()` at the database validation point. In the pessimistic path,
read it only after acquiring the row lock. Bound lock and statement waits.

## Consequences

The three strategies are compared under the same isolation behavior. Auction
expiry remains correct after lock waits, at the cost of an additional database
clock query in the pessimistic path.

