"""Login for seeded demo users. There is intentionally no signup flow."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.deps import get_current_user
from app.models import Account, User
from app.schemas import AccountOut, LoginRequest, MeOut, MeUpdate, TokenResponse
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await db.scalar(select(User).where(User.username == body.username))
    # Same error for "no such user" and "wrong password", so the API doesn't reveal
    # which usernames exist.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
    return TokenResponse(access_token=create_access_token(user.id, user.role))


@router.get("/me", response_model=MeOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> MeOut:
    accounts = (
        await db.scalars(
            select(Account)
            .where(Account.user_id == user.id)
            .options(selectinload(Account.bank))
            .order_by(Account.id)
        )
    ).all()
    return MeOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        senior_mode=user.senior_mode,
        accounts=[
            AccountOut(
                id=a.id,
                vpa=a.vpa,
                display_name=a.display_name,
                kind=a.kind,
                bank_code=a.bank.code,
                bank_name=a.bank.name,
                balance_paise=a.balance_paise,
                is_frozen=a.is_frozen,
            )
            for a in accounts
        ],
    )


@router.patch("/me", response_model=MeOut)
async def update_me(
    body: MeUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MeOut:
    """Preferences. Senior mode: larger text and simpler wording in the app."""
    user.senior_mode = body.senior_mode
    await db.commit()
    return await me(user, db)
