import os

from aiohttp import web


routes = web.RouteTableDef()


@routes.post("/webhook")
async def webhook_handler(request):
    data = await request.json()

    print("Received update:", data)

    return web.Response(text="ok")


app = web.Application()
app.add_routes(routes)

port = int(os.getenv("BOT_PORT", 8080))

web.run_app(app, port=port)
