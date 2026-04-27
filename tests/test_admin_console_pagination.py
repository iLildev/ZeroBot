"""HTTP tests for the paginated user-list endpoint introduced in Wave 2.

The Manager Bot's ``/users`` command now relies on ``GET /admin/users``
returning a ``UserListPage`` (``items``, ``total``, ``limit``, ``offset``)
instead of a bare list, plus an optional ``search`` substring filter.
We exercise all three on an in-memory SQLite DB.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from arcana.api import admin_console
from arcana.config import settings
from arcana.database.engine import Base
from arcana.database.models import User


@pytest_asyncio.fixture
async def client_with_users():
    """Build a TestClient with 25 deterministic users seeded."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    # Seed 25 users with predictable ids so we can assert ordering and
    # filter behaviour. Ids are zero-padded so ``created_at`` ordering
    # (which the endpoint sorts by) stays aligned with id order.
    async with sm() as session:
        for i in range(25):
            session.add(User(id=f"tg-{i:03d}"))
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


def test_list_users_returns_userlistpage_shape(client_with_users: TestClient) -> None:
    """Default response carries items + total + limit + offset."""
    r = client_with_users.get("/admin/users", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"items", "total", "limit", "offset"}
    assert body["total"] == 25
    assert body["offset"] == 0
    assert isinstance(body["items"], list)
    assert len(body["items"]) == 25  # default limit=50 fits everything


def test_list_users_respects_limit(client_with_users: TestClient) -> None:
    """``limit`` caps the page size; total still reports the full count."""
    r = client_with_users.get("/admin/users?limit=10", headers=_auth())
    body = r.json()
    assert body["limit"] == 10
    assert body["total"] == 25
    assert len(body["items"]) == 10


def test_list_users_respects_offset(client_with_users: TestClient) -> None:
    """``offset`` skips earlier rows; the second page begins where the first ended."""
    page1 = client_with_users.get("/admin/users?limit=10&offset=0", headers=_auth()).json()
    page2 = client_with_users.get("/admin/users?limit=10&offset=10", headers=_auth()).json()
    page3 = client_with_users.get("/admin/users?limit=10&offset=20", headers=_auth()).json()

    ids1 = [u["id"] for u in page1["items"]]
    ids2 = [u["id"] for u in page2["items"]]
    ids3 = [u["id"] for u in page3["items"]]

    # Pages don't overlap and together cover all 25 rows.
    assert set(ids1).isdisjoint(ids2)
    assert set(ids2).isdisjoint(ids3)
    assert len(set(ids1) | set(ids2) | set(ids3)) == 25
    assert len(ids3) == 5  # last page is partial


def test_list_users_search_filters_by_substring(client_with_users: TestClient) -> None:
    """``search`` does case-insensitive substring match on the user id."""
    r = client_with_users.get("/admin/users?search=02", headers=_auth())
    body = r.json()
    # Matches tg-002, tg-020..tg-024 => 6 ids contain "02".
    ids = [u["id"] for u in body["items"]]
    assert body["total"] == 6
    assert len(ids) == 6
    assert all("02" in i for i in ids)


def test_list_users_search_is_case_insensitive(client_with_users: TestClient) -> None:
    """Uppercase input still matches lowercase ids."""
    body = client_with_users.get("/admin/users?search=TG-001", headers=_auth()).json()
    ids = [u["id"] for u in body["items"]]
    assert ids == ["tg-001"]


def test_list_users_empty_search_returns_zero(client_with_users: TestClient) -> None:
    """A filter that matches nothing returns total=0 with an empty items list."""
    body = client_with_users.get("/admin/users?search=nope", headers=_auth()).json()
    assert body["total"] == 0
    assert body["items"] == []


def test_list_users_requires_admin_token(client_with_users: TestClient) -> None:
    """Endpoint rejects unauthenticated requests with 401."""
    assert client_with_users.get("/admin/users").status_code == 401


def test_user_row_includes_block_state(client_with_users: TestClient) -> None:
    """Each user row exposes ``is_blocked`` so the Manager Bot can render flags."""
    body = client_with_users.get("/admin/users?limit=1", headers=_auth()).json()
    row = body["items"][0]
    assert "is_blocked" in row
    assert row["is_blocked"] is False
    assert "phone_verified" in row
