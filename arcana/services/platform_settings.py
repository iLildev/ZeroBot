"""Live, DB-backed key-value settings the bots read at runtime.

Used for values an operator should be able to tweak from Telegram without
redeploying — currently just the customizable welcome message, but the
table is generic so future tunables (e.g. minimum balance, free-tier
quota) can land here without a fresh migration.

All helpers are plain functions taking an ``AsyncSession`` so callers
keep transaction control. Values are short ``Text`` blobs; a wrapper
helper can JSON-encode if needed.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arcana.database.models import PlatformSetting

# Reserved keys — keep them in one place so typos don't ship to prod.
KEY_WELCOME_MESSAGE = "welcome_message"


async def get_setting(
    session: AsyncSession,
    key: str,
    default: str | None = None,
) -> str | None:
    """Return the stored value for *key*, or *default* if missing."""
    row = await session.get(PlatformSetting, key)
    return row.value if row is not None else default


async def set_setting(
    session: AsyncSession,
    key: str,
    value: str,
    *,
    updated_by: str | None = None,
) -> PlatformSetting:
    """Insert or update *key* with *value* and commit the change.

    ``updated_by`` is recorded for audit so we can answer "who changed
    the welcome message?" without a separate audit log table.
    """
    row = await session.get(PlatformSetting, key)
    if row is None:
        row = PlatformSetting(key=key, value=value, updated_by=updated_by)
        session.add(row)
    else:
        row.value = value
        row.updated_by = updated_by
    await session.commit()
    return row


async def delete_setting(session: AsyncSession, key: str) -> bool:
    """Remove *key* from the table. Returns ``True`` if a row was deleted."""
    row = await session.get(PlatformSetting, key)
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def list_settings(session: AsyncSession) -> dict[str, str]:
    """Return a snapshot of every stored setting (small enough to fit in memory)."""
    rows = (await session.execute(select(PlatformSetting))).scalars().all()
    return {row.key: row.value for row in rows}
