"""Payment flow: API happy path, declines, validation, access control, and reversals."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import payments
from app.clock import Clock
from app.ledger import SUSPENSE_VPA, integrity_report
from app.models import Account, LedgerEntry, User
from app.state_machine import InvalidTransition, PaymentState
from tests.conftest import auth, balance, new_key

pytestmark = pytest.mark.usefixtures("seeded")

AARAV, RAVI, SHANTI = "aarav@swissbank", "ravistore@suraksha", "shanti@suraksha"


async def pay(client: AsyncClient, headers: dict, payee: str, amount: int, **extra):  # type: ignore[no-untyped-def]
    return await client.post(
        "/payments",
        json={"payee_vpa": payee, "amount_paise": amount, **extra},
        headers={**headers, "Idempotency-Key": new_key()},
    )


async def test_happy_path_moves_money_and_logs_every_step(
    client: AsyncClient, db: AsyncSession
) -> None:
    aarav_before, ravi_before = await balance(db, AARAV), await balance(db, RAVI)
    headers = await auth(client, "aarav")

    resp = await pay(client, headers, RAVI, 150_00, note="Milk and bread")
    assert resp.status_code == 201, resp.text
    created = resp.json()
    # The response is the state at acceptance; processing continues in the background.
    assert created["state"] == "bank_debited"
    assert created["payee_name"] == "Ravi General Store"
    assert len(created["reference"]) == 12

    detail = (await client.get(f"/payments/{created['id']}", headers=headers)).json()
    assert detail["state"] == "credited"
    assert [e["to_state"] for e in detail["events"]] == [
        "initiated",
        "bank_debited",
        "in_switch",
        "credited",
    ]
    assert await balance(db, AARAV) == aarav_before - 150_00
    assert await balance(db, RAVI) == ravi_before + 150_00
    assert await balance(db, SUSPENSE_VPA) == 0  # nothing left in flight
    assert (await integrity_report(db))["ok"]


async def test_not_enough_balance_creates_failed_payment_without_moving_money(
    client: AsyncClient, db: AsyncSession
) -> None:
    before = await balance(db, AARAV)
    resp = await pay(client, await auth(client, "aarav"), RAVI, before + 1)
    assert resp.status_code == 201
    body = resp.json()
    assert body["state"] == "failed"
    assert body["failure_reason"] == "Not enough balance in your account"
    assert await balance(db, AARAV) == before
    ledger_rows = await db.scalar(
        select(func.count()).select_from(LedgerEntry).where(LedgerEntry.payment_id == body["id"])
    )
    assert ledger_rows == 0


async def test_frozen_account_cannot_pay(client: AsyncClient, db: AsyncSession) -> None:
    await db.execute(update(Account).where(Account.vpa == AARAV).values(is_frozen=True))
    await db.commit()
    before = await balance(db, AARAV)
    resp = await pay(client, await auth(client, "aarav"), RAVI, 10_00)
    assert resp.json()["state"] == "failed"
    assert "frozen" in resp.json()["failure_reason"]
    assert await balance(db, AARAV) == before


@pytest.mark.parametrize(
    ("payee", "amount", "status"),
    [
        ("nobody@nowhere", 100, 404),  # unknown UPI ID
        (SUSPENSE_VPA, 100, 404),  # internal system accounts can't be paid
        (AARAV, 100, 400),  # paying yourself
        (RAVI, 1_00_000 * 100 + 1, 422),  # above the per-payment UPI limit
        (RAVI, 0, 422),  # amount must be positive
        (RAVI, -500, 422),
    ],
)
async def test_invalid_requests_are_rejected(
    client: AsyncClient, db: AsyncSession, payee: str, amount: int, status: int
) -> None:
    before = await balance(db, AARAV)
    resp = await pay(client, await auth(client, "aarav"), payee, amount)
    assert resp.status_code == status, resp.text
    assert await balance(db, AARAV) == before


async def test_idempotency_key_header_is_required(client: AsyncClient) -> None:
    resp = await client.post(
        "/payments",
        json={"payee_vpa": RAVI, "amount_paise": 100},
        headers=await auth(client, "aarav"),
    )
    assert resp.status_code == 400


async def test_only_people_involved_can_see_a_payment(client: AsyncClient) -> None:
    created = (await pay(client, await auth(client, "aarav"), RAVI, 5_00)).json()
    url = f"/payments/{created['id']}"
    assert (await client.get(url, headers=await auth(client, "aarav"))).status_code == 200
    assert (await client.get(url, headers=await auth(client, "ravi"))).status_code == 200  # payee
    assert (await client.get(url, headers=await auth(client, "admin"))).status_code == 200
    assert (await client.get(url, headers=await auth(client, "shanti"))).status_code == 404


async def test_list_shows_sent_and_received_payments(client: AsyncClient) -> None:
    created = (await pay(client, await auth(client, "aarav"), RAVI, 5_00)).json()
    for user in ("aarav", "ravi"):
        ids = [
            p["id"]
            for p in (await client.get("/payments", headers=await auth(client, user))).json()
        ]
        assert created["id"] in ids
    shanti_ids = [
        p["id"]
        for p in (await client.get("/payments", headers=await auth(client, "shanti"))).json()
    ]
    assert created["id"] not in shanti_ids


# --- Failure and reversal, driven through the service directly (Phase 3 adds the mock
# --- switch that triggers these on its own).


async def _aarav(db: AsyncSession) -> User:
    user = await db.scalar(select(User).where(User.username == "aarav"))
    assert user is not None
    return user


async def test_failure_after_debit_starts_and_completes_a_refund(
    db: AsyncSession, frozen_clock: Clock
) -> None:
    before = await balance(db, AARAV)
    at = await frozen_clock.now(db)
    p = await payments.accept_payment(
        db,
        payer_user_id=(await _aarav(db)).id,
        payee_vpa=RAVI,
        amount_paise=200_00,
        note=None,
        at=at,
    )
    await db.commit()
    await payments.send_to_switch(db, p.id, at)
    await db.commit()
    assert await balance(db, AARAV) == before - 200_00
    assert await balance(db, SUSPENSE_VPA) == 200_00  # money in flight, visibly
    assert (await integrity_report(db))["ok"]

    p = await payments.fail_payment(db, p.id, at, "Payee bank timed out")
    await db.commit()
    assert p.state == PaymentState.REVERSAL_PENDING
    assert (await integrity_report(db))["ok"]  # still in suspense, still accounted for

    p = await payments.complete_reversal(db, p.id, at)
    await db.commit()
    assert p.state == PaymentState.REVERSED
    assert await balance(db, AARAV) == before
    assert await balance(db, SUSPENSE_VPA) == 0
    assert (await integrity_report(db))["ok"]

    # A second refund attempt is refused, and no money moves.
    with pytest.raises(InvalidTransition):
        await payments.complete_reversal(db, p.id, at)
    await db.rollback()
    assert await balance(db, AARAV) == before


async def test_payee_cannot_be_credited_twice(db: AsyncSession, frozen_clock: Clock) -> None:
    at = await frozen_clock.now(db)
    p = await payments.accept_payment(
        db,
        payer_user_id=(await _aarav(db)).id,
        payee_vpa=RAVI,
        amount_paise=10_00,
        note=None,
        at=at,
    )
    await payments.send_to_switch(db, p.id, at)
    await payments.credit_payee(db, p.id, at)
    await db.commit()
    ravi_after = await balance(db, RAVI)
    with pytest.raises(InvalidTransition):
        await payments.credit_payee(db, p.id, at)
    await db.rollback()
    assert await balance(db, RAVI) == ravi_after


async def test_failure_before_debit_needs_no_refund(db: AsyncSession, frozen_clock: Clock) -> None:
    """A payment failed straight from `initiated` never took money, so no reversal."""
    at = await frozen_clock.now(db)
    p = await payments.accept_payment(
        db,
        payer_user_id=(await _aarav(db)).id,
        payee_vpa=RAVI,
        amount_paise=9_000_00,
        note=None,
        at=at,
    )  # > ₹8,450 balance
    assert p.state == PaymentState.FAILED
    with pytest.raises(InvalidTransition):
        await payments.complete_reversal(db, p.id, at)


async def test_payee_directory_excludes_self_and_system_accounts(client: AsyncClient) -> None:
    payees = (await client.get("/payees", headers=await auth(client, "aarav"))).json()
    vpas = [p["vpa"] for p in payees]
    assert AARAV not in vpas  # not yourself
    assert not any(v.endswith("@tracepay") for v in vpas)  # no internal accounts
    assert {SHANTI, RAVI, "streamflix@suraksha"} <= set(vpas)
    # People are listed before shops.
    kinds = [p["kind"] for p in payees]
    assert kinds == sorted(kinds, key=lambda k: k != "user")
    shanti = next(p for p in payees if p["vpa"] == SHANTI)
    assert shanti == {
        "vpa": SHANTI,
        "name": "Shanti Mehta",
        "kind": "user",
        "bank_name": "Suraksha Bank",
    }


async def test_payment_shows_both_names(client: AsyncClient) -> None:
    created = (await pay(client, await auth(client, "aarav"), RAVI, 5_00)).json()
    assert (created["payer_name"], created["payee_name"]) == ("Aarav Mehta", "Ravi General Store")
