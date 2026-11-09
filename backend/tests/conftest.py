"""Test fixtures. Tests run against a real Postgres database (tracepay_test), not SQLite,
because row locking, CHECK constraints and JSONB are Postgres behaviour we rely on."""

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

# Cheap password hashing for tests; must be set before app.config is imported.
os.environ.setdefault("BCRYPT_ROUNDS", "4")
os.environ.setdefault("RUN_BACKGROUND_JOBS", "false")

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.clock import Clock, get_clock
from app.config import settings
from app.db import Base, get_sessionmaker
from app.main import app
from app.models import Account
from app.seed import seed_demo_data

# A fixed "real" time for tests that need exact timestamps.
FROZEN_NOW = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    # A large pool so the concurrency tests really run transactions in parallel.
    eng = create_async_engine(settings.test_database_url, pool_size=30, max_overflow=30)
    # Fresh schema once per test run.
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # Every test starts from empty tables, so tests can't affect each other.
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def db(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
async def seeded(db: AsyncSession) -> None:
    await seed_demo_data(db)


@pytest.fixture
def clock() -> Clock:
    """Real time plus the DB offset: the same clock the app uses."""
    return Clock()


@pytest.fixture
def frozen_clock() -> Clock:
    """A clock whose real-time part never moves, for exact timestamp assertions."""
    return Clock(real_now=lambda: FROZEN_NOW)


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession], clock: Clock
) -> AsyncIterator[AsyncClient]:
    """HTTP client that calls the app in-process, with the DB pointed at the test database.

    httpx's ASGI transport waits for the whole app call, including background tasks, so
    when a request returns, the payment's background processing has finished too.
    """
    app.dependency_overrides[get_sessionmaker] = lambda: session_factory
    app.dependency_overrides[get_clock] = lambda: clock
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def login(client: AsyncClient, username: str, password: str = "demo1234") -> str:
    resp = await client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def auth(client: AsyncClient, username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {await login(client, username)}"}


def new_key() -> str:
    return str(uuid.uuid4())


async def balance(db: AsyncSession, vpa: str) -> int:
    """Read a balance fresh from the database (not from this session's cache)."""
    value = await db.scalar(
        select(Account.balance_paise)
        .where(Account.vpa == vpa)
        .execution_options(populate_existing=True)
    )
    assert value is not None
    return value
