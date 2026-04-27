"""Seed a freshly-planted bot with sensible defaults.

Called by the orchestrator immediately after a ``Bot`` row is inserted.
What we seed:

* The creator's Telegram user-id is registered as the bot's ``owner``
  in :mod:`arcana.services.bot_admins` so commands like
  ``/newpost`` work the moment the bot is alive.
* The bot's audience language is initialized to English. The owner can
  change it any time with ``/botlang``.

The function is intentionally idempotent (uses upsert-style helpers) so
re-runs during recovery / migrations don't blow up.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from arcana.services import bot_admins, bot_config


async def seed_new_bot(
    session: AsyncSession,
    *,
    bot_id: str,
    owner_user_id: str,
    default_lang: str = "en",
) -> None:
    """Wire up the platform-side defaults for a newly-planted bot.

    ``owner_user_id`` should be the Telegram user-id of the creator (so
    ``/start`` from that account on the planted bot inherits the owner
    role automatically).
    """
    # Strip the ``tg-`` prefix if the caller passed an Arcana platform id;
    # role rows store the raw Telegram id so they line up with what the
    # planted bot sees in ``message.from_user.id``.
    tg_only = owner_user_id[3:] if owner_user_id.startswith("tg-") else owner_user_id
    await bot_admins.set_owner(session, bot_id=bot_id, tg_user_id=tg_only)
    await bot_config.set_lang(session, bot_id=bot_id, lang=default_lang)
