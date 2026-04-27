"""Unit tests for the smart-defaults seed run on every newly-planted bot."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from arcana.database.engine import Base
from arcana.database.models import Bot, User
from arcana.services import bot_admins, bot_config
from arcana.services.smart_defaults import seed_new_bot


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
async def test_seed_creates_owner_and_default_lang(session_factory) -> None:
    async with session_factory() as s:
        await seed_new_bot(s, bot_id="bot-A", owner_user_id="tg-99")
        await s.commit()
        role = await bot_admins.get_role(s, bot_id="bot-A", tg_user_id="99")
        lang = await bot_config.get_lang(s, bot_id="bot-A")
    assert role == "owner"
    assert lang == "en"


@pytest.mark.asyncio
async def test_seed_strips_tg_prefix_from_owner(session_factory) -> None:
    """Owner rows store the raw Telegram id (no ``tg-`` prefix)."""
    async with session_factory() as s:
        await seed_new_bot(s, bot_id="bot-A", owner_user_id="tg-12345")
        await s.commit()
        # The raw integer-ish id resolves; the prefixed form does not.
        assert (
            await bot_admins.get_role(s, bot_id="bot-A", tg_user_id="12345")
            == "owner"
        )
        assert (
            await bot_admins.get_role(s, bot_id="bot-A", tg_user_id="tg-12345")
            is None
        )


@pytest.mark.asyncio
async def test_seed_is_idempotent(session_factory) -> None:
    async with session_factory() as s:
        await seed_new_bot(s, bot_id="bot-A", owner_user_id="42")
        await seed_new_bot(s, bot_id="bot-A", owner_user_id="42")
        await s.commit()
        rows = await bot_admins.list_admins(s, bot_id="bot-A")
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_seed_honors_default_lang_argument(session_factory) -> None:
    async with session_factory() as s:
        await seed_new_bot(
            s, bot_id="bot-A", owner_user_id="42", default_lang="fr"
        )
        await s.commit()
        assert await bot_config.get_lang(s, bot_id="bot-A") == "fr"
