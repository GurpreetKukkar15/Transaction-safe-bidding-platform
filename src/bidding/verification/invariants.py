"""Read committed state and report violations independently of write strategy."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from psycopg_pool import ConnectionPool

from bidding.db.repositories import AuctionRepository


@dataclass(frozen=True, slots=True)
class InvariantViolation:
    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class InvariantReport:
    auction_id: UUID
    bid_count: int
    violations: tuple[InvariantViolation, ...]

    @property
    def valid(self) -> bool:
        return not self.violations


def check_auction_invariants(pool: ConnectionPool, auction_id: UUID) -> InvariantReport:
    repository = AuctionRepository(pool)
    auction = repository.get(auction_id)
    if auction is None:
        return InvariantReport(
            auction_id,
            0,
            (InvariantViolation("auction_missing", "auction does not exist"),),
        )
    bids = repository.list_bids(auction_id)
    violations: list[InvariantViolation] = []

    if not bids:
        if (
            auction.current_price_cents is not None
            or auction.winning_bid_id is not None
            or auction.version != 0
        ):
            violations.append(
                InvariantViolation(
                    "empty_state_mismatch",
                    "auction without bids must have null price/winner and version zero",
                )
            )
        return InvariantReport(auction_id, 0, tuple(violations))

    expected_versions = list(range(1, len(bids) + 1))
    actual_versions = [bid.auction_version for bid in bids]
    if actual_versions != expected_versions:
        violations.append(
            InvariantViolation(
                "version_sequence",
                f"expected bid versions {expected_versions}, got {actual_versions}",
            )
        )
    if auction.version != len(bids):
        violations.append(
            InvariantViolation(
                "auction_version",
                f"auction version {auction.version} does not equal "
                f"bid count {len(bids)}",
            )
        )

    previous_price: int | None = None
    for bid in bids:
        required = (
            auction.starting_price_cents
            if previous_price is None
            else previous_price + auction.minimum_increment_cents
        )
        if bid.amount_cents < required:
            violations.append(
                InvariantViolation(
                    "non_monotonic_bid",
                    f"bid {bid.id} amount {bid.amount_cents} was below {required}",
                )
            )
        previous_price = bid.amount_cents
        if not auction.starts_at <= bid.accepted_at < auction.ends_at:
            violations.append(
                InvariantViolation(
                    "accepted_outside_window",
                    f"bid {bid.id} was accepted at {bid.accepted_at.isoformat()}",
                )
            )

    highest = max(bids, key=lambda bid: bid.amount_cents)
    winner = next(
        (bid for bid in bids if bid.id == auction.winning_bid_id),
        None,
    )
    if winner is None:
        violations.append(
            InvariantViolation(
                "winner_missing",
                "winning_bid_id does not identify an accepted bid in this auction",
            )
        )
    else:
        if auction.current_price_cents != winner.amount_cents:
            violations.append(
                InvariantViolation(
                    "winner_price_mismatch",
                    "auction price does not equal the winning bid amount",
                )
            )
        if winner.id != highest.id:
            violations.append(
                InvariantViolation(
                    "winner_not_highest",
                    f"winner {winner.amount_cents} is below "
                    f"highest bid {highest.amount_cents}",
                )
            )
    return InvariantReport(auction_id, len(bids), tuple(violations))
