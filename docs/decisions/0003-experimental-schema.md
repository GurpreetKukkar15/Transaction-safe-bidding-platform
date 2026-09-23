# ADR 0003: Keep the Experimental Schema Identical Across Strategies

## Status

Accepted

## Context

A unique `(auction_id, auction_version)` constraint would prevent duplicate
versions, but it would also cause an unsafe transaction to abort and conceal
the lost-update behavior being measured.

## Decision

Use the same schema for unsafe, pessimistic, and optimistic strategies. Omit
that one unique constraint deliberately and run an independent invariant
checker after every test and benchmark trial.

## Consequences

The unsafe anomaly remains observable and comparisons are fair. This schema is
an experimental design, not an unqualified production recommendation.

