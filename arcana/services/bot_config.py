"""Per-bot key/value configuration store.

Most callers only care about the bot's *audience* language (the language
the planted bot speaks to its end users — distinct from the platform UI
language stored on ``User``). The generic ``get`` / ``set`` helpers are
exposed so future settings (welcome text, opt-in flag, …) don't need a
new table.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arcana.database.models import BotConfig

# Canonical key names — keep in one place so typos can't drift.
KEY_LANG = "lang"
DEFAULT_LANG = "en"

# Conservative whitelist of ISO 639-1 codes we accept for ``botlang``.
# Matches the languages the Builder Bot already supports plus a small
# buffer for the long tail.
_ALLOWED_LANGS: frozenset[str] = frozenset(
    {
        "en", "ar", "fr", "es", "ru", "tr",
        "de", "it", "pt", "nl", "pl", "uk", "fa", "ur", "hi", "id",
        "ja", "ko", "zh",
    }
)


class InvalidConfigValue(ValueError):
    """Raised when a setter rejects a value (e.g. bad language code)."""


async def get(
    session: AsyncSession, *, bot_id: str, key: str, default: str | None = None
) -> str | None:
    """Return the stored value for ``key``, or ``default`` if unset."""
    row = await session.get(BotConfig, (bot_id, key))
    return row.value if row is not None else default


async def set_(
    session: AsyncSession, *, bot_id: str, key: str, value: str
) -> None:
    """Upsert a key/value pair. ``value`` is stored as plain text."""
    if not isinstance(value, str):
        raise InvalidConfigValue("value must be a string")
    existing = await session.get(BotConfig, (bot_id, key))
    if existing is not None:
        existing.value = value
        existing.updated_at = datetime.now(UTC)
    else:
        session.add(BotConfig(bot_id=bot_id, key=key, value=value))
    await session.flush()


async def all_for_bot(session: AsyncSession, *, bot_id: str) -> dict[str, str]:
    """Return every config row for a bot as a flat dict."""
    q = select(BotConfig).where(BotConfig.bot_id == bot_id)
    return {r.key: r.value for r in (await session.execute(q)).scalars().all()}


# ─────────────── language convenience ───────────────


def normalize_lang(value: str) -> str:
    """Validate a language code and return its lowercase form.

    Raises :class:`InvalidConfigValue` for codes outside the whitelist;
    callers in command handlers map this to a localized error message.
    """
    if not isinstance(value, str):
        raise InvalidConfigValue("language must be a string")
    code = value.strip().lower()
    if code not in _ALLOWED_LANGS:
        raise InvalidConfigValue(
            f"unsupported language: {value!r}. "
            f"Allowed: {', '.join(sorted(_ALLOWED_LANGS))}"
        )
    return code


async def get_lang(session: AsyncSession, *, bot_id: str) -> str:
    """Return the bot's audience language, defaulting to English."""
    return await get(
        session, bot_id=bot_id, key=KEY_LANG, default=DEFAULT_LANG
    ) or DEFAULT_LANG


async def set_lang(session: AsyncSession, *, bot_id: str, lang: str) -> str:
    """Validate and store the bot's audience language. Returns the stored code."""
    normalized = normalize_lang(lang)
    await set_(session, bot_id=bot_id, key=KEY_LANG, value=normalized)
    return normalized
