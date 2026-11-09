"""Simulated clock.

Every piece of deadline logic asks this clock for the time, never `datetime.now()` directly.
That makes time *injectable*:
- the demo can jump forward days ("time travel") to show a deadline being breached;
- tests can freeze time to get exact, repeatable timestamps.

Simulated time = real time + an offset stored in the `sim_clock` table. Keeping the offset
in the database (not in a Python variable) means every API worker sees the same time and
a jump survives restarts.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SimClock


def _real_now() -> datetime:
    return datetime.now(UTC)


class Clock:
    def __init__(self, real_now: Callable[[], datetime] = _real_now) -> None:
        # Tests pass a function returning a fixed datetime to freeze time.
        self._real_now = real_now

    async def offset_seconds(self, db: AsyncSession) -> int:
        offset = await db.scalar(select(SimClock.offset_seconds).where(SimClock.id == 1))
        return offset or 0

    async def now(self, db: AsyncSession) -> datetime:
        return self._real_now() + timedelta(seconds=await self.offset_seconds(db))

    async def advance(self, db: AsyncSession, seconds: int) -> None:
        """Move simulated time forward. Only forward: going back in time would let
        events happen "before" ones already recorded, which breaks the event log."""
        if seconds <= 0:
            raise ValueError("Can only move the clock forward")
        # Upsert, so this also works on a database where the row was never seeded.
        stmt = insert(SimClock).values(id=1, offset_seconds=seconds)
        stmt = stmt.on_conflict_do_update(
            index_elements=[SimClock.id],
            set_={"offset_seconds": SimClock.offset_seconds + seconds},
        )
        await db.execute(stmt)

    async def reset(self, db: AsyncSession) -> None:
        stmt = insert(SimClock).values(id=1, offset_seconds=0)
        stmt = stmt.on_conflict_do_update(index_elements=[SimClock.id], set_={"offset_seconds": 0})
        await db.execute(stmt)


_clock = Clock()


def get_clock() -> Clock:
    """FastAPI dependency. Tests override it with a frozen clock."""
    return _clock
