
# filename: app/services/notifications.py
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.models import Notification, Company

async def notify(session: AsyncSession, user_id: int, kind: str, message: str) -> None:
    n = Notification(user_id=user_id, kind=kind, message=message)
    session.add(n)
    await session.commit()

async def alert_on_drop(session: AsyncSession, company_id: int, old_rating: float | None, new_rating: float | None, user_id: int):
    if old_rating is None or new_rating is None:
        return
    if new_rating <= old_rating - 0.5:
        await notify(session, user_id, 'rating_drop', f'Rating dropped from {old_rating:.2f} to {new_rating:.2f}')
