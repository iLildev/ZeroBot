"""Unit tests for the per-bot admin/role service."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from arcana.database.engine import Base
from arcana.database.models import Bot, User
from arcana.services import bot_admins


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
async def test_set_owner_is_idempotent(session_factory) -> None:
    async with session_factory() as s:
        await bot_admins.set_owner(s, bot_id="bot-A", tg_user_id="100")
        await bot_admins.set_owner(s, bot_id="bot-A", tg_user_id="100")
        await s.commit()
        rows = await bot_admins.list_admins(s, bot_id="bot-A")
    assert len(rows) == 1 and rows[0].role == "owner"


@pytest.mark.asyncio
async def test_only_owner_can_add_admins(session_factory) -> None:
    async with session_factory() as s:
        await bot_admins.set_owner(s, bot_id="bot-A", tg_user_id="100")
        await s.commit()
        with pytest.raises(bot_admins.PermissionDenied):
            await bot_admins.add_admin(
                s, bot_id="bot-A", tg_user_id="200", by_user_id="999"
            )


@pytest.mark.asyncio
async def test_owner_can_add_and_remove_admins(session_factory) -> None:
    async with session_factory() as s:
        await bot_admins.set_owner(s, bot_id="bot-A", tg_user_id="100")
        await bot_admins.add_admin(
            s, bot_id="bot-A", tg_user_id="200", by_user_id="100"
        )
        await s.commit()
        rows = await bot_admins.list_admins(s, bot_id="bot-A")
        assert {r.tg_user_id for r in rows} == {"100", "200"}
        # Owner should always sort before admin.
        assert rows[0].role == "owner"
        # Removing the admin works.
        assert await bot_admins.remove_admin(
            s, bot_id="bot-A", tg_user_id="200", by_user_id="100"
        )
        await s.commit()
        rows = await bot_admins.list_admins(s, bot_id="bot-A")
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_cannot_remove_the_owner(session_factory) -> None:
    async with session_factory() as s:
        await bot_admins.set_owner(s, bot_id="bot-A", tg_user_id="100")
        await s.commit()
        with pytest.raises(bot_admins.PermissionDenied):
            await bot_admins.remove_admin(
                s, bot_id="bot-A", tg_user_id="100", by_user_id="100"
            )


@pytest.mark.asyncio
async def test_require_role_raises_for_strangers(session_factory) -> None:
    async with session_factory() as s:
        await bot_admins.set_owner(s, bot_id="bot-A", tg_user_id="100")
        await s.commit()
        with pytest.raises(bot_admins.PermissionDenied):
            await bot_admins.require_role(
                s, bot_id="bot-A", tg_user_id="999", roles=("owner",)
            )
        # Owner satisfies an "owner" requirement.
        assert (
            await bot_admins.require_role(
                s, bot_id="bot-A", tg_user_id="100", roles=("owner",)
            )
            == "owner"
        )
