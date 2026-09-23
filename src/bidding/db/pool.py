"""Bounded Psycopg connection-pool construction and session configuration."""

from __future__ import annotations

from collections.abc import Callable

from psycopg import Connection, IsolationLevel
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from bidding.config import Settings


def connection_configurer(settings: Settings) -> Callable[[Connection], None]:
    def configure(connection: Connection) -> None:
        connection.isolation_level = IsolationLevel.READ_COMMITTED
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('TimeZone', 'UTC', false)")
            cursor.execute(
                "SELECT set_config('lock_timeout', %s, false)",
                (f"{settings.lock_timeout_ms}ms",),
            )
            cursor.execute(
                "SELECT set_config('statement_timeout', %s, false)",
                (f"{settings.statement_timeout_ms}ms",),
            )
        # The pool requires configure callbacks to return idle connections.
        connection.commit()

    return configure


def create_pool(settings: Settings, *, name: str = "bidding-db") -> ConnectionPool:
    return ConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.pool_min_size,
        max_size=settings.pool_max_size,
        timeout=settings.pool_timeout_seconds,
        kwargs={"autocommit": False, "row_factory": dict_row},
        configure=connection_configurer(settings),
        name=name,
        open=False,
    )
