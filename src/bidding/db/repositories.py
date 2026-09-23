"""Ordinary auction reads/writes that do not choose a bidding strategy."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from psycopg_pool import ConnectionPool

from bidding.db.mappers import auction_from_row, bid_from_row
from bidding.domain.models import AcceptedBid, AuctionSnapshot

AUCTION_COLUMNS = """
    id, title, starting_price_cents, current_price_cents,
    minimum_increment_cents, winning_bid_id, version,
    starts_at, ends_at, created_at
"""

BID_COLUMNS = """
    id, request_id, auction_id, bidder_id, amount_cents,
    auction_version, accepted_at
"""


class AuctionRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create(
        self,
        *,
        title: str,
        starting_price_cents: int,
        minimum_increment_cents: int,
        starts_at: datetime,
        ends_at: datetime,
        auction_id: UUID | None = None,
    ) -> AuctionSnapshot:
        identifier = auction_id or uuid4()
        with self._pool.connection() as connection, connection.transaction():
            row = connection.execute(
                f"""
                    INSERT INTO auctions (
                        id, title, starting_price_cents,
                        minimum_increment_cents, starts_at, ends_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING {AUCTION_COLUMNS}
                    """,
                (
                    identifier,
                    title.strip(),
                    starting_price_cents,
                    minimum_increment_cents,
                    starts_at,
                    ends_at,
                ),
            ).fetchone()
        assert row is not None
        return auction_from_row(row)

    def get(self, auction_id: UUID) -> AuctionSnapshot | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                f"SELECT {AUCTION_COLUMNS} FROM auctions WHERE id = %s",
                (auction_id,),
            ).fetchone()
        return None if row is None else auction_from_row(row)

    def list_bids(self, auction_id: UUID) -> list[AcceptedBid]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {BID_COLUMNS}
                FROM bids
                WHERE auction_id = %s
                ORDER BY auction_version, accepted_at, id
                """,
                (auction_id,),
            ).fetchall()
        return [bid_from_row(row) for row in rows]
