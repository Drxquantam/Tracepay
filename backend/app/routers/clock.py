"""Simulated clock: anyone logged in can read it; only admins can move it."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock, get_clock
from app.db import get_db, get_sessionmaker
from app.deps import get_current_user, require_admin
from app.jobs import run_due_jobs, start_payments
from app.schemas import ClockAdvance, ClockOut
from app.worker import spawn

router = APIRouter(tags=["clock"])


async def _clock_out(db: AsyncSession, clock: Clock) -> ClockOut:
    return ClockOut(now=await clock.now(db), offset_seconds=await clock.offset_seconds(db))


@router.get("/clock", response_model=ClockOut, dependencies=[Depends(get_current_user)])
async def read_clock(db: AsyncSession = Depends(get_db), clock: Clock = Depends(get_clock)):
    return await _clock_out(db, clock)


@router.post("/admin/clock/advance", response_model=ClockOut, dependencies=[Depends(require_admin)])
async def advance_clock(
    body: ClockAdvance,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    maker: async_sessionmaker[AsyncSession] = Depends(get_sessionmaker),
) -> ClockOut:
    try:
        await clock.advance(db, body.seconds)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    await db.commit()
    # Run every time-based job straight away at the new time, so a jump past a deadline
    # opens the dispute (or expires a held payment) immediately, with no manual action
    # and no wait for the background loop.
    result = await run_due_jobs(maker, clock)
    if result.payments_to_run:
        spawn(start_payments(maker, clock, result.payments_to_run))
    out = await _clock_out(db, clock)
    out.disputes_opened = result.disputes_opened
    return out


@router.post("/admin/clock/reset", response_model=ClockOut, dependencies=[Depends(require_admin)])
async def reset_clock(
    db: AsyncSession = Depends(get_db), clock: Clock = Depends(get_clock)
) -> ClockOut:
    await clock.reset(db)
    await db.commit()
    return await _clock_out(db, clock)
