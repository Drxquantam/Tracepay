"""Ledger integrity endpoint, and the simulated clock."""

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app import payments
from app.clock import Clock
from app.ledger import integrity_report
from app.models import Account, User
from tests.conftest import FROZEN_NOW, auth, new_key

pytestmark = pytest.mark.usefixtures("seeded")


async def test_integrity_endpoint_is_admin_only_and_ok(client: AsyncClient) -> None:
    assert (
        await client.get("/admin/ledger/integrity", headers=await auth(client, "aarav"))
    ).status_code == 403
    resp = await client.get("/admin/ledger/integrity", headers=await auth(client, "admin"))
    assert resp.status_code == 200
    report = resp.json()
    assert report["ok"] is True
    assert report["ledger_total_paise"] == 0
    assert report["unbalanced_transactions"] == []
    assert report["balance_mismatches"] == []


async def test_integrity_check_catches_a_tampered_balance(db: AsyncSession) -> None:
    """If anyone edits a balance without writing ledger rows, the check must say so."""
    await db.execute(
        update(Account)
        .where(Account.vpa == "aarav@swissbank")
        .values(balance_paise=Account.balance_paise + 1_000_00)
    )
    await db.commit()
    report = await integrity_report(db)
    assert report["ok"] is False
    assert [m["vpa"] for m in report["balance_mismatches"]] == ["aarav@swissbank"]
    assert report["ledger_total_paise"] == 0  # the ledger itself is still fine


async def test_frozen_clock_plus_offset(db: AsyncSession, frozen_clock: Clock) -> None:
    assert await frozen_clock.now(db) == FROZEN_NOW
    await frozen_clock.advance(db, 3 * 24 * 3600)
    await frozen_clock.advance(db, 3600)
    await db.commit()
    assert await frozen_clock.now(db) == FROZEN_NOW + timedelta(days=3, hours=1)
    await frozen_clock.reset(db)
    assert await frozen_clock.now(db) == FROZEN_NOW


async def test_clock_cannot_go_backwards(db: AsyncSession, frozen_clock: Clock) -> None:
    with pytest.raises(ValueError):
        await frozen_clock.advance(db, -60)


async def test_time_travel_api_is_admin_only(client: AsyncClient) -> None:
    body = {"seconds": 2 * 24 * 3600}
    user = await client.post("/admin/clock/advance", json=body, headers=await auth(client, "aarav"))
    assert user.status_code == 403

    admin = await auth(client, "admin")
    before = (await client.get("/clock", headers=admin)).json()
    after = await client.post("/admin/clock/advance", json=body, headers=admin)
    assert after.status_code == 200
    assert after.json()["offset_seconds"] == before["offset_seconds"] + 2 * 24 * 3600

    reset = await client.post("/admin/clock/reset", headers=admin)
    assert reset.json()["offset_seconds"] == 0


async def test_payments_are_stamped_with_simulated_time(
    client: AsyncClient, db: AsyncSession
) -> None:
    """After jumping 10 days ahead, a new payment and its events carry the future date."""
    admin = await auth(client, "admin")
    await client.post("/admin/clock/advance", json={"seconds": 10 * 24 * 3600}, headers=admin)
    sim_now = (await client.get("/clock", headers=admin)).json()["now"]

    headers = await auth(client, "aarav")
    created = (
        await client.post(
            "/payments",
            json={"payee_vpa": "ravistore@suraksha", "amount_paise": 100},
            headers={**headers, "Idempotency-Key": new_key()},
        )
    ).json()
    detail = (await client.get(f"/payments/{created['id']}", headers=headers)).json()
    assert detail["created_at"][:10] == sim_now[:10]
    assert all(e["occurred_at"][:10] == sim_now[:10] for e in detail["events"])


async def test_service_uses_the_time_it_is_given(db: AsyncSession, frozen_clock: Clock) -> None:
    from sqlalchemy import select

    aarav = await db.scalar(select(User).where(User.username == "aarav"))
    assert aarav is not None
    at = await frozen_clock.now(db)
    p = await payments.accept_payment(
        db,
        payer_user_id=aarav.id,
        payee_vpa="ravistore@suraksha",
        amount_paise=100,
        note=None,
        at=at,
    )
    assert p.created_at == p.updated_at == FROZEN_NOW
