"""HTTP tests for the Wave 2 expansion of ``GET /admin/stats``.

Wave 2 added four new counters: ``users_verified``, ``users_blocked``,
``users_today``, ``users_this_week``. These tests seed users in known
states and assert each counter reflects them, against an in-memory
SQLite DB.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from arcana.api import admin_console
from arcana.config import settings
from arcana.database.engine import Base
from arcana.database.models import User


@pytest_asyncio.fixture
async def client_with_seed():
    """Build a TestClient with a deliberately mixed user population."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    now = datetime.now(UTC)
    async with sm() as session:
        # 3 verified, 2 unverified, 1 blocked, 1 verified-and-blocked.
        session.add(User(id="tg-1", phone_verified_at=now))
        session.add(User(id="tg-2", phone_verified_at=now))
        session.add(User(id="tg-3", phone_verified_at=now))
        session.add(User(id="tg-4"))
        session.add(User(id="tg-5"))
        session.add(User(id="tg-6", is_blocked=True, blocked_at=now))
        session.add(
            User(
                id="tg-7",
                phone_verified_at=now,
                is_blocked=True,
                blocked_at=now,
            )
        )
        # Backdate one user to last month so it counts toward "total"
        # but not toward today / this week.
        old = User(id="tg-old")
        session.add(old)
        await session.flush()
        old.created_at = now - timedelta(days=40)
        await session.commit()

    async def _override():
        async with sm() as session:
            yield session

    admin_console.app.dependency_overrides[admin_console.get_session] = _override
    try:
        yield TestClient(admin_console.app)
    finally:
        admin_console.app.dependency_overrides.clear()
        await engine.dispose()


def _auth() -> dict[str, str]:
    return {"X-Admin-Token": settings.ADMIN_TOKEN or "test-token"}


def test_stats_includes_wave2_counters(client_with_seed: TestClient) -> None:
    """The four new keys are present in the response body."""
    body = client_with_seed.get("/admin/stats", headers=_auth()).json()
    for key in ("users_verified", "users_blocked", "users_today", "users_this_week"):
        assert key in body, f"missing {key} in /admin/stats payload"


def test_stats_users_verified_count(client_with_seed: TestClient) -> None:
    """``users_verified`` counts every row with a non-null phone_verified_at."""
    body = client_with_seed.get("/admin/stats", headers=_auth()).json()
    # tg-1, tg-2, tg-3, tg-7 == 4 verified.
    assert body["users_verified"] == 4


def test_stats_users_blocked_count(client_with_seed: TestClient) -> None:
    """``users_blocked`` counts every row with ``is_blocked=True``."""
    body = client_with_seed.get("/admin/stats", headers=_auth()).json()
    # tg-6, tg-7 == 2 blocked.
    assert body["users_blocked"] == 2


def test_stats_users_today_excludes_old_rows(client_with_seed: TestClient) -> None:
    """``users_today`` only counts rows created since midnight UTC today."""
    body = client_with_seed.get("/admin/stats", headers=_auth()).json()
    # Seven fresh users today; tg-old was backdated 40 days.
    assert body["users_today"] == 7
    assert body["users_total"] == 8


def test_stats_users_this_week_excludes_old_rows(client_with_seed: TestClient) -> None:
    """``users_this_week`` covers the past 7 days but not the 40-day-old row."""
    body = client_with_seed.get("/admin/stats", headers=_auth()).json()
    assert body["users_this_week"] == 7


def test_stats_requires_admin_token(client_with_seed: TestClient) -> None:
    """Stats endpoint rejects calls without ``X-Admin-Token``."""
    assert client_with_seed.get("/admin/stats").status_code == 401
