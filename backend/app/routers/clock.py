"""Simulated clock: anyone logged in can read it; only admins can move it."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock, get_clock
from app.db import get_db
from app.deps import get_current_user, require_admin
from app.disputes import open_overdue_disputes
from app.schemas import ClockAdvance, ClockOut

router = APIRouter(tags=["clock"])


async def _clock_out(db: AsyncSession, clock: Clock) -> ClockOut:
    return ClockOut(now=await clock.now(db), offset_seconds=await clock.offset_seconds(db))


@router.get("/clock", response_model=ClockOut, dependencies=[Depends(get_current_user)])
async def read_clock(db: AsyncSession = Depends(get_db), clock: Clock = Depends(get_clock)):
    return await _clock_out(db, clock)


@router.post("/admin/clock/advance", response_model=ClockOut, dependencies=[Depends(require_admin)])
async def advance_clock(
    body: ClockAdvance, db: AsyncSession = Depends(get_db), clock: Clock = Depends(get_clock)
) -> ClockOut:
    try:
        await clock.advance(db, body.seconds)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    await db.commit()
    # Check deadlines straight away at the new time, so a jump past a deadline opens the
    # dispute immediately, with no manual action and no wait for the background loop.
    opened = await open_overdue_disputes(db, await clock.now(db))
    await db.commit()
    out = await _clock_out(db, clock)
    out.disputes_opened = len(opened)
    return out


@router.post("/admin/clock/reset", response_model=ClockOut, dependencies=[Depends(require_admin)])
async def reset_clock(
    db: AsyncSession = Depends(get_db), clock: Clock = Depends(get_clock)
) -> ClockOut:
    await clock.reset(db)
    await db.commit()
    return await _clock_out(db, clock)
