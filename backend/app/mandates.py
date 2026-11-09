"""Mandate engine: pre-debit notices, debits on the due date, and retries.

For each billing cycle of an active mandate:
  1. Notice: once the next debit is within 24 hours, create the cycle's MandateDebit row
     (status "notified") and send a pre-debit notice.
  2. Debit: when the attempt time arrives, make a normal payment to the merchant (so it
     goes through the same ledger, switch and tracker as any other payment).
     - accepted   → "succeeded", move the mandate to its next cycle
     - declined   → "retrying" on MANDATE_RETRY_HOURS, then "failed" for that cycle
  Paused mandates skip the cycle; revoked ones cancel it.

The 24-hour rule is enforced on the attempt time, not just the due date: an attempt may
never run less than 24 hours after its notice. If the notice went out late (say the
server was down, or the demo clock jumped a month), the debit moves later rather than
breaking the rule.
"""

import calendar
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Account, Mandate, MandateDebit
from app.money import format_inr
from app.notifications import notify
from app.payments import accept_payment
from app.rules import IST, MANDATE_RETRY_HOURS, PRE_DEBIT_NOTICE_HOURS
from app.state_machine import PaymentState

NOTICE = timedelta(hours=PRE_DEBIT_NOTICE_HOURS)


def add_months(t: datetime, months: int) -> datetime:
    """Same day next month, clamped to the month's last day (31 Jan → 28/29 Feb)."""
    month_index = t.month - 1 + months
    year, month = t.year + month_index // 12, month_index % 12 + 1
    day = min(t.day, calendar.monthrange(year, month)[1])
    return t.replace(year=year, month=month, day=day)


def next_period(t: datetime, frequency: str) -> datetime:
    return add_months(t, 1) if frequency == "monthly" else t + timedelta(weeks=1)


def cycle_amount(m: Mandate) -> tuple[int, bool]:
    """(amount, is_trial) for the mandate's next cycle."""
    if m.trial_debits_left > 0 and m.trial_amount_paise is not None:
        return m.trial_amount_paise, True
    return m.amount_paise, False


def upcoming(m: Mandate, count: int = 6) -> list[dict]:
    """The next few debits, for the dashboard and the calendar (projection only)."""
    if m.status != "active":
        return []
    out, due, trials = [], m.next_debit_at, m.trial_debits_left
    for _ in range(count):
        is_trial = trials > 0 and m.trial_amount_paise is not None
        out.append(
            {
                "due_at": due,
                "amount_paise": m.trial_amount_paise if is_trial else m.amount_paise,
                "is_trial": is_trial,
            }
        )
        trials -= 1
        due = next_period(due, m.frequency)
    return out


def _advance(m: Mandate) -> None:
    """Move the mandate to its next billing cycle."""
    if m.trial_debits_left > 0:
        m.trial_debits_left -= 1
    m.next_debit_at = next_period(m.next_debit_at, m.frequency)


def _ist(t: datetime) -> str:
    return t.astimezone(IST).strftime("%d %b, %I:%M %p")


async def process_mandates(db: AsyncSession, now: datetime) -> list[uuid.UUID]:
    """Run due notices and debits. Returns accepted payments for the caller to send through
    the switch. Rows are locked with SKIP LOCKED so two schedulers never take the same
    cycle; the unique (mandate, due date) constraint is the final guard."""
    await _send_notices(db, now)
    return await _attempt_debits(db, now)


