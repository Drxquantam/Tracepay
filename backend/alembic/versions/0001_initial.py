"""Core money schema: users, banks, accounts, payments, events, ledger, idempotency, clock.

Revision ID: 0001
Revises:
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("senior_mode", sa.Boolean, nullable=False),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "banks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("profile", sa.String(20), nullable=False),
        sa.Column("is_down", sa.Boolean, nullable=False),
    )

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("bank_id", sa.Integer, sa.ForeignKey("banks.id"), nullable=False),
        sa.Column("vpa", sa.String(100), nullable=False, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("balance_paise", sa.BigInteger, nullable=False),
        sa.Column("is_frozen", sa.Boolean, nullable=False),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "kind = 'system' OR balance_paise >= 0", name="ck_accounts_non_negative_balance"
        ),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(32), nullable=False, unique=True),
        sa.Column("payer_account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("payee_account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("amount_paise", sa.BigInteger, nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
        sa.CheckConstraint("amount_paise > 0", name="ck_payments_positive_amount"),
        sa.CheckConstraint("payer_account_id <> payee_account_id", name="ck_payments_not_self"),
    )
    op.create_index("ix_payments_payer_account_id", "payments", ["payer_account_id"])
    op.create_index("ix_payments_payee_account_id", "payments", ["payee_account_id"])
    op.create_index("ix_payments_state", "payments", ["state"])

    op.create_table(
        "payment_events",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payments.id"),
            nullable=False,
        ),
        sa.Column("from_state", sa.String(32), nullable=True),
        sa.Column("to_state", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(300), nullable=True),
        sa.Column("occurred_at", TZ, nullable=False),
        sa.Column("recorded_at", TZ, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_payment_events_payment_id", "payment_events", ["payment_id"])

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("txn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column(
            "payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payments.id"),
            nullable=True,
        ),
        sa.Column("amount_paise", sa.BigInteger, nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.CheckConstraint("amount_paise <> 0", name="ck_ledger_nonzero"),
    )
    op.create_index("ix_ledger_entries_txn_id", "ledger_entries", ["txn_id"])
    op.create_index("ix_ledger_entries_account_id", "ledger_entries", ["account_id"])
    op.create_index("ix_ledger_entries_payment_id", "ledger_entries", ["payment_id"])

    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("response_body", postgresql.JSONB, nullable=True),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "sim_clock",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("offset_seconds", sa.BigInteger, nullable=False),
        sa.CheckConstraint("id = 1", name="ck_sim_clock_single_row"),
    )


def downgrade() -> None:
    for table in (
        "sim_clock",
        "idempotency_keys",
        "ledger_entries",
        "payment_events",
        "payments",
        "accounts",
        "banks",
        "users",
    ):
        op.drop_table(table)
