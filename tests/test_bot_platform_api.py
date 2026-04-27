"""Integration tests for the planted-bot callback FastAPI app."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from arcana.api.bot_platform import _session, create_app
from arcana.database.engine import Base
from arcana.database.models import Bot, BotEvent, BotSubscriber, User


@pytest_asyncio.fixture
async def app_and_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        s.add(User(id="tg-1", is_admin=False))
        s.add(Bot(id="bot-A", user_id="tg-1", token="secret-A"))
        s.add(Bot(id="bot-B", user_id="tg-1", token="secret-B"))
        await s.commit()

    app = create_app()

    async def override():
        async with sm() as s:
            yield s

    app.dependency_overrides[_session] = override
    yield app, sm
    app.dependency_overrides.clear()
    await engine.dispose()


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_healthz_is_open(app_and_db) -> None:
    app, _ = app_and_db
    async with _client(app) as c:
        r = await c.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_subscribe_requires_token(app_and_db) -> None:
    app, _ = app_and_db
    async with _client(app) as c:
        r = await c.post(
            "/v1/bots/bot-A/subscribers", json={"tg_user_id": "42"}
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_subscribe_rejects_wrong_token(app_and_db) -> None:
    app, _ = app_and_db
    async with _client(app) as c:
        r = await c.post(
            "/v1/bots/bot-A/subscribers",
            json={"tg_user_id": "42"},
            headers={"X-Bot-Token": "wrong"},
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_subscribe_token_must_match_path_bot(app_and_db) -> None:
    """A token for bot-B must NOT authenticate writes to bot-A."""
    app, _ = app_and_db
    async with _client(app) as c:
        r = await c.post(
            "/v1/bots/bot-A/subscribers",
            json={"tg_user_id": "42"},
            headers={"X-Bot-Token": "secret-B"},
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_subscribe_unknown_bot_is_401_not_404(app_and_db) -> None:
    """We deliberately don't leak existence of bot ids."""
    app, _ = app_and_db
    async with _client(app) as c:
        r = await c.post(
            "/v1/bots/does-not-exist/subscribers",
            json={"tg_user_id": "42"},
            headers={"X-Bot-Token": "secret-A"},
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_subscribe_persists_and_records_event(app_and_db) -> None:
    app, sm = app_and_db
    async with _client(app) as c:
        r = await c.post(
            "/v1/bots/bot-A/subscribers",
            json={"tg_user_id": "42", "ref": "100"},
            headers={"X-Bot-Token": "secret-A"},
        )
    assert r.status_code == 201
    body = r.json()
    assert body["created"] is True and body["tg_user_id"] == "42"

    async with sm() as s:
        sub = await s.get(BotSubscriber, ("bot-A", "42"))
        assert sub is not None and sub.referrer_id == "100"
        events = (
            (await s.execute(select(BotEvent).where(BotEvent.bot_id == "bot-A")))
            .scalars()
            .all()
        )
        kinds = {e.kind for e in events}
    # subscribe + invite_used should both be recorded for a referred join.
    assert {"subscribe", "invite_used"} <= kinds


@pytest.mark.asyncio
async def test_subscribe_second_call_is_not_created(app_and_db) -> None:
    app, _ = app_and_db
    async with _client(app) as c:
        await c.post(
            "/v1/bots/bot-A/subscribers",
            json={"tg_user_id": "42"},
            headers={"X-Bot-Token": "secret-A"},
        )
        r = await c.post(
            "/v1/bots/bot-A/subscribers",
            json={"tg_user_id": "42"},
            headers={"X-Bot-Token": "secret-A"},
        )
    assert r.status_code == 201
    assert r.json()["created"] is False


@pytest.mark.asyncio
async def test_unregister_round_trip(app_and_db) -> None:
    app, _ = app_and_db
    async with _client(app) as c:
        await c.post(
            "/v1/bots/bot-A/subscribers",
            json={"tg_user_id": "42"},
            headers={"X-Bot-Token": "secret-A"},
        )
        r = await c.delete(
            "/v1/bots/bot-A/subscribers/42",
            headers={"X-Bot-Token": "secret-A"},
        )
    assert r.status_code == 200 and r.json() == {"removed": True}


@pytest.mark.asyncio
async def test_unregister_missing_returns_false(app_and_db) -> None:
    app, _ = app_and_db
    async with _client(app) as c:
        r = await c.delete(
            "/v1/bots/bot-A/subscribers/9999",
            headers={"X-Bot-Token": "secret-A"},
        )
    assert r.status_code == 200 and r.json() == {"removed": False}


@pytest.mark.asyncio
async def test_event_endpoint_records(app_and_db) -> None:
    app, sm = app_and_db
    async with _client(app) as c:
        r = await c.post(
            "/v1/bots/bot-A/events",
            json={"kind": "command", "name": "/start", "tg_user_id": "42"},
            headers={"X-Bot-Token": "secret-A"},
        )
    assert r.status_code == 201

    async with sm() as s:
        rows = (
            (await s.execute(select(BotEvent).where(BotEvent.bot_id == "bot-A")))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].kind == "command" and rows[0].name == "/start"


@pytest.mark.asyncio
async def test_event_rejects_invalid_kind(app_and_db) -> None:
    app, _ = app_and_db
    async with _client(app) as c:
        r = await c.post(
            "/v1/bots/bot-A/events",
            json={"kind": "evil", "name": "x"},
            headers={"X-Bot-Token": "secret-A"},
        )
    # Pydantic validation -> 422.
    assert r.status_code == 422
