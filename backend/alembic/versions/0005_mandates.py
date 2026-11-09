"""Mandate Manager: recurring debits and their per-cycle debit attempts.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "mandates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("payer_account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("merchant_account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("purpose", sa.String(120), nullable=False),
        sa.Column("amount_paise", sa.BigInteger, nullable=False),
        sa.Column("max_amount_paise", sa.BigInteger, nullable=False),
        sa.Column("frequency", sa.String(10), nullable=False),
        sa.Column("trial_amount_paise", sa.BigInteger, nullable=True),
        sa.Column("trial_debits_left", sa.Integer, nullable=False),
        sa.Column("next_debit_at", TZ, nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("revoked_at", TZ, nullable=True),
        sa.CheckConstraint("amount_paise > 0", name="ck_mandates_positive"),
        sa.CheckConstraint("amount_paise <= max_amount_paise", name="ck_mandates_within_cap"),
    )
    op.create_index("ix_mandates_payer_account_id", "mandates", ["payer_account_id"])
    op.create_table(
        "mandate_debits",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("mandate_id", sa.Integer, sa.ForeignKey("mandates.id"), nullable=False),
        sa.Column("due_at", TZ, nullable=False),
        sa.Column("amount_paise", sa.BigInteger, nullable=False),
        sa.Column("is_trial", sa.Boolean, nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("notice_sent_at", TZ, nullable=False),
        sa.Column("next_attempt_at", TZ, nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column(
            "payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id"), nullable=True
        ),
        sa.Column("failure_reason", sa.String(300), nullable=True),
        sa.UniqueConstraint("mandate_id", "due_at", name="uq_mandate_debit_cycle"),
    )
    op.create_index("ix_mandate_debits_mandate_id", "mandate_debits", ["mandate_id"])
    op.create_index("ix_mandate_debits_status", "mandate_debits", ["status"])


def downgrade() -> None:
    op.drop_table("mandate_debits")
    op.drop_table("mandates")
