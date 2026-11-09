"""Guardian mode: Shanti's payments are protected; Aarav is her trusted person.

Seeded rules for Shanti: approval for ₹10,000+ and for first-time payees, and a 30-minute
cooling-off for ₹25,000+. She has paid Aarav before, but never Ravi's shop.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.ledger import integrity_report
from tests.conftest import auth, balance, new_key

pytestmark = pytest.mark.usefixtures("seeded")

SHANTI, AARAV, RAVI = "shanti@suraksha", "aarav@swissbank", "ravistore@suraksha"
MIN = 60


@pytest.fixture
def clock(frozen_clock: Clock) -> Clock:
    return frozen_clock


async def pay(client: AsyncClient, payee: str, amount: int, user: str = "shanti") -> dict:
    resp = await client.post(
        "/payments",
        json={"payee_vpa": payee, "amount_paise": amount},
        headers={**await auth(client, user), "Idempotency-Key": new_key()},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def holds(client: AsyncClient, user: str) -> dict:
    return (await client.get("/guardian/holds", headers=await auth(client, user))).json()


async def act(client: AsyncClient, user: str, hold_id: int, action: str):  # type: ignore[no-untyped-def]
    return await client.post(
        f"/guardian/holds/{hold_id}/{action}", headers=await auth(client, user)
    )


async def jump(client: AsyncClient, seconds: int) -> None:
    resp = await client.post(
        "/admin/clock/advance", json={"seconds": seconds}, headers=await auth(client, "admin")
    )
    assert resp.status_code == 200


async def state_of(client: AsyncClient, payment_id: str, user: str = "shanti") -> dict:
    return (
        await client.get(f"/payments/{payment_id}/tracker", headers=await auth(client, user))
    ).json()


async def test_small_payment_to_known_person_is_not_held(client: AsyncClient) -> None:
    assert (await pay(client, AARAV, 500_00))["state"] == "bank_debited"


async def test_first_payment_to_new_payee_needs_approval_and_moves_no_money(
    client: AsyncClient, db: AsyncSession
) -> None:
    before = await balance(db, SHANTI)
    p = await pay(client, RAVI, 200_00)
    assert p["state"] == "held"
    assert await balance(db, SHANTI) == before  # nothing debited while held

    t = await state_of(client, p["id"])
    assert t["headline"] == "Waiting for Aarav Mehta's approval"
    assert (t["position"], t["health"]) == ("payer_bank", "delayed")
    assert t["hold"]["kind"] == "approval"
    assert "first payment to Ravi General Store" in t["hold"]["reasons"]
    assert t["rule"] is None  # no money in flight, so no turnaround deadline yet

    [request] = (await holds(client, "aarav"))["to_decide"]
    assert (request["payer_name"], request["amount_paise"]) == ("Shanti Mehta", 200_00)
    assert (await holds(client, "shanti"))["mine"][0]["id"] == request["id"]
    assert (await integrity_report(db))["ok"]


async def test_amount_threshold_needs_approval(client: AsyncClient) -> None:
    p = await pay(client, AARAV, 10_000_00)
    t = await state_of(client, p["id"])
    assert p["state"] == "held" and "₹10,000 or more" in t["hold"]["reasons"]


async def test_approval_sends_the_payment(client: AsyncClient, db: AsyncSession) -> None:
    shanti_before, ravi_before = await balance(db, SHANTI), await balance(db, RAVI)
    p = await pay(client, RAVI, 200_00)
    hold_id = (await holds(client, "aarav"))["to_decide"][0]["id"]

    resp = await act(client, "aarav", hold_id, "approve")
    assert resp.status_code == 200 and resp.json()["state"] == "bank_debited"
    t = await state_of(client, p["id"])
    assert t["payment"]["state"] == "credited"
    assert [e["to_state"] for e in t["payment"]["events"]][:3] == [
        "initiated",
        "held",
        "bank_debited",
    ]
    assert await balance(db, SHANTI) == shanti_before - 200_00
    assert await balance(db, RAVI) == ravi_before + 200_00
    assert (await holds(client, "aarav"))["to_decide"] == []
    # Deciding twice is refused.
    assert (await act(client, "aarav", hold_id, "deny")).status_code == 409


async def test_denial_stops_the_payment(client: AsyncClient, db: AsyncSession) -> None:
    before = await balance(db, SHANTI)
    p = await pay(client, RAVI, 200_00)
    hold_id = (await holds(client, "aarav"))["to_decide"][0]["id"]
    assert (await act(client, "aarav", hold_id, "deny")).json()["state"] == "failed"
    t = await state_of(client, p["id"])
    assert t["payment"]["failure_reason"] == "Stopped by Aarav Mehta"
    assert await balance(db, SHANTI) == before


async def test_only_the_trusted_person_can_decide(client: AsyncClient) -> None:
    await pay(client, RAVI, 200_00)
    hold_id = (await holds(client, "aarav"))["to_decide"][0]["id"]
    for user in ("shanti", "ravi"):  # not even the payer can approve their own hold
        assert (await act(client, user, hold_id, "approve")).status_code == 404


async def test_unanswered_request_expires(client: AsyncClient, db: AsyncSession) -> None:
    before = await balance(db, SHANTI)
    p = await pay(client, RAVI, 200_00)
    await jump(client, 59 * MIN)
    assert (await state_of(client, p["id"]))["payment"]["state"] == "held"
    await jump(client, 2 * MIN)  # past the 60-minute window
    t = await state_of(client, p["id"])
    assert t["payment"]["state"] == "failed"
    assert t["payment"]["failure_reason"] == "Not approved in time"
    assert await balance(db, SHANTI) == before


async def _cooling_only(client: AsyncClient) -> None:
    resp = await client.put(
        "/guardian/settings",
        json={
            "guardian_username": "aarav",
            "threshold_paise": None,
            "new_payee_approval": False,
            "cooling_off_threshold_paise": 25_000_00,
            "cooling_off_minutes": 30,
        },
        headers=await auth(client, "shanti"),
    )
    assert resp.status_code == 200


async def test_cooling_off_releases_itself(client: AsyncClient, db: AsyncSession) -> None:
    await _cooling_only(client)
    aarav_before = await balance(db, AARAV)
    p = await pay(client, AARAV, 30_000_00)
    t = await state_of(client, p["id"])
    assert (p["state"], t["hold"]["kind"], t["headline"]) == (
        "held",
        "cooling_off",
        "Cooling-off pause",
    )

    await jump(client, 29 * MIN)
    assert (await state_of(client, p["id"]))["payment"]["state"] == "held"
    await jump(client, 2 * MIN)
    assert (await state_of(client, p["id"]))["payment"]["state"] == "credited"
    assert await balance(db, AARAV) == aarav_before + 30_000_00


async def test_payer_can_cancel_during_cooling_off(client: AsyncClient, db: AsyncSession) -> None:
    await _cooling_only(client)
    before = await balance(db, SHANTI)
    p = await pay(client, AARAV, 30_000_00)
    hold_id = (await holds(client, "shanti"))["mine"][0]["id"]
    assert (await act(client, "aarav", hold_id, "cancel")).status_code == 404  # payer only
    assert (await act(client, "shanti", hold_id, "cancel")).json()["state"] == "failed"
    await jump(client, 40 * MIN)
    t = await state_of(client, p["id"])
    assert t["payment"]["failure_reason"] == "You cancelled this payment"
    assert await balance(db, SHANTI) == before


async def test_kill_switch(client: AsyncClient, db: AsyncSession) -> None:
    aarav, shanti, ravi = [await auth(client, u) for u in ("aarav", "shanti", "ravi")]
    # A stranger can't freeze Shanti; her trusted person can.
    assert (
        await client.post("/guardian/freeze", json={"username": "shanti"}, headers=ravi)
    ).status_code == 403
    resp = await client.post("/guardian/freeze", json={"username": "shanti"}, headers=aarav)
    assert resp.json() == {"username": "shanti", "is_frozen": True}

    before = await balance(db, SHANTI)
    p = await pay(client, AARAV, 500_00)
    assert p["state"] == "failed" and "frozen" in p["failure_reason"]
    assert await balance(db, SHANTI) == before

    # Shanti can unfreeze herself.
    resp = await client.post("/guardian/unfreeze", json={}, headers=shanti)
    assert resp.json()["is_frozen"] is False
    assert (await pay(client, AARAV, 500_00))["state"] == "bank_debited"


async def test_freezing_while_held_blocks_the_release(client: AsyncClient) -> None:
    p = await pay(client, RAVI, 200_00)
    hold_id = (await holds(client, "aarav"))["to_decide"][0]["id"]
    await client.post("/guardian/freeze", json={}, headers=await auth(client, "shanti"))
    assert (await act(client, "aarav", hold_id, "approve")).json()["state"] == "failed"
    assert "frozen" in (await state_of(client, p["id"]))["payment"]["failure_reason"]


async def test_overview_and_settings_validation(client: AsyncClient) -> None:
    aarav = await auth(client, "aarav")
    await pay(client, RAVI, 200_00)
    o = (await client.get("/guardian", headers=aarav)).json()
    assert o["rules"]["guardian"] is None  # nobody guards Aarav
    assert o["protecting"] == [
        {
            "username": "shanti",
            "full_name": "Shanti Mehta",
            "is_frozen": False,
            "pending_requests": 1,
        }
    ]
    assert [c["username"] for c in o["candidates"]] == [
        "shanti"
    ]  # people only, not self/shops/admin

    s = (await client.get("/guardian", headers=await auth(client, "shanti"))).json()
    assert s["rules"]["guardian"]["username"] == "aarav"
    assert s["rules"]["threshold_paise"] == 10_000_00

    bad = await client.put("/guardian/settings", json={"guardian_username": "aarav"}, headers=aarav)
    assert bad.status_code == 400  # can't be your own trusted person


async def test_notifications_tell_both_people(client: AsyncClient) -> None:
    await pay(client, RAVI, 200_00)
    a = (await client.get("/notifications", headers=await auth(client, "aarav"))).json()
    s = (await client.get("/notifications", headers=await auth(client, "shanti"))).json()
    assert a["unread"] == 1 and a["items"][0]["kind"] == "approval_request"
    assert a["items"][0]["title"] == "Shanti Mehta wants to pay ₹200 to Ravi General Store"
    assert s["items"][0]["title"] == "Your ₹200 payment is waiting for Aarav Mehta"

    headers = await auth(client, "aarav")
    await client.post(f"/notifications/{a['items'][0]['id']}/read", headers=headers)
    assert (await client.get("/notifications", headers=headers)).json()["unread"] == 0
    # Someone else's notification can't be touched.
    resp = await client.post(f"/notifications/{s['items'][0]['id']}/read", headers=headers)
    assert resp.status_code == 404


async def test_senior_mode_preference(client: AsyncClient) -> None:
    headers = await auth(client, "aarav")
    resp = await client.patch("/auth/me", json={"senior_mode": True}, headers=headers)
    assert resp.status_code == 200 and resp.json()["senior_mode"] is True
