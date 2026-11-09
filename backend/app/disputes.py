"""Disputes: opened automatically when a payment misses its turnaround deadline.

Who owes the compensation? The *payer's bank*. Under the rules this models, the customer's
own (remitter) bank owes compensation for a failed transaction that wasn't reversed in time.
The merchant or person who was paid owes nothing, and the copy below says so.
"""

from datetime import datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deadlines import compensation_paise, days_late, deadline_for, rule_for
from app.models import Account, Dispute, DisputeStep, Payment, PaymentEvent
from app.money import format_inr
from app.rules import IST, OMBUDSMAN_WAIT_DAYS
from app.state_machine import MONEY_IN_FLIGHT, note

STEPS = [
    (
        "app",
        "Complaint raised in TracePay",
        "TracePay noticed the missed deadline and opened this dispute automatically.",
    ),
    (
        "bank",
        "Complaint to your bank",
        "Send the claim summary to your bank's grievance desk and note the complaint number.",
    ),
    (
        "ombudsman",
        "Escalate to the RBI Ombudsman",
        f"If your bank rejects the complaint or doesn't reply within {OMBUDSMAN_WAIT_DAYS} days, "
        "you can complain under the RBI Integrated Ombudsman Scheme.",
    ),
]


class DisputeError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


async def open_overdue_disputes(db: AsyncSession, now: datetime) -> list[Dispute]:
    """Find payments whose money is still in flight past their deadline and open a dispute
    for each. Runs from a background loop and right after every time-travel jump.

    Safe to run concurrently: FOR UPDATE SKIP LOCKED makes two sweeps (or a sweep and a
    bank callback) take different rows instead of fighting over the same payment, and the
    unique constraint on disputes.payment_id is the final guarantee against duplicates.
    """
    already_disputed = exists().where(Dispute.payment_id == Payment.id)
    candidates = (
        await db.scalars(
            select(Payment)
            .where(Payment.state.in_(list(MONEY_IN_FLIGHT)), ~already_disputed)
            .options(
                selectinload(Payment.payee_account),
                selectinload(Payment.payer_account).selectinload(Account.bank),
            )
            .with_for_update(skip_locked=True, key_share=True, of=Payment)
        )
    ).all()

    opened = []
    for payment in candidates:
        rule = rule_for(payment.payee_account.kind)
        deadline = deadline_for(payment.created_at, rule.tat_days)
        if now <= deadline:
            continue
        bank = payment.payer_account.bank
        dispute = Dispute(
            payment_id=payment.id,
            rule_code=rule.code,
            tat_days=rule.tat_days,
            compensation_paise_per_day=rule.compensation_paise_per_day,
            deadline_at=deadline,
            opened_at=now,
            owed_by_bank_id=bank.id,
        )
        dispute.steps = [
            DisputeStep(
                step=step,
                position=i,
                title=title,
                description=desc,
                completed_at=now if step == "app" else None,  # the app step is us
            )
            for i, (step, title, desc) in enumerate(STEPS)
        ]
        db.add(dispute)
        note(
            db,
            payment,
            now,
            f"Deadline (T+{rule.tat_days}) missed. Dispute opened automatically: {bank.name} "
            f"owes you {format_inr(rule.compensation_paise_per_day)} for every day of delay.",
            kind="dispute",
        )
        opened.append(dispute)
    await db.flush()
    return opened


async def mark_resolved(db: AsyncSession, payment: Payment, at: datetime) -> None:
    """Called in the same transaction as a credit or a refund. From now on the
    compensation figure is fixed."""
    dispute = await db.scalar(select(Dispute).where(Dispute.payment_id == payment.id))
    if dispute is not None and dispute.resolved_at is None:
        dispute.resolved_at = at
        note(
            db,
            payment,
            at,
            "Money has now reached its destination, so the dispute is resolved. The "
            "compensation figure is now final.",
            kind="dispute",
        )


async def load_dispute(db: AsyncSession, dispute_id: int) -> Dispute | None:
    return await db.scalar(
        select(Dispute)
        .where(Dispute.id == dispute_id)
        .options(
            selectinload(Dispute.steps),
            selectinload(Dispute.owed_by_bank),
            selectinload(Dispute.payment).selectinload(Payment.payee_account),
            selectinload(Dispute.payment).selectinload(Payment.payer_account),
        )
        .execution_options(populate_existing=True)
    )


def _measured_until(d: Dispute, now: datetime) -> datetime:
    """Compensation grows until the money arrives, then stops.

    Never measured before the moment the dispute opened: if an admin resets the demo clock
    to an earlier time, a dispute must not shrink back to "0 days late". What was owed when
    it opened stays owed.
    """
    if d.resolved_at is not None:
        return d.resolved_at
    return max(now, d.opened_at)


