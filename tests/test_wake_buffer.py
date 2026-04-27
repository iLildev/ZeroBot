"""Tests for the in-memory wake buffer."""

import pytest

from arcana.core.wake_buffer import WakeBuffer


@pytest.mark.asyncio
async def test_add_then_flush_returns_in_fifo_order():
    """Updates are returned in the same order they were added."""
    buf = WakeBuffer()
    await buf.add("bot-1", {"id": 1})
    await buf.add("bot-1", {"id": 2})
    await buf.add("bot-1", {"id": 3})

    assert await buf.flush("bot-1") == [{"id": 1}, {"id": 2}, {"id": 3}]


@pytest.mark.asyncio
async def test_flush_clears_the_queue():
    """A second flush returns an empty list."""
    buf = WakeBuffer()
    await buf.add("bot-1", {"x": 1})
    assert await buf.flush("bot-1") == [{"x": 1}]
    assert await buf.flush("bot-1") == []


@pytest.mark.asyncio
async def test_flush_isolated_per_bot():
    """Flushing bot A must not affect bot B's queue."""
    buf = WakeBuffer()
    await buf.add("a", {"x": 1})
    await buf.add("b", {"y": 2})
    assert await buf.flush("a") == [{"x": 1}]
    assert await buf.flush("b") == [{"y": 2}]


@pytest.mark.asyncio
async def test_flush_unknown_bot_is_empty():
    """Flushing a never-touched bot returns an empty list, not a KeyError."""
    buf = WakeBuffer()
    assert await buf.flush("does-not-exist") == []
