"""Demo data. Run with `python -m app.seed`; safe to run repeatedly (skips if already seeded).

All people, banks and merchants below are fictional. Every demo user's password is
DEMO_PASSWORD — fine for a local simulation, never for anything real.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import payments
from app.db import SessionLocal
from app.ledger import OPENING_BALANCE_VPA, SUSPENSE_VPA, lock_accounts, post_transfer
from app.models import Account, AccountKind, Bank, BankProfile, SimClock, User, UserRole
from app.security import hash_password

DEMO_PASSWORD = "demo1234"


def rupees(amount: int) -> int:
    """Convert whole rupees to paise, so seed values read naturally."""
    return amount * 100


async def seed_demo_data(db: AsyncSession) -> bool:
    """Insert demo data. Returns False if the database was already seeded."""
    if await db.scalar(select(User).where(User.username == "admin")):
        return False

    now = datetime.now(UTC)
    db.add(SimClock(id=1, offset_seconds=0))

    # Two mock banks: one dependable, one that the chaos controls will love.
    suraksha = Bank(
        code="SURAKSHA",
        name="Suraksha Bank",
        profile=BankProfile.RELIABLE,
        is_down=False,
        response_delay_seconds=0.0,
    )
    # The flaky bank is also slow: it takes 2 real seconds to confirm a credit, so the flight
    # path animation has something to show even without chaos.
    jhatpat = Bank(
        code="JHATPAT",
        name="Jhatpat Bank",
        profile=BankProfile.FLAKY,
        is_down=False,
        response_delay_seconds=2.0,
    )
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

    # System accounts that keep the ledger balanced (see ledger.py).
    opening = account(
        None, suraksha, OPENING_BALANCE_VPA, "Opening balances (system)", AccountKind.SYSTEM
    )
    account(None, suraksha, SUSPENSE_VPA, "Settlement suspense (system)", AccountKind.SYSTEM)
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

    # Opening balances go through the real ledger code: the money comes from a system
    # account, so the ledger sums to zero from the very first row. The amounts are chosen
    # so that after the past payments below, balances land on round demo figures
    # (Aarav ₹8,450, Shanti ₹2,15,000, Ravi ₹46,320).
    for acc, amount in [
        (aarav_acc, rupees(6_840)),
        (shanti_acc, rupees(2_18_240)),
        (ravi_acc, rupees(45_970)),
    ]:
        locked = await lock_accounts(db, [opening.id, acc.id])
        post_transfer(
            db,
            from_account=locked[opening.id],
            to_account=locked[acc.id],
            amount_paise=amount,
            at=now - timedelta(days=30),
            description="Opening balance",
        )

    await _seed_past_payments(db, now, aarav, shanti)

    await db.commit()
    return True


async def _seed_past_payments(db: AsyncSession, now: datetime, aarav: User, shanti: User) -> None:
    """A little history, created with the same service code the API uses."""

    async def paid(user: User, payee: str, amount: int, note: str, days_ago: float) -> None:
        at = now - timedelta(days=days_ago)
        p = await payments.accept_payment(
            db, payer_user_id=user.id, payee_vpa=payee, amount_paise=amount, note=note, at=at
        )
        await payments.send_to_switch(db, p.id, at + timedelta(seconds=2))
        await payments.credit_payee(db, p.id, at + timedelta(seconds=4))

    await paid(shanti, "gridpower@jhatpat", rupees(1_240), "Electricity bill", 10)
    await paid(shanti, "aarav@jhatpat", rupees(2_000), "Pocket money", 5)
    await paid(aarav, "campuschai@jhatpat", rupees(40), "Chai and samosa", 2)
    await paid(aarav, "ravistore@suraksha", rupees(350), "Groceries", 1)

    # One payment that failed in the switch and was refunded, so the history shows a
    # reversal from day one.
    at = now - timedelta(days=3)
    p = await payments.accept_payment(
        db,
        payer_user_id=aarav.id,
        payee_vpa="campuschai@jhatpat",
        amount_paise=rupees(120),
        note="Snacks",
        at=at,
    )
    await payments.send_to_switch(db, p.id, at + timedelta(seconds=2))
    await payments.fail_payment(
        db, p.id, at + timedelta(seconds=30), "The payee's bank did not respond"
    )
    await payments.complete_reversal(db, p.id, at + timedelta(minutes=20))


async def main() -> None:
    async with SessionLocal() as db:
        created = await seed_demo_data(db)
    print("Seeded demo data." if created else "Demo data already present; skipping seed.")


if __name__ == "__main__":
    asyncio.run(main())
