"""Guardian mode, part 2: deciding on held payments, expiring them, and the kill switch.

Lock order matches the rest of the app: hold row → payment row → account rows.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ledger import lock_accounts
from app.models import Account, GuardianSettings, Payment, PaymentHold, User
from app.money import format_inr
from app.notifications import notify
from app.payments import fail_payment, release_held
from app.state_machine import PaymentState


class GuardianError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


async def guardian_id_of(db: AsyncSession, user_id: int) -> int | None:
    return await db.scalar(
        select(GuardianSettings.guardian_user_id).where(GuardianSettings.user_id == user_id)
    )


async def _lock_hold(db: AsyncSession, hold_id: int) -> PaymentHold:
    hold = await db.scalar(
        select(PaymentHold)
        .where(PaymentHold.id == hold_id)
        .options(
            selectinload(PaymentHold.payment).selectinload(Payment.payee_account),
            selectinload(PaymentHold.payment).selectinload(Payment.payer_account),
            selectinload(PaymentHold.guardian),
        )
        .with_for_update(key_share=True, of=PaymentHold)
        .execution_options(populate_existing=True)
    )
    if hold is None:
        raise GuardianError(404, "Request not found")
    return hold


def _describe(hold: PaymentHold) -> tuple[str, str, str]:
    p = hold.payment
    return format_inr(p.amount_paise), p.payee_account.display_name, f"/payments/{p.id}"


async def decide(
    db: AsyncSession, hold_id: int, guardian: User, approve: bool, at: datetime
) -> Payment:
    """The trusted person approves or denies. Works for both kinds of hold: denying a
    cooling-off hold is how the trusted person stops a payment that looks wrong."""
    hold = await _lock_hold(db, hold_id)
    if hold.guardian_user_id != guardian.id:
        raise GuardianError(404, "Request not found")
    if hold.status != "pending":
        raise GuardianError(409, f"This request was already {hold.status}")
    amount, payee, link = _describe(hold)
    payer_user_id = hold.payment.created_by_user_id
    hold.decided_at = at

    if approve:
        hold.status = "approved"
        payment = await release_held(db, hold.payment_id, at)
        if payment.state == PaymentState.BANK_DEBITED:
            notify(
                db,
                payer_user_id,
                kind="approved",
                at=at,
                link=link,
                title=f"{guardian.full_name} approved your {amount} to {payee}",
                body="It's on its way now. You can track it in the app.",
            )
        else:
            notify(
                db,
                payer_user_id,
                kind="declined",
                at=at,
                link=link,
                title=f"Your {amount} to {payee} could not be sent",
                body=f"It was approved, but then: {payment.failure_reason}.",
            )
        return payment

    hold.status = "denied"
    payment = await fail_payment(db, hold.payment_id, at, f"Stopped by {guardian.full_name}")
    notify(
        db,
        payer_user_id,
        kind="denied",
        at=at,
        link=link,
        title=f"{guardian.full_name} stopped your {amount} to {payee}",
        body="No money left your account. Talk to them if you think this was a mistake.",
    )
    return payment


async def cancel(db: AsyncSession, hold_id: int, user: User, at: datetime) -> Payment:
    """The payer changes their mind while the payment is held."""
    hold = await _lock_hold(db, hold_id)
    if hold.payment.created_by_user_id != user.id:
        raise GuardianError(404, "Request not found")
    if hold.status != "pending":
        raise GuardianError(409, f"This payment was already {hold.status}")
    # Read the details before fail_payment re-locks (and refreshes) the payment row.
    amount, payee, _ = _describe(hold)
    hold.status, hold.decided_at = "cancelled", at
    payment = await fail_payment(db, hold.payment_id, at, "You cancelled this payment")
    if hold.guardian_user_id:
        notify(
            db,
            hold.guardian_user_id,
            kind="cancelled",
            at=at,
            link="/guardian",
            title=f"{user.full_name} cancelled their {amount} to {payee}",
            body="Nothing for you to do.",
        )
    return payment


async def process_due_holds(db: AsyncSession, now: datetime) -> list[uuid.UUID]:
    """Expire approvals nobody answered and release finished cooling-off periods.
    Returns the payments that were debited, so the caller can send them through the switch.
    SKIP LOCKED lets this run alongside a guardian clicking "approve" without blocking."""
    due = (
        await db.scalars(
            select(PaymentHold)
            .where(PaymentHold.status == "pending", PaymentHold.due_at <= now)
            .options(
                selectinload(PaymentHold.payment).selectinload(Payment.payee_account),
                selectinload(PaymentHold.payment).selectinload(Payment.payer_account),
            )
            .with_for_update(key_share=True, skip_locked=True, of=PaymentHold)
        )
    ).all()

    to_run = []
    for hold in due:
        amount, payee, link = _describe(hold)
        payer_user_id = hold.payment.created_by_user_id
        hold.decided_at = now
        if hold.kind == "approval":
            hold.status = "expired"
            await fail_payment(db, hold.payment_id, now, "Not approved in time")
            notify(
                db,
                payer_user_id,
                kind="expired",
                at=now,
                link=link,
                title=f"Your {amount} to {payee} was cancelled",
                body="Nobody approved it in time. No money left your account.",
            )
        else:
            hold.status = "released"
            payment = await release_held(db, hold.payment_id, now)
            if payment.state == PaymentState.BANK_DEBITED:
                to_run.append(payment.id)
                notify(
                    db,
                    payer_user_id,
                    kind="released",
                    at=now,
                    link=link,
                    title=f"Your {amount} to {payee} is being sent",
                    body="The cooling-off period has ended.",
                )
    await db.flush()
    return to_run


async def set_frozen(
    db: AsyncSession, target: User, actor: User, frozen: bool, at: datetime
) -> Account:
    """The kill switch. The account holder or their trusted person can freeze or unfreeze.
    While frozen, every outgoing payment is declined, including held ones when released."""
    if actor.id != target.id and await guardian_id_of(db, target.id) != actor.id:
        raise GuardianError(403, "Only the account holder or their trusted person can do this")
    account = await db.scalar(select(Account).where(Account.user_id == target.id))
    if account is None:
        raise GuardianError(404, "No account to freeze")
    account = (await lock_accounts(db, [account.id]))[account.id]
    account.is_frozen = frozen

    word = "froze" if frozen else "unfroze"
    effect = (
        "All outgoing payments are blocked until it is unfrozen."
        if frozen
        else "Outgoing payments work again."
    )
    who = "You" if actor.id == target.id else actor.full_name
    notify(
        db,
        target.id,
        kind="freeze",
        at=at,
        link="/guardian",
        title=f"{who} {word} your account",
        body=effect,
    )
    guardian_id = await guardian_id_of(db, target.id)
    if guardian_id and guardian_id != actor.id:
        notify(
            db,
            guardian_id,
            kind="freeze",
            at=at,
            link="/guardian",
            title=f"{target.full_name} {word} their account",
            body=effect,
        )
    if actor.id != target.id:
        notify(
            db,
            actor.id,
            kind="freeze",
            at=at,
            link="/guardian",
            title=f"You {word} {target.full_name}'s account",
            body=effect,
        )
    return account
