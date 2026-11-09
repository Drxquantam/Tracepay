"""Business rules in one place.

Anything modelled on a real regulation is marked:
    MODELLED ON: ... (modelled on RBI/NPCI rules, verify against the current circular
    before quoting)
These values are for a simulation and may be outdated or simplified.
Turnaround-time and compensation rules are added in Phase 3.
"""

# Maximum amount for a single person-to-person or merchant UPI payment.
# MODELLED ON: NPCI's general per-transaction UPI limit of ₹1,00,000 (modelled on
# RBI/NPCI rules, verify against the current circular before quoting; some categories
# have higher limits, which this simulation ignores).
UPI_MAX_PER_TXN_PAISE = 1_00_000 * 100
