"""Tiny client for Arcana's bot-platform callback API.

Planted bots POST subscriber/event data back to the platform so the
owner can see /subscribers and /insights from the Builder Bot. We
keep the surface minimal (two helpers, no deps beyond aiohttp which
the template already pulls in for the webhook server) so the file
stays maintainable when the Builder Agent regenerates the bot's code.

If ``ARCANA_PLATFORM_URL`` is not set the helpers silently no-op,
so the template still runs cleanly outside of a hosted Arcana env.
"""

from __future__ import annotations

import logging
import os

import aiohttp

log = logging.getLogger(__name__)

_BASE = (os.getenv("ARCANA_PLATFORM_URL") or "").rstrip("/")
_TOKEN = os.getenv("BOT_TOKEN", "")
_TIMEOUT = aiohttp.ClientTimeout(total=5)


def _enabled() -> bool:
    return bool(_BASE and _TOKEN)


async def register_subscriber(
    bot_id: str, tg_user_id: str, *, ref: str | None = None
) -> None:
    """Tell the platform that ``tg_user_id`` interacted with this bot."""
    if not _enabled():
        return
    payload: dict[str, object] = {"tg_user_id": str(tg_user_id)}
    if ref:
        payload["ref"] = str(ref)
    url = f"{_BASE}/v1/bots/{bot_id}/subscribers"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                url, json=payload, headers={"X-Bot-Token": _TOKEN}
            ) as resp:
                if resp.status >= 400:
                    log.warning(
                        "register_subscriber failed: %s %s",
                        resp.status,
                        await resp.text(),
                    )
    except Exception:
        # Never let analytics break the user-facing flow.
        log.exception("register_subscriber crashed")


async def track_event(
    bot_id: str,
    *,
    kind: str,
    name: str,
    tg_user_id: str | None = None,
) -> None:
    """Record one analytics event (command tap, button click, …)."""
    if not _enabled():
        return
    payload: dict[str, object] = {"kind": kind, "name": name}
    if tg_user_id is not None:
        payload["tg_user_id"] = str(tg_user_id)
    url = f"{_BASE}/v1/bots/{bot_id}/events"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                url, json=payload, headers={"X-Bot-Token": _TOKEN}
            ) as resp:
                if resp.status >= 400:
                    log.warning(
                        "track_event failed: %s %s",
                        resp.status,
                        await resp.text(),
                    )
    except Exception:
        log.exception("track_event crashed")
