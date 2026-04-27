"""Broadcast a message to a single planted bot's subscribers.

Wraps :func:`arcana.services.broadcast.broadcast_text` (which already
handles FloodWait, blocked-user detection, and per-batch sleeps) with
the per-bot data-fetching this layer needs:

1. Pull the planted bot's token from the ``bots`` table.
2. Stream the still-active subscriber ids from ``bot_subscribers``.
3. On block detection, mark the row blocked so future runs skip it.
4. Record one ``broadcast`` event into ``bot_events`` for analytics.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from arcana.database.models import Bot as BotRow
from arcana.services import bot_analytics, subscribers
from arcana.services.broadcast import BroadcastResult, broadcast_text


class BroadcastError(Exception):
    """Raised when the bot cannot be looked up or has no token."""


async def _ids(session: AsyncSession, bot_id: str) -> AsyncIterator[int]:
    """Yield active subscribers as ints (Telegram chat-ids are numeric)."""
    async for tg_id in subscribers.iter_active_subscribers(
        session, bot_id=bot_id
    ):
        try:
            yield int(tg_id)
        except (TypeError, ValueError):
            # Defensive: skip rows that somehow stored a non-numeric id.
            continue


async def broadcast_to_subscribers(
    session: AsyncSession,
    *,
    bot_id: str,
    text: str,
    parse_mode: str | None = "HTML",
    bot_factory=Bot,
) -> BroadcastResult:
    """Send ``text`` to every active subscriber of ``bot_id``.

    ``bot_factory`` is dependency-injected so tests can pass a stub
    ``Bot`` class without monkey-patching aiogram.
    """
    if not text or not text.strip():
        raise BroadcastError("broadcast text cannot be empty")

    bot_row = await session.get(BotRow, bot_id)
    if bot_row is None:
        raise BroadcastError(f"bot {bot_id!r} not found")
    if not bot_row.token:
        raise BroadcastError(f"bot {bot_id!r} has no token")

    bot = bot_factory(token=bot_row.token)

    async def _on_blocked(tg_id: int) -> None:
        await subscribers.mark_blocked(
            session, bot_id=bot_id, tg_user_id=str(tg_id)
        )

    try:
        result = await broadcast_text(
            bot,
            _ids(session, bot_id),
            text=text,
            parse_mode=parse_mode,
            on_blocked=_on_blocked,
        )
    finally:
        # Aiogram bots hold an aiohttp session that must be closed.
        close = getattr(bot, "session", None)
        if close is not None and hasattr(close, "close"):
            try:
                await close.close()
            except Exception:  # pragma: no cover - defensive
                pass

    await bot_analytics.record_event(
        session, bot_id=bot_id, kind="broadcast", name=f"sent={result.sent}"
    )
    return result
