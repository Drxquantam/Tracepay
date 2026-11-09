"""The failures the mock bank and switch can be told to produce (chaos / fault injection)."""

from enum import StrEnum


class Fault(StrEnum):
    # The switch gives up waiting for the payee's bank, fails the payment and refunds it.
    TIMEOUT = "timeout"
    # The payee's bank is unreachable when the switch tries to credit, so the payment is
    # stuck in flight. (Bank-wide, this is `banks.is_down`.)
    BANK_DOWN = "bank_down"
    # The payee's bank never confirms or rejects the credit. The money is stuck: the classic
    # "debited but not credited" complaint.
    DEBITED_NOT_CREDITED = "debited_not_credited"
    # The payee's bank sends its "credited" confirmation twice. The second must be ignored.
    DUPLICATE_CALLBACK = "duplicate_callback"
    # The payee's bank answers, but only after a long pause.
    SLOW_RESPONSE = "slow_response"
