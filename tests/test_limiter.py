"""Tests for the per-bot token-bucket rate limiter."""

import time

from arcana.core.limiter import RateLimiter


def test_allows_up_to_rate_then_blocks():
    """The bucket starts full: ``rate`` allows in a burst, then refuses."""
    limiter = RateLimiter(rate=5)
    bot_id = "bot-A"

    # First five calls in the same instant should pass.
    allowed = sum(1 for _ in range(5) if limiter.allow(bot_id))
    assert allowed == 5

    # The sixth call (still in the same instant) is denied.
    assert limiter.allow(bot_id) is False


def test_refills_over_time():
    """Tokens accumulate at ``rate`` per second, so waiting allows more calls."""
    limiter = RateLimiter(rate=5)
    bot_id = "bot-B"

    # Drain the bucket.
    for _ in range(5):
        limiter.allow(bot_id)
    assert limiter.allow(bot_id) is False

    # Wait long enough for at least one token to refill (1/5 s).
    time.sleep(0.25)
    assert limiter.allow(bot_id) is True


def test_per_bot_isolation():
    """Draining bot A must not affect bot B's bucket."""
    limiter = RateLimiter(rate=2)
    for _ in range(2):
        limiter.allow("bot-A")
    assert limiter.allow("bot-A") is False
    # bot-B's bucket is untouched.
    assert limiter.allow("bot-B") is True
