"""The scripted demo story, run with one click (admin panel) or one command (make demo).

1. Aarav (student) pays Ravi's shop ₹450; Suraksha Bank (Ravi's bank) is slow to answer.
2. While the payment is in flight, the demo kills Suraksha Bank.
3. When the switch tries to credit Ravi, the bank is down: the tracker shows the true
   state ("stuck between banks"); the money is safe in suspense.
4. The simulated clock jumps 8 days, past the T+5 merchant deadline.
5. With no manual action, the system opens a dispute and works out the compensation
   (3 days late: ₹300, owed by Aarav's bank, not by Ravi).

SIMULATION ONLY. The timings below are real seconds, so viewers can watch each step.
"""

import asyncio
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.faults import Fault
from app.jobs import run_due_jobs
from app.models import Account, Bank, User
from app.payments import accept_payment
from app.switch import run_payment

# Real-second pauses between story beats (tests shrink these).
KILL_BANK_AFTER_SECONDS = 3.0
PAUSE_BEFORE_TIME_JUMP_SECONDS = 4.0
TIME_JUMP_DAYS = 8

DEMO_PAYER, DEMO_PAYEE, DEMO_AMOUNT_PAISE = "aarav", "ravistore@suraksha", 450_00


async def start_demo(maker: async_sessionmaker[AsyncSession], clock: Clock) -> uuid.UUID:
    """Set the stage and create the payment. Returns its id so the UI can watch it."""
    async with maker() as db:
        # A clean stage: every bank healthy, Aarav's account not frozen.
        await db.execute(update(Bank).values(is_down=False, fault=None))
        user = await db.scalar(select(User).where(User.username == DEMO_PAYER))
        assert user is not None, "Demo data missing: run the seed first"
        await db.execute(update(Account).where(Account.user_id == user.id).values(is_frozen=False))
        await db.commit()

        payment = await accept_payment(
            db,
            payer_user_id=user.id,
            payee_vpa=DEMO_PAYEE,
            amount_paise=DEMO_AMOUNT_PAISE,
            note="Groceries (demo story)",
            at=await clock.now(db),
            fault=Fault.SLOW_RESPONSE,
        )
        await db.commit()
        return payment.id


async def play_story(
    maker: async_sessionmaker[AsyncSession], clock: Clock, payment_id: uuid.UUID
) -> None:
    """Steps 2 to 5. Runs in the background after start_demo returns."""
    in_flight = asyncio.create_task(run_payment(maker, clock, payment_id))

    await asyncio.sleep(KILL_BANK_AFTER_SECONDS)
    async with maker() as db:  # 2. kill the payee's bank mid-flight
        await db.execute(update(Bank).where(Bank.code == "SURAKSHA").values(is_down=True))
        await db.commit()

    await in_flight  # 3. the switch finds the bank down: the payment is stuck
    await asyncio.sleep(PAUSE_BEFORE_TIME_JUMP_SECONDS)

    async with maker() as db:  # 4. time travel past the deadline
        await clock.advance(db, TIME_JUMP_DAYS * 24 * 3600)
        await db.commit()
    await run_due_jobs(maker, clock)  # 5. dispute opens, compensation computed
