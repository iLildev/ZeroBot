"""Unit tests for the per-bot invite link / referral service."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from arcana.database.engine import Base
from arcana.database.models import Bot, User
from arcana.services import bot_invites, subscribers


def test_make_invite_link_round_trip() -> None:
    link = bot_invites.make_invite_link(
        bot_username="DemoBot", inviter_tg_user_id=12345
    )
    assert link == "https://t.me/DemoBot?start=ref_12345"
    assert bot_invites.parse_ref("ref_12345") == "12345"


def test_parse_ref_returns_none_for_unknown_payloads() -> None:
    assert bot_invites.parse_ref(None) is None
    assert bot_invites.parse_ref("") is None
    assert bot_invites.parse_ref("hello") is None
    assert bot_invites.parse_ref("ref_") is None
    assert bot_invites.parse_ref("ref_abc") is None


def test_make_invite_link_rejects_bad_username() -> None:
    with pytest.raises(ValueError):
        bot_invites.make_invite_link(bot_username="", inviter_tg_user_id=1)
    with pytest.raises(ValueError):
        bot_invites.make_invite_link(bot_username="x", inviter_tg_user_id=1)


def test_make_ref_payload_rejects_non_numeric() -> None:
    with pytest.raises(ValueError):
        bot_invites.make_ref_payload("abc")


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
async def test_top_inviters_counts_referrals(session_factory) -> None:
    async with session_factory() as s:
        # Inviter "100" brings 3 subs; inviter "200" brings 1.
        for uid, ref in [
            ("1", "100"),
            ("2", "100"),
            ("3", "100"),
            ("4", "200"),
            ("5", None),  # organic — no referrer
        ]:
            await subscribers.register_subscriber(
                s, bot_id="bot-A", tg_user_id=uid, referrer_id=ref
            )
        await s.commit()
        leaders = await bot_invites.top_inviters(s, bot_id="bot-A", limit=5)
    assert [(le.inviter_id, le.invites) for le in leaders] == [
        ("100", 3),
        ("200", 1),
    ]


@pytest.mark.asyncio
async def test_invites_by_specific_user(session_factory) -> None:
    async with session_factory() as s:
        await subscribers.register_subscriber(
            s, bot_id="bot-A", tg_user_id="1", referrer_id="100"
        )
        await subscribers.register_subscriber(
            s, bot_id="bot-A", tg_user_id="2", referrer_id="100"
        )
        await s.commit()
        n = await bot_invites.invites_by(
            s, bot_id="bot-A", inviter_tg_user_id="100"
        )
    assert n == 2
