"""Translate database rows into immutable domain values."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bidding.domain.models import AcceptedBid, AuctionSnapshot


def auction_from_row(row: Mapping[str, Any]) -> AuctionSnapshot:
    return AuctionSnapshot(
        id=row["id"],
        title=row["title"],
        starting_price_cents=row["starting_price_cents"],
        current_price_cents=row["current_price_cents"],
        minimum_increment_cents=row["minimum_increment_cents"],
        winning_bid_id=row["winning_bid_id"],
        version=row["version"],
        starts_at=row["starts_at"],
        ends_at=row["ends_at"],
        created_at=row["created_at"],
    )


def bid_from_row(row: Mapping[str, Any]) -> AcceptedBid:
    return AcceptedBid(
        id=row["id"],
        request_id=row["request_id"],
        auction_id=row["auction_id"],
        bidder_id=row["bidder_id"],
        amount_cents=row["amount_cents"],
        auction_version=row["auction_version"],
        accepted_at=row["accepted_at"],
    )
