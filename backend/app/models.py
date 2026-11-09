"""Database tables.

Money rule used everywhere: amounts are integers in **paise** (₹1 = 100 paise), stored as
BIGINT. Floats can't represent 0.10 exactly, and rounding errors in a ledger are bugs.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UserRole(StrEnum):
    CUSTOMER = "customer"
    MERCHANT = "merchant"
    ADMIN = "admin"


class AccountKind(StrEnum):
    USER = "user"  # a person's savings account
    MERCHANT = "merchant"  # a shop's settlement account
    # Internal accounts the platform uses to keep the ledger balanced, e.g. the
    # "opening balance" source. Only these may go negative.
    SYSTEM = "system"


class BankProfile(StrEnum):
    RELIABLE = "reliable"
    FLAKY = "flaky"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default=UserRole.CUSTOMER)
    password_hash: Mapped[str] = mapped_column(String(200))
    senior_mode: Mapped[bool] = mapped_column(Boolean, default=False)  # large-text UI preference
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    accounts: Mapped[list["Account"]] = relationship(back_populates="user")


class Bank(Base):
    __tablename__ = "banks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)  # e.g. "SURAKSHA"
    name: Mapped[str] = mapped_column(String(120))
    profile: Mapped[str] = mapped_column(String(20), default=BankProfile.RELIABLE)
    is_down: Mapped[bool] = mapped_column(Boolean, default=False)  # toggled by chaos controls
    # A fault (see app/faults.py) applied to every payment this bank receives; None = healthy.
    fault: Mapped[str | None] = mapped_column(String(30))
    # Normal latency (real seconds) before this bank confirms a credit. The flaky bank is slow.
    response_delay_seconds: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        # Last line of defence against overdrafts: even if application code had a bug,
        # Postgres refuses to store a negative customer balance. System accounts keep no
        # cached balance at all (see ledger.py, rule 4), so theirs must stay 0.
        CheckConstraint(
            "(kind <> 'system' AND balance_paise >= 0) OR (kind = 'system' AND balance_paise = 0)",
            name="ck_accounts_balance_rules",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    bank_id: Mapped[int] = mapped_column(ForeignKey("banks.id"))
    vpa: Mapped[str] = mapped_column(String(100), unique=True)  # UPI ID, e.g. "aarav@suraksha"
    display_name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default=AccountKind.USER)
    # Cached balance for user/merchant accounts (always 0 for system accounts). The ledger
    # is the source of truth; this column is updated in the same DB transaction as the
    # ledger rows, and the integrity check compares the two.
    balance_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False)  # guardian kill switch
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User | None] = relationship(back_populates="accounts")
    bank: Mapped[Bank] = relationship()


class LedgerEntry(Base):
    """One leg of a double-entry transaction.

    Signed amount: negative = money leaves the account (debit), positive = money arrives
    (credit). Every `txn_id` has rows that sum to exactly zero, so the sum over the
    whole table is always zero. Rows are append-only: corrections are new transactions
    (e.g. a reversal), never edits.
    """

    __tablename__ = "ledger_entries"
    __table_args__ = (CheckConstraint("amount_paise <> 0", name="ck_ledger_nonzero"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    txn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"), index=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    description: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # simulated time


class Payment(Base):
    """A UPI-style payment. Its lifecycle is driven by the state machine (Phase 2).

    `state` is a plain string rather than a Postgres ENUM so new states (e.g. `held` for
    guardian mode) can be added without a type migration; the state machine in Python is
    the single place that decides which values and transitions are legal.
    """

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="ck_payments_positive_amount"),
        CheckConstraint("payer_account_id <> payee_account_id", name="ck_payments_not_self"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(32), unique=True)  # UTR-like reference number
    payer_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    payee_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(String(32), index=True)
    note: Mapped[str | None] = mapped_column(String(200))
    failure_reason: Mapped[str | None] = mapped_column(String(300))  # plain-language reason
    # Fault chosen for this one payment (demo / chaos testing). Overrides the bank's fault.
    injected_fault: Mapped[str | None] = mapped_column(String(30))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # simulated time
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # simulated time

    payer_account: Mapped[Account] = relationship(foreign_keys=[payer_account_id])
    payee_account: Mapped[Account] = relationship(foreign_keys=[payee_account_id])
    events: Mapped[list["PaymentEvent"]] = relationship(
        back_populates="payment", order_by="PaymentEvent.id"
    )


class PaymentEvent(Base):
    """Append-only event log: one row per state transition, so the full history of a
    payment can be replayed and shown on the tracker timeline."""

    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"), index=True)
    # "transition" = a state change; "note" = something happened but the state didn't change
    # (e.g. "no reply from the payee's bank"); "dispute" = deadline missed, dispute opened.
    kind: Mapped[str] = mapped_column(String(20), default="transition", server_default="transition")
    from_state: Mapped[str | None] = mapped_column(String(32))  # None for the first event
    to_state: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(300))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # simulated time
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )  # real wall-clock time, useful when debugging time-travel demos

    payment: Mapped[Payment] = relationship(back_populates="events")


class Dispute(Base):
    """Opened automatically when a payment with money in flight misses its deadline.

    The rule's numbers are *copied* onto the dispute when it opens. If the rules file changes
    later, an existing dispute keeps the terms that applied when it was opened.
    """

    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # unique: one payment can never get two disputes, even if two sweeps run at once.
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"), unique=True)
    rule_code: Mapped[str] = mapped_column(String(40))
    tat_days: Mapped[int] = mapped_column(Integer)
    compensation_paise_per_day: Mapped[int] = mapped_column(BigInteger)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # simulated time
    # Set when the money finally lands or comes back; compensation stops growing then.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The payer's bank owes the compensation (not the merchant or the person paid).
    owed_by_bank_id: Mapped[int] = mapped_column(ForeignKey("banks.id"))

    payment: Mapped[Payment] = relationship()
    owed_by_bank: Mapped[Bank] = relationship()
    steps: Mapped[list["DisputeStep"]] = relationship(
        back_populates="dispute", order_by="DisputeStep.position"
    )


class DisputeStep(Base):
    """One rung of the escalation ladder: the app, then the bank, then the RBI ombudsman."""

    __tablename__ = "dispute_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dispute_id: Mapped[int] = mapped_column(ForeignKey("disputes.id"), index=True)
    step: Mapped[str] = mapped_column(String(20))  # "app" | "bank" | "ombudsman"
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(400))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    dispute: Mapped[Dispute] = relationship(back_populates="steps")


class GuardianSettings(Base):
    """A user's guardian-mode rules and their trusted person. One row per protected user."""

    __tablename__ = "guardian_settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    guardian_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # Payments of this amount or more need the trusted person's approval (None = off).
    threshold_paise: Mapped[int | None] = mapped_column(BigInteger)
    # The first-ever payment to someone needs approval (a common pattern in scams).
    new_payee_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    # Payments of this amount or more wait out a cooling-off period first (None = off).
    cooling_off_threshold_paise: Mapped[int | None] = mapped_column(BigInteger)
    cooling_off_minutes: Mapped[int] = mapped_column(Integer, default=30)

    guardian: Mapped[User | None] = relationship(foreign_keys=[guardian_user_id])


