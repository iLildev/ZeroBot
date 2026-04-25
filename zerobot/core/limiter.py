import time


class RateLimiter:
    def __init__(self, rate: int = 5):
        self.rate = rate
        self.tokens = {}
        self.last = {}

    def allow(self, bot_id: str) -> bool:
        now = time.time()

        tokens = self.tokens.get(bot_id, self.rate)
        last = self.last.get(bot_id, now)

        delta = now - last
        tokens = min(self.rate, tokens + delta * self.rate)

        if tokens < 1:
            self.tokens[bot_id] = tokens
            self.last[bot_id] = now
            return False

        self.tokens[bot_id] = tokens - 1
        self.last[bot_id] = now
        return True
