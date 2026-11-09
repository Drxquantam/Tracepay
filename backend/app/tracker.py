"""Money in Flight tracker: the true state of one payment, in plain language.

Turns a payment, its event log and its dispute into what the flight-path screen needs:
where the money is (payer's bank → switch → payee's bank, or on its way back), whether it's
healthy or delayed, the deadline countdown and any compensation owed.
"""

from datetime import datetime

from app.deadlines import days_late, deadline_for, rule_for
from app.disputes import dispute_view
from app.models import Dispute, Payment
from app.money import format_inr
from app.state_machine import MONEY_IN_FLIGHT, PaymentState

S = PaymentState
RESOLVED = (S.CREDITED, S.REVERSED)


def tracker_view(p: Payment, dispute: Dispute | None, now: datetime) -> dict:
    """`p` must have payer_account.bank, payee_account.bank and events loaded."""
    state = PaymentState(p.state)
    payer_bank, payee_bank = p.payer_account.bank.name, p.payee_account.bank.name
    payee, amount = p.payee_account.display_name, format_inr(p.amount_paise)
    money_moved = any(e.to_state == S.BANK_DEBITED for e in p.events)
    # Stuck = money in flight, and the latest thing that happened was a "no reply" note
    # rather than progress.
    stuck = state in MONEY_IN_FLIGHT and bool(p.events) and p.events[-1].kind != "transition"

    rule = rule_for(p.payee_account.kind) if money_moved else None
    deadline = deadline_for(p.created_at, rule.tat_days) if rule else None
    resolved_at = p.updated_at if state in RESOLVED else None
    breached = deadline is not None and (resolved_at or now) > deadline
    late = days_late(deadline, resolved_at or now) if deadline else 0

    if state == S.INITIATED:
        position, health, headline = "payer_bank", "ok", "Waiting for your bank"
        detail = "Your payment request has been received."
    elif state == S.FAILED:
        position, health, headline = "payer_bank", "failed", "Payment failed"
        detail = f"{p.failure_reason or 'The payment did not go through'}. No money was taken."
    elif state == S.BANK_DEBITED:
        position, health, headline = "payer_bank", "ok", "Debited from your account"
        detail = f"{amount} left your {payer_bank} account and is heading to the UPI switch."
    elif state == S.IN_SWITCH and stuck:
        position, health, headline = "switch", "delayed", "Your money is stuck between banks"
        detail = (
            f"{amount} left your {payer_bank} account, but {payee_bank} hasn't confirmed it "
            f"reached {payee}. It is safe and being tracked."
        )
    elif state == S.IN_SWITCH:
        position, health, headline = "switch", "ok", f"On its way to {payee}"
        detail = f"The UPI switch is passing your payment to {payee_bank}."
    elif state == S.CREDITED:
        position, health, headline = "payee_bank", "ok", f"Money reached {payee}"
        detail = f"{amount} was credited to {payee} at {payee_bank}."
    elif state == S.REVERSAL_PENDING:
        position, health, headline = "returning", "delayed", "Refund on its way back to you"
        detail = f"{p.failure_reason or 'The payment failed'}. {payer_bank} is returning {amount}."
    else:  # REVERSED
        position, health, headline = "returning", "ok", "Refunded to your account"
        detail = f"{amount} is back in your {payer_bank} account."

    if breached and resolved_at is None:
        health = "late"  # red on the flight path: past the deadline and still not fixed

    return {
        "stages": [
            {"key": "payer_bank", "label": payer_bank},
            {"key": "switch", "label": "UPI switch (simulated)"},
            {"key": "payee_bank", "label": payee_bank},
        ],
        "position": position,
        "health": health,
        "headline": headline,
        "detail": detail,
        "rule": (
            {
                "code": rule.code,
                "title": rule.title,
                "tat_days": rule.tat_days,
                "compensation_paise_per_day": rule.compensation_paise_per_day,
            }
            if rule
            else None
        ),
        "deadline_at": deadline,
        # Negative once the deadline has passed; None when there's nothing to count down.
        "seconds_to_deadline": (
            (deadline - now).total_seconds() if deadline and resolved_at is None else None
        ),
        "breached": breached,
        "days_late": late,
        "dispute": dispute_view(dispute, now) if dispute else None,
        "sim_now": now,
    }
