"""Unit tests for the per-bot analytics service."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from arcana.database.engine import Base
from arcana.database.models import Bot, User
from arcana.services import bot_analytics, subscribers


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
async def test_record_event_validates_kind(session_factory) -> None:
    async with session_factory() as s:
        with pytest.raises(ValueError):
            await bot_analytics.record_event(
                s, bot_id="bot-A", kind="bogus", name="x"
            )


@pytest.mark.asyncio
async def test_record_event_rejects_empty_name(session_factory) -> None:
    async with session_factory() as s:
        with pytest.raises(ValueError):
            await bot_analytics.record_event(
                s, bot_id="bot-A", kind="command", name=""
            )


@pytest.mark.asyncio
async def test_top_commands_orders_by_count(session_factory) -> None:
    async with session_factory() as s:
        for name in ("/start", "/start", "/start", "/help", "/help", "/info"):
            await bot_analytics.record_event(
                s, bot_id="bot-A", kind="command", name=name
            )
        await s.commit()
        rows = await bot_analytics.top_commands(s, bot_id="bot-A", limit=2)
    assert [(r.name, r.count) for r in rows] == [("/start", 3), ("/help", 2)]


@pytest.mark.asyncio
async def test_top_buttons_independent_of_commands(session_factory) -> None:
    async with session_factory() as s:
        await bot_analytics.record_event(
            s, bot_id="bot-A", kind="command", name="/start"
        )
        await bot_analytics.record_event(
            s, bot_id="bot-A", kind="button", name="menu:help"
        )
        await bot_analytics.record_event(
            s, bot_id="bot-A", kind="button", name="menu:help"
        )
        await s.commit()
        btns = await bot_analytics.top_buttons(s, bot_id="bot-A", limit=5)
    assert [(b.name, b.count) for b in btns] == [("menu:help", 2)]


@pytest.mark.asyncio
async def test_dropoff_funnel_zero_when_no_subs(session_factory) -> None:
    async with session_factory() as s:
        funnel = await bot_analytics.dropoff_funnel(s, bot_id="bot-A")
    assert funnel.subscribers == 0 and funnel.dropoff_pct == 0.0


@pytest.mark.asyncio
async def test_dropoff_funnel_counts_engagement(session_factory) -> None:
    async with session_factory() as s:
        for uid in ("1", "2", "3", "4"):
            await subscribers.register_subscriber(
                s, bot_id="bot-A", tg_user_id=uid
            )
        # Only "1" engages.
        await bot_analytics.record_event(
            s, bot_id="bot-A", kind="command", name="/start", tg_user_id="1"
        )
        await s.commit()
        funnel = await bot_analytics.dropoff_funnel(s, bot_id="bot-A")
    assert funnel.subscribers == 4
    assert funnel.engaged == 1
    assert 70.0 < funnel.dropoff_pct <= 75.0


@pytest.mark.asyncio
async def test_suggestions_no_subscribers_hint(session_factory) -> None:
    async with session_factory() as s:
        tips = await bot_analytics.suggestions(s, bot_id="bot-A")
    assert any("share" in t.lower() for t in tips)


@pytest.mark.asyncio
async def test_suggestions_high_dropoff_hint(session_factory) -> None:
    async with session_factory() as s:
        for uid in map(str, range(20)):
            await subscribers.register_subscriber(
                s, bot_id="bot-A", tg_user_id=uid
            )
        await s.commit()
        tips = await bot_analytics.suggestions(s, bot_id="bot-A")
    assert any("never used" in t.lower() or "/start" in t for t in tips)
