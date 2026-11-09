"""Money in Flight end to end: a stuck payment, a time jump past the deadline, a dispute
opened automatically, compensation computed, escalation steps, and the claim summary.

All tests here use a frozen clock: payments are made at 15 Jan 2026, 15:30 IST, so the
P2P (T+1) deadline is 17 Jan 00:00 IST and the merchant (T+5) deadline is 21 Jan 00:00 IST.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.disputes import open_overdue_disputes
from app.models import Bank, Dispute
from tests.conftest import auth, new_key

pytestmark = pytest.mark.usefixtures("seeded")

DAY = 24 * 3600


@pytest.fixture
def clock(frozen_clock: Clock) -> Clock:
    """Override conftest's clock for this module: the app runs on frozen time."""
    return frozen_clock


async def stuck_payment(
    client: AsyncClient,
    payee: str = "shanti@suraksha",
    amount: int = 500_00,
    fault: str = "debited_not_credited",
) -> str:
    resp = await client.post(
        "/payments",
        json={"payee_vpa": payee, "amount_paise": amount, "simulate_fault": fault},
        headers={**await auth(client, "aarav"), "Idempotency-Key": new_key()},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def jump(client: AsyncClient, seconds: int) -> dict:
    resp = await client.post(
        "/admin/clock/advance", json={"seconds": seconds}, headers=await auth(client, "admin")
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def tracker(client: AsyncClient, payment_id: str, user: str = "aarav") -> dict:
    resp = await client.get(f"/payments/{payment_id}/tracker", headers=await auth(client, user))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def dispute_count(db: AsyncSession) -> int:
    return await db.scalar(select(func.count()).select_from(Dispute)) or 0


async def test_countdown_before_the_deadline(client: AsyncClient) -> None:
    t = await tracker(client, await stuck_payment(client))
    assert t["rule"]["code"] == "P2P_DEBITED_NOT_CREDITED"
    # 17 Jan 00:00 IST (sent with its +05:30 offset) is 16 Jan 18:30 UTC.
    assert t["deadline_at"] == "2026-01-17T00:00:00+05:30"
    assert datetime.fromisoformat(t["deadline_at"]) == datetime(2026, 1, 16, 18, 30, tzinfo=UTC)
    assert t["seconds_to_deadline"] == 32.5 * 3600
    assert t["breached"] is False and t["dispute"] is None


async def test_jump_past_deadline_opens_dispute_with_compensation(
    client: AsyncClient, db: AsyncSession
) -> None:
    payment_id = await stuck_payment(client)

    assert (await jump(client, 1 * DAY))["disputes_opened"] == 0  # 16 Jan: still on time
    assert (await jump(client, 3 * DAY))["disputes_opened"] == 1  # 19 Jan: deadline missed

    t = await tracker(client, payment_id)
    assert t["breached"] is True and t["health"] == "late"
    d = t["dispute"]
    assert d["status"] == "open"
    # 19 Jan 15:30 IST is 2 days 15.5 hours past the deadline: 3 days of delay.
    assert d["days_late"] == 3
    assert d["compensation_owed_paise"] == 300_00
    assert d["headline"] == "Your bank is 3 days late: ₹300 owed"
    # The bank owes this, not the person who was paid.
    assert d["owed_by_bank"] == "Jhatpat Bank"
    assert d["who_owes"] == (
        "This compensation is owed by Jhatpat Bank, your bank, not by Shanti Mehta."
    )
    assert t["payment"]["events"][-1]["kind"] == "dispute"
    assert await dispute_count(db) == 1


async def test_compensation_keeps_growing_while_unresolved(client: AsyncClient) -> None:
    payment_id = await stuck_payment(client)
    await jump(client, 4 * DAY)
    await jump(client, 2 * DAY)
    assert (await tracker(client, payment_id))["dispute"]["compensation_owed_paise"] == 500_00


async def test_merchant_payments_get_t_plus_5(client: AsyncClient) -> None:
    payment_id = await stuck_payment(client, payee="ravistore@suraksha")
    assert (await jump(client, 4 * DAY))["disputes_opened"] == 0  # 19 Jan, before 21 Jan
    assert (await jump(client, 3 * DAY))["disputes_opened"] == 1  # 22 Jan 15:30 IST
    d = (await tracker(client, payment_id))["dispute"]
    assert d["rule_code"] == "MERCHANT_NOT_CONFIRMED" and d["tat_days"] == 5
    assert (d["days_late"], d["compensation_owed_paise"]) == (2, 200_00)
    assert "not by Ravi General Store" in d["who_owes"]


async def test_resolution_freezes_compensation(client: AsyncClient) -> None:
    payment_id = await stuck_payment(client)
    await jump(client, 4 * DAY)
    resp = await client.post(
        f"/admin/payments/{payment_id}/resolve",
        json={"outcome": "credit"},
        headers=await auth(client, "admin"),
    )
    assert resp.status_code == 200
    await jump(client, 10 * DAY)

    t = await tracker(client, payment_id)
    assert t["payment"]["state"] == "credited"
    assert t["dispute"]["status"] == "resolved"
    assert t["dispute"]["compensation_owed_paise"] == 300_00  # not 1,300
    assert t["dispute"]["headline"] == "Your bank was 3 days late: ₹300 owed"
    assert t["health"] == "ok" and t["seconds_to_deadline"] is None


async def test_late_refund_is_also_disputed(client: AsyncClient, db: AsyncSession) -> None:
    """Timeout, and the payer's bank goes down before refunding: stuck in reversal_pending."""
    payment_id = await stuck_payment(client, fault="debited_not_credited")
    await db.execute(update(Bank).where(Bank.code == "JHATPAT").values(is_down=True))
    await db.commit()
    await client.post(
        f"/admin/payments/{payment_id}/retry-refund", headers=await auth(client, "admin")
    )  # nothing pending yet: no-op
    await jump(client, 4 * DAY)
    t = await tracker(client, payment_id)
    assert t["dispute"] is not None and t["dispute"]["days_late"] == 3


async def test_healthy_or_declined_payments_never_get_disputes(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await auth(client, "aarav")
    for amount in (100_00, 10_000_00):  # one credited, one declined (not enough balance)
        await client.post(
            "/payments",
            json={"payee_vpa": "shanti@suraksha", "amount_paise": amount},
            headers={**headers, "Idempotency-Key": new_key()},
        )
    await jump(client, 30 * DAY)
    assert await dispute_count(db) == 0


async def test_sweep_is_idempotent_and_safe_in_parallel(
    client: AsyncClient,
    db: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    frozen_clock: Clock,
) -> None:
    await stuck_payment(client)
    await stuck_payment(client)
    await frozen_clock.advance(db, 4 * DAY)
    await db.commit()

    async def sweep() -> int:
        async with session_factory() as s:
            opened = await open_overdue_disputes(s, await frozen_clock.now(s))
            await s.commit()
            return len(opened)

    results = await asyncio.gather(*(sweep() for _ in range(5)))
    assert sum(results) == 2  # two payments, two disputes, however many sweeps ran
    assert await sweep() == 0
    assert await dispute_count(db) == 2


async def test_escalation_steps(client: AsyncClient) -> None:
    payment_id = await stuck_payment(client)
    await jump(client, 4 * DAY)
    d = (await tracker(client, payment_id))["dispute"]
    headers = await auth(client, "aarav")
    base = f"/disputes/{d['id']}/steps"

    steps = {s["step"]: s for s in d["steps"]}
    assert list(steps) == ["app", "bank", "ombudsman"]
    assert steps["app"]["completed_at"] is not None  # raised automatically
    assert steps["ombudsman"]["available_at"] is None

    assert (await client.post(f"{base}/ombudsman/complete", headers=headers)).status_code == 409
    resp = await client.post(f"{base}/bank/complete", headers=headers)
    assert resp.status_code == 200
    bank_step = next(s for s in resp.json()["steps"] if s["step"] == "bank")
    assert bank_step["completed_at"] is not None
    # The ombudsman unlocks 30 days after the bank complaint, not before.
    assert (await client.post(f"{base}/ombudsman/complete", headers=headers)).status_code == 409
    await jump(client, 30 * DAY)
    resp = await client.post(f"{base}/ombudsman/complete", headers=headers)
    assert resp.status_code == 200
    assert all(s["completed_at"] for s in resp.json()["steps"])
    assert (await client.post(f"{base}/nonsense/complete", headers=headers)).status_code == 404


async def test_claim_summary_has_every_reference(client: AsyncClient) -> None:
    payment_id = await stuck_payment(client)
    await jump(client, 4 * DAY)
    t = await tracker(client, payment_id)
    resp = await client.get(
        f"/disputes/{t['dispute']['id']}/claim", headers=await auth(client, "aarav")
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    text = resp.text
    for expected in (
        "SIMULATION ONLY",
        t["payment"]["reference"],
        "Amount: ₹500",
        "From: aarav@jhatpat",
        "To: shanti@suraksha (Shanti Mehta)",
        "Grievance Redressal Officer, Jhatpat Bank",
        "Days of delay: 3",
        "Compensation claimed: ₹300 (₹100 per day of delay)",
        "not from the merchant or payee",
        "15 Jan 2026, 03:30 PM IST",
        "deadline of T+1 (end of 16 Jan 2026 IST)",
    ):
        assert expected in text, expected


async def test_only_the_payer_sees_the_dispute(client: AsyncClient) -> None:
    payment_id = await stuck_payment(client)
    await jump(client, 4 * DAY)
    dispute_id = (await tracker(client, payment_id))["dispute"]["id"]

    def get(user_headers: dict):  # type: ignore[no-untyped-def]
        return client.get(f"/disputes/{dispute_id}", headers=user_headers)

    assert (await get(await auth(client, "aarav"))).status_code == 200
    assert (await get(await auth(client, "admin"))).status_code == 200
    assert (await get(await auth(client, "shanti"))).status_code == 404  # the payee
    assert len((await client.get("/disputes", headers=await auth(client, "aarav"))).json()) == 1
    assert (await client.get("/disputes", headers=await auth(client, "shanti"))).json() == []


async def test_time_travel_alone_opens_dispute_with_no_other_action(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The headline promise: one clock jump and the dispute exists, with nobody clicking
    'raise complaint'."""
    await stuck_payment(client)
    assert await dispute_count(db) == 0
    await jump(client, 2 * DAY)
    assert await dispute_count(db) == 1
    opened_after = await db.scalar(select(Dispute.opened_at))
    deadline = await db.scalar(select(Dispute.deadline_at))
    assert opened_after is not None and deadline is not None
    assert opened_after - deadline == timedelta(hours=15, minutes=30)
