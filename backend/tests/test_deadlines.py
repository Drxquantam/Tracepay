"""Pure unit tests for deadline, compensation and money-formatting maths."""

from datetime import UTC, datetime, timedelta

import pytest

from app.deadlines import compensation_paise, days_late, deadline_for, rule_for
from app.money import format_inr
from app.rules import IST, MERCHANT_NOT_CONFIRMED, P2P_DEBITED_NOT_CREDITED


def ist(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=IST)


def test_rule_depends_on_who_was_paid() -> None:
    assert rule_for("merchant") is MERCHANT_NOT_CONFIRMED
    assert rule_for("user") is P2P_DEBITED_NOT_CREDITED


def test_rules_carry_their_source() -> None:
    for rule in (P2P_DEBITED_NOT_CREDITED, MERCHANT_NOT_CONFIRMED):
        assert "Verify against the current circular" in rule.modelled_on


@pytest.mark.parametrize(
    ("made_at", "tat", "deadline"),
    [
        (ist(2026, 1, 15, 10, 0), 1, ist(2026, 1, 17)),  # T+1 = end of 16 Jan
        (ist(2026, 1, 15, 23, 50), 1, ist(2026, 1, 17)),  # late-night payment still gets T+1
        (ist(2026, 1, 15, 0, 5), 1, ist(2026, 1, 17)),
        (ist(2026, 1, 15, 10, 0), 5, ist(2026, 1, 21)),  # merchant T+5
        (ist(2026, 1, 31, 12, 0), 1, ist(2026, 2, 2)),  # across a month boundary
    ],
)
def test_deadline_is_end_of_day_t_plus_n_in_ist(
    made_at: datetime, tat: int, deadline: datetime
) -> None:
    assert deadline_for(made_at, tat) == deadline


def test_day_t_is_the_indian_date_not_the_utc_date() -> None:
    """20:00 UTC on 15 Jan is already 01:30 on 16 Jan in India, so T is 16 Jan."""
    made_at = datetime(2026, 1, 15, 20, 0, tzinfo=UTC)
    assert deadline_for(made_at, 1) == ist(2026, 1, 18)


@pytest.mark.parametrize(
    ("after_deadline", "late"),
    [
        (timedelta(0), 0),  # exactly on the deadline is on time
        (-timedelta(hours=5), 0),
        (timedelta(seconds=1), 1),  # any part of a day counts as a day
        (timedelta(days=1), 1),
        (timedelta(days=2, hours=12), 3),
        (timedelta(days=3), 3),
    ],
)
def test_days_late(after_deadline: timedelta, late: int) -> None:
    deadline = ist(2026, 1, 17)
    assert days_late(deadline, deadline + after_deadline) == late


def test_compensation_is_rate_times_days_late() -> None:
    deadline = ist(2026, 1, 17)
    assert compensation_paise(deadline, deadline + timedelta(days=2, hours=1), 100_00) == 300_00
    assert compensation_paise(deadline, deadline - timedelta(hours=1), 100_00) == 0


@pytest.mark.parametrize(
    ("paise", "text"),
    [
        (0, "₹0"),
        (100_00, "₹100"),
        (1_000_00, "₹1,000"),
        (8_450_00, "₹8,450"),
        (1_00_000_00, "₹1,00,000"),
        (2_15_000_00, "₹2,15,000"),
        (12_34_567_50, "₹12,34,567.50"),
        (1_23_45_678_05, "₹1,23,45,678.05"),
        (-300_00, "-₹300"),
    ],
)
def test_indian_digit_grouping(paise: int, text: str) -> None:
    assert format_inr(paise) == text
