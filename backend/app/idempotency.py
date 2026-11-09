"""Idempotency keys: a retried payment request must never move money twice.

Phones lose signal. A user taps Pay, the request reaches us, but the response never makes
it back. The app retries. Without protection, that's two payments. With an
`Idempotency-Key` header (a random id the client makes once per payment *attempt*), a
retry gets the first attempt's saved response instead.

How it works, inside the same DB transaction as the payment itself:
1. INSERT the key ... ON CONFLICT DO NOTHING.
   - If the insert succeeds, this request owns the key and does the work.
   - If an identical request is in progress right now, Postgres makes our insert *wait*
     on the unique index until that transaction ends. Then:
       * it committed: the insert does nothing and we replay its saved response;
       * it rolled back (e.g. a validation error): our insert succeeds and we do the work.
2. Same key with a *different* body is a client bug. We return 409 instead of guessing.
Because the key row and the payment commit together, no window exists where the money
moved but the key wasn't saved, or the other way round.
"""

import hashlib
import json

from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IdempotencyKey


def hash_request(body: BaseModel) -> str:
    # Hash the *parsed* body with sorted keys, so whitespace or key order in the raw JSON
    # doesn't make an identical retry look different.
    canonical = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


async def claim_key(
    db: AsyncSession, user_id: int, key: str, request_hash: str
) -> IdempotencyKey | None:
    """Return None if this request now owns the key, or the existing record if the key was
    already used (by this user; keys are scoped per user)."""
    claimed = await db.scalar(
        insert(IdempotencyKey)
        .values(user_id=user_id, key=key, request_hash=request_hash)
        .on_conflict_do_nothing(index_elements=["user_id", "key"])
        .returning(IdempotencyKey.key)
    )
    if claimed is not None:
        return None
    return await db.get(IdempotencyKey, (user_id, key), populate_existing=True)


async def save_response(
    db: AsyncSession, user_id: int, key: str, status_code: int, body: dict
) -> None:
    await db.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
        .values(status_code=status_code, response_body=body)
    )
