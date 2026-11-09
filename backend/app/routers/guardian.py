"""Guardian mode endpoints: rules, the approve/deny inbox, cancel, and the kill switch.

Guardian mode lowers risk but can't stop every coached scam: someone being coached can be
talked into asking for approval, or into switching the rules off. The UI says so too.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.clock import Clock, get_clock
from app.db import get_db, get_sessionmaker
from app.deps import get_current_user
from app.guardian import GuardianError, cancel, decide, set_frozen
from app.models import Account, GuardianSettings, Payment, PaymentHold, User, UserRole
from app.schemas import (
    FreezeRequest,
    GuardianOverview,
    GuardianRulesIn,
    GuardianRulesOut,
    HoldOut,
    HoldsOut,
    PersonOut,
    ProtectedPersonOut,
)
from app.state_machine import PaymentState
from app.switch import run_payment

router = APIRouter(prefix="/guardian", tags=["guardian"])


def _person(u: User) -> PersonOut:
    return PersonOut(username=u.username, full_name=u.full_name)


async def _frozen(db: AsyncSession, user_id: int) -> bool:
    return bool(await db.scalar(select(Account.is_frozen).where(Account.user_id == user_id)))


@router.get("", response_model=GuardianOverview)
async def overview(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> GuardianOverview:
    settings = await db.scalar(
        select(GuardianSettings)
        .where(GuardianSettings.user_id == user.id)
        .options(selectinload(GuardianSettings.guardian))
    )
    rules = GuardianRulesOut(
        guardian=_person(settings.guardian) if settings and settings.guardian else None,
        threshold_paise=settings.threshold_paise if settings else None,
        new_payee_approval=settings.new_payee_approval if settings else False,
        cooling_off_threshold_paise=settings.cooling_off_threshold_paise if settings else None,
        cooling_off_minutes=settings.cooling_off_minutes if settings else 30,
    )
    wards = (
        await db.scalars(
            select(User)
            .join(GuardianSettings, GuardianSettings.user_id == User.id)
            .where(GuardianSettings.guardian_user_id == user.id)
        )
    ).all()
    protecting = []
    for w in wards:
        pending = await db.scalar(
            select(func.count())
            .select_from(PaymentHold)
            .join(Payment, Payment.id == PaymentHold.payment_id)
            .where(Payment.created_by_user_id == w.id, PaymentHold.status == "pending")
        )
        protecting.append(
            ProtectedPersonOut(
                username=w.username,
                full_name=w.full_name,
                is_frozen=await _frozen(db, w.id),
                pending_requests=pending or 0,
            )
        )
    candidates = (
        await db.scalars(
            select(User)
            .where(User.id != user.id, User.role == UserRole.CUSTOMER)
            .order_by(User.full_name)
        )
    ).all()
    return GuardianOverview(
        rules=rules,
        is_frozen=await _frozen(db, user.id),
        protecting=protecting,
        candidates=[_person(c) for c in candidates],
    )


@router.put("/settings", response_model=GuardianRulesOut)
async def save_rules(
    body: GuardianRulesIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GuardianRulesOut:
    guardian = None
    if body.guardian_username:
        guardian = await db.scalar(select(User).where(User.username == body.guardian_username))
        if guardian is None or guardian.role != UserRole.CUSTOMER:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such person")
        if guardian.id == user.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't be your own trusted person")

    settings = await db.get(GuardianSettings, user.id)
    if settings is None:
        settings = GuardianSettings(user_id=user.id)
        db.add(settings)
    settings.guardian_user_id = guardian.id if guardian else None
    settings.threshold_paise = body.threshold_paise
    settings.new_payee_approval = body.new_payee_approval
    settings.cooling_off_threshold_paise = body.cooling_off_threshold_paise
    settings.cooling_off_minutes = body.cooling_off_minutes
    await db.commit()
    return GuardianRulesOut(
        guardian=_person(guardian) if guardian else None,
        threshold_paise=settings.threshold_paise,
        new_payee_approval=settings.new_payee_approval,
        cooling_off_threshold_paise=settings.cooling_off_threshold_paise,
        cooling_off_minutes=settings.cooling_off_minutes,
    )


def _hold_out(h: PaymentHold) -> HoldOut:
    p = h.payment
    return HoldOut(
        id=h.id,
        payment_id=p.id,
        kind=h.kind,  # type: ignore[arg-type]
        status=h.status,
        reasons=h.reasons,
        created_at=h.created_at,
        due_at=h.due_at,
        payer_name=p.payer_account.display_name,
        payee_name=p.payee_account.display_name,
        amount_paise=p.amount_paise,
        guardian_name=h.guardian.full_name if h.guardian else None,
    )


@router.get("/holds", response_model=HoldsOut)
async def list_holds(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> HoldsOut:
    holds = (
        await db.scalars(
            select(PaymentHold)
            .join(Payment, Payment.id == PaymentHold.payment_id)
            .where(
                PaymentHold.status == "pending",
                or_(PaymentHold.guardian_user_id == user.id, Payment.created_by_user_id == user.id),
            )
            .options(
                selectinload(PaymentHold.payment).selectinload(Payment.payer_account),
                selectinload(PaymentHold.payment).selectinload(Payment.payee_account),
                selectinload(PaymentHold.guardian),
            )
            .order_by(PaymentHold.due_at)
        )
    ).all()
    return HoldsOut(
        to_decide=[_hold_out(h) for h in holds if h.guardian_user_id == user.id],
        mine=[_hold_out(h) for h in holds if h.payment.created_by_user_id == user.id],
    )


async def _act(
    action: str,
    hold_id: int,
    user: User,
    db: AsyncSession,
    clock: Clock,
    maker: async_sessionmaker[AsyncSession],
    background: BackgroundTasks,
) -> dict:
    now = await clock.now(db)
    try:
        if action == "cancel":
            payment = await cancel(db, hold_id, user, now)
        else:
            payment = await decide(db, hold_id, user, action == "approve", now)
    except GuardianError as e:
        await db.rollback()
        raise HTTPException(e.status_code, e.message) from e
    await db.commit()
    if payment.state == PaymentState.BANK_DEBITED:
        background.add_task(run_payment, maker, clock, payment.id)
    return {"payment_id": str(payment.id), "state": payment.state}


@router.post("/holds/{hold_id}/approve")
async def approve(
    hold_id: int,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    maker: async_sessionmaker[AsyncSession] = Depends(get_sessionmaker),
) -> dict:
    return await _act("approve", hold_id, user, db, clock, maker, background)


@router.post("/holds/{hold_id}/deny")
async def deny(
    hold_id: int,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    maker: async_sessionmaker[AsyncSession] = Depends(get_sessionmaker),
) -> dict:
    return await _act("deny", hold_id, user, db, clock, maker, background)


@router.post("/holds/{hold_id}/cancel")
async def cancel_hold(
    hold_id: int,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    maker: async_sessionmaker[AsyncSession] = Depends(get_sessionmaker),
) -> dict:
    return await _act("cancel", hold_id, user, db, clock, maker, background)


async def _freeze(body: FreezeRequest, user: User, db: AsyncSession, clock: Clock, frozen: bool):  # type: ignore[no-untyped-def]
    target = user
    if body.username and body.username != user.username:
        found = await db.scalar(select(User).where(User.username == body.username))
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such person")
        target = found
    try:
        account = await set_frozen(db, target, user, frozen, await clock.now(db))
    except GuardianError as e:
        await db.rollback()
        raise HTTPException(e.status_code, e.message) from e
    await db.commit()
    return {"username": target.username, "is_frozen": account.is_frozen}


@router.post("/freeze")
async def freeze(
    body: FreezeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> dict:
    """One-tap kill switch: block every outgoing payment from the account."""
    return await _freeze(body, user, db, clock, True)


@router.post("/unfreeze")
async def unfreeze(
    body: FreezeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> dict:
    return await _freeze(body, user, db, clock, False)
