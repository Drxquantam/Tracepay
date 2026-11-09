"""Admin tools: the one-click demo story, and the payments-needing-attention list."""

import pytest
from httpx import AsyncClient

from app import demo, switch
from tests.conftest import auth, new_key

pytestmark = pytest.mark.usefixtures("seeded")


@pytest.fixture(autouse=True)
def fast_story(monkeypatch: pytest.MonkeyPatch) -> None:
    # Same story, shorter pauses: the bank dies while the payee's bank is "thinking".
    monkeypatch.setattr(switch, "SLOW_RESPONSE_SECONDS", 0.6)
    monkeypatch.setattr(demo, "KILL_BANK_AFTER_SECONDS", 0.2)
    monkeypatch.setattr(demo, "PAUSE_BEFORE_TIME_JUMP_SECONDS", 0.0)


async def test_demo_story_ends_in_a_dispute_with_compensation(client: AsyncClient) -> None:
    admin = await auth(client, "admin")
    # The client fixture waits for spawned work, so the whole story has played out by the
    # time this returns.
    resp = await client.post("/admin/demo", headers=admin)
    assert resp.status_code == 200
    payment_id = resp.json()["payment_id"]

    t = (
        await client.get(f"/payments/{payment_id}/tracker", headers=await auth(client, "aarav"))
    ).json()
    assert t["payment"]["state"] == "in_switch"  # honestly stuck, never faked as done
    assert "Suraksha Bank is not responding" in " ".join(
        e["reason"] or "" for e in t["payment"]["events"]
    )
    assert t["health"] == "late"
    d = t["dispute"]
    assert d["headline"] == "Your bank is 3 days late: ₹300 owed"
    assert d["owed_by_bank"] == "SwissBank"
    assert "not by Ravi General Store" in d["who_owes"]

    integrity = (await client.get("/admin/ledger/integrity", headers=admin)).json()
    assert integrity["ok"] and integrity["suspense_balance_paise"] == 450_00


async def test_demo_and_admin_lists_are_admin_only(client: AsyncClient) -> None:
    aarav = await auth(client, "aarav")
    assert (await client.post("/admin/demo", headers=aarav)).status_code == 403
    assert (await client.get("/admin/payments", headers=aarav)).status_code == 403


async def test_attention_list_shows_unsettled_payments_only(client: AsyncClient) -> None:
    headers = await auth(client, "aarav")
    stuck = await client.post(
        "/payments",
        json={
            "payee_vpa": "ravistore@suraksha",
            "amount_paise": 100_00,
            "simulate_fault": "debited_not_credited",
        },
        headers={**headers, "Idempotency-Key": new_key()},
    )
    await client.post(
        "/payments",
        json={"payee_vpa": "ravistore@suraksha", "amount_paise": 100_00},
        headers={**headers, "Idempotency-Key": new_key()},
    )
    listed = (await client.get("/admin/payments", headers=await auth(client, "admin"))).json()
    assert [p["id"] for p in listed] == [stuck.json()["id"]]
