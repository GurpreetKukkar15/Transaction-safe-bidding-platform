from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from psycopg import errors

from bidding.db.migrations import migrate
from bidding.db.repositories import AuctionRepository

pytestmark = pytest.mark.integration


def test_migration_is_recorded_once(direct_connection) -> None:
    rows = direct_connection.execute(
        "SELECT version, name FROM schema_migrations ORDER BY version"
    ).fetchall()

    assert rows == [{"version": 1, "name": "initial_schema"}]


def test_migration_rejects_applied_checksum_drift(direct_connection) -> None:
    with direct_connection.transaction(force_rollback=True):
        direct_connection.execute(
            "UPDATE schema_migrations SET checksum = 'not-the-real-checksum' "
            "WHERE version = 1"
        )

        with pytest.raises(RuntimeError, match="applied migration 001 has changed"):
            migrate(direct_connection)


def test_database_session_is_explicitly_configured(db_pool) -> None:
    with db_pool.connection() as connection:
        values = connection.execute(
            """
            SELECT
                current_setting('transaction_isolation') AS isolation,
                current_setting('TimeZone') AS timezone,
                current_setting('lock_timeout') AS lock_timeout,
                current_setting('statement_timeout') AS statement_timeout
            """
        ).fetchone()

    assert values == {
        "isolation": "read committed",
        "timezone": "UTC",
        "lock_timeout": "2s",
        "statement_timeout": "10s",
    }


def test_database_rejects_invalid_money(direct_connection, clean_database) -> None:
    now = datetime.now(UTC)

    with pytest.raises(errors.CheckViolation), direct_connection.transaction():
        direct_connection.execute(
            """
                INSERT INTO auctions (
                    id, title, starting_price_cents,
                    minimum_increment_cents, starts_at, ends_at
                )
                VALUES (%s, 'Invalid', 0, 100, %s, %s)
                """,
            (uuid4(), now, now + timedelta(hours=1)),
        )


def test_winning_bid_must_belong_to_same_auction(
    direct_connection, clean_database
) -> None:
    now = datetime.now(UTC)
    first_auction = uuid4()
    second_auction = uuid4()
    bid_id = uuid4()

    with pytest.raises(errors.ForeignKeyViolation), direct_connection.transaction():
        for auction_id in (first_auction, second_auction):
            direct_connection.execute(
                """
                    INSERT INTO auctions (
                        id, title, starting_price_cents,
                        minimum_increment_cents, starts_at, ends_at
                    ) VALUES (%s, 'Auction', 100, 10, %s, %s)
                    """,
                (auction_id, now - timedelta(minutes=1), now + timedelta(hours=1)),
            )
        direct_connection.execute(
            """
                INSERT INTO bids (
                    id, request_id, auction_id, bidder_id,
                    amount_cents, auction_version
                ) VALUES (%s, %s, %s, 'alice', 100, 1)
                """,
            (bid_id, uuid4(), first_auction),
        )
        direct_connection.execute(
            """
                UPDATE auctions
                SET current_price_cents = 100,
                    winning_bid_id = %s,
                    version = 1
                WHERE id = %s
                """,
            (bid_id, second_auction),
        )


def test_bid_insert_rolls_back_if_transaction_fails(
    direct_connection, db_pool, clean_database
) -> None:
    now = datetime.now(UTC)
    auction = AuctionRepository(db_pool).create(
        title="Rollback test",
        starting_price_cents=100,
        minimum_increment_cents=10,
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(hours=1),
    )

    with (
        pytest.raises(RuntimeError, match="deliberate"),
        direct_connection.transaction(),
    ):
        direct_connection.execute(
            """
                INSERT INTO bids (
                    id, request_id, auction_id, bidder_id,
                    amount_cents, auction_version
                ) VALUES (%s, %s, %s, 'alice', 100, 1)
            """,
            (uuid4(), uuid4(), auction.id),
        )
        raise RuntimeError("deliberate rollback")

    count = direct_connection.execute(
        "SELECT count(*) AS count FROM bids WHERE auction_id = %s",
        (auction.id,),
    ).fetchone()
    assert count == {"count": 0}


def test_history_query_uses_designed_index(direct_connection, clean_database) -> None:
    direct_connection.execute("SET LOCAL enable_seqscan = off")
    plan = direct_connection.execute(
        """
        EXPLAIN (FORMAT TEXT)
        SELECT * FROM bids
        WHERE auction_id = %s
        ORDER BY auction_version DESC, accepted_at DESC
        """,
        (uuid4(),),
    ).fetchall()
    text = "\n".join(row["QUERY PLAN"] for row in plan)

    assert "bids_auction_history_idx" in text
