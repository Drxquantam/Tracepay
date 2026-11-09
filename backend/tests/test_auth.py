import pytest
from httpx import AsyncClient

from tests.conftest import login

pytestmark = pytest.mark.usefixtures("seeded")


async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "simulation": True}


async def test_login_returns_token_and_me_shows_accounts(client: AsyncClient) -> None:
    token = await login(client, "aarav")
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    me = resp.json()
    assert me["full_name"] == "Aarav Mehta"
    assert me["role"] == "customer"
    assert [a["vpa"] for a in me["accounts"]] == ["aarav@jhatpat"]
    assert me["accounts"][0]["balance_paise"] == 8_450_00
    assert me["accounts"][0]["bank_name"] == "Jhatpat Bank"


async def test_wrong_password_and_unknown_user_give_same_error(client: AsyncClient) -> None:
    wrong_pw = await client.post("/auth/login", json={"username": "aarav", "password": "nope"})
    no_user = await client.post("/auth/login", json={"username": "ghost", "password": "nope"})
    assert wrong_pw.status_code == no_user.status_code == 401
    # Identical messages: the API must not reveal which usernames exist.
    assert wrong_pw.json() == no_user.json()


@pytest.mark.parametrize("header", [None, "Bearer not-a-real-token", "Basic abc"])
async def test_me_rejects_missing_or_bad_token(client: AsyncClient, header: str | None) -> None:
    headers = {"Authorization": header} if header else {}
    resp = await client.get("/auth/me", headers=headers)
    assert resp.status_code == 401
