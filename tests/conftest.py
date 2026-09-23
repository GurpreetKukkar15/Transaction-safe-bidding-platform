from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from bidding.config import Settings
from bidding.db.migrations import migrate
from bidding.db.pool import create_pool


@pytest.fixture(scope="session")
def integration_database_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for integration tests")
    with psycopg.connect(database_url) as connection:
        migrate(connection)
    return database_url


@pytest.fixture(scope="session")
def db_pool(integration_database_url: str) -> Iterator[ConnectionPool]:
    settings = Settings(
        database_url=integration_database_url,
        pool_min_size=2,
        pool_max_size=12,
        pool_timeout_seconds=5,
        lock_timeout_ms=2_000,
        statement_timeout_ms=10_000,
    )
    pool = create_pool(settings, name="pytest-db")
    pool.open(wait=True, timeout=10)
    yield pool
    pool.close()


@pytest.fixture
def clean_database(db_pool: ConnectionPool) -> Iterator[None]:
    with db_pool.connection() as connection:
        connection.execute("TRUNCATE TABLE bids, auctions CASCADE")
    yield
    with db_pool.connection() as connection:
        connection.execute("TRUNCATE TABLE bids, auctions CASCADE")


@pytest.fixture
def direct_connection(integration_database_url: str):
    # Low-level schema tests opt into transactions explicitly. Autocommit keeps
    # read-only assertions from holding table locks until fixture teardown.
    with psycopg.connect(
        integration_database_url,
        autocommit=True,
        row_factory=dict_row,
    ) as connection:
        yield connection
