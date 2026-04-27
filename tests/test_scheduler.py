"""Unit tests for the async background-task scheduler."""

from __future__ import annotations

import asyncio

import pytest

from arcana.services.scheduler import (
    DEFAULT_INTERVAL_SECONDS,
    Scheduler,
    build_default_scheduler,
)


@pytest.mark.asyncio
async def test_add_rejects_duplicate_names() -> None:
    s = Scheduler()
    s.add("x", lambda: asyncio.sleep(0))
    with pytest.raises(ValueError):
        s.add("x", lambda: asyncio.sleep(0))


@pytest.mark.asyncio
async def test_add_rejects_non_positive_interval() -> None:
    s = Scheduler()
    with pytest.raises(ValueError):
        s.add("x", lambda: asyncio.sleep(0), interval_seconds=0)


@pytest.mark.asyncio
async def test_run_once_fires_factory() -> None:
    calls = 0

    async def job() -> None:
        nonlocal calls
        calls += 1

    s = Scheduler()
    s.add("counter", job)
    await s.run_once("counter")
    await s.run_once("counter")
    status = s.task_status("counter")
    assert calls == 2
    assert status is not None and status["runs"] == 2
    assert status["last_error"] is None


@pytest.mark.asyncio
async def test_run_once_unknown_task_raises() -> None:
    s = Scheduler()
    with pytest.raises(KeyError):
        await s.run_once("missing")


@pytest.mark.asyncio
async def test_failure_is_caught_and_logged() -> None:
    async def boom() -> None:
        raise RuntimeError("kaboom")

    s = Scheduler()
    s.add("boom", boom)
    await s.run_once("boom")  # must not raise
    status = s.task_status("boom")
    assert status is not None
    assert status["runs"] == 1
    assert "kaboom" in str(status["last_error"])


@pytest.mark.asyncio
async def test_start_runs_tasks_in_background_then_stop() -> None:
    counter = 0

    async def tick() -> None:
        nonlocal counter
        counter += 1

    s = Scheduler()
    s.add("tick", tick, interval_seconds=0.05)
    await s.start()
    # Let several ticks fire.
    await asyncio.sleep(0.25)
    assert s.running is True
    await s.stop(timeout=1.0)
    assert s.running is False
    assert counter >= 2


@pytest.mark.asyncio
async def test_start_is_idempotent() -> None:
    s = Scheduler()
    s.add("noop", lambda: asyncio.sleep(0))
    await s.start()
    await s.start()  # second call is a no-op
    assert s.running
    await s.stop()


@pytest.mark.asyncio
async def test_stop_without_start_is_safe() -> None:
    s = Scheduler()
    await s.stop()  # must not raise


@pytest.mark.asyncio
async def test_remove_cancels_running_task() -> None:
    async def tick() -> None:
        await asyncio.sleep(0)

    s = Scheduler()
    s.add("tick", tick, interval_seconds=0.05)
    await s.start()
    s.remove("tick")
    assert s.task_status("tick") is None
    await s.stop()


def test_build_default_scheduler_has_three_tasks() -> None:
    s = build_default_scheduler()
    for name in (
        "cleanup_inactive_sessions",
        "update_analytics_rollups",
        "process_queued_operations",
    ):
        st = s.task_status(name)
        assert st is not None
        assert st["interval"] == DEFAULT_INTERVAL_SECONDS
