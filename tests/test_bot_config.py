"""Unit tests for the per-bot configuration store."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from arcana.database.engine import Base
from arcana.database.models import Bot, User
from arcana.services import bot_config


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
async def test_get_lang_falls_back_to_default(session_factory) -> None:
    async with session_factory() as s:
        assert await bot_config.get_lang(s, bot_id="bot-A") == bot_config.DEFAULT_LANG


@pytest.mark.asyncio
async def test_set_lang_persists_and_normalizes(session_factory) -> None:
    async with session_factory() as s:
        applied = await bot_config.set_lang(s, bot_id="bot-A", lang="  EN  ")
        await s.commit()
    assert applied == "en"
    async with session_factory() as s:
        assert await bot_config.get_lang(s, bot_id="bot-A") == "en"


@pytest.mark.asyncio
async def test_set_lang_rejects_unknown_codes(session_factory) -> None:
    async with session_factory() as s:
        with pytest.raises(bot_config.InvalidConfigValue):
            await bot_config.set_lang(s, bot_id="bot-A", lang="zz")


@pytest.mark.asyncio
async def test_generic_get_set_round_trip(session_factory) -> None:
    async with session_factory() as s:
        await bot_config.set_(s, bot_id="bot-A", key="welcome", value="hi")
        await s.commit()
        assert await bot_config.get(s, bot_id="bot-A", key="welcome") == "hi"
        assert (
            await bot_config.get(s, bot_id="bot-A", key="missing", default="?")
            == "?"
        )


@pytest.mark.asyncio
async def test_all_for_bot_returns_dict(session_factory) -> None:
    async with session_factory() as s:
        await bot_config.set_lang(s, bot_id="bot-A", lang="fr")
        await bot_config.set_(s, bot_id="bot-A", key="welcome", value="bonjour")
        await s.commit()
        snap = await bot_config.all_for_bot(s, bot_id="bot-A")
    assert snap[bot_config.KEY_LANG] == "fr"
    assert snap["welcome"] == "bonjour"
