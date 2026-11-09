"""Demo data. Run with `python -m app.seed`; safe to run repeatedly (skips if already seeded).

All people, banks and merchants below are fictional. Every demo user's password is
DEMO_PASSWORD — fine for a local simulation, never for anything real.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models import (
    Account,
    AccountKind,
    Bank,
    BankProfile,
    LedgerEntry,
    SimClock,
    User,
    UserRole,
)
from app.security import hash_password

DEMO_PASSWORD = "demo1234"
OPENING_BALANCE_VPA = "opening.balance@tracepay"


def rupees(amount: int) -> int:
    """Convert whole rupees to paise, so seed values read naturally."""
    return amount * 100


def _post_opening_balance(
    db: AsyncSession, source: Account, target: Account, amount_paise: int, now: datetime
) -> None:
    """Give an account its starting money *through the ledger*.

    The money comes from a system account that goes negative by the same amount, so the
    ledger sums to zero from the very first row. (The full ledger service with row locking
    arrives in Phase 2; the seed runs alone, so it can write the two legs directly.)
    """
    txn_id = uuid.uuid4()
    db.add_all(
        [
            LedgerEntry(
                txn_id=txn_id,
                account_id=source.id,
                amount_paise=-amount_paise,
                description=f"Opening balance for {target.vpa}",
                created_at=now,
            ),
            LedgerEntry(
                txn_id=txn_id,
                account_id=target.id,
                amount_paise=amount_paise,
                description="Opening balance",
                created_at=now,
            ),
        ]
    )
    source.balance_paise -= amount_paise
    target.balance_paise += amount_paise


async def seed_demo_data(db: AsyncSession) -> bool:
    """Insert demo data. Returns False if the database was already seeded."""
    if await db.scalar(select(User).where(User.username == "admin")):
        return False

    now = datetime.now(UTC)
    db.add(SimClock(id=1, offset_seconds=0))

    # Two mock banks: one dependable, one that the chaos controls will love.
    suraksha = Bank(
        code="SURAKSHA", name="Suraksha Bank", profile=BankProfile.RELIABLE, is_down=False
    )
    jhatpat = Bank(code="JHATPAT", name="Jhatpat Bank", profile=BankProfile.FLAKY, is_down=False)
    db.add_all([suraksha, jhatpat])

    pw = hash_password(DEMO_PASSWORD)
    aarav = User(
        username="aarav",
        full_name="Aarav Mehta",
        role=UserRole.CUSTOMER,
        password_hash=pw,
        senior_mode=False,
    )  # college student
    shanti = User(
        username="shanti",
        full_name="Shanti Mehta",
        role=UserRole.CUSTOMER,
        password_hash=pw,
        senior_mode=True,
    )  # Aarav's grandmother, trusted person
    ravi = User(
        username="ravi",
        full_name="Ravi Kumar",
        role=UserRole.MERCHANT,
        password_hash=pw,
        senior_mode=False,
    )  # runs a kirana store
    admin = User(
        username="admin",
        full_name="Demo Admin",
        role=UserRole.ADMIN,
        password_hash=pw,
        senior_mode=False,
    )
    db.add_all([aarav, shanti, ravi, admin])
    await db.flush()  # assigns ids, needed for the foreign keys below

    def account(user: User | None, bank: Bank, vpa: str, name: str, kind: str) -> Account:
        acc = Account(
            user_id=user.id if user else None,
            bank_id=bank.id,
            vpa=vpa,
            display_name=name,
            kind=kind,
            balance_paise=0,
            is_frozen=False,
        )
        db.add(acc)
        return acc

    opening = account(
        None, suraksha, OPENING_BALANCE_VPA, "Opening balances (system)", AccountKind.SYSTEM
    )
    # Aarav banks with the flaky bank, so the demo's "bank dies mid-flight" story is natural.
    aarav_acc = account(aarav, jhatpat, "aarav@jhatpat", "Aarav Mehta", AccountKind.USER)
    shanti_acc = account(shanti, suraksha, "shanti@suraksha", "Shanti Mehta", AccountKind.USER)
    ravi_acc = account(
        ravi, suraksha, "ravistore@suraksha", "Ravi General Store", AccountKind.MERCHANT
    )
    # Merchants with no login, used for payments and (Phase 6) recurring mandates.
    account(None, suraksha, "streamflix@suraksha", "StreamFlix (demo OTT)", AccountKind.MERCHANT)
    account(
        None, jhatpat, "gridpower@jhatpat", "GridPower Electricity (demo)", AccountKind.MERCHANT
    )
    account(None, jhatpat, "campuschai@jhatpat", "Campus Chai Point", AccountKind.MERCHANT)
    await db.flush()

    for acc, amount in [
        (aarav_acc, rupees(8_450)),
        (shanti_acc, rupees(2_15_000)),
        (ravi_acc, rupees(46_320)),
    ]:
        _post_opening_balance(db, opening, acc, amount, now)

    await db.commit()
    return True


async def main() -> None:
    async with SessionLocal() as db:
        created = await seed_demo_data(db)
    print("Seeded demo data." if created else "Demo data already present; skipping seed.")


if __name__ == "__main__":
    asyncio.run(main())
