"""Payment state machine.

    initiated ─► bank_debited ─► in_switch ─► credited
        │             │              │
        └─────────────┴──────────────┴──► failed ─► reversal_pending ─► reversed

`failed` straight from `initiated` means no money moved (e.g. insufficient balance), so
nothing needs reversing. Failing after the debit means the payer's money is stuck in
flight, so the payment must go on to `reversal_pending` and `reversed`.

This module is the *only* place that changes `payment.state`. Every change is checked
against ALLOWED and written to the payment_events table, so the history can't skip a
step or be silently rewritten.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentEvent


class PaymentState(StrEnum):
    INITIATED = "initiated"
    BANK_DEBITED = "bank_debited"
    IN_SWITCH = "in_switch"
    CREDITED = "credited"
    FAILED = "failed"
    REVERSAL_PENDING = "reversal_pending"
    REVERSED = "reversed"


S = PaymentState
ALLOWED: dict[PaymentState, frozenset[PaymentState]] = {
    S.INITIATED: frozenset({S.BANK_DEBITED, S.FAILED}),
    S.BANK_DEBITED: frozenset({S.IN_SWITCH, S.FAILED}),
    S.IN_SWITCH: frozenset({S.CREDITED, S.FAILED}),
    S.FAILED: frozenset({S.REVERSAL_PENDING}),
    S.REVERSAL_PENDING: frozenset({S.REVERSED}),
    S.CREDITED: frozenset(),  # terminal: money reached the payee
    S.REVERSED: frozenset(),  # terminal: money returned to the payer
}

# States where the payer's money has left their account but hasn't reached the payee or
# come back yet. It sits in the settlement suspense account (see ledger.py).
MONEY_IN_FLIGHT = frozenset({S.BANK_DEBITED, S.IN_SWITCH, S.REVERSAL_PENDING})


class InvalidTransition(Exception):
    pass


def record_created(db: AsyncSession, payment: Payment, at: datetime) -> None:
    """The first event of every payment: from nothing to `initiated`."""
    payment.state = S.INITIATED
    payment.created_at = payment.updated_at = at
    db.add(
        PaymentEvent(
            payment_id=payment.id,
            from_state=None,
            to_state=S.INITIATED,
            reason="Payment request received",
            occurred_at=at,
        )
    )


def transition(
    db: AsyncSession,
    payment: Payment,
    to_state: PaymentState,
    at: datetime,
    reason: str | None = None,
) -> None:
    """Move a payment to `to_state`, or raise InvalidTransition if that move isn't allowed.

    The caller must hold a lock on the payment row (SELECT ... FOR UPDATE) and commit
    afterwards, so the state change, its event row and any ledger rows commit together.
    """
    current = PaymentState(payment.state)
    if to_state not in ALLOWED[current]:
        raise InvalidTransition(
            f"Cannot move payment {payment.reference} from {current} to {to_state}"
        )
    db.add(
        PaymentEvent(
            payment_id=payment.id,
            from_state=current,
            to_state=to_state,
            reason=reason,
            occurred_at=at,
        )
    )
    payment.state = to_state
    payment.updated_at = at
