"""Guardian mode, part 1: should this payment be held, and placing the hold.

Kept separate from guardian.py (approve / deny / expire / freeze) because the payment
service calls *this* module while guardian.py calls the payment service. Splitting them
avoids a circular import.

Guardian mode lowers risk, but it can't stop every scam: a victim who is being coached
can be talked into getting approval, or into changing their own rules.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Account, GuardianSettings, Payment, PaymentHold
from app.money import format_inr
from app.notifications import notify
from app.rules import APPROVAL_EXPIRES_AFTER_MINUTES
from app.state_machine import PaymentState, transition


@dataclass(frozen=True)
class HoldDecision:
    kind: str  # "approval" | "cooling_off"
    reasons: list[str]
    guardian_user_id: int
    guardian_name: str
    minutes: int  # how long until it expires (approval) or releases (cooling-off)


async def has_paid_before(db: AsyncSession, payer_id: int, payee_id: int) -> bool:
    return bool(
        await db.scalar(
            select(
                exists().where(
                    Payment.payer_account_id == payer_id,
                    Payment.payee_account_id == payee_id,
                    Payment.state == PaymentState.CREDITED,
                )
            )
        )
    )


async def evaluate(
    db: AsyncSession, payer: Account, payee: Account, amount_paise: int
) -> HoldDecision | None:
    """Return a hold decision if any of the payer's guardian rules apply, else None.
    Approval rules win over cooling-off: if the trusted person must look at it anyway,
    making the user also wait out a timer adds nothing."""
    if payer.user_id is None:
        return None
    settings = await db.scalar(
        select(GuardianSettings)
        .where(GuardianSettings.user_id == payer.user_id)
        .options(selectinload(GuardianSettings.guardian))
    )
    if settings is None or settings.guardian is None:
        return None
    guardian = settings.guardian

    reasons = []
    if settings.threshold_paise is not None and amount_paise >= settings.threshold_paise:
        reasons.append(f"It is {format_inr(settings.threshold_paise)} or more")
    if settings.new_payee_approval and not await has_paid_before(db, payer.id, payee.id):
        reasons.append(f"It is the first payment to {payee.display_name}")
    if reasons:
        return HoldDecision(
            "approval", reasons, guardian.id, guardian.full_name, APPROVAL_EXPIRES_AFTER_MINUTES
        )

    cooling = settings.cooling_off_threshold_paise
    if cooling is not None and amount_paise >= cooling:
        minutes = settings.cooling_off_minutes
        return HoldDecision(
            "cooling_off",
            [f"Large payments ({format_inr(cooling)}+) wait {minutes} minutes before sending"],
            guardian.id,
            guardian.full_name,
            minutes,
        )
    return None


def place_hold(
    db: AsyncSession,
    payment: Payment,
    decision: HoldDecision,
    *,
    payer: Account,
    payee: Account,
    at: datetime,
) -> PaymentHold:
    """Put the payment in `held`, record why, and tell both people in plain language."""
    because = "; ".join(decision.reasons)
    amount = format_inr(payment.amount_paise)
    link = f"/payments/{payment.id}"
    if decision.kind == "approval":
        transition(
            db,
            payment,
            PaymentState.HELD,
            at,
            f"Held for {decision.guardian_name}'s approval: {because}",
        )
    else:
        transition(db, payment, PaymentState.HELD, at, f"Cooling-off period: {because}")

    hold = PaymentHold(
        payment_id=payment.id,
        kind=decision.kind,
        reasons=because,
        guardian_user_id=decision.guardian_user_id,
        status="pending",
        created_at=at,
        due_at=at + timedelta(minutes=decision.minutes),
    )
    db.add(hold)

    assert payer.user_id is not None
    if decision.kind == "approval":
        notify(
            db,
            decision.guardian_user_id,
            kind="approval_request",
            at=at,
            link="/guardian",
            title=f"{payer.display_name} wants to pay {amount} to {payee.display_name}",
            body=f"Please approve or deny. Why you're being asked: {because}. If nobody "
            f"answers in {decision.minutes} minutes, the payment is cancelled.",
        )
        notify(
            db,
            payer.user_id,
            kind="held",
            at=at,
            link=link,
            title=f"Your {amount} payment is waiting for {decision.guardian_name}",
            body=f"No money has left your account. Why: {because}.",
        )
    else:
        notify(
            db,
            payer.user_id,
            kind="held",
            at=at,
            link=link,
            title=f"Your {amount} payment will send in {decision.minutes} minutes",
            body="This pause gives you time to stop it if anyone is pressuring you. "
            "You can cancel it until then.",
        )
        notify(
            db,
            decision.guardian_user_id,
            kind="cooling_off",
            at=at,
            link="/guardian",
            title=f"{payer.display_name} is sending {amount} to {payee.display_name}",
            body=f"It sends automatically in {decision.minutes} minutes. You can stop it "
            "before then if something seems wrong.",
        )
    return hold
