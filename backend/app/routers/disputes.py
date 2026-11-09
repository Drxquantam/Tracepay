"""Disputes the payer can see, their escalation checklist, and the claim summary."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.clock import Clock, get_clock
from app.db import get_db
from app.deps import get_current_user
from app.disputes import DisputeError, claim_text, complete_step, dispute_view, load_dispute
from app.models import Account, Dispute, Payment, PaymentEvent, User, UserRole
from app.schemas import DisputeOut

router = APIRouter(prefix="/disputes", tags=["disputes"])


async def _visible(db: AsyncSession, dispute_id: int, user: User) -> Dispute:
    dispute = await load_dispute(db, dispute_id)
    # Only the payer (whose bank owes them) and admins see a dispute.
    if dispute is None or not (
        dispute.payment.payer_account.user_id == user.id or user.role == UserRole.ADMIN
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute not found")
    return dispute


@router.get("", response_model=list[DisputeOut])
async def list_my_disputes(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> list[dict]:
    query = (
        select(Dispute)
        .join(Payment, Payment.id == Dispute.payment_id)
        .join(Account, Account.id == Payment.payer_account_id)
        .options(
            selectinload(Dispute.steps),
            selectinload(Dispute.owed_by_bank),
            selectinload(Dispute.payment).selectinload(Payment.payee_account),
        )
        .order_by(Dispute.opened_at.desc())
    )
    if user.role != UserRole.ADMIN:
        query = query.where(Account.user_id == user.id)
    now = await clock.now(db)
    return [dispute_view(d, now) for d in await db.scalars(query)]


@router.get("/{dispute_id}", response_model=DisputeOut)
async def get_dispute(
    dispute_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> dict:
    return dispute_view(await _visible(db, dispute_id, user), await clock.now(db))


@router.get("/{dispute_id}/claim", response_class=PlainTextResponse)
async def get_claim_summary(
    dispute_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> str:
    """Copyable claim text with all the transaction references."""
    dispute = await _visible(db, dispute_id, user)
    events = (
        await db.scalars(
            select(PaymentEvent)
            .where(PaymentEvent.payment_id == dispute.payment_id)
            .order_by(PaymentEvent.id)
        )
    ).all()
    return claim_text(dispute, list(events), await clock.now(db))


@router.post("/{dispute_id}/steps/{step}/complete", response_model=DisputeOut)
async def complete_dispute_step(
    dispute_id: int,
    step: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> dict:
    dispute = await _visible(db, dispute_id, user)
    now = await clock.now(db)
    try:
        await complete_step(db, dispute, step, now)
    except DisputeError as e:
        raise HTTPException(e.status_code, e.message) from e
    await db.commit()
    return dispute_view(dispute, now)
