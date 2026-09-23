# ADR 0004: WebSockets Are Versioned Best-Effort Hints

## Status

Accepted

## Context

A database commit and an in-memory WebSocket send cannot be made atomic. A
single-process connection manager also cannot broadcast across multiple
workers, and slow or disconnected clients may miss events.

## Decision

Broadcast only after commit, include the committed auction version, send an
authoritative snapshot on connection, bound individual send time, and remove
failed clients. Run one application worker. Require HTTP resynchronization
after reconnect or a version gap.

## Consequences

No rejected or rolled-back bid creates a phantom event, but not every committed
bid is guaranteed to produce a delivered message. Reliable event delivery and
multi-process fan-out remain explicit non-goals.

