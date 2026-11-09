"""Business rules in one place.

Every value modelled on a real regulation is marked "MODELLED ON". They are modelled on
RBI/NPCI rules: verify against the current circular before quoting. This is a simulation,
so these values may be outdated or simplified and are not legal or financial advice.
"""

from dataclasses import dataclass
from datetime import timedelta, timezone

# Indian Standard Time. "Day T" in the turnaround rules is a calendar day in India.
# A fixed +05:30 offset is exact for IST (India has no daylight saving time).
IST = timezone(timedelta(hours=5, minutes=30), name="IST")

# Maximum amount for a single person-to-person or merchant UPI payment.
# MODELLED ON: NPCI's general per-transaction UPI limit of ₹1,00,000 (modelled on RBI/NPCI
# rules, verify against the current circular before quoting; some categories have higher
# limits, which this simulation ignores).
UPI_MAX_PER_TXN_PAISE = 1_00_000 * 100


@dataclass(frozen=True)
class TurnaroundRule:
    code: str
    title: str  # plain-language name shown to users
    tat_days: int  # money must be credited or returned by the end of day T + tat_days
    compensation_paise_per_day: int  # owed for each day (or part day) after the deadline
    modelled_on: str


# MODELLED ON: RBI's circular on harmonisation of turnaround time (TAT) and customer
# compensation for failed transactions (2019), UPI rows (modelled on RBI rules, verify
# against the current circular before quoting).
P2P_DEBITED_NOT_CREDITED = TurnaroundRule(
    code="P2P_DEBITED_NOT_CREDITED",
    title="Money debited but not credited to the person you paid",
    tat_days=1,
    compensation_paise_per_day=100 * 100,
    modelled_on="RBI TAT harmonisation circular (2019), UPI person-to-person: auto-reversal "
    "by T+1, ₹100 per day of delay after that. Verify against the current circular.",
)
MERCHANT_NOT_CONFIRMED = TurnaroundRule(
    code="MERCHANT_NOT_CONFIRMED",
    title="Money debited but the shop did not get confirmation",
    tat_days=5,
    compensation_paise_per_day=100 * 100,
    modelled_on="RBI TAT harmonisation circular (2019), UPI person-to-merchant: auto-reversal "
    "by T+5, ₹100 per day of delay after that. Verify against the current circular.",
)

# Days to wait for the bank's reply before the ombudsman step unlocks.
# MODELLED ON: RBI Integrated Ombudsman Scheme 2021, which lets a customer complain if the
# bank rejects the complaint or doesn't reply within 30 days (modelled on RBI rules, verify
# against the current scheme before quoting).
OMBUDSMAN_WAIT_DAYS = 30

# --- Simulation knobs (not regulations) ---

# Extra wait added by the "slow_response" fault, in *real* seconds, so the demo has time to
# watch the payment in flight and kill a bank mid-flight.
SLOW_RESPONSE_SECONDS = 8.0

# How often the background job checks for payments that have missed their deadline.
DEADLINE_SWEEP_INTERVAL_SECONDS = 15

# --- Guardian mode (simulation knobs, not regulations) ---

# A payment waiting for the trusted person's approval fails if nobody decides in time.
APPROVAL_EXPIRES_AFTER_MINUTES = 60
# Default cooling-off period for large payments, if the user doesn't choose one.
DEFAULT_COOLING_OFF_MINUTES = 30