class PaymentHold(Base):
    """Why a payment is held, and what happened to the hold.

    kind="approval":    waits for the trusted person; at `due_at` it expires (payment fails).
    kind="cooling_off": waits until `due_at`, then is released automatically, unless the
                        user or the trusted person cancels it first.
    """

    __tablename__ = "payment_holds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    reasons: Mapped[str] = mapped_column(String(400))  # plain language, "; "-separated
    guardian_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    # pending | approved | denied | expired | released | cancelled
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # simulated time
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # simulated time
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    payment: Mapped[Payment] = relationship()
    guardian: Mapped[User | None] = relationship()


class Notification(Base):
    """In-app notification centre (the simulation's stand-in for SMS and push)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # e.g. "approval_request", "dispute"
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(String(400))
    link: Mapped[str | None] = mapped_column(String(200))  # a path in the web app
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # simulated time
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Mandate(Base):
    """A recurring debit the user authorised for a merchant (an e-mandate / UPI AutoPay)."""

    __tablename__ = "mandates"
    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="ck_mandates_positive"),
        CheckConstraint("amount_paise <= max_amount_paise", name="ck_mandates_within_cap"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payer_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    merchant_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    purpose: Mapped[str] = mapped_column(String(120))
    amount_paise: Mapped[int] = mapped_column(BigInteger)  # regular amount (after any trial)
    max_amount_paise: Mapped[int] = mapped_column(BigInteger)  # cap per debit the user agreed to
    frequency: Mapped[str] = mapped_column(String(10))  # "monthly" | "weekly"
    # Trial-to-paid: e.g. ₹1 for the first debit, then ₹499. The dashboard flags these.
    trial_amount_paise: Mapped[int | None] = mapped_column(BigInteger)
    trial_debits_left: Mapped[int] = mapped_column(Integer, default=0)
    next_debit_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(12), default="active")  # active|paused|revoked
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    payer_account: Mapped[Account] = relationship(foreign_keys=[payer_account_id])
    merchant_account: Mapped[Account] = relationship(foreign_keys=[merchant_account_id])
    debits: Mapped[list["MandateDebit"]] = relationship(
        back_populates="mandate", order_by="MandateDebit.due_at.desc()"
    )


class MandateDebit(Base):
    """One billing cycle of a mandate: notice sent, then one or more debit attempts.

    The unique (mandate_id, due_at) pair means a cycle can only ever exist once, so running
    the scheduler twice (or two schedulers at once) can't charge the same cycle twice.
    """

    __tablename__ = "mandate_debits"
    __table_args__ = (UniqueConstraint("mandate_id", "due_at", name="uq_mandate_debit_cycle"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id"), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False)
    # notified | retrying | succeeded | failed | skipped (paused) | cancelled (revoked)
    status: Mapped[str] = mapped_column(String(12), index=True)
    notice_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Earliest moment the next attempt may run: never sooner than 24 h after the notice.
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"))  # latest
    failure_reason: Mapped[str | None] = mapped_column(String(300))

    mandate: Mapped[Mandate] = relationship(back_populates="debits")


class IdempotencyKey(Base):
    """Remembers the result of a request made with an `Idempotency-Key` header.

    Keys are scoped per user (composite primary key), so two users can't collide.
    `request_hash` lets us detect the same key being reused with a *different* payload,
    which is a client bug and gets a 409 Conflict instead of a silent replay.
    """

    __tablename__ = "idempotency_keys"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))  # sha256 hex of the request body
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SimClock(Base):
    """Single-row table holding how far the simulated clock is ahead of real time.

    Stored in the DB (not in memory) so every API worker and the test suite agree on the
    current simulated time, and a time jump survives restarts.
    """

    __tablename__ = "sim_clock"
    __table_args__ = (CheckConstraint("id = 1", name="ck_sim_clock_single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    offset_seconds: Mapped[int] = mapped_column(BigInteger, default=0)
