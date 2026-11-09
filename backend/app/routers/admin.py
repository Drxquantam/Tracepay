"""Admin-only tools: ledger integrity, payments needing attention, and the demo story.
Chaos controls and time travel live in chaos.py and clock.py."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.clock import Clock, get_clock
from app.db import get_db, get_sessionmaker
from app.demo import play_story, start_demo
from app.deps import require_admin
from app.ledger import integrity_report
from app.models import Payment
from app.routers.payments import payment_out
from app.schemas import PaymentOut
from app.state_machine import MONEY_IN_FLIGHT, PaymentState
from app.worker import spawn

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/ledger/integrity")
async def ledger_integrity(db: AsyncSession = Depends(get_db)) -> dict:
    """Proves debits and credits cancel out to zero and the cached balances are honest."""
    return await integrity_report(db)


@router.get("/payments", response_model=list[PaymentOut])
async def payments_needing_attention(db: AsyncSession = Depends(get_db)) -> list[PaymentOut]:
    """Payments that aren't settled yet: held, or with money in flight."""
    states = [*MONEY_IN_FLIGHT, PaymentState.HELD]
    payments = await db.scalars(
        select(Payment)
        .where(Payment.state.in_(states))
        .options(selectinload(Payment.payer_account), selectinload(Payment.payee_account))
        .order_by(Payment.created_at.desc())
        .limit(50)
    )
    return [payment_out(p) for p in payments]


@router.post("/demo")
async def run_demo(
    maker: async_sessionmaker[AsyncSession] = Depends(get_sessionmaker),
    clock: Clock = Depends(get_clock),
) -> dict:
    """Start the scripted Money in Flight story. Returns the payment to watch; the rest of
    the story (bank dies, time jumps, dispute opens) plays out over the next ~15 seconds."""
    payment_id = await start_demo(maker, clock)
    spawn(play_story(maker, clock, payment_id))
    return {"payment_id": str(payment_id)}
