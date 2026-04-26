"""Background watchdog that hibernates bots after a period of inactivity.

The :py:meth:`Hibernator.monitor` coroutine is meant to be launched from a
service's lifespan (see ``zerobot.core.gateway``). It periodically scans
the in-memory ``last_seen`` map; any bot that has been silent for longer
than ``timeout`` seconds is reaped through a fresh orchestrator session
and its database row is updated to ``is_hibernated = True``.
"""

import asyncio
import contextlib
import logging
import time
from collections import defaultdict
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from zerobot.core.orchestrator import Orchestrator
from zerobot.database.models import Bot

log = logging.getLogger(__name__)

# Default cadence between hibernation sweeps, in seconds.
DEFAULT_SWEEP_INTERVAL = 30

SessionFactory = Callable[[], AsyncSession]


class Hibernator:
    """Track last-seen timestamps and reap bots that have been idle too long."""

    def __init__(
        self,
        timeout: int = 1800,
        sweep_interval: int = DEFAULT_SWEEP_INTERVAL,
    ) -> None:
        self.timeout = timeout
        self.sweep_interval = sweep_interval
        self.last_seen: dict[str, float] = defaultdict(time.time)

    def touch(self, bot_id: str) -> None:
        """Record activity for *bot_id*; resets its idle timer."""
        self.last_seen[bot_id] = time.time()

    def forget(self, bot_id: str) -> None:
        """Drop *bot_id* from the in-memory tracker (after reap)."""
        self.last_seen.pop(bot_id, None)

    def is_idle(self, bot_id: str) -> bool:
        """Return ``True`` if *bot_id* has been silent for longer than ``timeout``."""
        last = self.last_seen.get(bot_id)
        if last is None:
            return False
        return (time.time() - last) > self.timeout

    async def _reap_one(self, bot_id: str, session_factory: SessionFactory) -> None:
        """Reap *bot_id* and mark it hibernated in the database."""
        async with session_factory() as session:
            orchestrator = Orchestrator(session)
            with contextlib.suppress(Exception):
                await orchestrator.reap_bot(bot_id)

            bot = await session.get(Bot, bot_id)
            if bot is not None:
                bot.is_active = False
                bot.is_hibernated = True
                bot.port = None
                await session.commit()

        self.forget(bot_id)
        log.info("hibernator: reaped idle bot %s", bot_id)

    async def monitor(self, session_factory: SessionFactory) -> None:
        """Run forever, sweeping for idle bots every ``sweep_interval`` seconds.

        ``session_factory`` is a callable that returns an ``AsyncSession`` for
        each cycle (typically ``zerobot.database.engine.async_session_maker``).
        Exceptions inside the loop are logged but never propagate, so a single
        DB hiccup can't kill the watchdog.
        """
        log.info(
            "hibernator: monitor started (timeout=%ss, sweep=%ss)",
            self.timeout,
            self.sweep_interval,
        )
        while True:
            try:
                idle_bots = [
                    bot_id for bot_id in list(self.last_seen.keys()) if self.is_idle(bot_id)
                ]
                for bot_id in idle_bots:
                    try:
                        await self._reap_one(bot_id, session_factory)
                    except Exception:  # noqa: BLE001
                        log.exception("hibernator: failed to reap %s", bot_id)
            except Exception:  # noqa: BLE001
                log.exception("hibernator: sweep failed")
            await asyncio.sleep(self.sweep_interval)
