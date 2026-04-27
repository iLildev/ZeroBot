"""Per-bot admin / owner role management.

Every planted bot has exactly one **owner** (auto-seeded at creation
time as the platform user who created the bot). The owner can promote
additional Telegram users to **admin**, who can then run ops commands
(broadcast, view subscribers) but cannot transfer ownership or
delete the bot.

This module is intentionally storage-only — UI commands live in the
Builder Bot. Permission checks are exposed via :func:`require_role`
so callers can write ``await require_role(session, bot_id=..., user="123",
roles=("owner", "admin"))`` and let the raised :class:`PermissionDenied`
propagate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arcana.database.models import BotAdminRole

Role = Literal["owner", "admin"]
_VALID_ROLES: tuple[Role, ...] = ("owner", "admin")


class PermissionDenied(Exception):
    """Raised when a user lacks the required role for an action."""


class AdminEntry(NamedTuple):
    """Row returned by :func:`list_admins`."""

    tg_user_id: str
    role: Role
    assigned_at: datetime
    assigned_by: str | None


async def get_role(
    session: AsyncSession, *, bot_id: str, tg_user_id: str
) -> Role | None:
    """Return the user's role for a bot, or ``None`` if they have none."""
    row = await session.get(BotAdminRole, (bot_id, str(tg_user_id)))
    return row.role if row is not None else None  # type: ignore[return-value]


async def set_owner(
    session: AsyncSession, *, bot_id: str, tg_user_id: str
) -> None:
    """Assign (or replace) the owner of a bot. Idempotent."""
    existing = await session.get(BotAdminRole, (bot_id, str(tg_user_id)))
    if existing is not None:
        existing.role = "owner"
        existing.assigned_at = datetime.now(UTC)
        await session.flush()
        return
    session.add(
        BotAdminRole(
            bot_id=bot_id,
            tg_user_id=str(tg_user_id),
            role="owner",
            assigned_at=datetime.now(UTC),
            assigned_by=None,
        )
    )
    await session.flush()


async def add_admin(
    session: AsyncSession,
    *,
    bot_id: str,
    tg_user_id: str,
    by_user_id: str,
) -> None:
    """Promote a Telegram user to ``admin``. Caller must be the owner."""
    if await get_role(session, bot_id=bot_id, tg_user_id=by_user_id) != "owner":
        raise PermissionDenied("only the bot owner can add admins")
    if str(tg_user_id) == str(by_user_id):
        # No-op: the owner is already higher than admin.
        return
    existing = await session.get(BotAdminRole, (bot_id, str(tg_user_id)))
    if existing is not None:
        if existing.role == "owner":
            raise PermissionDenied("cannot demote the owner")
        existing.role = "admin"
        existing.assigned_by = str(by_user_id)
        existing.assigned_at = datetime.now(UTC)
        await session.flush()
        return
    session.add(
        BotAdminRole(
            bot_id=bot_id,
            tg_user_id=str(tg_user_id),
            role="admin",
            assigned_at=datetime.now(UTC),
            assigned_by=str(by_user_id),
        )
    )
    await session.flush()


async def remove_admin(
    session: AsyncSession,
    *,
    bot_id: str,
    tg_user_id: str,
    by_user_id: str,
) -> bool:
    """Revoke admin status. Returns ``True`` if a row was deleted."""
    if await get_role(session, bot_id=bot_id, tg_user_id=by_user_id) != "owner":
        raise PermissionDenied("only the bot owner can remove admins")
    target = await session.get(BotAdminRole, (bot_id, str(tg_user_id)))
    if target is None:
        return False
    if target.role == "owner":
        raise PermissionDenied("cannot remove the owner")
    await session.delete(target)
    await session.flush()
    return True


async def list_admins(
    session: AsyncSession, *, bot_id: str
) -> list[AdminEntry]:
    """Return every owner/admin row for a bot, owners first."""
    q = select(BotAdminRole).where(BotAdminRole.bot_id == bot_id)
    rows = (await session.execute(q)).scalars().all()
    rows.sort(key=lambda r: (0 if r.role == "owner" else 1, r.assigned_at))
    return [
        AdminEntry(
            tg_user_id=r.tg_user_id,
            role=r.role,  # type: ignore[arg-type]
            assigned_at=r.assigned_at,
            assigned_by=r.assigned_by,
        )
        for r in rows
    ]


async def require_role(
    session: AsyncSession,
    *,
    bot_id: str,
    tg_user_id: str,
    roles: tuple[Role, ...] = _VALID_ROLES,
) -> Role:
    """Assert the caller has at least one of ``roles`` for the bot.

    Returns the actual role on success, raises :class:`PermissionDenied`
    otherwise. Useful as the first line of any privileged command handler.
    """
    actual = await get_role(session, bot_id=bot_id, tg_user_id=tg_user_id)
    if actual is None or actual not in roles:
        raise PermissionDenied(
            f"requires one of {roles} for bot {bot_id}, got {actual!r}"
        )
    return actual
