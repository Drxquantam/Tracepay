import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AccountKind, LedgerEntry, User
from app.seed import seed_demo_data

pytestmark = pytest.mark.usefixtures("seeded")


async def test_ledger_sums_to_zero_after_seed(db: AsyncSession) -> None:
    total = await db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount_paise), 0)))
    assert total == 0


async def test_each_transaction_is_balanced(db: AsyncSession) -> None:
    unbalanced = (
        await db.execute(
            select(LedgerEntry.txn_id)
            .group_by(LedgerEntry.txn_id)
            .having(func.sum(LedgerEntry.amount_paise) != 0)
        )
    ).all()
    assert unbalanced == []


async def test_cached_balances_match_ledger(db: AsyncSession) -> None:
    ledger_sums = dict(
        (
            await db.execute(
                select(LedgerEntry.account_id, func.sum(LedgerEntry.amount_paise)).group_by(
                    LedgerEntry.account_id
                )
            )
        ).all()
    )
    for acc in (await db.scalars(select(Account))).all():
        assert acc.balance_paise == ledger_sums.get(acc.id, 0), acc.vpa


async def test_only_system_accounts_are_negative(db: AsyncSession) -> None:
    negatives = (await db.scalars(select(Account).where(Account.balance_paise < 0))).all()
    assert negatives and all(a.kind == AccountKind.SYSTEM for a in negatives)


async def test_seed_is_idempotent(db: AsyncSession) -> None:
    users_before = await db.scalar(select(func.count()).select_from(User))
    assert await seed_demo_data(db) is False
    assert await db.scalar(select(func.count()).select_from(User)) == users_before


async def test_database_refuses_negative_user_balance(db: AsyncSession) -> None:
    """The CHECK constraint is a safety net under the application's own checks."""
    acc = await db.scalar(select(Account).where(Account.vpa == "aarav@jhatpat"))
    assert acc is not None
    acc.balance_paise = -1
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()
