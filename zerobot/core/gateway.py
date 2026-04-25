from fastapi import FastAPI, Request, HTTPException
from sqlalchemy import select

from database.engine import AsyncSessionLocal
from database.models import Bot
from core.delivery import DeliveryManager
from core.wake_buffer import wake_buffer


app = FastAPI(title="ZeroBot Gateway")
delivery = DeliveryManager()


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/webhook/{bot_id}")
async def handle_update(bot_id: str, request: Request):
    update = await request.json()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Bot).where(Bot.id == bot_id)
        )
        bot = result.scalar_one_or_none()

        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")

        if not bot.is_active:
            raise HTTPException(status_code=403, detail="Bot is inactive")

        if bot.is_hibernated:
            await wake_buffer.add(bot_id, update)
            # لاحقاً سنضيف:
            # await orchestrator.wake_bot(bot_id)
            return {"status": "buffered"}

        if bot.port is None:
            raise HTTPException(status_code=503, detail="Bot has no port assigned")

        await delivery.forward(bot.port, update)
        return {"status": "delivered"}
