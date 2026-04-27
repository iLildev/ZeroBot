"""Unit tests for the top-level Flask keep-alive server."""

from __future__ import annotations

import keep_alive


def test_root_returns_ok() -> None:
    client = keep_alive.create_app().test_client()
    r = client.get("/")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok"
    assert body["service"] == "arcana-keep-alive"
    assert "started_at" in body


def test_health_endpoint_returns_ok() -> None:
    client = keep_alive.create_app().test_client()
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_unknown_path_404s() -> None:
    client = keep_alive.create_app().test_client()
    assert client.get("/nope").status_code == 404


def test_module_exports_app_singleton() -> None:
    """The module-level ``app`` is what gunicorn / `python keep_alive.py` use."""
    assert keep_alive.app is not None
    r = keep_alive.app.test_client().get("/health")
    assert r.status_code == 200
