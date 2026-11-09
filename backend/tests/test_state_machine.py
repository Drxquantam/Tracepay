"""Unit tests for the state machine graph, plus the event log it writes."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentEvent
from app.state_machine import ALLOWED, InvalidTransition, PaymentState, transition

S = PaymentState
AT = datetime(2026, 1, 1, tzinfo=UTC)


class _FakeSession:
    """Just enough of a session to collect added rows, for pure unit tests."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)


def _payment(state: PaymentState) -> Payment:
    return Payment(id=uuid.uuid4(), reference="000000000001", state=state)


VALID = [
    (S.INITIATED, S.BANK_DEBITED),
    (S.INITIATED, S.FAILED),
    (S.BANK_DEBITED, S.IN_SWITCH),
    (S.BANK_DEBITED, S.FAILED),
    (S.IN_SWITCH, S.CREDITED),
    (S.IN_SWITCH, S.FAILED),
    (S.FAILED, S.REVERSAL_PENDING),
    (S.REVERSAL_PENDING, S.REVERSED),
]


@pytest.mark.parametrize(("start", "end"), VALID)
def test_valid_transitions_are_allowed_and_logged(start: S, end: S) -> None:
    db, p = _FakeSession(), _payment(start)
    transition(db, p, end, AT, "because")  # type: ignore[arg-type]
    assert p.state == end
    assert p.updated_at == AT
    [event] = db.added
    assert isinstance(event, PaymentEvent)
    assert (event.from_state, event.to_state, event.reason) == (start, end, "because")


ALL_PAIRS = [(a, b) for a in S for b in S]
INVALID = [pair for pair in ALL_PAIRS if pair not in VALID]


@pytest.mark.parametrize(("start", "end"), INVALID)
def test_every_other_transition_is_rejected(start: S, end: S) -> None:
    db, p = _FakeSession(), _payment(start)
    with pytest.raises(InvalidTransition):
        transition(db, p, end, AT)  # type: ignore[arg-type]
    assert p.state == start  # unchanged
    assert db.added == []  # and nothing written to the event log


def test_terminal_states_have_no_exits() -> None:
    assert ALLOWED[S.CREDITED] == frozenset()
    assert ALLOWED[S.REVERSED] == frozenset()


def test_graph_lists_every_state() -> None:
    assert set(ALLOWED) == set(S)


@pytest.mark.usefixtures("seeded")
async def test_seeded_reversal_has_full_event_history(db: AsyncSession) -> None:
    """The seed's refunded payment shows every step, in order, in the event log."""
    payment = await db.scalar(select(Payment).where(Payment.state == S.REVERSED))
    assert payment is not None
    events = (
        await db.scalars(
            select(PaymentEvent)
            .where(PaymentEvent.payment_id == payment.id)
            .order_by(PaymentEvent.id)
        )
    ).all()
    assert [(e.from_state, e.to_state) for e in events] == [
        (None, S.INITIATED),
        (S.INITIATED, S.BANK_DEBITED),
        (S.BANK_DEBITED, S.IN_SWITCH),
        (S.IN_SWITCH, S.FAILED),
        (S.FAILED, S.REVERSAL_PENDING),
        (S.REVERSAL_PENDING, S.REVERSED),
    ]
    times = [e.occurred_at for e in events]
    assert times == sorted(times)
