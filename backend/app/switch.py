"""Mock UPI switch and banks, with fault injection.

    payer's bank ──debit──► switch ──credit request──► payee's bank ──"credited"──► done

`run_payment` plays the switch for one payment, after the API has accepted it and the
payer's bank has debited it. Where a fault comes from, highest priority first:
  1. the payee's bank is switched off (`banks.is_down`, the "kill the bank" button);
  2. a fault chosen for this payment (`payments.injected_fault`);
  3. a fault set on the payee's bank (`banks.fault`).

Faults are read again *after* waiting for the bank. So if someone kills the bank while the
payment is in flight, the payment reacts to the bank's state at the moment it answers,
not the moment the payment started. That's what the demo's "kill the bank mid-flight"
relies on.

A stuck payment is never "fixed" by guessing. It stays in `in_switch` (or
`reversal_pending`), its money stays visible in the suspense account, and the deadline
sweep turns it into a dispute if it's still stuck past the turnaround deadline.
"""

import asyncio
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.faults import Fault
from app.models import Account, Bank, Payment
from app.payments import (
    complete_reversal,
    fail_payment,
    handle_credit_confirmation,
    lock_payment,
    send_to_switch,
)
from app.rules import SLOW_RESPONSE_SECONDS
from app.state_machine import PaymentState, note

SAFE = "Your money is safe in transit and is being tracked."


async def _bank_of(db: AsyncSession, account_id: int) -> Bank:
    account = await db.get(Account, account_id)
    assert account is not None
    # populate_existing: always read the bank's *current* chaos settings from the database.
    bank = await db.get(Bank, account.bank_id, populate_existing=True)
    assert bank is not None
    return bank


async def payee_bank_and_fault(db: AsyncSession, payment: Payment) -> tuple[Bank, str | None]:
    bank = await _bank_of(db, payment.payee_account_id)
    if bank.is_down:
        return bank, Fault.BANK_DOWN
    return bank, payment.injected_fault or bank.fault


async def run_payment(
    maker: async_sessionmaker[AsyncSession], clock: Clock, payment_id: uuid.UUID
) -> None:
    """Carry one debited payment through the switch. Each step is its own short DB
    transaction, and no connection is held while we wait for the bank."""
    # 1. Hand the payment to the switch.
    async with maker() as db:
        payment = await lock_payment(db, payment_id)
        if payment.state != PaymentState.BANK_DEBITED:
            return
        await send_to_switch(db, payment_id, await clock.now(db))
        bank, fault = await payee_bank_and_fault(db, payment)
        wait = bank.response_delay_seconds
        if fault == Fault.SLOW_RESPONSE:
            wait += SLOW_RESPONSE_SECONDS
        await db.commit()

    # 2. Wait for the payee's bank to answer (real seconds, so the demo can watch).
    if wait > 0:
        await asyncio.sleep(wait)

    # 3. The payee's bank answers, or doesn't.
    async with maker() as db:
        payment = await lock_payment(db, payment_id)
        if payment.state != PaymentState.IN_SWITCH:
            return  # someone (e.g. an admin "resolve") already settled it
        bank, fault = await payee_bank_and_fault(db, payment)
        now = await clock.now(db)

        if fault == Fault.BANK_DOWN:
            note(db, payment, now, f"{bank.name} is not responding. {SAFE}")
            await db.commit()
            return
        if fault == Fault.DEBITED_NOT_CREDITED:
            note(db, payment, now, f"No confirmation from {bank.name} yet. {SAFE}")
            await db.commit()
            return
        if fault == Fault.TIMEOUT:
            await fail_payment(db, payment_id, now, f"{bank.name} did not respond in time")
            await db.commit()
            await refund(maker, clock, payment_id)
            return

        await handle_credit_confirmation(db, payment_id, now, bank.name)
        await db.commit()

    # 4. Fault: the bank's "credited" callback arrives a second time. Must be a no-op.
    if fault == Fault.DUPLICATE_CALLBACK:
        async with maker() as db:
            await handle_credit_confirmation(db, payment_id, await clock.now(db), bank.name)
            await db.commit()


async def refund(
    maker: async_sessionmaker[AsyncSession], clock: Clock, payment_id: uuid.UUID
) -> None:
    """The payer's bank returns the money. If that bank is down, the refund waits, and the
    deadline sweep will notice if it waits too long."""
    async with maker() as db:
        payment = await lock_payment(db, payment_id)
        if payment.state != PaymentState.REVERSAL_PENDING:
            return  # nothing waiting to be refunded (already refunded, or never debited)
        payer_bank = await _bank_of(db, payment.payer_account_id)
        now = await clock.now(db)
        if payer_bank.is_down:
            note(
                db,
                payment,
                now,
                f"Your refund is waiting on {payer_bank.name}, which is not responding. {SAFE}",
            )
        else:
            await complete_reversal(db, payment_id, now)
        await db.commit()


class ResolveError(Exception):
    pass


async def resolve_stuck(
    db: AsyncSession, payment_id: uuid.UUID, outcome: str, at: datetime
) -> Payment:
    """Admin / demo control: the bank finally acts on a stuck payment.
    outcome="credit": the payee's bank confirms. outcome="reverse": the money goes back."""
    payment = await lock_payment(db, payment_id)
    state = PaymentState(payment.state)
    if outcome == "credit":
        if state != PaymentState.IN_SWITCH:
            raise ResolveError(f"Only a payment in the switch can be credited (it is {state})")
        bank, _ = await payee_bank_and_fault(db, payment)
        return await handle_credit_confirmation(db, payment_id, at, bank.name)
    if outcome == "reverse":
        if state in (PaymentState.BANK_DEBITED, PaymentState.IN_SWITCH):
            await fail_payment(db, payment_id, at, "The payment could not be completed")
            state = PaymentState.REVERSAL_PENDING
        if state != PaymentState.REVERSAL_PENDING:
            raise ResolveError(f"Nothing to refund: the payment is {state}")
        return await complete_reversal(db, payment_id, at)
    raise ResolveError(f"Unknown outcome {outcome!r}")