async def _send_notices(db: AsyncSession, now: datetime) -> None:
    mandates = (
        await db.scalars(
            select(Mandate)
            .where(Mandate.status == "active", Mandate.next_debit_at <= now + NOTICE)
            .options(selectinload(Mandate.payer_account), selectinload(Mandate.merchant_account))
            .with_for_update(key_share=True, skip_locked=True, of=Mandate)
        )
    ).all()
    for m in mandates:
        exists = await db.scalar(
            select(MandateDebit.id).where(
                MandateDebit.mandate_id == m.id, MandateDebit.due_at == m.next_debit_at
            )
        )
        if exists:
            continue
        amount, is_trial = cycle_amount(m)
        db.add(
            MandateDebit(
                mandate_id=m.id,
                due_at=m.next_debit_at,
                amount_paise=amount,
                is_trial=is_trial,
                status="notified",
                notice_sent_at=now,
                next_attempt_at=max(m.next_debit_at, now + NOTICE),
                attempts=0,
            )
        )
        if m.payer_account.user_id is not None:
            trial = (
                f" Trial price: after the trial it becomes {format_inr(m.amount_paise)}."
                if is_trial
                else ""
            )
            notify(
                db,
                m.payer_account.user_id,
                kind="pre_debit",
                at=now,
                link="/mandates",
                title=f"Pre-debit notice: {format_inr(amount)} to "
                f"{m.merchant_account.display_name} on {_ist(max(m.next_debit_at, now + NOTICE))}",
                body=f"For {m.purpose}.{trial} Pause or cancel the mandate before then if you "
                "don't want this debit.",
            )
    await db.flush()


async def _attempt_debits(db: AsyncSession, now: datetime) -> list[uuid.UUID]:
    rows = (
        await db.execute(
            select(MandateDebit, Mandate)
            .join(Mandate, Mandate.id == MandateDebit.mandate_id)
            .where(
                MandateDebit.status.in_(["notified", "retrying"]),
                MandateDebit.next_attempt_at <= now,
            )
            .options(selectinload(Mandate.payer_account), selectinload(Mandate.merchant_account))
            .order_by(MandateDebit.next_attempt_at)
            # Lock both rows: the debit (status) and the mandate (next date, trial counter).
            .with_for_update(key_share=True, skip_locked=True, of=[MandateDebit, Mandate])  # type: ignore[list-item]
        )
    ).all()

    to_run: list[uuid.UUID] = []
    for debit, m in rows:
        user_id = m.payer_account.user_id
        merchant = m.merchant_account.display_name
        amount = format_inr(debit.amount_paise)

        if m.status == "revoked":
            debit.status, debit.next_attempt_at = "cancelled", None
            continue
        if m.status == "paused":
            debit.status, debit.next_attempt_at = "skipped", None
            _advance(m)
            continue
        if debit.amount_paise > m.max_amount_paise:
            debit.status, debit.next_attempt_at = "failed", None
            debit.failure_reason = "Above the cap you agreed to for this mandate"
            _advance(m)
            continue

        assert user_id is not None
        payment = await accept_payment(
            db,
            payer_user_id=user_id,
            payee_vpa=m.merchant_account.vpa,
            amount_paise=debit.amount_paise,
            note=f"AutoPay: {m.purpose}",
            at=now,
            guardian_check=False,  # authorised when the mandate was set up
        )
        debit.attempts += 1
        debit.payment_id = payment.id

        if payment.state == PaymentState.BANK_DEBITED:
            debit.status, debit.next_attempt_at, debit.failure_reason = "succeeded", None, None
            _advance(m)
            to_run.append(payment.id)
            notify(
                db,
                user_id,
                kind="mandate_paid",
                at=now,
                link=f"/payments/{payment.id}",
                title=f"AutoPay: {amount} paid to {merchant}",
                body=f"For {m.purpose}.",
            )
            continue

        debit.failure_reason = payment.failure_reason
        if debit.attempts <= len(MANDATE_RETRY_HOURS):
            debit.status = "retrying"
            debit.next_attempt_at = now + timedelta(hours=MANDATE_RETRY_HOURS[debit.attempts - 1])
            notify(
                db,
                user_id,
                kind="mandate_failed",
                at=now,
                link="/mandates",
                title=f"AutoPay to {merchant} failed: we'll retry",
                body=f"{payment.failure_reason}. Next try: {_ist(debit.next_attempt_at)}.",
            )
        else:
            debit.status, debit.next_attempt_at = "failed", None
            _advance(m)
            notify(
                db,
                user_id,
                kind="mandate_failed",
                at=now,
                link="/mandates",
                title=f"AutoPay to {merchant} failed after {debit.attempts} tries",
                body=f"{payment.failure_reason}. This month's {amount} was not paid. You may "
                "want to pay the merchant directly.",
            )
    await db.flush()
    return to_run


async def payer_account_for(db: AsyncSession, user_id: int) -> Account | None:
    return await db.scalar(select(Account).where(Account.user_id == user_id).order_by(Account.id))
