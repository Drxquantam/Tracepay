"""Mandate Manager: notices 24 h ahead, debits on time, trial → paid, retries, pause,
revoke, and no double charges.

Frozen clock: "now" is 15 Jan 2026 10:00 UTC. Test mandates are set up for StreamFlix
(₹1 trial, then ₹499/month, cap ₹649) with the first debit 2 days later, on 17 Jan 10:00.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.ledger import integrity_report
from app.mandates import add_months
from tests.conftest import FROZEN_NOW, auth, balance

pytestmark = pytest.mark.usefixtures("seeded")

H = 3600
DAY = 24 * H
AARAV = "aarav@swissbank"
DUE = FROZEN_NOW + timedelta(days=2)


@pytest.fixture
def clock(frozen_clock: Clock) -> Clock:
    return frozen_clock


async def create(client: AsyncClient, **overrides: object) -> dict:
    body = {
        "merchant_vpa": "streamflix@suraksha",
        "purpose": "StreamFlix Premium",
        "amount_paise": 499_00,
        "max_amount_paise": 649_00,
        "frequency": "monthly",
        "first_debit_at": DUE.isoformat(),
        "trial_amount_paise": 1_00,
        "trial_debits": 1,
        **overrides,
    }
    resp = await client.post("/mandates", json=body, headers=await auth(client, "aarav"))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def get(client: AsyncClient, mandate_id: int) -> dict:
    mandates = (await client.get("/mandates", headers=await auth(client, "aarav"))).json()
    return next(m for m in mandates if m["id"] == mandate_id)


async def jump(client: AsyncClient, seconds: int) -> None:
    resp = await client.post(
        "/admin/clock/advance", json={"seconds": seconds}, headers=await auth(client, "admin")
    )
    assert resp.status_code == 200


async def freeze(client: AsyncClient, frozen: bool) -> None:
    await client.post(
        "/guardian/freeze" if frozen else "/guardian/unfreeze",
        json={},
        headers=await auth(client, "aarav"),
    )


def at(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(UTC)


@pytest.mark.parametrize(
    ("overrides", "status"),
    [
        ({"first_debit_at": (FROZEN_NOW + timedelta(hours=23)).isoformat()}, 422),  # < 24 h notice
        ({"max_amount_paise": 15_001_00, "amount_paise": 15_000_00}, 422),  # above e-mandate limit
        ({"amount_paise": 700_00}, 422),  # above its own cap
        ({"merchant_vpa": "shanti@suraksha"}, 404),  # mandates are for merchants only
        ({"merchant_vpa": "nobody@nowhere"}, 404),
    ],
)
async def test_create_validation(client: AsyncClient, overrides: dict, status: int) -> None:
    body = {
        "merchant_vpa": "streamflix@suraksha",
        "purpose": "x" * 3,
        "amount_paise": 499_00,
        "max_amount_paise": 649_00,
        "first_debit_at": DUE.isoformat(),
        **overrides,
    }
    resp = await client.post("/mandates", json=body, headers=await auth(client, "aarav"))
    assert resp.status_code == status, resp.text


async def test_upcoming_projection_flags_the_trial(client: AsyncClient) -> None:
    m = await create(client)
    assert [(u["amount_paise"], u["is_trial"]) for u in m["upcoming"]] == [
        (1_00, True),
        *[(499_00, False)] * 5,
    ]
    assert at(m["upcoming"][1]["due_at"]) == DUE.replace(month=2)


async def test_notice_goes_out_24_hours_before_and_moves_no_money(
    client: AsyncClient, db: AsyncSession
) -> None:
    m = await create(client)
    before = await balance(db, AARAV)
    await jump(client, 12 * H)  # 15 Jan 22:00: still more than 24 h away
    assert (await get(client, m["id"]))["debits"] == []

    await jump(client, 12 * H)  # 16 Jan 10:00: exactly 24 h before the debit
    [debit] = (await get(client, m["id"]))["debits"]
    assert (debit["status"], debit["amount_paise"], debit["is_trial"]) == ("notified", 1_00, True)
    assert at(debit["next_attempt_at"]) == DUE
    note = (await client.get("/notifications", headers=await auth(client, "aarav"))).json()
    assert note["items"][0]["title"].startswith("Pre-debit notice: ₹1 to StreamFlix (demo OTT)")
    assert "after the trial it becomes ₹499" in note["items"][0]["body"]
    assert await balance(db, AARAV) == before


async def test_trial_then_paid_debits_on_schedule(client: AsyncClient, db: AsyncSession) -> None:
    m = await create(client)
    before = await balance(db, AARAV)
    await jump(client, 2 * DAY)  # straight to 17 Jan 10:00 in one jump
    # The notice only went out now (the clock jumped straight past the window), so the
    # debit waits a full 24 h after it. That's the late-notice rule at work.
    m1 = await get(client, m["id"])
    assert m1["debits"][0]["status"] == "notified"
    await jump(client, 1 * DAY)
    m1 = await get(client, m["id"])
    first = m1["debits"][0]
    assert (first["status"], first["amount_paise"], first["attempts"]) == ("succeeded", 1_00, 1)
    payment = (
        await client.get(f"/payments/{first['payment_id']}", headers=await auth(client, "aarav"))
    ).json()
    assert payment["state"] == "credited" and payment["note"] == "AutoPay: StreamFlix Premium"
    assert at(m1["next_debit_at"]) == DUE.replace(month=2)
    assert m1["trial_debits_left"] == 0

    await jump(client, 31 * DAY)  # into the window for 17 Feb, notice sent on time
    await jump(client, 2 * DAY)
    second = (await get(client, m["id"]))["debits"][0]
    assert (second["status"], second["amount_paise"], second["is_trial"]) == (
        "succeeded",
        499_00,
        False,
    )
    assert await balance(db, AARAV) == before - 1_00 - 499_00
    assert (await integrity_report(db))["ok"]


async def _to_due(client: AsyncClient) -> None:
    """Notice exactly on time (16 Jan 10:00), then arrive at the due time (17 Jan 10:00)."""
    await jump(client, 24 * H)
    await jump(client, 24 * H)


async def test_failed_debit_retries_then_succeeds(client: AsyncClient, db: AsyncSession) -> None:
    m = await create(client)
    await freeze(client, True)
    await _to_due(client)
    d = (await get(client, m["id"]))["debits"][0]
    assert (d["status"], d["attempts"]) == ("retrying", 1)
    assert "frozen" in d["failure_reason"]
    assert at(d["next_attempt_at"]) == DUE + timedelta(hours=6)

    await freeze(client, False)
    await jump(client, 6 * H)
    d = (await get(client, m["id"]))["debits"][0]
    assert (d["status"], d["attempts"]) == ("succeeded", 2)


async def test_gives_up_after_the_retry_schedule(client: AsyncClient) -> None:
    m = await create(client)
    await freeze(client, True)
    await _to_due(client)
    await jump(client, 6 * H)
    d = (await get(client, m["id"]))["debits"][0]
    assert (d["status"], d["attempts"]) == ("retrying", 2)
    await jump(client, 24 * H)
    m1 = await get(client, m["id"])
    assert (m1["debits"][0]["status"], m1["debits"][0]["attempts"]) == ("failed", 3)
    # The mandate moves on to next month's cycle.
    assert at(m1["next_debit_at"]) == DUE.replace(month=2)
    notes = (await client.get("/notifications", headers=await auth(client, "aarav"))).json()
    assert "failed after 3 tries" in notes["items"][0]["title"]


async def test_pause_skips_and_resume_moves_forward(client: AsyncClient, db: AsyncSession) -> None:
    m = await create(client)
    await jump(client, 24 * H)  # notice sent
    headers = await auth(client, "aarav")
    assert (await client.post(f"/mandates/{m['id']}/pause", headers=headers)).json()[
        "status"
    ] == "paused"
    before = await balance(db, AARAV)
    await jump(client, 24 * H)  # due time passes while paused
    m1 = await get(client, m["id"])
    assert m1["debits"][0]["status"] == "skipped" and m1["upcoming"] == []
    assert await balance(db, AARAV) == before

    await jump(client, 40 * DAY)  # well past February's date too
    resumed = (await client.post(f"/mandates/{m['id']}/resume", headers=headers)).json()
    assert resumed["status"] == "active"
    # No catch-up: the next debit is in the future, with room for a 24-hour notice.
    now = FROZEN_NOW + timedelta(hours=48) + timedelta(days=40)
    assert at(resumed["next_debit_at"]) >= now + timedelta(hours=24)


async def test_revoke_stops_everything(client: AsyncClient, db: AsyncSession) -> None:
    m = await create(client)
    await jump(client, 24 * H)  # notice sent
    headers = await auth(client, "aarav")
    revoked = (await client.post(f"/mandates/{m['id']}/revoke", headers=headers)).json()
    assert revoked["status"] == "revoked" and revoked["next_debit_at"] is None
    assert revoked["debits"][0]["status"] == "cancelled"
    before = await balance(db, AARAV)
    await jump(client, 90 * DAY)
    assert len((await get(client, m["id"]))["debits"]) == 1
    assert await balance(db, AARAV) == before
    assert (await client.post(f"/mandates/{m['id']}/resume", headers=headers)).status_code == 409


async def test_running_the_scheduler_twice_charges_once(
    client: AsyncClient, db: AsyncSession
) -> None:
    m = await create(client, trial_amount_paise=None)
    before = await balance(db, AARAV)
    await _to_due(client)
    admin = await auth(client, "admin")
    for _ in range(3):
        await client.post("/admin/deadlines/sweep", headers=admin)
    debits = (await get(client, m["id"]))["debits"]
    assert len(debits) == 1 and debits[0]["attempts"] == 1
    assert await balance(db, AARAV) == before - 499_00


async def test_only_the_owner_can_manage_a_mandate(client: AsyncClient) -> None:
    m = await create(client)
    resp = await client.post(f"/mandates/{m['id']}/revoke", headers=await auth(client, "shanti"))
    assert resp.status_code == 404


async def test_seeded_mandates(client: AsyncClient) -> None:
    mandates = (await client.get("/mandates", headers=await auth(client, "aarav"))).json()
    assert {m["purpose"] for m in mandates} == {"StreamFlix Premium", "Hostel electricity"}
    streamflix = next(m for m in mandates if m["purpose"] == "StreamFlix Premium")
    assert (streamflix["trial_amount_paise"], streamflix["amount_paise"]) == (1_00, 499_00)


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (datetime(2026, 1, 31, tzinfo=UTC), 1, datetime(2026, 2, 28, tzinfo=UTC)),
        (datetime(2028, 1, 31, tzinfo=UTC), 1, datetime(2028, 2, 29, tzinfo=UTC)),  # leap year
        (datetime(2026, 12, 15, tzinfo=UTC), 1, datetime(2027, 1, 15, tzinfo=UTC)),
        (datetime(2026, 3, 31, tzinfo=UTC), 1, datetime(2026, 4, 30, tzinfo=UTC)),
    ],
)
def test_add_months(start: datetime, months: int, expected: datetime) -> None:
    assert add_months(start, months) == expected
