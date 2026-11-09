"""Everything that happens because *time passed*, in one function.

Called every few seconds by the background loop in main.py, and straight after every
time-travel jump. One entry point means both paths always behave the same way.
"""

import asyncio
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.disputes import open_overdue_disputes
from app.guardian import process_due_holds
from app.switch import run_payment


@dataclass
class JobResult:
    disputes_opened: int = 0
    holds_processed: int = 0
    payments_to_run: list[uuid.UUID] = field(default_factory=list)


async def run_due_jobs(maker: async_sessionmaker[AsyncSession], clock: Clock) -> JobResult:
    """Run each job in its own short transaction, then send any newly debited payments
    through the mock switch."""
    result = JobResult()
    async with maker() as db:
        released = await process_due_holds(db, await clock.now(db))
        await db.commit()
    result.payments_to_run += released
    result.holds_processed = len(released)

    async with maker() as db:
        opened = await open_overdue_disputes(db, await clock.now(db))
        await db.commit()
    result.disputes_opened = len(opened)
    return result


async def start_payments(
    maker: async_sessionmaker[AsyncSession], clock: Clock, payment_ids: list[uuid.UUID]
) -> None:
    """Run released payments through the switch concurrently (each one may wait on a slow
    bank, so one doesn't hold up the rest)."""
    await asyncio.gather(*(run_payment(maker, clock, pid) for pid in payment_ids))
