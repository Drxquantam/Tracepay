"""Admin-only tools. Chaos controls arrive in Phase 3."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import require_admin
from app.ledger import integrity_report

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/ledger/integrity")
async def ledger_integrity(db: AsyncSession = Depends(get_db)) -> dict:
    """Proves debits and credits cancel out to zero and the cached balances are honest."""
    return await integrity_report(db)
