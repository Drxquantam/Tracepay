"""Guardian mode: settings, payment holds and the notification centre.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "guardian_settings",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("guardian_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("threshold_paise", sa.BigInteger, nullable=True),
        sa.Column("new_payee_approval", sa.Boolean, nullable=False),
        sa.Column("cooling_off_threshold_paise", sa.BigInteger, nullable=True),
        sa.Column("cooling_off_minutes", sa.Integer, nullable=False),
    )
    op.create_table(
        "payment_holds",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payments.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("reasons", sa.String(400), nullable=False),
        sa.Column("guardian_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("due_at", TZ, nullable=False),
        sa.Column("decided_at", TZ, nullable=True),
    )
    op.create_index("ix_payment_holds_guardian_user_id", "payment_holds", ["guardian_user_id"])
    op.create_index("ix_payment_holds_status", "payment_holds", ["status"])
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.String(400), nullable=False),
        sa.Column("link", sa.String(200), nullable=True),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("read_at", TZ, nullable=True),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("payment_holds")
    op.drop_table("guardian_settings")
