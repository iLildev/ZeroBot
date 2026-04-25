from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.engine import async_session_maker
from database.models import Bot, User
from database.wallet import WalletService
from core.orchestrator import Orchestrator


app = FastAPI(title="ZeroBot User Console")


async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session


# ─────────────── Schemas ───────────────


class BotOut(BaseModel):
    id: str
    user_id: str
    is_active: bool
    is_hibernated: bool
    port: int | None


class WalletOut(BaseModel):
    user_id: str
    balance: int


class CreateBotIn(BaseModel):
    bot_id: str
    token: str


class TopupIn(BaseModel):
    amount: int


def _bot_out(bot: Bot) -> BotOut:
    return BotOut(
        id=bot.id,
        user_id=bot.user_id,
        is_active=bot.is_active,
        is_hibernated=bot.is_hibernated,
        port=bot.port,
    )


# ─────────────── Health ───────────────


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# ─────────────── Wallet ───────────────


@app.get("/users/{user_id}/wallet", response_model=WalletOut)
async def get_wallet(user_id: str, session: AsyncSession = Depends(get_session)):
    # Auto-create user on first wallet access (so onboarding is implicit)
    user = await session.get(User, user_id)
    if not user:
        session.add(User(id=user_id))
        await session.commit()

    wallet = await WalletService(session).get_wallet(user_id)
    return WalletOut(user_id=wallet.user_id, balance=wallet.balance)


@app.post("/users/{user_id}/wallet/topup", response_model=WalletOut)
async def topup_wallet(
    user_id: str,
    body: TopupIn,
    session: AsyncSession = Depends(get_session),
):
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    user = await session.get(User, user_id)
    if not user:
        session.add(User(id=user_id))
        await session.commit()

    service = WalletService(session)
    await service.add(user_id, body.amount)
    wallet = await service.get_wallet(user_id)
    return WalletOut(user_id=wallet.user_id, balance=wallet.balance)


# ─────────────── Bots ───────────────


@app.get("/users/{user_id}/bots", response_model=list[BotOut])
async def list_user_bots(user_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Bot).where(Bot.user_id == user_id))
    return [_bot_out(b) for b in result.scalars().all()]


@app.post("/users/{user_id}/bots", response_model=BotOut, status_code=201)
async def create_bot(
    user_id: str,
    body: CreateBotIn,
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, user_id)
    if not user:
        session.add(User(id=user_id))
        await session.commit()

    existing = await session.get(Bot, body.bot_id)
    if existing:
        raise HTTPException(status_code=409, detail="bot_id already exists")

    orchestrator = Orchestrator(session)

    try:
        await orchestrator.plant_bot(
            bot_id=body.bot_id,
            user_id=user_id,
            token=body.token,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    bot = await session.get(Bot, body.bot_id)
    return _bot_out(bot)


@app.get("/bots/{bot_id}", response_model=BotOut)
async def get_bot(bot_id: str, session: AsyncSession = Depends(get_session)):
    bot = await session.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return _bot_out(bot)


@app.delete("/bots/{bot_id}")
async def stop_bot(bot_id: str, session: AsyncSession = Depends(get_session)):
    bot = await session.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    orchestrator = Orchestrator(session)
    await orchestrator.reap_bot(bot_id)

    bot.is_active = False
    bot.is_hibernated = True
    bot.port = None
    await session.commit()

    return {"status": "stopped"}
