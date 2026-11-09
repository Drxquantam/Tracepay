"""A retried request must never move money twice."""

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment
from tests.conftest import auth, balance, new_key

pytestmark = pytest.mark.usefixtures("seeded")

AARAV, RAVI = "aarav@swissbank", "ravistore@suraksha"
BODY = {"payee_vpa": RAVI, "amount_paise": 99_00, "note": "Retry me"}


async def _payment_count(db: AsyncSession) -> int:
    return await db.scalar(select(func.count()).select_from(Payment)) or 0


async def test_same_key_same_body_replays_saved_result(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = {**await auth(client, "aarav"), "Idempotency-Key": new_key()}
    before, count_before = await balance(db, AARAV), await _payment_count(db)

    first = await client.post("/payments", json=BODY, headers=headers)
    second = await client.post("/payments", json=BODY, headers=headers)
    third = await client.post("/payments", json=BODY, headers=headers)

    assert first.status_code == second.status_code == third.status_code == 201
    assert "Idempotent-Replayed" not in first.headers
    assert second.headers["Idempotent-Replayed"] == "true"
    # Byte-for-byte the same answer, even though the payment has since been credited.
    assert second.json() == third.json() == first.json()
    assert await _payment_count(db) == count_before + 1
    assert await balance(db, AARAV) == before - 99_00  # charged once


async def test_same_key_different_body_is_a_conflict(client: AsyncClient, db: AsyncSession) -> None:
    headers = {**await auth(client, "aarav"), "Idempotency-Key": new_key()}
    assert (await client.post("/payments", json=BODY, headers=headers)).status_code == 201
    before = await balance(db, AARAV)

    changed = {**BODY, "amount_paise": 999_00}
    resp = await client.post("/payments", json=changed, headers=headers)
    assert resp.status_code == 409
    assert await balance(db, AARAV) == before


async def test_body_formatting_does_not_matter(client: AsyncClient) -> None:
    """Same fields in a different order is the same request, not a conflict."""
    headers = {
        **await auth(client, "aarav"),
        "Idempotency-Key": new_key(),
        "Content-Type": "application/json",
    }
    a = await client.post(
        "/payments",
        content='{"payee_vpa":"ravistore@suraksha","amount_paise":500}',
        headers=headers,
    )
    b = await client.post(
        "/payments",
        content='{ "amount_paise": 500,  "payee_vpa": "ravistore@suraksha" }',
        headers=headers,
    )
    assert a.status_code == b.status_code == 201
    assert b.headers.get("Idempotent-Replayed") == "true"


async def test_keys_are_scoped_per_user(client: AsyncClient, db: AsyncSession) -> None:
    key = new_key()
    body = {"payee_vpa": RAVI, "amount_paise": 10_00}
    a = await client.post(
        "/payments", json=body, headers={**await auth(client, "aarav"), "Idempotency-Key": key}
    )
    s = await client.post(
        "/payments", json=body, headers={**await auth(client, "shanti"), "Idempotency-Key": key}
    )
    assert a.status_code == s.status_code == 201
    assert a.json()["id"] != s.json()["id"]
    assert "Idempotent-Replayed" not in s.headers


async def test_rejected_request_does_not_burn_the_key(client: AsyncClient) -> None:
    """A validation error rolls back, so the client can fix the request and reuse the key."""
    headers = {**await auth(client, "aarav"), "Idempotency-Key": new_key()}
    bad = await client.post(
        "/payments", json={"payee_vpa": "typo@nowhere", "amount_paise": 500}, headers=headers
    )
    assert bad.status_code == 404
    good = await client.post(
        "/payments", json={"payee_vpa": RAVI, "amount_paise": 500}, headers=headers
    )
    assert good.status_code == 201
    assert "Idempotent-Replayed" not in good.headers


async def test_parallel_retries_with_one_key_create_one_payment(
    client: AsyncClient, db: AsyncSession
) -> None:
    """A user mashing the Pay button: 20 identical requests arrive at the same moment."""
    headers = {**await auth(client, "aarav"), "Idempotency-Key": new_key()}
    before, count_before = await balance(db, AARAV), await _payment_count(db)

    responses = await asyncio.gather(
        *(client.post("/payments", json=BODY, headers=headers) for _ in range(20))
    )

    assert {r.status_code for r in responses} == {201}
    assert len({r.json()["id"] for r in responses}) == 1
    assert sum(r.headers.get("Idempotent-Replayed") == "true" for r in responses) == 19
    assert await _payment_count(db) == count_before + 1
    assert await balance(db, AARAV) == before - 99_00
