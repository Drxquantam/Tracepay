"""Payment service: the steps a payment goes through, each one a single DB transaction.

    accept_payment   initiated → bank_debited   (payer → suspense)   or → failed (no money moved)
    send_to_switch   bank_debited → in_switch
    credit_payee     in_switch → credited       (suspense → payee)
    fail_payment     … → failed → reversal_pending   (if money had left the payer)
    complete_reversal  reversal_pending → reversed   (suspense → payer)

The functions don't commit; their caller does. That way the state change, its event row
and its ledger rows always commit together, or not at all.

Lock order, everywhere: the payment row first, then accounts in ascending id order
(inside lock_accounts). A single global order is what keeps parallel payments from
deadlocking each other.
"""

import secrets
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.ledger import SUSPENSE_VPA, get_system_account, lock_accounts, post_transfer
from app.models import Account, AccountKind, Payment
from app.rules import UPI_MAX_PER_TXN_PAISE
from app.state_machine import (
    MONEY_IN_FLIGHT,
    PaymentState,
    record_created,
    transition,
)


class PaymentError(Exception):
    """A request we refuse outright, before any payment exists (bad payee, over limit...)."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def new_reference() -> str:
    """A 12-digit reference number, shaped like a UPI transaction reference (UTR).
    Random, so references don't reveal how many payments the platform handles. The DB's
    unique constraint is the backstop against the (tiny) chance of a collision."""
    return f"{secrets.randbelow(10**12):012d}"


async def accept_payment(
    db: AsyncSession,
    *,
    payer_user_id: int,
    payee_vpa: str,
    amount_paise: int,
    note: str | None,
    at: datetime,
) -> Payment:
    """Create a payment and, if the payer can afford it, debit them.

    Business declines (frozen account, not enough balance) still create a payment, in the
    `failed` state, so the user sees what happened in their history, like a real UPI app.
    """
    if amount_paise > UPI_MAX_PER_TXN_PAISE:
        raise PaymentError(422, "Amount is above the per-payment UPI limit")

    payer = await db.scalar(
        select(Account).where(Account.user_id == payer_user_id).order_by(Account.id).limit(1)
    )
    if payer is None:
        raise PaymentError(400, "You don't have an account to pay from")
    payee = await db.scalar(select(Account).where(Account.vpa == payee_vpa.strip().lower()))
    if payee is None or payee.kind == AccountKind.SYSTEM:
        raise PaymentError(404, f"No one with the UPI ID {payee_vpa!r} was found")
    if payee.id == payer.id:
        raise PaymentError(400, "You can't pay yourself")

    suspense = await get_system_account(db, SUSPENSE_VPA)
    # The key line for concurrency safety: lock the payer's row *before* reading the
    # balance. A second payment from the same account waits here until we commit, then
    # sees the reduced balance.
    locked = await lock_accounts(db, [payer.id, suspense.id])
    payer, suspense = locked[payer.id], locked[suspense.id]

    payment = Payment(
        id=uuid.uuid4(),
        reference=new_reference(),
        payer_account=payer,
        payee_account=payee,
        amount_paise=amount_paise,
        note=note,
        created_by_user_id=payer_user_id,
    )
    db.add(payment)
    record_created(db, payment, at)
    # Insert the payment row now, so the ledger rows below can reference it by foreign key
    # (SQLAlchemy only orders inserts automatically along relationships, and LedgerEntry
    # deliberately has none).
    await db.flush()

    if payer.is_frozen:
        _decline(db, payment, at, "Your account is frozen, so outgoing payments are paused")
    elif payer.balance_paise < amount_paise:
        _decline(db, payment, at, "Not enough balance in your account")
    else:
        post_transfer(
            db,
            from_account=payer,
            to_account=suspense,
            amount_paise=amount_paise,
            at=at,
            description=f"Debit for payment {payment.reference}",
            payment_id=payment.id,
        )
        transition(db, payment, PaymentState.BANK_DEBITED, at, "Your bank debited your account")

    await db.flush()
    return payment


def _decline(db: AsyncSession, payment: Payment, at: datetime, reason: str) -> None:
    payment.failure_reason = reason
    transition(db, payment, PaymentState.FAILED, at, reason)


async def lock_payment(db: AsyncSession, payment_id: uuid.UUID) -> Payment:
    """Lock a payment row so two workers (or a duplicate bank callback) can't advance
    the same payment at the same time."""
    payment = await db.scalar(
        select(Payment)
        .where(Payment.id == payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if payment is None:
        raise LookupError(f"Payment {payment_id} not found")
    return payment


async def send_to_switch(db: AsyncSession, payment_id: uuid.UUID, at: datetime) -> Payment:
    payment = await lock_payment(db, payment_id)
    transition(db, payment, PaymentState.IN_SWITCH, at, "Sent through the UPI switch")
    return payment


async def credit_payee(db: AsyncSession, payment_id: uuid.UUID, at: datetime) -> Payment:
    payment = await lock_payment(db, payment_id)
    suspense = await get_system_account(db, SUSPENSE_VPA)
    locked = await lock_accounts(db, [suspense.id, payment.payee_account_id])
    # Transition first: it raises if the payment isn't in_switch, so a payee can never be
    # credited twice for one payment.
    transition(db, payment, PaymentState.CREDITED, at, "Credited to the payee's account")
    post_transfer(
        db,
        from_account=locked[suspense.id],
        to_account=locked[payment.payee_account_id],
        amount_paise=payment.amount_paise,
        at=at,
        description=f"Credit for payment {payment.reference}",
        payment_id=payment.id,
    )
    return payment


async def fail_payment(
    db: AsyncSession, payment_id: uuid.UUID, at: datetime, reason: str
) -> Payment:
    """Mark a payment failed. If the payer had already been debited, their money is in
    suspense, so a refund (reversal) is started in the same transaction: we never leave a
    failed payment holding someone's money without a refund on the way."""
    payment = await lock_payment(db, payment_id)
    money_left_payer = PaymentState(payment.state) in MONEY_IN_FLIGHT
    payment.failure_reason = reason
    transition(db, payment, PaymentState.FAILED, at, reason)
    if money_left_payer:
        transition(
            db, payment, PaymentState.REVERSAL_PENDING, at, "Refund to your account has started"
        )
    return payment


