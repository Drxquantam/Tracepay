"""Admin chaos controls: make the mock banks misbehave, settle stuck payments, run the
deadline sweep. SIMULATION ONLY."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock, get_clock
from app.db import get_db, get_sessionmaker
from app.deps import require_admin
from app.jobs import run_due_jobs, start_payments
from app.models import Bank
from app.schemas import BankChaosOut, BankChaosUpdate, ResolveRequest
from app.switch import ResolveError, refund, resolve_stuck

router = APIRouter(prefix="/admin", tags=["admin: chaos"], dependencies=[Depends(require_admin)])


@router.get("/chaos/banks", response_model=list[BankChaosOut])
async def list_banks(db: AsyncSession = Depends(get_db)) -> list[Bank]:
    return list(await db.scalars(select(Bank).order_by(Bank.id)))


@router.put("/chaos/banks/{code}", response_model=BankChaosOut)
async def update_bank(code: str, body: BankChaosUpdate, db: AsyncSession = Depends(get_db)) -> Bank:
    bank = await db.scalar(select(Bank).where(Bank.code == code.upper()))
    if bank is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No bank {code!r}")
    # Only change what was sent; "fault": null is an explicit "clear the fault".
    sent = body.model_fields_set
    if "is_down" in sent and body.is_down is not None:
        bank.is_down = body.is_down
    if "fault" in sent:
        bank.fault = body.fault
    if "response_delay_seconds" in sent and body.response_delay_seconds is not None:
        bank.response_delay_seconds = body.response_delay_seconds
    await db.commit()
    return bank


@router.post("/chaos/reset", response_model=list[BankChaosOut])
async def reset_chaos(db: AsyncSession = Depends(get_db)) -> list[Bank]:
    """Bring every bank back up and clear all faults (normal latencies are kept)."""
    await db.execute(update(Bank).values(is_down=False, fault=None))
    await db.commit()
    return list(await db.scalars(select(Bank).order_by(Bank.id)))


@router.post("/payments/{payment_id}/resolve")
async def resolve_payment(
    payment_id: uuid.UUID,
    body: ResolveRequest,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> dict:
    """The bank finally acts on a stuck payment: credit the payee, or refund the payer."""
    try:
        payment = await resolve_stuck(db, payment_id, body.outcome, await clock.now(db))
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found") from e
    except ResolveError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    await db.commit()
    return {"id": str(payment.id), "state": payment.state}


@router.post("/payments/{payment_id}/retry-refund")
async def retry_refund(
    payment_id: uuid.UUID,
    maker: async_sessionmaker[AsyncSession] = Depends(get_sessionmaker),
    clock: Clock = Depends(get_clock),
) -> dict:
    """Ask the payer's bank to try a waiting refund again (e.g. after it comes back up)."""
    await refund(maker, clock, payment_id)
    return {"id": str(payment_id), "status": "refund attempted"}


@router.post("/deadlines/sweep")
async def sweep_deadlines(
    background: BackgroundTasks,
    maker: async_sessionmaker[AsyncSession] = Depends(get_sessionmaker),
    clock: Clock = Depends(get_clock),
) -> dict:
    """Run the time-based jobs now, instead of waiting for the background loop."""
    result = await run_due_jobs(maker, clock)
    if result.payments_to_run:
        background.add_task(start_payments, maker, clock, result.payments_to_run)
    return {"disputes_opened": result.disputes_opened, "holds_processed": result.holds_processed}
