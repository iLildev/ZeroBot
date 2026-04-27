"""Unit tests for the ``platform_settings`` service.

The service is the single read/write path for the ``platform_settings``
table that backs admin-tunable knobs like the custom /start welcome
message. We exercise the round-trip (set / get / list / delete) on an
in-memory SQLite engine so we don't need a Postgres instance.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from arcana.database.engine import Base
from arcana.services.platform_settings import (
    KEY_WELCOME_MESSAGE,
    delete_setting,
    get_setting,
    list_settings,
    set_setting,
)


@pytest_asyncio.fixture
async def db():
    """Spin up an in-memory SQLite DB with all tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    yield sm
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_setting_returns_none_when_missing(db) -> None:
    """A key that has never been written should report as ``None``."""
    async with db() as session:
        assert await get_setting(session, "missing_key") is None


@pytest.mark.asyncio
async def test_set_then_get_roundtrip(db) -> None:
    """``set_setting`` persists and ``get_setting`` reads the same value back."""
    async with db() as session:
        await set_setting(session, KEY_WELCOME_MESSAGE, "Welcome to Arcana!")
        await session.commit()

    async with db() as session:
        assert await get_setting(session, KEY_WELCOME_MESSAGE) == "Welcome to Arcana!"


@pytest.mark.asyncio
async def test_set_setting_overwrites_existing_value(db) -> None:
    """Setting an existing key should overwrite — not append or duplicate."""
    async with db() as session:
        await set_setting(session, KEY_WELCOME_MESSAGE, "v1")
        await session.commit()
    async with db() as session:
        await set_setting(session, KEY_WELCOME_MESSAGE, "v2", updated_by="admin-42")
        await session.commit()
    async with db() as session:
        assert await get_setting(session, KEY_WELCOME_MESSAGE) == "v2"
        # And there should be exactly one row, not two.
        all_settings = await list_settings(session)
        assert all_settings == {KEY_WELCOME_MESSAGE: "v2"}


@pytest.mark.asyncio
async def test_set_setting_records_updated_by(db) -> None:
    """The ``updated_by`` audit field is stored verbatim when supplied."""
    from arcana.database.models import PlatformSetting

    async with db() as session:
        await set_setting(session, "k", "v", updated_by="tg-7")
        await session.commit()
    async with db() as session:
        row = await session.get(PlatformSetting, "k")
        assert row is not None
        assert row.updated_by == "tg-7"
        assert row.updated_at is not None


@pytest.mark.asyncio
async def test_list_settings_returns_all_keys(db) -> None:
    """``list_settings`` returns the full key->value mapping."""
    async with db() as session:
        await set_setting(session, "a", "1")
        await set_setting(session, "b", "2")
        await session.commit()
    async with db() as session:
        rows = await list_settings(session)
        assert rows == {"a": "1", "b": "2"}


@pytest.mark.asyncio
async def test_delete_setting_returns_true_when_present(db) -> None:
    """Deleting a present key returns True and clears the value."""
    async with db() as session:
        await set_setting(session, "k", "v")
        await session.commit()
    async with db() as session:
        assert await delete_setting(session, "k") is True
        await session.commit()
    async with db() as session:
        assert await get_setting(session, "k") is None


@pytest.mark.asyncio
async def test_delete_setting_returns_false_when_missing(db) -> None:
    """Deleting an absent key returns False and is a no-op."""
    async with db() as session:
        assert await delete_setting(session, "never_existed") is False


@pytest.mark.asyncio
async def test_welcome_message_key_constant_is_stable() -> None:
    """The shared welcome-message key is a stable string used by both bots.

    The Manager Bot writes via ``PUT /admin/settings/welcome_message``;
    the Builder Bot reads via ``get_setting(session, KEY_WELCOME_MESSAGE)``.
    Drifting this constant would silently disconnect the two bots.
    """
    assert KEY_WELCOME_MESSAGE == "welcome_message"
