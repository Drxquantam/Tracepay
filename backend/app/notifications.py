"""Writing to the in-app notification centre. Messages are plain language: say what
happened and what, if anything, the person should do."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification


def notify(
    db: AsyncSession,
    user_id: int,
    *,
    kind: str,
    title: str,
    body: str,
    at: datetime,
    link: str | None = None,
) -> None:
    db.add(
        Notification(user_id=user_id, kind=kind, title=title, body=body, link=link, created_at=at)
    )
