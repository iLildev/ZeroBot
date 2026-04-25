import time
from collections import defaultdict


class Tracker:
    def __init__(self):
        self.messages = defaultdict(int)
        self.started_at = time.time()

    def track(self, bot_id: str):
        self.messages[bot_id] += 1

    def report(self, bot_id: str) -> str:
        count = self.messages.get(bot_id, 0)
        uptime = int(time.time() - self.started_at)

        bar = "█" * (count % 10) + "░" * (10 - (count % 10))

        return (
            f"📊 Bot Stats\n"
            f"Messages: {count}\n"
            f"Uptime: {uptime}s\n"
            f"Load: [{bar}]\n"
            f"\nPowered by @iLildev"
        )
