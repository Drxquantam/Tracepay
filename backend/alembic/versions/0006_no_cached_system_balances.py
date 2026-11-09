"""System accounts keep no cached balance (removes the suspense "hot row").

Their balance is the sum of their ledger rows; see app/ledger.py, rule 4. This zeroes the
old cached values and tightens the CHECK constraint so they stay zero.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_accounts_non_negative_balance", "accounts", type_="check")
    op.execute("UPDATE accounts SET balance_paise = 0 WHERE kind = 'system'")
    op.create_check_constraint(
        "ck_accounts_balance_rules",
        "accounts",
        "(kind <> 'system' AND balance_paise >= 0) OR (kind = 'system' AND balance_paise = 0)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_accounts_balance_rules", "accounts", type_="check")
    # Restore cached system balances from the ledger.
    op.execute(
        "UPDATE accounts a SET balance_paise = COALESCE("
        "(SELECT SUM(amount_paise) FROM ledger_entries l WHERE l.account_id = a.id), 0) "
        "WHERE kind = 'system'"
    )
    op.create_check_constraint(
        "ck_accounts_non_negative_balance", "accounts", "kind = 'system' OR balance_paise >= 0"
    )
