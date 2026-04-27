"""Unit tests for the per-bot subscriber service."""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from arcana.database.engine import Base
from arcana.database.models import Bot, User
from arcana.services import subscribers


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        s.add(User(id="tg-1", is_admin=False))
        s.add(Bot(id="bot-A", user_id="tg-1", token="t"))
        await s.commit()
    yield sm
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_returns_true_on_first_then_false(session_factory) -> None:
    async with session_factory() as s:
        assert await subscribers.register_subscriber(
            s, bot_id="bot-A", tg_user_id="42"
        )
        assert not await subscribers.register_subscriber(
            s, bot_id="bot-A", tg_user_id="42"
        )
        await s.commit()


@pytest.mark.asyncio
async def test_referrer_is_locked_in_after_first_call(session_factory) -> None:
    async with session_factory() as s:
        await subscribers.register_subscriber(
            s, bot_id="bot-A", tg_user_id="42", referrer_id="100"
        )
        # Re-register with a different ref must NOT overwrite.
        await subscribers.register_subscriber(
            s, bot_id="bot-A", tg_user_id="42", referrer_id="999"
        )
        await s.commit()
        recent = await subscribers.recent_subscribers(s, bot_id="bot-A")
    assert recent[0].referrer_id == "100"


@pytest.mark.asyncio
async def test_stats_split_active_vs_blocked(session_factory) -> None:
    async with session_factory() as s:
        for uid in ("1", "2", "3"):
            await subscribers.register_subscriber(s, bot_id="bot-A", tg_user_id=uid)
        await subscribers.mark_blocked(s, bot_id="bot-A", tg_user_id="2")
        await s.commit()
        stats = await subscribers.stats(s, bot_id="bot-A")
    assert (stats.total, stats.active, stats.blocked) == (3, 2, 1)


@pytest.mark.asyncio
async def test_recent_orders_newest_first(session_factory) -> None:
    async with session_factory() as s:
        for uid in ("1", "2", "3"):
            await subscribers.register_subscriber(s, bot_id="bot-A", tg_user_id=uid)
            # Tiny pause so joined_at differs in monotonic order.
            await asyncio.sleep(0.005)
        await s.commit()
        recent = await subscribers.recent_subscribers(s, bot_id="bot-A", limit=2)
    assert [r.tg_user_id for r in recent] == ["3", "2"]


@pytest.mark.asyncio
async def test_unregister_returns_false_on_missing(session_factory) -> None:
    async with session_factory() as s:
        assert not await subscribers.unregister_subscriber(
            s, bot_id="bot-A", tg_user_id="999"
        )


@pytest.mark.asyncio
async def test_iter_active_skips_blocked(session_factory) -> None:
    async with session_factory() as s:
        for uid in ("1", "2", "3"):
            await subscribers.register_subscriber(s, bot_id="bot-A", tg_user_id=uid)
        await subscribers.mark_blocked(s, bot_id="bot-A", tg_user_id="2")
        await s.commit()
        live = [u async for u in subscribers.iter_active_subscribers(s, bot_id="bot-A")]
    assert sorted(live) == ["1", "3"]
