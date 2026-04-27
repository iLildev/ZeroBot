"""Lightweight per-bot analytics + the Growth Engine suggestion layer.

Two responsibilities:

1. **Recording.** :func:`record_event` writes one row to ``bot_events``.
   Planted bots call this via the platform callback API every time the
   user runs a command, taps a button, subscribes, etc.
2. **Reading.** :func:`top_commands`, :func:`top_buttons`,
   :func:`dropoff_funnel`, :func:`suggestions` aggregate those rows into
   actionable summaries — the rule-based "Growth Engine" the spec asks
   for.

This is intentionally **not** AI-powered. The suggestions come from a
small handful of rules tuned to surface obvious issues (low-engagement
buttons, weak onboarding, dead bots) so they stay explainable.
"""

from __future__ import annotations

from typing import Literal, NamedTuple

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from arcana.database.models import BotEvent, BotSubscriber

# Closed set so typos don't silently create new event kinds.
EventKind = Literal[
    "command", "button", "subscribe", "unsubscribe", "broadcast", "invite_used"
]
_VALID_KINDS: frozenset[str] = frozenset(
    ["command", "button", "subscribe", "unsubscribe", "broadcast", "invite_used"]
)
# Hard cap on per-row strings so a misbehaving bot can't bloat the table.
_MAX_NAME_LEN = 64


class CountedName(NamedTuple):
    """Generic ``(name, count)`` row."""

    name: str
    count: int


class FunnelStats(NamedTuple):
    """Subscribers vs. how many of them ever sent a command."""

    subscribers: int
    engaged: int  # subscribers who fired at least one ``command`` event
    dropoff_pct: float  # percentage that subscribed but never engaged


async def record_event(
    session: AsyncSession,
    *,
    bot_id: str,
    kind: str,
    name: str,
    tg_user_id: str | None = None,
) -> None:
    """Persist a single event. Validates ``kind`` and clamps ``name`` length."""
    if kind not in _VALID_KINDS:
        raise ValueError(f"unknown event kind: {kind!r}")
    if not name:
        raise ValueError("event name cannot be empty")
    safe_name = name.strip()[:_MAX_NAME_LEN]
    session.add(
        BotEvent(
            bot_id=bot_id,
            tg_user_id=str(tg_user_id) if tg_user_id is not None else None,
            kind=kind,
            name=safe_name,
        )
    )
    await session.flush()


async def _top_by_kind(
    session: AsyncSession, *, bot_id: str, kind: str, limit: int
) -> list[CountedName]:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    q = (
        select(BotEvent.name, func.count().label("c"))
        .where(BotEvent.bot_id == bot_id, BotEvent.kind == kind)
        .group_by(BotEvent.name)
        .order_by(desc("c"))
        .limit(limit)
    )
    rows = (await session.execute(q)).all()
    return [CountedName(name=r[0], count=int(r[1])) for r in rows]


async def top_commands(
    session: AsyncSession, *, bot_id: str, limit: int = 5
) -> list[CountedName]:
    """Return the most-invoked slash-commands."""
    return await _top_by_kind(session, bot_id=bot_id, kind="command", limit=limit)


async def top_buttons(
    session: AsyncSession, *, bot_id: str, limit: int = 5
) -> list[CountedName]:
    """Return the most-tapped inline-keyboard buttons."""
    return await _top_by_kind(session, bot_id=bot_id, kind="button", limit=limit)


async def dropoff_funnel(
    session: AsyncSession, *, bot_id: str
) -> FunnelStats:
    """Return total subscribers vs how many ever fired a ``command`` event."""
    sub_q = select(func.count()).select_from(BotSubscriber).where(
        BotSubscriber.bot_id == bot_id
    )
    subs = int((await session.execute(sub_q)).scalar_one())

    eng_q = (
        select(func.count(func.distinct(BotEvent.tg_user_id)))
        .where(
            BotEvent.bot_id == bot_id,
            BotEvent.kind == "command",
            BotEvent.tg_user_id.is_not(None),
        )
    )
    engaged = int((await session.execute(eng_q)).scalar_one())
    pct = (1.0 - engaged / subs) * 100.0 if subs > 0 else 0.0
    # Engagement can technically exceed subs (engaged user who later
    # un-subscribed and was deleted), so clamp the percentage to [0, 100].
    pct = max(0.0, min(100.0, pct))
    return FunnelStats(subscribers=subs, engaged=engaged, dropoff_pct=pct)


async def suggestions(
    session: AsyncSession, *, bot_id: str
) -> list[str]:
    """Return a few human-readable improvement hints based on the data.

    The rules are intentionally simple and explainable:

    * No subscribers yet → suggest sharing the bot's invite link.
    * High drop-off (>60%) on a non-trivial audience → onboarding flow
      probably weak.
    * Buttons with click counts in the bottom quartile vs the top → flag
      them as candidates for removal/rewording.
    * No ``command`` events at all but subscribers exist → bot has no
      handlers wired up.
    """
    out: list[str] = []
    funnel = await dropoff_funnel(session, bot_id=bot_id)

    if funnel.subscribers == 0:
        out.append(
            "No subscribers yet — share the bot's invite link from /insights "
            "to kick off the growth loop."
        )
        return out

    if funnel.subscribers >= 10 and funnel.dropoff_pct > 60.0:
        out.append(
            f"{funnel.dropoff_pct:.0f}% of subscribers never used a command — "
            "consider a friendlier /start message or a simpler menu."
        )

    cmds = await top_commands(session, bot_id=bot_id, limit=10)
    if funnel.subscribers > 0 and not cmds:
        out.append(
            "Subscribers are joining but no commands have been recorded — "
            "make sure the bot has at least /start and /help wired up."
        )

    btns = await top_buttons(session, bot_id=bot_id, limit=10)
    if len(btns) >= 4:
        top_count = btns[0].count
        weak = [b for b in btns if b.count <= max(1, top_count // 4)]
        if weak:
            names = ", ".join(b.name for b in weak[:3])
            out.append(
                f"Buttons {names} get very few taps — consider renaming or "
                "removing them."
            )

    if not out:
        out.append("Nothing alarming — keep iterating ✨.")
    return out
