"""Subscriber bookkeeping for planted bots.

A subscriber is a Telegram user who has interacted with a planted bot
(typically by tapping ``/start``). The platform keeps a row per
``(bot_id, tg_user_id)`` so the bot owner can see growth, run
broadcasts, and reason about churn — all without the planted bot
having to manage its own database.

Every helper here is idempotent: planted bots can re-register the same
subscriber on every interaction without inflating counts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NamedTuple

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from arcana.database.models import BotSubscriber


class SubscriberStats(NamedTuple):
    """Aggregated counts for a single bot."""

    total: int
    active: int  # not blocked
    blocked: int


class RecentSubscriber(NamedTuple):
    """A row returned by :func:`recent_subscribers`."""

    tg_user_id: str
    referrer_id: str | None
    joined_at: datetime
    is_blocked: bool


async def register_subscriber(
    session: AsyncSession,
    *,
    bot_id: str,
    tg_user_id: str,
    referrer_id: str | None = None,
) -> bool:
    """Register or refresh a subscriber. Returns ``True`` if newly created.

    The referrer is only honoured on the **first** registration — we never
    overwrite an existing referrer, so a user re-clicking a different
    invite link can't steal the original inviter's credit.
    """
    now = datetime.now(UTC)
    existing = await session.get(BotSubscriber, (bot_id, str(tg_user_id)))
    if existing is not None:
        existing.last_seen_at = now
        existing.is_blocked = False
        await session.flush()
        return False

    sub = BotSubscriber(
        bot_id=bot_id,
        tg_user_id=str(tg_user_id),
        referrer_id=str(referrer_id) if referrer_id is not None else None,
        joined_at=now,
        last_seen_at=now,
        is_blocked=False,
    )
    session.add(sub)
    await session.flush()
    return True


async def mark_blocked(
    session: AsyncSession, *, bot_id: str, tg_user_id: str
) -> bool:
    """Flag a subscriber as having blocked / removed the bot."""
    sub = await session.get(BotSubscriber, (bot_id, str(tg_user_id)))
    if sub is None:
        return False
    sub.is_blocked = True
    await session.flush()
    return True


async def unregister_subscriber(
    session: AsyncSession, *, bot_id: str, tg_user_id: str
) -> bool:
    """Hard-delete a subscriber (used when the user opts out explicitly)."""
    sub = await session.get(BotSubscriber, (bot_id, str(tg_user_id)))
    if sub is None:
        return False
    await session.delete(sub)
    await session.flush()
    return True


async def stats(session: AsyncSession, *, bot_id: str) -> SubscriberStats:
    """Return total / active / blocked counts for a bot."""
    total_q = select(func.count()).select_from(BotSubscriber).where(
        BotSubscriber.bot_id == bot_id
    )
    blocked_q = select(func.count()).select_from(BotSubscriber).where(
        BotSubscriber.bot_id == bot_id, BotSubscriber.is_blocked.is_(True)
    )
    total = (await session.execute(total_q)).scalar_one()
    blocked = (await session.execute(blocked_q)).scalar_one()
    return SubscriberStats(total=total, active=total - blocked, blocked=blocked)


async def recent_subscribers(
    session: AsyncSession, *, bot_id: str, limit: int = 10
) -> list[RecentSubscriber]:
    """Return the most-recently-joined subscribers, newest first."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    q = (
        select(BotSubscriber)
        .where(BotSubscriber.bot_id == bot_id)
        .order_by(desc(BotSubscriber.joined_at))
        .limit(limit)
    )
    rows = (await session.execute(q)).scalars().all()
    return [
        RecentSubscriber(
            tg_user_id=r.tg_user_id,
            referrer_id=r.referrer_id,
            joined_at=r.joined_at,
            is_blocked=r.is_blocked,
        )
        for r in rows
    ]


async def iter_active_subscribers(
    session: AsyncSession, *, bot_id: str
):
    """Async iterator of (still-active) Telegram user-ids for broadcasts."""
    q = (
        select(BotSubscriber.tg_user_id)
        .where(
            BotSubscriber.bot_id == bot_id,
            BotSubscriber.is_blocked.is_(False),
        )
    )
    result = await session.execute(q)
    for row in result.scalars().all():
        yield row
