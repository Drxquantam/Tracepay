"""Deadline and compensation maths. Pure functions (no database), so they're easy to test.

Turnaround rules count calendar days in India: "T" is the day the payment was made, and
"T+1" means the money must be back (or delivered) by the end of the next day, IST.
"""

import math
from datetime import date, datetime, time, timedelta

from app.models import AccountKind
from app.rules import IST, MERCHANT_NOT_CONFIRMED, P2P_DEBITED_NOT_CREDITED, TurnaroundRule

DAY = timedelta(days=1)


def rule_for(payee_kind: str) -> TurnaroundRule:
    """Paying a shop gets the merchant rule; paying a person gets the P2P rule."""
    if payee_kind == AccountKind.MERCHANT:
        return MERCHANT_NOT_CONFIRMED
    return P2P_DEBITED_NOT_CREDITED


def deadline_for(created_at: datetime, tat_days: int) -> datetime:
    """End of day T + tat_days, in IST. (The deadline is the midnight that starts the next
    day, so a payment made at 11:50 pm still gets all of day T+1.)"""
    day_t: date = created_at.astimezone(IST).date()
    return datetime.combine(day_t + timedelta(days=tat_days + 1), time.min, tzinfo=IST)


def days_late(deadline_at: datetime, until: datetime) -> int:
    """Days of delay after the deadline. A part day counts as a whole day (an hour late is
    one day late); this simulation's reading of "per day of delay"."""
    if until <= deadline_at:
        return 0
    return math.ceil((until - deadline_at) / DAY)


def compensation_paise(deadline_at: datetime, until: datetime, paise_per_day: int) -> int:
    return days_late(deadline_at, until) * paise_per_day
