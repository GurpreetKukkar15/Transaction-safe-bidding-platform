import pytest

from bidding.config import Settings


def test_settings_parse_environment() -> None:
    settings = Settings.from_env(
        {
            "DATABASE_URL": "postgresql://example/test",
            "BID_STRATEGY": "OPTIMISTIC",
            "DB_POOL_MIN_SIZE": "1",
            "DB_POOL_MAX_SIZE": "12",
            "DB_POOL_TIMEOUT_SECONDS": "2.5",
            "DB_LOCK_TIMEOUT_MS": "750",
            "DB_STATEMENT_TIMEOUT_MS": "3000",
            "OPTIMISTIC_MAX_ATTEMPTS": "7",
        }
    )

    assert settings.bid_strategy == "optimistic"
    assert settings.pool_max_size == 12
    assert settings.pool_timeout_seconds == 2.5
    assert settings.optimistic_max_attempts == 7


def test_settings_reject_unknown_strategy() -> None:
    with pytest.raises(ValueError, match="bid_strategy"):
        Settings("postgresql://example/test", bid_strategy="magical")


def test_settings_reject_inverted_pool_limits() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        Settings(
            "postgresql://example/test",
            pool_min_size=10,
            pool_max_size=2,
        )


def test_environment_integer_has_clear_error() -> None:
    with pytest.raises(ValueError, match="DB_POOL_MAX_SIZE must be an integer"):
        Settings.from_env(
            {
                "DATABASE_URL": "postgresql://example/test",
                "DB_POOL_MAX_SIZE": "many",
            }
        )
