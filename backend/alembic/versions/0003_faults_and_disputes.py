"""Fault injection columns, event kinds, disputes and their escalation steps.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("banks", sa.Column("fault", sa.String(30), nullable=True))
    op.add_column(
        "banks",
        sa.Column("response_delay_seconds", sa.Float, nullable=False, server_default="0"),
    )
    op.add_column("payments", sa.Column("injected_fault", sa.String(30), nullable=True))
    op.add_column(
        "payment_events",
        sa.Column("kind", sa.String(20), nullable=False, server_default="transition"),
    )

    op.create_table(
        "disputes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payments.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("rule_code", sa.String(40), nullable=False),
        sa.Column("tat_days", sa.Integer, nullable=False),
        sa.Column("compensation_paise_per_day", sa.BigInteger, nullable=False),
        sa.Column("deadline_at", TZ, nullable=False),
        sa.Column("opened_at", TZ, nullable=False),
        sa.Column("resolved_at", TZ, nullable=True),
        sa.Column("owed_by_bank_id", sa.Integer, sa.ForeignKey("banks.id"), nullable=False),
    )
    op.create_table(
        "dispute_steps",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dispute_id", sa.Integer, sa.ForeignKey("disputes.id"), nullable=False),
        sa.Column("step", sa.String(20), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.String(400), nullable=False),
        sa.Column("completed_at", TZ, nullable=True),
    )
    op.create_index("ix_dispute_steps_dispute_id", "dispute_steps", ["dispute_id"])


def downgrade() -> None:
    op.drop_table("dispute_steps")
    op.drop_table("disputes")
    op.drop_column("payment_events", "kind")
    op.drop_column("payments", "injected_fault")
    op.drop_column("banks", "response_delay_seconds")
    op.drop_column("banks", "fault")
