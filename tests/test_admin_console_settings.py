"""HTTP tests for the platform-settings admin endpoints.

Exercises the full ``/admin/settings`` surface (list, get, put, delete)
against a real FastAPI ``TestClient`` wired to an in-memory SQLite
database. Auth is exercised too: every endpoint must reject calls
without the ``X-Admin-Token`` header.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from arcana.api import admin_console
from arcana.config import settings
from arcana.database.engine import Base


@pytest_asyncio.fixture
async def client():
    """Build a TestClient whose admin app reads/writes an isolated DB."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)

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


def test_get_setting_404_when_missing(client: TestClient) -> None:
    """Reading a never-set key returns ``404``, not an empty body."""
    r = client.get("/admin/settings/welcome_message", headers=_auth())
    assert r.status_code == 404


def test_put_then_get_setting_roundtrip(client: TestClient) -> None:
    """PUT stores the value; the next GET returns it with audit metadata."""
    r = client.put(
        "/admin/settings/welcome_message",
        json={"value": "Welcome to Arcana"},
        headers={**_auth(), "X-Admin-User": "tg-99"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["key"] == "welcome_message"
    assert body["value"] == "Welcome to Arcana"
    assert body["updated_by"] == "tg-99"
    assert body["updated_at"] is not None

    r2 = client.get("/admin/settings/welcome_message", headers=_auth())
    assert r2.status_code == 200
    assert r2.json()["value"] == "Welcome to Arcana"


def test_put_setting_overwrites(client: TestClient) -> None:
    """A second PUT replaces the value rather than duplicating the row."""
    client.put("/admin/settings/k", json={"value": "v1"}, headers=_auth())
    client.put("/admin/settings/k", json={"value": "v2"}, headers=_auth())
    body = client.get("/admin/settings/k", headers=_auth()).json()
    assert body["value"] == "v2"

    listing = client.get("/admin/settings", headers=_auth()).json()
    matching = [row for row in listing if row["key"] == "k"]
    assert len(matching) == 1


def test_delete_setting_then_get_returns_404(client: TestClient) -> None:
    """DELETE removes the row; a follow-up GET returns 404."""
    client.put("/admin/settings/k", json={"value": "v"}, headers=_auth())
    r = client.delete("/admin/settings/k", headers=_auth())
    assert r.status_code == 200
    assert r.json() == {"deleted": True, "key": "k"}

    assert client.get("/admin/settings/k", headers=_auth()).status_code == 404


def test_delete_missing_setting_returns_404(client: TestClient) -> None:
    """DELETE on an absent key is reported, not silently swallowed."""
    r = client.delete("/admin/settings/never_set", headers=_auth())
    assert r.status_code == 404


def test_list_settings_returns_all_keys(client: TestClient) -> None:
    """GET /admin/settings lists every stored row (unordered)."""
    client.put("/admin/settings/a", json={"value": "1"}, headers=_auth())
    client.put("/admin/settings/b", json={"value": "2"}, headers=_auth())
    rows = client.get("/admin/settings", headers=_auth()).json()
    seen = {row["key"]: row["value"] for row in rows}
    assert seen == {"a": "1", "b": "2"}


def test_settings_endpoints_require_admin_token(client: TestClient) -> None:
    """All settings endpoints reject calls without ``X-Admin-Token``."""
    assert client.get("/admin/settings").status_code == 401
    assert client.get("/admin/settings/k").status_code == 401
    assert client.put("/admin/settings/k", json={"value": "v"}).status_code == 401
    assert client.delete("/admin/settings/k").status_code == 401
