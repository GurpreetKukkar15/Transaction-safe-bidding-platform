"""Environment-backed application configuration with strict validation."""

from __future__ import annotations

import os
from dataclasses import dataclass

VALID_STRATEGIES = frozenset({"unsafe", "pessimistic", "optimistic"})


def _positive_int(environment: dict[str, str], name: str, default: int) -> int:
    raw = environment.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _positive_float(environment: dict[str, str], name: str, default: float) -> float:
    raw = environment.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    bid_strategy: str = "pessimistic"
    pool_min_size: int = 2
    pool_max_size: int = 20
    pool_timeout_seconds: float = 5.0
    lock_timeout_ms: int = 2_000
    statement_timeout_ms: int = 5_000
    optimistic_max_attempts: int = 5

    def __post_init__(self) -> None:
        if not self.database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("database_url must use the PostgreSQL protocol")
        if self.bid_strategy not in VALID_STRATEGIES:
            choices = ", ".join(sorted(VALID_STRATEGIES))
            raise ValueError(f"bid_strategy must be one of: {choices}")
        for field_name in (
            "pool_min_size",
            "pool_max_size",
            "lock_timeout_ms",
            "statement_timeout_ms",
            "optimistic_max_attempts",
        ):
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name} must be positive")
        if self.pool_timeout_seconds <= 0:
            raise ValueError("pool_timeout_seconds must be positive")
        if self.pool_min_size > self.pool_max_size:
            raise ValueError("pool_min_size cannot exceed pool_max_size")

    @classmethod
    def from_env(cls, environment: dict[str, str] | None = None) -> Settings:
        env = dict(os.environ if environment is None else environment)
        database_url = env.get(
            "DATABASE_URL",
            "postgresql://bidding:bidding@localhost:54329/bidding",
        )
        return cls(
            database_url=database_url,
            bid_strategy=env.get("BID_STRATEGY", "pessimistic").lower(),
            pool_min_size=_positive_int(env, "DB_POOL_MIN_SIZE", 2),
            pool_max_size=_positive_int(env, "DB_POOL_MAX_SIZE", 20),
            pool_timeout_seconds=_positive_float(env, "DB_POOL_TIMEOUT_SECONDS", 5.0),
            lock_timeout_ms=_positive_int(env, "DB_LOCK_TIMEOUT_MS", 2_000),
            statement_timeout_ms=_positive_int(env, "DB_STATEMENT_TIMEOUT_MS", 5_000),
            optimistic_max_attempts=_positive_int(env, "OPTIMISTIC_MAX_ATTEMPTS", 5),
        )
