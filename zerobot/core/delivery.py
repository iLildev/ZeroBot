import httpx


class DeliveryManager:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=5.0)

    async def forward(self, port: int, update: dict):
        url = f"http://127.0.0.1:{port}/webhook"

        try:
            await self.client.post(url, json=update)
        except Exception as e:
            raise RuntimeError(f"Delivery failed: {e}")
