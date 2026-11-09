"""Payment service: the steps a payment goes through, each one a single DB transaction.

    accept_payment   initiated → bank_debited   (payer → suspense)   or → failed (no money moved)
    send_to_switch   bank_debited → in_switch
    credit_payee     in_switch → credited       (suspense → payee)
    fail_payment     … → failed → reversal_pending   (if money had left the payer)
    complete_reversal  reversal_pending → reversed   (suspense → payer)

The mock UPI switch (switch.py) decides *when* each step runs and injects faults.

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
from sqlalchemy.ext.asyncio import AsyncSession

from app import guardian_rules
from app.disputes import mark_resolved
from app.ledger import SUSPENSE_VPA, get_system_account, lock_accounts, post_transfer
from app.models import Account, AccountKind, Bank, Payment
from app.rules import UPI_MAX_PER_TXN_PAISE
from app.state_machine import (
    MONEY_IN_FLIGHT,
    InvalidTransition,
    PaymentState,
    note,
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
    fault: str | None = None,
    guardian_check: bool = True,
) -> Payment:
    """Create a payment and then either decline it, hold it (guardian mode), or debit it.

    Business declines (frozen account, not enough balance) still create a payment, in the
    `failed` state, so the user sees what happened in their history, like a real UPI app.
    guardian_check=False skips guardian rules: used for mandate debits, which the user
    already authorised when they set up the mandate.
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
    payer_bank = await db.get(Bank, payer.bank_id, populate_existing=True)
    assert payer_bank is not None
    hold = await guardian_rules.evaluate(db, payer, payee, amount_paise) if guardian_check else None

    # The key line for concurrency safety: lock the payer's row *before* reading the
    # balance. A second payment from the same account waits here until we commit, then
    # sees the reduced balance. Only the payer is locked: the suspense account is a system
    # account with no cached balance (ledger.py, rule 4), so payments from different
    # people never queue behind each other. Plain reads happen before this line, to hold
    # the lock as briefly as possible.
    payer = (await lock_accounts(db, [payer.id]))[payer.id]

    payment = Payment(
        id=uuid.uuid4(),
        reference=new_reference(),
        payer_account=payer,
        payee_account=payee,
        amount_paise=amount_paise,
        note=note,
        created_by_user_id=payer_user_id,
        injected_fault=fault,
    )
    db.add(payment)
    record_created(db, payment, at)
    # Insert the payment row now, so the ledger rows below can reference it by foreign key
    # (SQLAlchemy only orders inserts automatically along relationships, and LedgerEntry
    # deliberately has none).
    await db.flush()

    decline = _decline_reason(payer, payer_bank, amount_paise)
    if decline:
        _decline(db, payment, at, decline)
    elif hold:
        guardian_rules.place_hold(db, payment, hold, payer=payer, payee=payee, at=at)
    else:
        _debit(db, payment, payer, suspense, at)
    await db.flush()
    return payment


def _decline_reason(payer: Account, payer_bank: Bank, amount_paise: int) -> str | None:
    """Why the payer's bank would refuse right now, or None. Checked on locked rows."""
    if payer_bank.is_down:
        return f"{payer_bank.name} is not responding right now. No money was taken."
    if payer.is_frozen:
        return "Your account is frozen, so outgoing payments are paused"
    if payer.balance_paise < amount_paise:
        return "Not enough balance in your account"
    return None


def _decline(db: AsyncSession, payment: Payment, at: datetime, reason: str) -> None:
    payment.failure_reason = reason
    transition(db, payment, PaymentState.FAILED, at, reason)


def _debit(
    db: AsyncSession, payment: Payment, payer: Account, suspense: Account, at: datetime
) -> None:
    """Payer → suspense. The payer must already be locked."""
    post_transfer(
        db,
        from_account=payer,
        to_account=suspense,
        amount_paise=payment.amount_paise,
        at=at,
        description=f"Debit for payment {payment.reference}",
        payment_id=payment.id,
    )
    transition(db, payment, PaymentState.BANK_DEBITED, at, "Your bank debited your account")


async def release_held(db: AsyncSession, payment_id: uuid.UUID, at: datetime) -> Payment:
    """A held payment is approved (or its cooling-off ends): try the debit now.

    Everything is checked again on freshly locked rows, because a lot can change while a
    payment waits: the balance, the bank, or someone pressing the kill switch.
    """
    payment = await lock_payment(db, payment_id)
    if payment.state != PaymentState.HELD:
        raise InvalidTransition(f"Payment {payment.reference} is {payment.state}, not held")
    payer = await db.get(Account, payment.payer_account_id)
    assert payer is not None
    payer_bank = await db.get(Bank, payer.bank_id, populate_existing=True)
    assert payer_bank is not None
    suspense = await get_system_account(db, SUSPENSE_VPA)
    payer = (await lock_accounts(db, [payer.id]))[payer.id]

    decline = _decline_reason(payer, payer_bank, payment.amount_paise)
    if decline:
        _decline(db, payment, at, decline)
    else:
        _debit(db, payment, payer, suspense, at)
    return payment


async def lock_payment(db: AsyncSession, payment_id: uuid.UUID) -> Payment:
    """Lock a payment row so two workers (or a duplicate bank callback) can't advance
    the same payment at the same time."""
    payment = await db.scalar(
        select(Payment)
        .where(Payment.id == payment_id)
        # NO KEY UPDATE, as for accounts: events and ledger rows referencing this payment
        # can still be inserted by our own and other transactions' foreign-key checks.
        .with_for_update(key_share=True)
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
    # Transition first: it raises if the payment isn't in_switch, so a payee can never be
    # credited twice for one payment.
    transition(db, payment, PaymentState.CREDITED, at, "Credited to the payee's account")
    await mark_resolved(db, payment, at)
    suspense = await get_system_account(db, SUSPENSE_VPA)
    payee = (await lock_accounts(db, [payment.payee_account_id]))[payment.payee_account_id]
    post_transfer(
        db,
        from_account=suspense,
        to_account=payee,
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
    # Transition first: it raises if the payment isn't reversal_pending, so a refund can
    # never be paid out twice.
    transition(db, payment, PaymentState.REVERSED, at, "Money returned to your account")
    await mark_resolved(db, payment, at)
    suspense = await get_system_account(db, SUSPENSE_VPA)
    payer = (await lock_accounts(db, [payment.payer_account_id]))[payment.payer_account_id]
    post_transfer(
        db,
        from_account=suspense,
        to_account=payer,
        amount_paise=payment.amount_paise,
        at=at,
        description=f"Reversal of payment {payment.reference}",
        payment_id=payment.id,
    )
    return payment


async def handle_credit_confirmation(
    db: AsyncSession, payment_id: uuid.UUID, at: datetime, bank_name: str
) -> Payment:
    """The payee's bank says "credited". Banks can send this callback more than once
    (retries, network glitches), so a repeat must be harmless: log it and move no money."""
    payment = await lock_payment(db, payment_id)
    if payment.state == PaymentState.CREDITED:
        note(db, payment, at, f"Duplicate confirmation from {bank_name} ignored. No money moved.")
        return payment
    return await credit_payee(db, payment_id, at)
