from pathlib import Path

import pytest

from bidding.db.migrations import discover_migrations, migration_from_path


def test_discover_migrations_returns_ordered_initial_schema() -> None:
    migrations = discover_migrations()

    assert [migration.version for migration in migrations] == [1]
    assert migrations[0].name == "initial_schema"
    assert "CREATE TABLE auctions" in migrations[0].sql


def test_migration_checksum_changes_with_content(tmp_path: Path) -> None:
    path = tmp_path / "001_example.sql"
    path.write_text("SELECT 1;", encoding="utf-8")
    first = migration_from_path(path)

    path.write_text("SELECT 2;", encoding="utf-8")
    second = migration_from_path(path)

    assert first.checksum != second.checksum


def test_invalid_migration_filename_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "migration.sql"
    path.write_text("SELECT 1;", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid migration filename"):
        migration_from_path(path)