async def complete_reversal(db: AsyncSession, payment_id: uuid.UUID, at: datetime) -> Payment:
    payment = await lock_payment(db, payment_id)
    suspense = await get_system_account(db, SUSPENSE_VPA)
    locked = await lock_accounts(db, [suspense.id, payment.payer_account_id])
    # Transition first: it raises if the payment isn't reversal_pending, so a refund can
    # never be paid out twice.
    transition(db, payment, PaymentState.REVERSED, at, "Money returned to your account")
    post_transfer(
        db,
        from_account=locked[suspense.id],
        to_account=locked[payment.payer_account_id],
        amount_paise=payment.amount_paise,
        at=at,
        description=f"Reversal of payment {payment.reference}",
        payment_id=payment.id,
    )
    return payment


async def process_payment(
    maker: async_sessionmaker[AsyncSession], clock: Clock, payment_id: uuid.UUID
) -> None:
    """Carry a debited payment through the switch to the payee (Phase 2: happy path only).

    Runs after the HTTP response is sent, like a real PSP. If the process died between
    steps, the payment would sit in `bank_debited` or `in_switch` with the money safe in
    suspense; Phase 3 adds the mock bank and switch (with fault injection) and the
    deadline checks that catch exactly that case.
    """
    async with maker() as db:
        await send_to_switch(db, payment_id, await clock.now(db))
        await db.commit()
    async with maker() as db:
        await credit_payee(db, payment_id, await clock.now(db))
        await db.commit()
