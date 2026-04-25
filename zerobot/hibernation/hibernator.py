import asyncio
import time
from collections import defaultdict


class Hibernator:
    def __init__(self, timeout: int = 1800):
        self.timeout = timeout
        self.last_seen: dict[str, float] = defaultdict(lambda: time.time())

    def touch(self, bot_id: str):
        self.last_seen[bot_id] = time.time()

    def is_idle(self, bot_id: str) -> bool:
        return (time.time() - self.last_seen[bot_id]) > self.timeout

    async def monitor(self, orchestrator):
        while True:
            for bot_id in list(self.last_seen.keys()):
                if self.is_idle(bot_id):
                    await orchestrator.reap_bot(bot_id)
            await asyncio.sleep(30)
