"""Tiny mock subscriber for testing the event publisher pipeline."""
import asyncio
import json
import os
from aiohttp import web

received: list[dict] = []


async def on_event(request: web.Request) -> web.Response:
    body = await request.json()
    received.append(body)
    print(f"📬 received: {body}")
    return web.json_response({"ok": True})


async def dump(request: web.Request) -> web.Response:
    return web.json_response(received)


async def main():
    app = web.Application()
    app.router.add_post("/events", on_event)
    app.router.add_get("/received", dump)

    port = int(os.getenv("MOCK_PORT", "8765"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    print(f"🎧 mock listener on http://127.0.0.1:{port}")

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
