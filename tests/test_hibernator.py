"""Tests for the Hibernator's idle-tracking logic."""

import time

from arcana.hibernation.hibernator import Hibernator


def test_touch_resets_idle_timer():
    """A bot that's been touched is not idle."""
    h = Hibernator(timeout=1)
    h.touch("bot-1")
    assert h.is_idle("bot-1") is False


def test_unknown_bot_is_not_idle():
    """An untracked bot is not considered idle (no spurious reaps)."""
    h = Hibernator(timeout=1)
    assert h.is_idle("never-seen") is False


def test_bot_becomes_idle_after_timeout():
    """After ``timeout`` seconds with no touch, the bot is reported idle."""
    h = Hibernator(timeout=0)  # zero-second timeout: anything past now is idle
    h.touch("bot-1")
    time.sleep(0.05)
    assert h.is_idle("bot-1") is True


def test_forget_drops_the_bot():
    """``forget`` is what the reaper uses to take a bot off the radar."""
    h = Hibernator()
    h.touch("bot-1")
    assert "bot-1" in h.last_seen
    h.forget("bot-1")
    assert "bot-1" not in h.last_seen


def test_forget_is_idempotent():
    """Forgetting a never-touched bot does not raise."""
    h = Hibernator()
    h.forget("never-seen")  # no exception
