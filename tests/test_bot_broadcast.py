"""Unit tests for the per-bot broadcast wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from arcana.database.engine import Base
from arcana.database.models import Bot, BotEvent, BotSubscriber, User
from arcana.services import bot_broadcast, subscribers
from sqlalchemy import select


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        s.add(User(id="tg-1", is_admin=False))
        s.add(Bot(id="bot-A", user_id="tg-1", token="real-token"))
        await s.commit()
    yield sm
    await engine.dispose()


def _stub_bot_factory(send_impl):
    """Return a callable matching ``Bot(token=...)`` that returns a stub."""

    def _factory(token: str):
        bot = MagicMock()
        bot.token = token
        bot.send_message = AsyncMock(side_effect=send_impl)
        bot.session = MagicMock()
        bot.session.close = AsyncMock()
        return bot

    return _factory


@pytest.mark.asyncio
async def test_broadcast_to_subscribers_sends_to_all_active(session_factory) -> None:
    sent: list[int] = []

    async def send(uid, text, parse_mode=None):
        sent.append(uid)

    async with session_factory() as s:
        for uid in ("1", "2", "3"):
            await subscribers.register_subscriber(s, bot_id="bot-A", tg_user_id=uid)
        await subscribers.mark_blocked(s, bot_id="bot-A", tg_user_id="2")
        await s.commit()
        result = await bot_broadcast.broadcast_to_subscribers(
            s,
            bot_id="bot-A",
            text="hello",
            bot_factory=_stub_bot_factory(send),
        )
        await s.commit()
    assert sorted(sent) == [1, 3]
    assert (result.sent, result.blocked, result.failed) == (2, 0, 0)


@pytest.mark.asyncio
async def test_broadcast_marks_newly_blocked_users(session_factory) -> None:
    async def send(uid, text, parse_mode=None):
        if uid == 2:
            raise TelegramForbiddenError(method=MagicMock(), message="blocked")

    async with session_factory() as s:
        for uid in ("1", "2"):
            await subscribers.register_subscriber(s, bot_id="bot-A", tg_user_id=uid)
        await s.commit()
        result = await bot_broadcast.broadcast_to_subscribers(
            s,
            bot_id="bot-A",
            text="ping",
            bot_factory=_stub_bot_factory(send),
        )
        await s.commit()
        # Subscriber "2" should now be flagged blocked.
        sub = await s.get(BotSubscriber, ("bot-A", "2"))
    assert result.blocked == 1
    assert sub is not None and sub.is_blocked is True


@pytest.mark.asyncio
async def test_broadcast_records_event(session_factory) -> None:
    async def send(uid, text, parse_mode=None):
        pass

    async with session_factory() as s:
        await subscribers.register_subscriber(s, bot_id="bot-A", tg_user_id="1")
        await s.commit()
        await bot_broadcast.broadcast_to_subscribers(
            s,
            bot_id="bot-A",
            text="x",
            bot_factory=_stub_bot_factory(send),
        )
        await s.commit()
        events = (
            (await s.execute(select(BotEvent).where(BotEvent.kind == "broadcast")))
            .scalars()
            .all()
        )
    assert len(events) == 1
    assert events[0].name.startswith("sent=")


@pytest.mark.asyncio
async def test_broadcast_rejects_empty_text(session_factory) -> None:
    async with session_factory() as s:
        with pytest.raises(bot_broadcast.BroadcastError):
            await bot_broadcast.broadcast_to_subscribers(
                s, bot_id="bot-A", text="   ",
                bot_factory=_stub_bot_factory(lambda *a, **k: None),
            )


@pytest.mark.asyncio
async def test_broadcast_unknown_bot(session_factory) -> None:
    async with session_factory() as s:
        with pytest.raises(bot_broadcast.BroadcastError):
            await bot_broadcast.broadcast_to_subscribers(
                s, bot_id="nope", text="hi",
                bot_factory=_stub_bot_factory(lambda *a, **k: None),
            )
