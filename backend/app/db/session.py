from collections.abc import AsyncIterator

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

SCHEMA_REVISION = "0005_local_providers"
DATABASE_UNAVAILABLE = (
    "Database unavailable or migrations missing. Check PostgreSQL and migrations."
)


def build_engine(url: str) -> AsyncEngine:
    return create_async_engine(
        url,
        pool_size=3,
        max_overflow=0,
        pool_timeout=2,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 2, "options": "-c statement_timeout=3000 -c timezone=UTC"},
    )


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] | None = request.app.state.db_sessions
    if factory is None:
        raise HTTPException(status_code=503, detail=DATABASE_UNAVAILABLE)
    # Every request owns a transaction; failed requests roll back on exit.
    async with factory() as session, session.begin():
        yield session
