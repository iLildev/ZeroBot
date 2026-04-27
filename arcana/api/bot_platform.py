"""HTTP callback API used by planted bots.

Planted bots run in their own venv as separate subprocesses and don't
share Arcana's SQLAlchemy session — so when a planted bot wants to
register a new subscriber or emit an analytics event, it POSTs to
this small FastAPI app.

Authentication is the bot's own Telegram token (sent in the
``X-Bot-Token`` header). Anyone holding the token already has full
control of the bot, so this is the same trust boundary Telegram itself
uses — no new secret to leak.

Routes:

* ``POST   /v1/bots/{bot_id}/subscribers`` — register / refresh a sub
* ``DELETE /v1/bots/{bot_id}/subscribers/{tg_user_id}`` — opt-out
* ``POST   /v1/bots/{bot_id}/events`` — record one analytics event
* ``GET    /healthz`` — uncredentialed liveness probe
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from arcana.database.engine import async_session_maker
from arcana.database.models import Bot as BotRow
from arcana.services import bot_analytics, subscribers


async def _session() -> AsyncSession:
    async with async_session_maker() as s:
        yield s


async def _authorize(
    bot_id: str,
    session: AsyncSession,
    token: str | None,
) -> BotRow:
    """Constant-error-message gate: 401 unless token matches stored token."""
    if not token:
        raise HTTPException(status_code=401, detail="missing X-Bot-Token")
    bot = await session.get(BotRow, bot_id)
    if bot is None or bot.token != token:
        # Don't leak whether the bot exists — same response either way.
        raise HTTPException(status_code=401, detail="invalid bot credentials")
    return bot


class SubscribeIn(BaseModel):
    """Body for ``POST /subscribers``."""

    tg_user_id: str = Field(..., min_length=1, max_length=32)
    ref: str | None = Field(default=None, max_length=32)


class EventIn(BaseModel):
    """Body for ``POST /events``."""

    tg_user_id: str | None = Field(default=None, max_length=32)
    kind: Literal[
        "command", "button", "subscribe", "unsubscribe", "broadcast", "invite_used"
    ]
    name: str = Field(..., min_length=1, max_length=64)


def create_app() -> FastAPI:
    """Build the bot-platform FastAPI app. One factory so tests can mount it fresh."""
    app = FastAPI(title="Arcana Bot-Platform Callback API")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/bots/{bot_id}/subscribers", status_code=201)
    async def register(
        bot_id: Annotated[str, Path(min_length=1)],
        body: SubscribeIn,
        session: Annotated[AsyncSession, Depends(_session)],
        x_bot_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        await _authorize(bot_id, session, x_bot_token)
        created = await subscribers.register_subscriber(
            session,
            bot_id=bot_id,
            tg_user_id=body.tg_user_id,
            referrer_id=body.ref,
        )
        if created:
            await bot_analytics.record_event(
                session,
                bot_id=bot_id,
                kind="subscribe",
                name="start",
                tg_user_id=body.tg_user_id,
            )
            if body.ref:
                await bot_analytics.record_event(
                    session,
                    bot_id=bot_id,
                    kind="invite_used",
                    name=body.ref,
                    tg_user_id=body.tg_user_id,
                )
        await session.commit()
        return {"created": created, "tg_user_id": body.tg_user_id}

    @app.delete("/v1/bots/{bot_id}/subscribers/{tg_user_id}", status_code=200)
    async def unregister(
        bot_id: Annotated[str, Path(min_length=1)],
        tg_user_id: Annotated[str, Path(min_length=1, max_length=32)],
        session: Annotated[AsyncSession, Depends(_session)],
        x_bot_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, bool]:
        await _authorize(bot_id, session, x_bot_token)
        removed = await subscribers.unregister_subscriber(
            session, bot_id=bot_id, tg_user_id=tg_user_id
        )
        if removed:
            await bot_analytics.record_event(
                session,
                bot_id=bot_id,
                kind="unsubscribe",
                name="manual",
                tg_user_id=tg_user_id,
            )
        await session.commit()
        return {"removed": removed}

    @app.post("/v1/bots/{bot_id}/events", status_code=201)
    async def event(
        bot_id: Annotated[str, Path(min_length=1)],
        body: EventIn,
        session: Annotated[AsyncSession, Depends(_session)],
        x_bot_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        await _authorize(bot_id, session, x_bot_token)
        await bot_analytics.record_event(
            session,
            bot_id=bot_id,
            kind=body.kind,
            name=body.name,
            tg_user_id=body.tg_user_id,
        )
        await session.commit()
        return {"status": "recorded"}

    return app


# Module-level instance for ``uvicorn arcana.api.bot_platform:app``.
app = create_app()
