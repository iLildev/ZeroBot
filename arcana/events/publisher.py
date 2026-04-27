"""Lightweight fire-and-forget event publisher.

Subscribers register a webhook URL via the ``MANAGER_EVENT_URL`` env var.
Publishers call :py:func:`fire` from any async context — delivery happens
in the background and never blocks the caller.

Security
--------
When ``EVENT_SHARED_SECRET`` is set, every outbound request is signed with
HMAC-SHA256 over the raw JSON body. Subscribers can verify the signature
via :py:func:`compute_signature`. When the secret is absent, the publisher
operates in legacy unsigned mode and emits a one-time warning.

Delivery is best-effort: network errors are swallowed silently so a down
manager bot can never break the platform's API responses.

# ar: لماذا نبتلع أخطاء الشبكة بدلاً من رفعها؟
# ar: لأنّ هذه الأحداث "fire-and-forget": مهمّتها الإبلاغ عمّا حدث
# ar: لا التحكّم بسير العمل. لو فشل المستلم (Manager Bot معطّل مثلاً)
# ar: يجب ألّا يتسبّب ذلك في فشل عمليّة المستخدم الأصليّة (إنشاء بوت،
# ar: شحن محفظة، إلخ). للضمانات الأقوى نستخدم endpoint مختلف وقائمة
# ar: انتظار حقيقيّة (مرحلة لاحقة).
"""

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import os
from typing import Any

import httpx

log = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-Arcana-Signature"
SIGNATURE_SCHEME = "sha256"

# Lazily-initialised shared HTTP client (one per process).
_client: httpx.AsyncClient | None = None
_warned_unsigned = False


def _get_client() -> httpx.AsyncClient:
    """Return (creating on first use) the shared async HTTP client."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=3.0)
    return _client


def _subscriber_url() -> str:
    """Return the configured subscriber URL, or an empty string if disabled."""
    return os.getenv("MANAGER_EVENT_URL", "").strip()


def _shared_secret() -> str:
    """Return the configured HMAC secret, or an empty string if unsigned."""
    return os.getenv("EVENT_SHARED_SECRET", "").strip()


def compute_signature(secret: str, body: bytes) -> str:
    """Return the ``sha256=<hex>`` signature for *body* using *secret*."""
    digest = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return f"{SIGNATURE_SCHEME}={digest}"


def verify_signature(secret: str, body: bytes, header_value: str | None) -> bool:
    """Return ``True`` if *header_value* is a valid signature for *body*.

    Constant-time comparison; rejects anything that isn't ``sha256=<hex>``.
    """
    if not secret or not header_value:
        return False
    expected = compute_signature(secret, body)
    return hmac.compare_digest(expected, header_value)


async def publish(event_type: str, payload: dict[str, Any]) -> None:
    """Awaitable delivery (≤3s). Errors are swallowed."""
    global _warned_unsigned

    url = _subscriber_url()
    if not url:
        return

    body_dict = {"event": event_type, "payload": payload}
    body_bytes = json.dumps(body_dict, ensure_ascii=False).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    secret = _shared_secret()
    if secret:
        headers[SIGNATURE_HEADER] = compute_signature(secret, body_bytes)
    elif not _warned_unsigned:
        log.warning(
            "EVENT_SHARED_SECRET is not set — events are sent UNSIGNED. "
            "Anyone on the network can forge events to %s",
            url,
        )
        _warned_unsigned = True

    with contextlib.suppress(Exception):
        await _get_client().post(url, content=body_bytes, headers=headers)


def fire(event_type: str, payload: dict[str, Any]) -> None:
    """Schedule fire-and-forget delivery without blocking the caller."""
    if not _subscriber_url():
        return

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(publish(event_type, payload))
    except RuntimeError:
        # No running loop (sync context) — drop the event silently.
        pass
