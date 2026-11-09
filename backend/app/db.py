"""Database engine and session factory (SQLAlchemy 2.x, async)."""

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


# Connections per server process. With several worker processes, keep
# workers x (pool_size + max_overflow) under Postgres's max_connections (100 by default).
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
)

# expire_on_commit=False: objects stay readable after commit, so a route can
# return them without triggering a lazy reload (which async SQLAlchemy forbids).
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """FastAPI dependency for code that opens its *own* sessions, such as background
    payment processing that runs after the request's session has closed.
    Tests override this one function to point everything at the test database."""
    return SessionLocal


async def get_db(
    maker: async_sessionmaker[AsyncSession] = Depends(get_sessionmaker),
) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    async with maker() as session:
        yield session
