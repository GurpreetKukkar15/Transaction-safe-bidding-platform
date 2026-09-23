"""FastAPI application factory and resource lifecycle."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from psycopg_pool import ConnectionPool

from bidding.api.routes import router
from bidding.api.websockets import AuctionConnectionManager
from bidding.application.service import BiddingService
from bidding.config import Settings
from bidding.db.migrations import migrate
from bidding.db.pool import create_pool
from bidding.db.repositories import AuctionRepository
from bidding.db.strategies import strategy_from_name


def create_app(
    *,
    settings: Settings | None = None,
    pool: ConnectionPool | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        owns_pool = pool is None
        database_pool = pool or create_pool(resolved_settings)
        if owns_pool:
            await run_in_threadpool(database_pool.open, wait=True, timeout=30)
        try:

            def apply_migrations() -> None:
                with database_pool.connection() as connection:
                    migrate(connection)

            await run_in_threadpool(apply_migrations)
            repository = AuctionRepository(database_pool)
            strategy = strategy_from_name(
                resolved_settings.bid_strategy,
                database_pool,
                optimistic_max_attempts=resolved_settings.optimistic_max_attempts,
            )
            application.state.settings = resolved_settings
            application.state.db_pool = database_pool
            application.state.bidding_service = BiddingService(repository, strategy)
            application.state.connection_manager = AuctionConnectionManager()
            yield
        finally:
            if owns_pool:
                await run_in_threadpool(database_pool.close)

    application = FastAPI(
        title="Transaction-Safe Bidding Platform",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(router)
    return application


app = create_app()
