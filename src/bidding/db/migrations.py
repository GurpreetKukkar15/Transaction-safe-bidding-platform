"""Small ordered SQL migration runner with checksum drift detection."""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import psycopg
from psycopg import Connection
from psycopg.rows import tuple_row

from bidding.config import Settings

MIGRATION_NAME = re.compile(r"^(?P<version>\d{3})_(?P<name>[a-z0-9_]+)\.sql$")
MIGRATION_LOCK_ID = 724_310_991


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str
    checksum: str


def migration_from_path(path: Path) -> Migration:
    match = MIGRATION_NAME.fullmatch(path.name)
    if match is None:
        raise ValueError(f"invalid migration filename: {path.name}")
    sql = path.read_text(encoding="utf-8")
    return Migration(
        version=int(match.group("version")),
        name=match.group("name"),
        sql=sql,
        checksum=hashlib.sha256(sql.encode()).hexdigest(),
    )


def discover_migrations() -> list[Migration]:
    sql_directory = resources.files("bidding.db").joinpath("sql")
    paths = sorted(
        Path(item) for item in sql_directory.iterdir() if item.name.endswith(".sql")
    )
    migrations = [migration_from_path(path) for path in paths]
    versions = [migration.version for migration in migrations]
    if len(versions) != len(set(versions)):
        raise ValueError("migration versions must be unique")
    return migrations


def migrate(connection: Connection) -> list[int]:
    applied_now: list[int] = []
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_ID,))
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version integer PRIMARY KEY,
                name text NOT NULL,
                checksum text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
            )
            """
        )
        with connection.cursor(row_factory=tuple_row) as cursor:
            existing_rows = cursor.execute(
                """
                SELECT version, name, checksum
                FROM schema_migrations
                ORDER BY version
                """
            ).fetchall()
        existing = {row[0]: (row[1], row[2]) for row in existing_rows}

        for migration in discover_migrations():
            previous = existing.get(migration.version)
            if previous is not None:
                if previous != (migration.name, migration.checksum):
                    raise RuntimeError(
                        f"applied migration {migration.version:03d} has changed"
                    )
                continue
            connection.execute(migration.sql)
            connection.execute(
                """
                INSERT INTO schema_migrations (version, name, checksum)
                VALUES (%s, %s, %s)
                """,
                (migration.version, migration.name, migration.checksum),
            )
            applied_now.append(migration.version)
    return applied_now


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply pending database migrations")
    parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL URL; defaults to DATABASE_URL or the local development URL",
    )
    arguments = parser.parse_args()
    settings = Settings.from_env()
    database_url = arguments.database_url or settings.database_url
    with psycopg.connect(database_url) as connection:
        versions = migrate(connection)
    if versions:
        print("Applied migrations:", ", ".join(f"{v:03d}" for v in versions))
    else:
        print("Database schema is already current")


if __name__ == "__main__":
    main()
