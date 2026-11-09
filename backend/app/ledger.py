"""Double-entry ledger.

Rules:
1. Money never appears or disappears. Every movement is one *transaction* with two rows:
   -amount on the account it leaves, +amount on the account it reaches. So each
   transaction sums to zero, and the whole ledger always sums to zero.
2. Rows are append-only. A mistake is fixed with a new, opposite transaction (a reversal),
   never by editing history. That's what makes the ledger auditable.
3. User and merchant accounts keep a cached `accounts.balance_paise`, changed in the
   *same* database transaction as the ledger rows, on rows locked with
   SELECT ... FOR NO KEY UPDATE, so the two can never disagree.
4. System accounts (suspense, opening balances) keep NO cached balance: their balance is
   just the sum of their ledger rows. Every payment touches the suspense account, so a
   cached balance there would be one row that every payment must lock and update: a
   "hot row" that makes payments queue up one at a time. The k6 load test measured
   exactly that (about 10 payments/s). Appending ledger rows needs no shared lock.
   This is safe because nothing ever has to check a system account's balance before
   moving money; only real customers can't go below zero.

Money in flight: when a payer's bank debits them, the money moves to the platform's
settlement *suspense* account. It moves out of suspense when the payee is credited, or
back to the payer on reversal. So at any moment "how much money is stuck in flight" is
just the suspense account's balance, which the integrity check verifies.
"""

import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AccountKind, LedgerEntry, Payment
from app.state_machine import MONEY_IN_FLIGHT

OPENING_BALANCE_VPA = "opening.balance@tracepay"
SUSPENSE_VPA = "settlement.suspense@tracepay"


async def lock_accounts(db: AsyncSession, account_ids: Iterable[int]) -> dict[int, Account]:
    """Lock account rows and return them by id.

    - Until our transaction commits, any other transaction trying to lock the same rows
      waits. So two payments from one account run one after the other, and the second
      sees the balance the first left behind. That's what stops a double-spend.
    - Rows are always locked in ascending id order. If transaction A locked 1-then-2
      while B locked 2-then-1, each could wait for the other forever (a deadlock).
      One global order makes that impossible.
    - The lock is FOR NO KEY UPDATE, not FOR UPDATE. We only change `balance_paise`, never
      the row's key. FOR UPDATE would also block the KEY SHARE locks Postgres takes when
      *another* transaction inserts a row pointing at this account (a payment, a ledger
      entry); that clash deadlocked the 100-parallel-payments test. FOR NO KEY UPDATE still
      blocks other balance changes, but lets those foreign-key checks through.
    - populate_existing re-reads the row from the database even if this session already
      holds a copy, so we never check a balance against stale data.
    """
    ids = sorted(set(account_ids))
    rows = await db.scalars(
        select(Account)
        .where(Account.id.in_(ids))
        .order_by(Account.id)
        .with_for_update(key_share=True)  # renders FOR NO KEY UPDATE on Postgres
        .execution_options(populate_existing=True)
    )
    accounts = {a.id: a for a in rows}
    if len(accounts) != len(ids):
        raise LookupError(f"Accounts not found: {set(ids) - set(accounts)}")
    return accounts


async def get_system_account(db: AsyncSession, vpa: str) -> Account:
    account = await db.scalar(select(Account).where(Account.vpa == vpa))
    if account is None:
        raise LookupError(f"System account {vpa} is missing; has the database been seeded?")
    return account


def post_transfer(
    db: AsyncSession,
    *,
    from_account: Account,
    to_account: Account,
    amount_paise: int,
    at: datetime,
    description: str,
    payment_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Write one balanced transaction moving `amount_paise` between two accounts.

    Every non-system account involved must already be locked by `lock_accounts` in the
    current transaction (system accounts are never locked: see rule 4). Nothing is
    committed here: the caller commits once, together with the payment's
    state change, so either all of it happens or none of it does.
    """
    if amount_paise <= 0:
        raise ValueError("Transfer amount must be positive")
    txn_id = uuid.uuid4()
    db.add_all(
        [
            LedgerEntry(
                txn_id=txn_id,
                account_id=from_account.id,
                payment_id=payment_id,
                amount_paise=-amount_paise,
                description=description,
                created_at=at,
            ),
            LedgerEntry(
                txn_id=txn_id,
                account_id=to_account.id,
                payment_id=payment_id,
                amount_paise=amount_paise,
                description=description,
                created_at=at,
            ),
        ]
    )
    # Safe read-modify-write: the rows are locked, so nobody else can change them meanwhile.
    if from_account.kind != AccountKind.SYSTEM:
        from_account.balance_paise -= amount_paise
    if to_account.kind != AccountKind.SYSTEM:
        to_account.balance_paise += amount_paise
    return txn_id


async def ledger_balance(db: AsyncSession, account_id: int) -> int:
    """An account's balance computed from the ledger (the only balance system accounts
    have)."""
    total = await db.scalar(
        select(func.sum(LedgerEntry.amount_paise)).where(LedgerEntry.account_id == account_id)
    )
    return int(total or 0)


async def integrity_report(db: AsyncSession) -> dict:
    """Prove the ledger is consistent. Every check here should always pass.

    (Postgres returns SUM() of BIGINT as NUMERIC, hence the int() conversions.)
    """
    total = int(await db.scalar(select(func.sum(LedgerEntry.amount_paise))) or 0)

    unbalanced_txns = (
        await db.scalars(
            select(LedgerEntry.txn_id)
            .group_by(LedgerEntry.txn_id)
            .having(func.sum(LedgerEntry.amount_paise) != 0)
        )
    ).all()

    ledger_sum = func.coalesce(func.sum(LedgerEntry.amount_paise), 0)
    mismatches = (
        await db.execute(
            select(Account.vpa, Account.balance_paise, ledger_sum)
            .outerjoin(LedgerEntry, LedgerEntry.account_id == Account.id)
            .where(Account.kind != AccountKind.SYSTEM)  # system accounts have no cache
            .group_by(Account.id)
            .having(Account.balance_paise != ledger_sum)
        )
    ).all()

    suspense = await db.scalar(select(Account).where(Account.vpa == SUSPENSE_VPA))
    suspense_balance = await ledger_balance(db, suspense.id) if suspense else 0
    in_flight_total = int(
        await db.scalar(
            select(func.sum(Payment.amount_paise)).where(Payment.state.in_(list(MONEY_IN_FLIGHT)))
        )
        or 0
    )

    ok = (
        total == 0
        and not unbalanced_txns
        and not mismatches
        and suspense_balance == in_flight_total
    )
    return {
        "ok": ok,
        # 1. Debits and credits cancel out across the whole ledger.
        "ledger_total_paise": total,
        # 2. ...and inside every single transaction.
        "unbalanced_transactions": [str(t) for t in unbalanced_txns],
        # 3. Each cached (customer) balance equals the sum of that account's ledger rows.
        "balance_mismatches": [
            {"vpa": vpa, "cached_paise": cached, "ledger_paise": int(ledger)}
            for vpa, cached, ledger in mismatches
        ],
        # 4. Every paisa in suspense belongs to a payment that is currently in flight.
        "suspense_balance_paise": suspense_balance,
        "in_flight_payments_paise": in_flight_total,
    }
