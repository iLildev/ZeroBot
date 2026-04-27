"""Invite-link / referral bookkeeping for the growth loop.

A planted bot's invite link looks like ``https://t.me/<bot_username>?start=ref_<inviter_id>``.
When a new user taps it Telegram delivers ``/start ref_<inviter_id>``
to the bot, the bot extracts the inviter id with :func:`parse_ref`,
and registers the subscriber via :mod:`arcana.services.subscribers`
with that ``referrer_id``.

Counts (top inviters, leaderboard) are derived directly from the
``bot_subscribers`` table — there's no separate "invites" table to
keep in sync.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from arcana.database.models import BotSubscriber

# Telegram's ``/start`` payload allows: A-Z a-z 0-9 _ - up to 64 chars.
# We use the ``ref_<digits>`` convention so it's both human-readable
# and trivially distinguishable from any future payload kinds.
_REF_PREFIX = "ref_"
_REF_RE = re.compile(r"^ref_(\d{1,20})$")
# Telegram bot usernames: 5-32 chars, letters/digits/underscore, must end
# with "bot" (case-insensitive). We're lenient on case but strict on shape.
_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


class InviteLeaderEntry(NamedTuple):
    """One row of the per-bot inviter leaderboard."""

    inviter_id: str
    invites: int


def make_ref_payload(inviter_tg_user_id: str | int) -> str:
    """Build the ``/start`` payload string for a given inviter."""
    s = str(inviter_tg_user_id)
    if not s.isdigit():
        raise ValueError("inviter id must be a positive integer")
    return f"{_REF_PREFIX}{s}"


def make_invite_link(*, bot_username: str, inviter_tg_user_id: str | int) -> str:
    """Return a t.me deep link encoding the inviter id."""
    if not _USERNAME_RE.match(bot_username or ""):
        raise ValueError(f"invalid bot username: {bot_username!r}")
    payload = make_ref_payload(inviter_tg_user_id)
    return f"https://t.me/{bot_username}?start={payload}"


def parse_ref(start_payload: str | None) -> str | None:
    """Extract the inviter id from a ``/start`` payload, or ``None``."""
    if not start_payload:
        return None
    match = _REF_RE.match(start_payload.strip())
    return match.group(1) if match else None


async def top_inviters(
    session: AsyncSession, *, bot_id: str, limit: int = 10
) -> list[InviteLeaderEntry]:
    """Return the inviters with the most successful referrals for a bot."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    q = (
        select(BotSubscriber.referrer_id, func.count().label("c"))
        .where(
            BotSubscriber.bot_id == bot_id,
            BotSubscriber.referrer_id.is_not(None),
        )
        .group_by(BotSubscriber.referrer_id)
        .order_by(desc("c"))
        .limit(limit)
    )
    rows = (await session.execute(q)).all()
    return [InviteLeaderEntry(inviter_id=r[0], invites=int(r[1])) for r in rows]


async def invites_by(
    session: AsyncSession, *, bot_id: str, inviter_tg_user_id: str
) -> int:
    """Return the total number of successful referrals by one inviter."""
    q = (
        select(func.count())
        .select_from(BotSubscriber)
        .where(
            BotSubscriber.bot_id == bot_id,
            BotSubscriber.referrer_id == str(inviter_tg_user_id),
        )
    )
    return int((await session.execute(q)).scalar_one())
