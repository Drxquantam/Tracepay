"""A tiny simulated UPI directory, so the pay screen can show contacts and shops."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.deps import get_current_user
from app.models import Account, AccountKind, User
from app.schemas import PayeeOut

router = APIRouter(tags=["payees"])


@router.get("/payees", response_model=list[PayeeOut])
async def list_payees(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[PayeeOut]:
    # Everyone except the platform's own system accounts and the user themself.
    accounts = await db.scalars(
        select(Account)
        .where(Account.kind != AccountKind.SYSTEM)
        .where((Account.user_id != user.id) | Account.user_id.is_(None))
        .options(selectinload(Account.bank))
        .order_by(Account.kind.desc(), Account.display_name)  # people first, then shops
    )
    return [
        PayeeOut(vpa=a.vpa, name=a.display_name, kind=a.kind, bank_name=a.bank.name)
        for a in accounts
    ]