def owed_paise(d: Dispute, now: datetime) -> int:
    return compensation_paise(d.deadline_at, _measured_until(d, now), d.compensation_paise_per_day)


def ombudsman_available_at(d: Dispute) -> datetime | None:
    bank_step = next(s for s in d.steps if s.step == "bank")
    if bank_step.completed_at is None:
        return None
    return bank_step.completed_at + timedelta(days=OMBUDSMAN_WAIT_DAYS)


def dispute_view(d: Dispute, now: datetime) -> dict:
    late = days_late(d.deadline_at, _measured_until(d, now))
    owed = owed_paise(d, now)
    bank, payee = d.owed_by_bank.name, d.payment.payee_account.display_name
    day_word = "day" if late == 1 else "days"
    verb = "was" if d.resolved_at else "is"
    unlocks = ombudsman_available_at(d)
    return {
        "id": d.id,
        "status": "resolved" if d.resolved_at else "open",
        "payment_id": d.payment_id,
        "payment_reference": d.payment.reference,
        "amount_paise": d.payment.amount_paise,
        "payee_name": payee,
        "rule_code": d.rule_code,
        "tat_days": d.tat_days,
        "compensation_paise_per_day": d.compensation_paise_per_day,
        "deadline_at": d.deadline_at,
        "opened_at": d.opened_at,
        "resolved_at": d.resolved_at,
        "days_late": late,
        "compensation_owed_paise": owed,
        "owed_by_bank": bank,
        "headline": f"Your bank {verb} {late} {day_word} late: {format_inr(owed)} owed",
        "who_owes": f"This compensation is owed by {bank}, your bank, not by {payee}.",
        "steps": [
            {
                "step": s.step,
                "title": s.title,
                "description": s.description,
                "completed_at": s.completed_at,
                "available_at": unlocks if s.step == "ombudsman" else None,
            }
            for s in d.steps
        ],
    }


async def complete_step(db: AsyncSession, d: Dispute, step: str, at: datetime) -> None:
    """Tick off an escalation step. Steps go in order, and the ombudsman step only unlocks
    after the bank has had its waiting period."""
    target = next((s for s in d.steps if s.step == step), None)
    if target is None:
        raise DisputeError(404, f"No step called {step!r}")
    if target.completed_at is not None:
        return  # already done; ticking it again changes nothing
    earlier_open = [s for s in d.steps if s.position < target.position and not s.completed_at]
    if earlier_open:
        raise DisputeError(409, f"Finish '{earlier_open[0].title}' first")
    if step == "ombudsman":
        unlocks = ombudsman_available_at(d)
        if unlocks is None or at < unlocks:
            raise DisputeError(
                409,
                f"The ombudsman step unlocks {OMBUDSMAN_WAIT_DAYS} days after you complain to "
                "your bank, if the bank hasn't resolved it by then",
            )
    target.completed_at = at


def _last_day(deadline_at: datetime) -> str:
    """The deadline is the midnight that *starts* the next day; people think of it as
    "the end of" the day before, so name that day."""
    return (deadline_at.astimezone(IST) - timedelta(seconds=1)).strftime("%d %b %Y")


def claim_text(d: Dispute, events: list[PaymentEvent], now: datetime) -> str:
    """A ready-to-send claim summary with every reference the bank will ask for."""
    p = d.payment
    view = dispute_view(d, now)

    def ist(t: datetime) -> str:
        return t.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")

    lines = [
        "COMPENSATION CLAIM: FAILED UPI TRANSACTION",
        "(Generated by TracePay. SIMULATION ONLY: not a real transaction.)",
        "",
        f"To: Grievance Redressal Officer, {d.owed_by_bank.name}",
        "",
        f"Transaction reference (UTR): {p.reference}",
        f"Amount: {format_inr(p.amount_paise)}",
        f"Date of transaction: {ist(p.created_at)}",
        f"From: {p.payer_account.vpa}",
        f"To: {p.payee_account.vpa} ({p.payee_account.display_name})",
        f"Current status: {p.state.replace('_', ' ')}",
        "",
        f"The amount was debited from my account but did not reach the payee and was not "
        f"returned to me by the deadline of T+{d.tat_days} (end of "
        f"{_last_day(d.deadline_at)} IST).",
        f"Days of delay: {view['days_late']}",
        f"Compensation claimed: {format_inr(view['compensation_owed_paise'])} "
        f"({format_inr(d.compensation_paise_per_day)} per day of delay)",
        "",
        "This compensation is claimed from my bank, not from the merchant or payee.",
        "Rule relied on (modelled on RBI rules; verify against the current circular): "
        "harmonisation of turnaround time and customer compensation for failed transactions.",
        "",
        "Timeline:",
        *[f"  {ist(e.occurred_at)}  {e.reason or e.to_state}" for e in events],
    ]
    return "\n".join(lines) + "\n"
