"""Lightweight async scheduler for periodic background tasks.

The spec calls for a 5-minute heartbeat that runs maintenance jobs
(stale-session cleanup, analytics roll-ups, queued-broadcast retries)
without blocking the bot's main event loop.

Design choices:

* Pure ``asyncio`` — no celery / APScheduler dependency, no extra
  process to deploy.
* Tasks register a coroutine **factory** plus an interval. Factories
  let us build a fresh awaitable per tick (you cannot ``await`` the
  same coroutine twice).
* Each task is shielded so a single failure doesn't kill its sibling
  loops; failures get logged and the loop continues.
* ``start()`` / ``stop()`` are both idempotent so the scheduler can be
  embedded in a long-running service without ceremony.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 300  # five minutes — see spec.

TaskFactory = Callable[[], Awaitable[None]]


@dataclass
class _RegisteredTask:
    name: str
    factory: TaskFactory
    interval: float
    last_run_at: float = 0.0
    last_error: str | None = None
    runs: int = 0


class Scheduler:
    """Run a set of named tasks at fixed intervals on the asyncio loop.

    Typical use:

        sched = Scheduler()
        sched.add("cleanup", do_cleanup)              # every 300s
        sched.add("rollup", roll_up_analytics, 60)    # every 60s
        await sched.start()
        ...
        await sched.stop()
    """

    def __init__(self) -> None:
        self._tasks: dict[str, _RegisteredTask] = {}
        self._runners: dict[str, asyncio.Task[None]] = {}
        self._stopped = asyncio.Event()
        self._stopped.set()  # starts stopped

    def add(
        self,
        name: str,
        factory: TaskFactory,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        """Register a task. Must be called before :meth:`start`."""
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if name in self._tasks:
            raise ValueError(f"task {name!r} already registered")
        self._tasks[name] = _RegisteredTask(
            name=name, factory=factory, interval=float(interval_seconds)
        )

    def remove(self, name: str) -> None:
        """Unregister a task and cancel its runner if running."""
        self._tasks.pop(name, None)
        runner = self._runners.pop(name, None)
        if runner is not None and not runner.done():
            runner.cancel()

    @property
    def running(self) -> bool:
        return not self._stopped.is_set()

    def task_status(self, name: str) -> dict[str, object] | None:
        """Inspect a single task's runtime state — used by health probes."""
        t = self._tasks.get(name)
        if t is None:
            return None
        return {
            "name": t.name,
            "interval": t.interval,
            "runs": t.runs,
            "last_run_at": t.last_run_at,
            "last_error": t.last_error,
        }

    async def start(self) -> None:
        """Spawn one async loop per registered task. Idempotent."""
        if self.running:
            return
        self._stopped.clear()
        for task in self._tasks.values():
            self._runners[task.name] = asyncio.create_task(
                self._run_loop(task), name=f"sched:{task.name}"
            )
        log.info("scheduler started with %d task(s)", len(self._tasks))

    async def stop(self, timeout: float = 5.0) -> None:
        """Signal every loop to exit and wait up to ``timeout`` seconds."""
        if not self.running:
            return
        self._stopped.set()
        for runner in self._runners.values():
            runner.cancel()
        # Drain — ignore CancelledError, surface other failures via logs.
        for runner in self._runners.values():
            try:
                await asyncio.wait_for(runner, timeout=timeout)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                log.exception("scheduler runner raised during shutdown")
        self._runners.clear()
        log.info("scheduler stopped")

    async def run_once(self, name: str) -> None:
        """Manually fire a single task — handy for tests + admin probes."""
        task = self._tasks.get(name)
        if task is None:
            raise KeyError(name)
        await self._fire(task)

    async def _fire(self, task: _RegisteredTask) -> None:
        try:
            await task.factory()
            task.last_error = None
        except Exception as exc:  # noqa: BLE001 - we want to keep the loop alive
            task.last_error = repr(exc)
            log.exception("scheduled task %r failed", task.name)
        finally:
            task.last_run_at = time.time()
            task.runs += 1

    async def _run_loop(self, task: _RegisteredTask) -> None:
        try:
            while not self._stopped.is_set():
                await self._fire(task)
                # Sleep in small slices so ``stop()`` is responsive.
                deadline = time.time() + task.interval
                while not self._stopped.is_set() and time.time() < deadline:
                    await asyncio.sleep(min(0.5, deadline - time.time()))
        except asyncio.CancelledError:
            raise


# ─────────────── default placeholder jobs ───────────────


async def cleanup_inactive_sessions() -> None:
    """Placeholder: no-op for now, wired so the scheduler has work to do."""
    log.debug("cleanup_inactive_sessions tick")


async def update_analytics_rollups() -> None:
    """Placeholder for future per-bot analytics aggregation."""
    log.debug("update_analytics_rollups tick")


async def process_queued_operations() -> None:
    """Placeholder for retrying failed broadcasts and other queued ops."""
    log.debug("process_queued_operations tick")


def build_default_scheduler() -> Scheduler:
    """Return a scheduler pre-loaded with the three spec-required tasks."""
    s = Scheduler()
    s.add("cleanup_inactive_sessions", cleanup_inactive_sessions)
    s.add("update_analytics_rollups", update_analytics_rollups)
    s.add("process_queued_operations", process_queued_operations)
    return s
