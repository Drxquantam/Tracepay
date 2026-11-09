"""Concurrency: parallel payments must never overdraw an account or unbalance the ledger."""

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ledger import SUSPENSE_VPA, integrity_report
from tests.conftest import auth, balance, new_key

pytestmark = pytest.mark.usefixtures("seeded")

AARAV, RAVI, SHANTI = "aarav@jhatpat", "ravistore@suraksha", "shanti@suraksha"


async def test_100_parallel_payments_cannot_overdraw(client: AsyncClient, db: AsyncSession) -> None:
    """Aarav has ₹8,450. Fire 100 payments of ₹100 at the same instant.

    Without row locking, many requests would read the same starting balance, all decide
    "enough money", and the account would go negative (or Postgres's CHECK constraint
    would blow up requests at random). With SELECT ... FOR UPDATE they queue on Aarav's
    row: exactly 84 succeed, 16 are declined, and ₹50 is left.
    """
    start = await balance(db, AARAV)
    assert start == 8_450_00
    ravi_start = await balance(db, RAVI)
    headers = await auth(client, "aarav")

    async def one_payment(i: int):  # type: ignore[no-untyped-def]
        return await client.post(
            "/payments",
            json={"payee_vpa": RAVI, "amount_paise": 100_00, "note": f"parallel #{i}"},
            headers={**headers, "Idempotency-Key": new_key()},
        )

    responses = await asyncio.gather(*(one_payment(i) for i in range(100)))

    assert all(r.status_code == 201 for r in responses), [r.text for r in responses[:3]]
    states = [r.json()["state"] for r in responses]
    accepted = states.count("bank_debited")
    declined = states.count("failed")
    assert (accepted, declined) == (84, 16)

    final = await balance(db, AARAV)
    assert final >= 0
    assert final == start - accepted * 100_00 == 50_00
    assert await balance(db, RAVI) == ravi_start + accepted * 100_00
    assert await balance(db, SUSPENSE_VPA) == 0

    report = await integrity_report(db)
    assert report["ledger_total_paise"] == 0
    assert report["ok"], report


async def test_crossing_payments_do_not_deadlock(client: AsyncClient, db: AsyncSession) -> None:
    """Aarav pays Shanti while Shanti pays Aarav, 30 times each, all at once.

    Each transaction locks both people's rows plus the suspense account. Because rows are
    always locked in ascending id order, no two transactions can each hold a lock the
    other needs, so there's no deadlock. Postgres would abort one side with a
    'deadlock detected' error, which would surface here as a 500.
    """
    total_before = await balance(db, AARAV) + await balance(db, SHANTI)
    a_headers, s_headers = await auth(client, "aarav"), await auth(client, "shanti")

    def send(headers: dict, payee: str):  # type: ignore[no-untyped-def]
        return client.post(
            "/payments",
            json={"payee_vpa": payee, "amount_paise": 10_00},
            headers={**headers, "Idempotency-Key": new_key()},
        )

    calls = [send(a_headers, SHANTI) for _ in range(30)] + [
        send(s_headers, AARAV) for _ in range(30)
    ]
    responses = await asyncio.gather(*calls)

    assert [r.status_code for r in responses] == [201] * 60
    assert all(r.json()["state"] == "bank_debited" for r in responses)
    # Both were paid ₹300 and paid out ₹300: the pair's combined total is unchanged.
    assert await balance(db, AARAV) + await balance(db, SHANTI) == total_before
    assert (await integrity_report(db))["ok"]
