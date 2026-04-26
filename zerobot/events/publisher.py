"""Lightweight fire-and-forget event publisher.

Subscribers register a webhook URL via the MANAGER_EVENT_URL env var.
Publishers call `fire(event, payload)` from any async context — delivery
happens in the background and never blocks the caller.

Delivery is best-effort: network errors are swallowed silently so a down
manager bot can never break the platform's API responses.
"""

import asyncio
import os
from typing import Any

import httpx


_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=3.0)
    return _client


def _subscriber_url() -> str:
    return os.getenv("MANAGER_EVENT_URL", "").strip()


async def publish(event_type: str, payload: dict[str, Any]) -> None:
    """Awaitable delivery (≤3s). Errors are swallowed."""
    url = _subscriber_url()
    if not url:
        return

    body = {"event": event_type, "payload": payload}

    try:
        await _get_client().post(url, json=body)
    except Exception:
        pass


def fire(event_type: str, payload: dict[str, Any]) -> None:
    """Schedule fire-and-forget delivery without blocking the caller."""
    if not _subscriber_url():
        return

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(publish(event_type, payload))
    except RuntimeError:
        # no running loop (sync context) — drop the event
        pass
