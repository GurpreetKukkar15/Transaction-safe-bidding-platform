"""Unsafe, pessimistic, and optimistic PostgreSQL bid transactions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from uuid import UUID, uuid4

from psycopg import Connection, errors
from psycopg_pool import ConnectionPool

from bidding.db.mappers import auction_from_row, bid_from_row
from bidding.db.repositories import AUCTION_COLUMNS, BID_COLUMNS
from bidding.domain.models import (
    AcceptedBid,
    BidCommand,
    BidOutcome,
    BidRejectionReason,
)
from bidding.domain.rules import evaluate_bid


class BidStrategy(Protocol):
    def place_bid(self, command: BidCommand) -> BidOutcome: ...


class StrategyBusyError(RuntimeError):
    """A bounded database wait expired; callers may retry the whole request."""


class _OptimisticMiss(RuntimeError):
    def __init__(self, observed_version: int) -> None:
        self.observed_version = observed_version
        super().__init__(f"optimistic update missed version {observed_version}")


def _existing_bid(connection: Connection, request_id: UUID) -> AcceptedBid | None:
    row = connection.execute(
        f"SELECT {BID_COLUMNS} FROM bids WHERE request_id = %s",
        (request_id,),
    ).fetchone()
    return None if row is None else bid_from_row(row)


def _replay_or_reject(existing: AcceptedBid, command: BidCommand) -> BidOutcome:
    if (
        existing.auction_id == command.auction_id
        and existing.bidder_id == command.bidder_id.strip()
        and existing.amount_cents == command.amount_cents
    ):
        return BidOutcome.replayed(existing)
    return BidOutcome.rejected(BidRejectionReason.REQUEST_ID_REUSED)


def _resolve_duplicate_request(pool: ConnectionPool, command: BidCommand) -> BidOutcome:
    with pool.connection() as connection:
        existing = _existing_bid(connection, command.request_id)
    if existing is None:
        raise RuntimeError("unique violation was not caused by request_id")
    return _replay_or_reject(existing, command)


def _read_auction(connection: Connection, auction_id: UUID, *, lock: bool = False):
    suffix = " FOR UPDATE" if lock else ""
    row = connection.execute(
        f"SELECT {AUCTION_COLUMNS} FROM auctions WHERE id = %s{suffix}",
        (auction_id,),
    ).fetchone()
    return None if row is None else auction_from_row(row)


def _database_time(connection: Connection):
    row = connection.execute("SELECT clock_timestamp() AS now").fetchone()
    assert row is not None
    return row["now"]


def _insert_bid(
    connection: Connection,
    command: BidCommand,
    *,
    bid_id: UUID,
    auction_version: int,
) -> AcceptedBid:
    row = connection.execute(
        f"""
        INSERT INTO bids (
            id, request_id, auction_id, bidder_id,
            amount_cents, auction_version
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING {BID_COLUMNS}
        """,
        (
            bid_id,
            command.request_id,
            command.auction_id,
            command.bidder_id.strip(),
            command.amount_cents,
            auction_version,
        ),
    ).fetchone()
    assert row is not None
    return bid_from_row(row)


class UnsafeBidStrategy:
    """Intentionally incorrect read-check-write used only as a baseline."""

    def __init__(
        self,
        pool: ConnectionPool,
        *,
        after_read_hook: Callable[[], None] | None = None,
    ) -> None:
        self._pool = pool
        self._after_read_hook = after_read_hook

    def place_bid(self, command: BidCommand) -> BidOutcome:
        try:
            # Keep acquisition and transaction scopes visually separate for teaching.
            with self._pool.connection() as connection:  # noqa: SIM117
                with connection.transaction():
                    existing = _existing_bid(connection, command.request_id)
                    if existing is not None:
                        return _replay_or_reject(existing, command)
                    auction = _read_auction(connection, command.auction_id)
                    if auction is None:
                        return BidOutcome.rejected(BidRejectionReason.AUCTION_NOT_FOUND)
                    evaluation = evaluate_bid(
                        auction,
                        amount_cents=command.amount_cents,
                        now=_database_time(connection),
                    )
                    if not evaluation.accepted:
                        assert evaluation.rejection_reason is not None
                        return BidOutcome.rejected(
                            evaluation.rejection_reason,
                            minimum_acceptable_cents=(
                                evaluation.minimum_acceptable_cents
                            ),
                        )
                    if self._after_read_hook is not None:
                        self._after_read_hook()

                    bid_id = uuid4()
                    bid = _insert_bid(
                        connection,
                        command,
                        bid_id=bid_id,
                        auction_version=auction.version + 1,
                    )
                    # Deliberately missing a version predicate and row lock.
                    connection.execute(
                        """
                        UPDATE auctions
                        SET current_price_cents = %s,
                            winning_bid_id = %s,
                            version = %s
                        WHERE id = %s
                        """,
                        (
                            command.amount_cents,
                            bid_id,
                            auction.version + 1,
                            command.auction_id,
                        ),
                    )
                    return BidOutcome.accepted(bid)
        except errors.UniqueViolation:
            return _resolve_duplicate_request(self._pool, command)


class PessimisticBidStrategy:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def place_bid(self, command: BidCommand) -> BidOutcome:
        try:
            # Keep acquisition and transaction scopes visually separate for teaching.
            with self._pool.connection() as connection:  # noqa: SIM117
                with connection.transaction():
                    existing = _existing_bid(connection, command.request_id)
                    if existing is not None:
                        return _replay_or_reject(existing, command)
                    auction = _read_auction(connection, command.auction_id, lock=True)
                    if auction is None:
                        return BidOutcome.rejected(BidRejectionReason.AUCTION_NOT_FOUND)
                    # The lock may have waited. Read actual time only after it is held.
                    now = _database_time(connection)
                    existing = _existing_bid(connection, command.request_id)
                    if existing is not None:
                        return _replay_or_reject(existing, command)
                    evaluation = evaluate_bid(
                        auction,
                        amount_cents=command.amount_cents,
                        now=now,
                    )
                    if not evaluation.accepted:
                        assert evaluation.rejection_reason is not None
                        return BidOutcome.rejected(
                            evaluation.rejection_reason,
                            minimum_acceptable_cents=(
                                evaluation.minimum_acceptable_cents
                            ),
                        )

                    bid_id = uuid4()
                    bid = _insert_bid(
                        connection,
                        command,
                        bid_id=bid_id,
                        auction_version=auction.version + 1,
                    )
                    connection.execute(
                        """
                        UPDATE auctions
                        SET current_price_cents = %s,
                            winning_bid_id = %s,
                            version = version + 1
                        WHERE id = %s
                        """,
                        (command.amount_cents, bid_id, command.auction_id),
                    )
                    return BidOutcome.accepted(bid)
        except errors.UniqueViolation:
            return _resolve_duplicate_request(self._pool, command)
        except (errors.LockNotAvailable, errors.QueryCanceled) as exc:
            raise StrategyBusyError("database wait timeout expired") from exc


class OptimisticBidStrategy:
    def __init__(self, pool: ConnectionPool, *, max_attempts: int = 5) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        self._pool = pool
        self._max_attempts = max_attempts

    def place_bid(self, command: BidCommand) -> BidOutcome:
        for attempt in range(1, self._max_attempts + 1):
            try:
                return self._attempt(command, attempt=attempt)
            except _OptimisticMiss:
                classification = self._classify_after_miss(command, attempt=attempt)
                if classification is not None:
                    return classification
            except errors.UniqueViolation:
                return _resolve_duplicate_request(self._pool, command)
            except errors.QueryCanceled as exc:
                raise StrategyBusyError("database statement timeout expired") from exc

        return BidOutcome.rejected(
            BidRejectionReason.CONFLICT_RETRY_EXHAUSTED,
            attempts=self._max_attempts,
            conflicts=self._max_attempts,
        )

    def _attempt(self, command: BidCommand, *, attempt: int) -> BidOutcome:
        with self._pool.connection() as connection, connection.transaction():
            existing = _existing_bid(connection, command.request_id)
            if existing is not None:
                outcome = _replay_or_reject(existing, command)
                return BidOutcome(
                    status=outcome.status,
                    bid=outcome.bid,
                    rejection_reason=outcome.rejection_reason,
                    minimum_acceptable_cents=outcome.minimum_acceptable_cents,
                    attempts=attempt,
                    conflicts=attempt - 1,
                )
            auction = _read_auction(connection, command.auction_id)
            if auction is None:
                return BidOutcome.rejected(
                    BidRejectionReason.AUCTION_NOT_FOUND,
                    attempts=attempt,
                )
            evaluation = evaluate_bid(
                auction,
                amount_cents=command.amount_cents,
                now=_database_time(connection),
            )
            if not evaluation.accepted:
                assert evaluation.rejection_reason is not None
                return BidOutcome.rejected(
                    evaluation.rejection_reason,
                    minimum_acceptable_cents=(evaluation.minimum_acceptable_cents),
                    attempts=attempt,
                )

            bid_id = uuid4()
            bid = _insert_bid(
                connection,
                command,
                bid_id=bid_id,
                auction_version=auction.version + 1,
            )
            row = connection.execute(
                """
                    WITH validation_clock AS (
                        SELECT clock_timestamp() AS now
                    )
                    UPDATE auctions AS auction
                    SET current_price_cents = %s,
                        winning_bid_id = %s,
                        version = auction.version + 1
                    FROM validation_clock
                    WHERE auction.id = %s
                      AND auction.version = %s
                      AND validation_clock.now >= auction.starts_at
                      AND validation_clock.now < auction.ends_at
                      AND %s >= CASE
                            WHEN auction.current_price_cents IS NULL
                                THEN auction.starting_price_cents
                            ELSE auction.current_price_cents
                                 + auction.minimum_increment_cents
                          END
                    RETURNING auction.version
                    """,
                (
                    command.amount_cents,
                    bid_id,
                    command.auction_id,
                    auction.version,
                    command.amount_cents,
                ),
            ).fetchone()
            if row is None:
                raise _OptimisticMiss(auction.version)
            return BidOutcome.accepted(
                bid,
                attempts=attempt,
                conflicts=attempt - 1,
            )

    def _classify_after_miss(
        self, command: BidCommand, *, attempt: int
    ) -> BidOutcome | None:
        with self._pool.connection() as connection:
            existing = _existing_bid(connection, command.request_id)
            if existing is not None:
                return _replay_or_reject(existing, command)
            auction = _read_auction(connection, command.auction_id)
            if auction is None:
                return BidOutcome.rejected(
                    BidRejectionReason.AUCTION_NOT_FOUND,
                    attempts=attempt,
                    conflicts=attempt,
                )
            evaluation = evaluate_bid(
                auction,
                amount_cents=command.amount_cents,
                now=_database_time(connection),
            )
        if not evaluation.accepted:
            assert evaluation.rejection_reason is not None
            return BidOutcome.rejected(
                evaluation.rejection_reason,
                minimum_acceptable_cents=evaluation.minimum_acceptable_cents,
                attempts=attempt,
                conflicts=attempt,
            )
        if attempt >= self._max_attempts:
            return BidOutcome.rejected(
                BidRejectionReason.CONFLICT_RETRY_EXHAUSTED,
                attempts=attempt,
                conflicts=attempt,
            )
        return None


def strategy_from_name(
    name: str,
    pool: ConnectionPool,
    *,
    optimistic_max_attempts: int = 5,
) -> BidStrategy:
    if name == "unsafe":
        return UnsafeBidStrategy(pool)
    if name == "pessimistic":
        return PessimisticBidStrategy(pool)
    if name == "optimistic":
        return OptimisticBidStrategy(pool, max_attempts=optimistic_max_attempts)
    raise ValueError(f"unknown bid strategy: {name}")
