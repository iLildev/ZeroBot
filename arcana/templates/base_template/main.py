"""Default Arcana planted-bot template (smart defaults).

A freshly-planted bot now starts with a working onboarding flow out of
the box — no more empty echo-only stubs. The template provides:

* ``/start`` — friendly welcome, captures referral codes
  (``/start ref_<inviter_id>``), and opens the menu.
* ``/help`` — lists what the bot can do.
* ``/info`` — quick stats / about page.
* An inline keyboard menu (Help / Start / Info) so end-users can drive
  the bot by tapping instead of typing.
* Behind the scenes: every interaction is reported back to the Arcana
  platform via the small ``arcana_helpers`` module so the owner can
  see subscriber counts and analytics in the Builder Bot.

All of the platform integration is **opt-in**: if the bot is run
outside Arcana (no ``ARCANA_PLATFORM_URL`` env var), the helper turns
into a no-op and the bot still works as a normal aiogram bot.
"""

import logging
import os

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiohttp import web

from arcana_helpers import register_subscriber, track_event

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("BOT_PORT", "8080"))
BOT_ID = os.getenv("BOT_ID", "unknown")

bot = Bot(token=TOKEN)
dp = Dispatcher()


def _menu_keyboard() -> InlineKeyboardMarkup:
    """Three-button inline keyboard shown on /start."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="ℹ️ Info", callback_data="menu:info"),
                InlineKeyboardButton(text="❓ Help", callback_data="menu:help"),
            ],
            [
                InlineKeyboardButton(text="🚀 Start", callback_data="menu:start"),
            ],
        ]
    )


WELCOME_TEXT = (
    "👋 Welcome!\n\n"
    "I'm a brand-new bot built on Arcana. Tap a button below to "
    "explore — or send /help to see everything I can do."
)
HELP_TEXT = (
    "Available commands:\n\n"
    "/start — show the welcome message and menu\n"
    "/help — this list\n"
    "/info — about this bot"
)
INFO_TEXT = (
    "🪄 Built with Arcana — the multi-tenant Telegram bot platform.\n"
    "Ask the owner to teach me new tricks!"
)


@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject) -> None:
    """Send the welcome message + menu, and register the user as a subscriber.

    A ``/start ref_<id>`` payload (from an invite link) is forwarded to
    the platform so the inviter gets credit.
    """
    user = message.from_user
    if user is None:
        return
    ref = None
    payload = (command.args or "").strip()
    if payload.startswith("ref_"):
        rest = payload[len("ref_"):]
        if rest.isdigit():
            ref = rest

    await register_subscriber(BOT_ID, str(user.id), ref=ref)
    await track_event(BOT_ID, kind="command", name="start", tg_user_id=str(user.id))
    await message.answer(WELCOME_TEXT, reply_markup=_menu_keyboard())


@dp.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    """List the bot's commands."""
    user = message.from_user
    if user is not None:
        await track_event(
            BOT_ID, kind="command", name="help", tg_user_id=str(user.id)
        )
    await message.answer(HELP_TEXT)


@dp.message(Command("info"))
async def cmd_info(message: types.Message) -> None:
    """Show the about page."""
    user = message.from_user
    if user is not None:
        await track_event(
            BOT_ID, kind="command", name="info", tg_user_id=str(user.id)
        )
    await message.answer(INFO_TEXT)


@dp.callback_query()
async def on_button(query: types.CallbackQuery) -> None:
    """Handle taps on the inline-keyboard menu."""
    data = query.data or ""
    user = query.from_user
    if user is not None:
        await track_event(
            BOT_ID, kind="button", name=data, tg_user_id=str(user.id)
        )
    if data == "menu:help":
        await query.message.answer(HELP_TEXT)
    elif data == "menu:info":
        await query.message.answer(INFO_TEXT)
    elif data == "menu:start":
        await query.message.answer(WELCOME_TEXT, reply_markup=_menu_keyboard())
    await query.answer()


# 🌐 Webhook handler.
async def handle_webhook(request: web.Request):
    """Forward an inbound Telegram update to the aiogram dispatcher."""
    data = await request.json()
    update = types.Update.model_validate(data)
    await dp.feed_update(bot, update)
    return web.Response(text="ok")


# 🚀 App definition.
app = web.Application()
app.router.add_post("/webhook", handle_webhook)


if __name__ == "__main__":
    web.run_app(app, port=PORT)
