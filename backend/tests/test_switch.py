"""Mock bank and switch: each injected fault produces the right, honest outcome."""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import payments, switch
from app.clock import Clock
from app.ledger import SUSPENSE_VPA, integrity_report
from app.models import Bank, Payment, User
from app.state_machine import PaymentState
from tests.conftest import auth, balance, new_key

pytestmark = pytest.mark.usefixtures("seeded")

AARAV, RAVI = "aarav@jhatpat", "ravistore@suraksha"


async def pay(client: AsyncClient, amount: int = 250_00, fault: str | None = None) -> dict:
    body: dict = {"payee_vpa": RAVI, "amount_paise": amount}
    if fault:
        body["simulate_fault"] = fault
    resp = await client.post(
        "/payments",
        json=body,
        headers={**await auth(client, "aarav"), "Idempotency-Key": new_key()},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def tracker(client: AsyncClient, payment_id: str) -> dict:
    resp = await client.get(f"/payments/{payment_id}/tracker", headers=await auth(client, "aarav"))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def set_bank(db: AsyncSession, code: str, **values: object) -> None:
    await db.execute(update(Bank).where(Bank.code == code).values(**values))
    await db.commit()


async def test_no_fault_reaches_payee(client: AsyncClient) -> None:
    t = await tracker(client, (await pay(client))["id"])
    assert (t["payment"]["state"], t["position"], t["health"]) == ("credited", "payee_bank", "ok")
    assert t["headline"] == "Money reached Ravi General Store"


@pytest.mark.parametrize("fault", ["debited_not_credited", "bank_down"])
async def test_stuck_payment_shows_true_state_and_money_stays_accounted_for(
    client: AsyncClient, db: AsyncSession, fault: str
) -> None:
    before = await balance(db, AARAV)
    t = await tracker(client, (await pay(client, 250_00, fault))["id"])

    assert t["payment"]["state"] == "in_switch"
    assert (t["position"], t["health"]) == ("switch", "delayed")
    assert t["headline"] == "Your money is stuck between banks"
    assert t["payment"]["events"][-1]["kind"] == "note"
    assert "safe in transit" in t["payment"]["events"][-1]["reason"]
    assert t["breached"] is False and t["dispute"] is None
    assert t["rule"]["code"] == "MERCHANT_NOT_CONFIRMED"  # Ravi is a shop: T+5
    # The money has left Aarav, sits in suspense, and the books still balance.
    assert await balance(db, AARAV) == before - 250_00
    assert await balance(db, SUSPENSE_VPA) == 250_00
    assert (await integrity_report(db))["ok"]


async def test_payee_bank_switched_off_strands_payments(
    client: AsyncClient, db: AsyncSession
) -> None:
    await set_bank(db, "SURAKSHA", is_down=True)
    assert (await pay(client))["state"] == "bank_debited"
    t = await tracker(client, (await pay(client))["id"])
    assert t["payment"]["state"] == "in_switch"
    assert "Suraksha Bank is not responding" in t["payment"]["events"][-1]["reason"]


async def test_payer_bank_down_declines_without_taking_money(
    client: AsyncClient, db: AsyncSession
) -> None:
    await set_bank(db, "JHATPAT", is_down=True)
    before = await balance(db, AARAV)
    created = await pay(client)
    assert created["state"] == "failed"
    assert (
        created["failure_reason"] == "Jhatpat Bank is not responding right now. No money was taken."
    )
    assert await balance(db, AARAV) == before
    t = await tracker(client, created["id"])
    assert t["rule"] is None and t["deadline_at"] is None  # nothing to chase


async def test_timeout_fails_and_refunds(client: AsyncClient, db: AsyncSession) -> None:
    before = await balance(db, AARAV)
    t = await tracker(client, (await pay(client, 250_00, "timeout"))["id"])
    assert t["payment"]["state"] == "reversed"
    assert t["payment"]["failure_reason"] == "Suraksha Bank did not respond in time"
    assert [e["to_state"] for e in t["payment"]["events"]] == [
        "initiated",
        "bank_debited",
        "in_switch",
        "failed",
        "reversal_pending",
        "reversed",
    ]
    assert (t["position"], t["health"]) == ("returning", "ok")
    assert await balance(db, AARAV) == before
    assert (await integrity_report(db))["ok"]


async def test_duplicate_callback_credits_only_once(client: AsyncClient, db: AsyncSession) -> None:
    ravi_before = await balance(db, RAVI)
    t = await tracker(client, (await pay(client, 250_00, "duplicate_callback"))["id"])
    assert t["payment"]["state"] == "credited"
    assert await balance(db, RAVI) == ravi_before + 250_00  # not 500
    last = t["payment"]["events"][-1]
    assert last["kind"] == "note" and last["reason"].startswith("Duplicate confirmation")
    assert (await integrity_report(db))["ok"]


async def _accept(db: AsyncSession, clock: Clock, fault: str | None) -> uuid.UUID:
    aarav = await db.scalar(select(User).where(User.username == "aarav"))
    assert aarav is not None
    p = await payments.accept_payment(
        db,
        payer_user_id=aarav.id,
        payee_vpa=RAVI,
        amount_paise=300_00,
        note=None,
        at=await clock.now(db),
        fault=fault,
    )
    await db.commit()
    return p.id


async def _state(maker: async_sessionmaker[AsyncSession], payment_id: uuid.UUID) -> str:
    async with maker() as s:
        state = await s.scalar(select(Payment.state).where(Payment.id == payment_id))
        assert state is not None
        return state


async def test_bank_killed_mid_flight(
    db: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The demo story: the payment is in flight (slow bank), the admin kills the payee's
    bank, and when the bank's turn comes the payment is honestly stuck."""
    monkeypatch.setattr(switch, "SLOW_RESPONSE_SECONDS", 1.0)
    payment_id = await _accept(db, clock, "slow_response")

    task = asyncio.create_task(switch.run_payment(session_factory, clock, payment_id))
    for _ in range(50):  # wait until the switch has it
        if await _state(session_factory, payment_id) == PaymentState.IN_SWITCH:
            break
        await asyncio.sleep(0.02)
    await set_bank(db, "SURAKSHA", is_down=True)  # kill the bank mid-flight
    await task

    assert await _state(session_factory, payment_id) == PaymentState.IN_SWITCH
    assert await balance(db, SUSPENSE_VPA) == 300_00


async def test_slow_response_eventually_credits(
    db: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(switch, "SLOW_RESPONSE_SECONDS", 0.2)
    payment_id = await _accept(db, clock, "slow_response")
    await switch.run_payment(session_factory, clock, payment_id)
    assert await _state(session_factory, payment_id) == PaymentState.CREDITED


async def test_refund_waits_while_payer_bank_is_down(
    db: AsyncSession, session_factory: async_sessionmaker[AsyncSession], clock: Clock
) -> None:
    before = await balance(db, AARAV)
    payment_id = await _accept(db, clock, "timeout")
    await set_bank(db, "JHATPAT", is_down=True)  # payer's bank dies after debiting
    await switch.run_payment(session_factory, clock, payment_id)
    assert await _state(session_factory, payment_id) == PaymentState.REVERSAL_PENDING
    assert await balance(db, AARAV) == before - 300_00

    await set_bank(db, "JHATPAT", is_down=False)
    await switch.refund(session_factory, clock, payment_id)
    assert await _state(session_factory, payment_id) == PaymentState.REVERSED
    assert await balance(db, AARAV) == before
    # Retrying a finished refund is a harmless no-op.
    await switch.refund(session_factory, clock, payment_id)
    assert await balance(db, AARAV) == before


# --- Chaos API -------------------------------------------------------------------------


async def test_chaos_api_is_admin_only(client: AsyncClient) -> None:
    aarav = await auth(client, "aarav")
    assert (await client.get("/admin/chaos/banks", headers=aarav)).status_code == 403
    assert (
        await client.put("/admin/chaos/banks/SURAKSHA", json={"is_down": True}, headers=aarav)
    ).status_code == 403


async def test_bank_level_fault_set_clear_and_reset(client: AsyncClient) -> None:
    admin = await auth(client, "admin")
    resp = await client.put(
        "/admin/chaos/banks/suraksha", json={"fault": "debited_not_credited"}, headers=admin
    )
    assert resp.status_code == 200 and resp.json()["fault"] == "debited_not_credited"
    assert (await tracker(client, (await pay(client))["id"]))["payment"]["state"] == "in_switch"

    # Sending only is_down leaves the fault alone; "fault": null clears it.
    resp = await client.put("/admin/chaos/banks/SURAKSHA", json={"is_down": True}, headers=admin)
    assert resp.json()["fault"] == "debited_not_credited" and resp.json()["is_down"] is True
    resp = await client.put("/admin/chaos/banks/SURAKSHA", json={"fault": None}, headers=admin)
    assert resp.json()["fault"] is None

    banks = (await client.post("/admin/chaos/reset", headers=admin)).json()
    assert all(not b["is_down"] and b["fault"] is None for b in banks)
    assert (await tracker(client, (await pay(client))["id"]))["payment"]["state"] == "credited"


async def test_admin_resolves_stuck_payment(client: AsyncClient, db: AsyncSession) -> None:
    admin = await auth(client, "admin")
    ravi_before = await balance(db, RAVI)
    stuck = await pay(client, 250_00, "debited_not_credited")
    url = f"/admin/payments/{stuck['id']}/resolve"

    resp = await client.post(url, json={"outcome": "credit"}, headers=admin)
    assert resp.status_code == 200 and resp.json()["state"] == "credited"
    assert await balance(db, RAVI) == ravi_before + 250_00
    # Can't settle it twice.
    assert (await client.post(url, json={"outcome": "reverse"}, headers=admin)).status_code == 409

    aarav_before = await balance(db, AARAV)
    stuck2 = await pay(client, 100_00, "debited_not_credited")
    resp = await client.post(
        f"/admin/payments/{stuck2['id']}/resolve", json={"outcome": "reverse"}, headers=admin
    )
    assert resp.json()["state"] == "reversed"
    assert await balance(db, AARAV) == aarav_before
    assert (await integrity_report(db))["ok"]
