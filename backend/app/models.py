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
    ForeignKey,
    Integer,
    String,
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


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        # Last line of defence against overdrafts: even if application code had a bug,
        # Postgres refuses to store a negative balance for a non-system account.
        CheckConstraint(
            "kind = 'system' OR balance_paise >= 0", name="ck_accounts_non_negative_balance"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    bank_id: Mapped[int] = mapped_column(ForeignKey("banks.id"))
    vpa: Mapped[str] = mapped_column(String(100), unique=True)  # UPI ID, e.g. "aarav@suraksha"
    display_name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default=AccountKind.USER)
    # Cached balance. The ledger is the source of truth; this column is updated in the same
    # DB transaction as the ledger rows, and the integrity check compares the two.
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
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # simulated time
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # simulated time

    events: Mapped[list["PaymentEvent"]] = relationship(
        back_populates="payment", order_by="PaymentEvent.id"
    )


class PaymentEvent(Base):
    """Append-only event log: one row per state transition, so the full history of a
    payment can be replayed and shown on the tracker timeline."""

    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"), index=True)
    from_state: Mapped[str | None] = mapped_column(String(32))  # None for the first event
    to_state: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(300))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # simulated time
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )  # real wall-clock time, useful when debugging time-travel demos

    payment: Mapped[Payment] = relationship(back_populates="events")


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
