"""Payment endpoints. POST /payments requires an Idempotency-Key header."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Response, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.clock import Clock, get_clock
from app.db import get_db, get_sessionmaker
from app.deps import get_current_user
from app.idempotency import claim_key, hash_request, save_response
from app.models import Account, Dispute, Payment, User, UserRole
from app.payments import PaymentError, accept_payment
from app.schemas import (
    PaymentCreate,
    PaymentDetailOut,
    PaymentEventOut,
    PaymentOut,
    TrackerOut,
)
from app.state_machine import PaymentState
from app.switch import run_payment
from app.tracker import tracker_view

router = APIRouter(prefix="/payments", tags=["payments"])


def payment_out(p: Payment) -> PaymentOut:
    return PaymentOut(
        id=p.id,
        reference=p.reference,
        payer_vpa=p.payer_account.vpa,
        payer_name=p.payer_account.display_name,
        payee_vpa=p.payee_account.vpa,
        payee_name=p.payee_account.display_name,
        amount_paise=p.amount_paise,
        state=p.state,
        failure_reason=p.failure_reason,
        note=p.note,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.post("", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def create_payment(
    body: PaymentCreate,
    response: Response,
    background: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, max_length=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    maker: async_sessionmaker[AsyncSession] = Depends(get_sessionmaker),
) -> PaymentOut | dict:
    if not idempotency_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Idempotency-Key header is required")

    request_hash = hash_request(body)
    existing = await claim_key(db, user.id, idempotency_key, request_hash)
    if existing is not None:
        # Copy what we need before rollback(), which expires every loaded object.
        saved_hash, saved_status, saved_body = (
            existing.request_hash,
            existing.status_code,
            existing.response_body,
        )
        await db.rollback()
        if saved_hash != request_hash:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This Idempotency-Key was already used for a different payment",
            )
        # A retry of a request we already handled: send back exactly what we sent then.
        # No money moves.
        response.status_code = saved_status or status.HTTP_201_CREATED
        response.headers["Idempotent-Replayed"] = "true"
        return saved_body or {}

    try:
        payment = await accept_payment(
            db,
            payer_user_id=user.id,
            payee_vpa=body.payee_vpa,
            amount_paise=body.amount_paise,
            note=body.note,
            at=await clock.now(db),
            fault=body.simulate_fault,
        )
    except PaymentError as e:
        # Rolling back also releases the idempotency key, so the client can fix the
        # request and retry with the same key.
        await db.rollback()
        raise HTTPException(e.status_code, e.message) from e

    out = payment_out(payment)
    await save_response(
        db, user.id, idempotency_key, status.HTTP_201_CREATED, out.model_dump(mode="json")
    )
    await db.commit()

    # The rest of the journey (switch, credit) happens after we've answered the client,
    # the way a real PSP replies "accepted" and settles asynchronously.
    if payment.state == PaymentState.BANK_DEBITED:
        background.add_task(run_payment, maker, clock, payment.id)
    return out


def _with_accounts():  # type: ignore[no-untyped-def]
    return (selectinload(Payment.payer_account), selectinload(Payment.payee_account))


@router.get("", response_model=list[PaymentOut])
async def list_my_payments(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[PaymentOut]:
    my_accounts = select(Account.id).where(Account.user_id == user.id)
    payments = await db.scalars(
        select(Payment)
        .where(
            or_(
                Payment.payer_account_id.in_(my_accounts), Payment.payee_account_id.in_(my_accounts)
            )
        )
        .options(*_with_accounts())
        .order_by(Payment.created_at.desc())
        .limit(50)
    )
    return [payment_out(p) for p in payments]


async def load_visible_payment(db: AsyncSession, payment_id: uuid.UUID, user: User) -> Payment:
    """Load a payment with its accounts, banks and events, if this user may see it."""
    payment = await db.scalar(
        select(Payment)
        .where(Payment.id == payment_id)
        .options(
            selectinload(Payment.payer_account).selectinload(Account.bank),
            selectinload(Payment.payee_account).selectinload(Account.bank),
            selectinload(Payment.events),
        )
    )
    involved = payment is not None and user.id in (
        payment.payer_account.user_id,
        payment.payee_account.user_id,
    )
    if payment is None or not (involved or user.role == UserRole.ADMIN):
        # 404 rather than 403, so nobody can probe which payment ids exist.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return payment


def detail_out(payment: Payment) -> PaymentDetailOut:
    return PaymentDetailOut(
        **payment_out(payment).model_dump(),
        events=[PaymentEventOut.model_validate(e) for e in payment.events],
    )


@router.get("/{payment_id}", response_model=PaymentDetailOut)
async def get_payment(
    payment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentDetailOut:
    return detail_out(await load_visible_payment(db, payment_id, user))


@router.get("/{payment_id}/tracker", response_model=TrackerOut)
async def track_payment(
    payment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> TrackerOut:
    """Money in Flight: where the money is now, the deadline countdown, and any dispute."""
    payment = await load_visible_payment(db, payment_id, user)
    dispute = await db.scalar(
        select(Dispute)
        .where(Dispute.payment_id == payment.id)
        # Dispute.payment resolves to the payment object loaded above (same session),
        # which already has its accounts and banks.
        .options(
            selectinload(Dispute.steps),
            selectinload(Dispute.owed_by_bank),
            selectinload(Dispute.payment),
        )
    )
    view = tracker_view(payment, dispute, await clock.now(db))
    return TrackerOut(payment=detail_out(payment), **view)
