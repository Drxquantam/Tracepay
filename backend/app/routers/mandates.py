"""Mandate Manager: every recurring debit in one place, with one-tap pause/resume/revoke."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.clock import Clock, get_clock
from app.db import get_db
from app.deps import get_current_user
from app.mandates import NOTICE, next_period, payer_account_for, upcoming
from app.models import Account, AccountKind, Mandate, User
from app.rules import E_MANDATE_MAX_WITHOUT_AFA_PAISE
from app.schemas import MandateCreate, MandateDebitOut, MandateOut

router = APIRouter(prefix="/mandates", tags=["mandates"])


def mandate_out(m: Mandate) -> MandateOut:
    return MandateOut(
        id=m.id,
        merchant_name=m.merchant_account.display_name,
        merchant_vpa=m.merchant_account.vpa,
        purpose=m.purpose,
        amount_paise=m.amount_paise,
        max_amount_paise=m.max_amount_paise,
        frequency=m.frequency,  # type: ignore[arg-type]
        trial_amount_paise=m.trial_amount_paise,
        trial_debits_left=m.trial_debits_left,
        status=m.status,  # type: ignore[arg-type]
        next_debit_at=m.next_debit_at if m.status == "active" else None,
        created_at=m.created_at,
        upcoming=upcoming(m),
        debits=[MandateDebitOut.model_validate(d) for d in m.debits[:6]],
    )


async def _load(db: AsyncSession, mandate_id: int, user: User, lock: bool = False) -> Mandate:
    query = (
        select(Mandate)
        .where(Mandate.id == mandate_id)
        .options(
            selectinload(Mandate.merchant_account),
            selectinload(Mandate.payer_account),
            selectinload(Mandate.debits),
        )
        .execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update(key_share=True, of=Mandate)
    m = await db.scalar(query)
    if m is None or m.payer_account.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mandate not found")
    return m


@router.get("", response_model=list[MandateOut])
async def list_mandates(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[MandateOut]:
    mandates = await db.scalars(
        select(Mandate)
        .join(Account, Account.id == Mandate.payer_account_id)
        .where(Account.user_id == user.id)
        .options(selectinload(Mandate.merchant_account), selectinload(Mandate.debits))
        .order_by(Mandate.status, Mandate.next_debit_at)
    )
    return [mandate_out(m) for m in mandates]


@router.post("", response_model=MandateOut, status_code=status.HTTP_201_CREATED)
async def create_mandate(
    body: MandateCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> MandateOut:
    """Approve a merchant's recurring-debit request (in real UPI the merchant asks and the
    user approves in their app; this simulation lets the user set it up directly)."""
    now = await clock.now(db)
    payer = await payer_account_for(db, user.id)
    merchant = await db.scalar(select(Account).where(Account.vpa == body.merchant_vpa.lower()))
    if payer is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You don't have an account")
    if merchant is None or merchant.kind != AccountKind.MERCHANT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No merchant with that UPI ID")
    if body.max_amount_paise > E_MANDATE_MAX_WITHOUT_AFA_PAISE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Caps above ₹15,000 need extra authentication on every debit, which this "
            "simulation doesn't support",
        )
    if body.amount_paise > body.max_amount_paise or (
        body.trial_amount_paise and body.trial_amount_paise > body.max_amount_paise
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Amount is above the cap")
    if body.first_debit_at < now + NOTICE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "The first debit must be at least 24 hours away, so the pre-debit notice can go out",
        )
    m = Mandate(
        payer_account_id=payer.id,
        merchant_account_id=merchant.id,
        purpose=body.purpose,
        amount_paise=body.amount_paise,
        max_amount_paise=body.max_amount_paise,
        frequency=body.frequency,
        trial_amount_paise=body.trial_amount_paise,
        trial_debits_left=body.trial_debits if body.trial_amount_paise else 0,
        next_debit_at=body.first_debit_at,
        status="active",
        created_at=now,
    )
    db.add(m)
    await db.commit()
    return mandate_out(await _load(db, m.id, user))


@router.post("/{mandate_id}/pause", response_model=MandateOut)
async def pause(
    mandate_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MandateOut:
    m = await _load(db, mandate_id, user, lock=True)
    if m.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mandate is {m.status}")
    m.status = "paused"
    await db.commit()
    return mandate_out(await _load(db, mandate_id, user))


@router.post("/{mandate_id}/resume", response_model=MandateOut)
async def resume(
    mandate_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> MandateOut:
    m = await _load(db, mandate_id, user, lock=True)
    if m.status != "paused":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mandate is {m.status}")
    # Skip any cycles that passed while paused: no surprise catch-up debits, and the next
    # one is far enough away for a proper 24-hour notice.
    now = await clock.now(db)
    while m.next_debit_at < now + NOTICE:
        m.next_debit_at = next_period(m.next_debit_at, m.frequency)
    m.status = "active"
    await db.commit()
    return mandate_out(await _load(db, mandate_id, user))


@router.post("/{mandate_id}/revoke", response_model=MandateOut)
async def revoke(
    mandate_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> MandateOut:
    """One tap, permanent: no more debits, and any notified/retrying cycle is cancelled."""
    m = await _load(db, mandate_id, user, lock=True)
    if m.status == "revoked":
        raise HTTPException(status.HTTP_409_CONFLICT, "Mandate is already revoked")
    m.status, m.revoked_at = "revoked", await clock.now(db)
    for d in m.debits:
        if d.status in ("notified", "retrying"):
            d.status, d.next_attempt_at = "cancelled", None
    await db.commit()
    return mandate_out(await _load(db, mandate_id, user))
