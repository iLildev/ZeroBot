# ZeroBot

> **A multi-tenant platform for hosting hibernating Telegram bots, with a
> wallet-based billing layer and an autonomous coding agent (Builder Agent)
> over Telegram.**

ZeroBot lets users plant, manage, and pay for their own Telegram bots from
inside another Telegram bot. The platform handles isolation (each bot gets
its own virtualenv), lifecycle (wake / hibernate based on traffic), wallet
billing in **crystals**, and an autonomous coding agent that turns
natural-language requests into working code in a sandboxed workspace.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Ruff](https://img.shields.io/badge/lint-ruff-orange)](https://docs.astral.sh/ruff/)

---

## Features

- 🤖 **Multi-tenant bot hosting** — every user gets isolated venvs and ports.
- 💎 **Wallet billing in crystals** — pay-per-action with admin grant/deduct.
- 😴 **Hibernation** — idle bots are reaped; updates are buffered and replayed
  on wake.
- 👑 **Admin control plane** over Telegram — full CRUD over users, bots, and
  ports without leaving Telegram.
- 🧠 **Builder Agent** — Claude-powered autonomous coder with bash, file I/O,
  and web-fetch tools running in a per-user sandbox.
- 📡 **Fire-and-forget events** — the platform notifies the Manager Bot of
  every meaningful action.

## Architecture

```
┌─────────────┐      ┌─────────────┐      ┌──────────────┐
│  Telegram   │─────▶│   Gateway   │─────▶│  Bot process │
└─────────────┘      └──────┬──────┘      └──────────────┘
                            │
                ┌───────────┼───────────┐
                ▼           ▼           ▼
         ┌──────────┐ ┌──────────┐ ┌──────────┐
         │ Wake     │ │ Rate     │ │ Hibernator│
         │ buffer   │ │ limiter  │ │           │
         └──────────┘ └──────────┘ └──────────┘
                            │
                            ▼
                ┌────────────────────────┐
                │   Orchestrator         │
                │ (DB + venv + runtime)  │
                └───────────┬────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
 ┌─────────────┐   ┌─────────────────┐   ┌──────────────┐
 │ Admin       │   │ Builder Agent   │   │ Manager Bot  │
 │ Console API │   │ (Claude + tools)│   │ (Telegram)   │
 └─────────────┘   └─────────────────┘   └──────────────┘
```

## Project layout

```
zerobot/
├── agents/         Builder Agent — Claude + sandbox + tools + REPL
├── analytics/      Per-bot in-memory counters
├── api/            FastAPI services (admin_console, user_console)
├── bots/           Standalone first-party Telegram bots
│   ├── builder_bot/   Builder Agent's Telegram interface
│   └── manager_bot/   Admin control plane over Telegram
├── core/           Gateway, orchestrator, runtime, wake buffer, limiter
├── database/       Async SQLAlchemy engine, models, wallet, port registry
├── events/         Fire-and-forget event publisher
├── hibernation/    Idle-detection watchdog
├── isolation/      Per-bot virtualenv lifecycle
├── templates/      Starter templates copied into freshly planted bots
└── tests/          Helper scripts used during development
```

---

## Quick start

### 1. Install

```bash
git clone https://github.com/iLildev/zerobot.git
cd zerobot
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp .env.example .env
$EDITOR .env       # fill in DATABASE_URL, ADMIN_TOKEN, bot tokens, …
```

See `.env.example` for the full set of supported variables and what each
one does.

### 3. Bootstrap the database

```bash
python -m zerobot.main
```

This creates tables, applies any new additive column migrations, seeds the
port registry from `PORT_RANGE_START..PORT_RANGE_END`, and bootstraps the
admin user defined by `ADMIN_USER_ID`.

### 4. Run the services

Each component is a separate process. Start them in separate terminals (or
behind your favourite supervisor):

```bash
# Public Telegram webhook ingress (port 8001)
uvicorn zerobot.core.gateway:app --host 0.0.0.0 --port 8001

# End-user wallet + bot management API (port 8000)
uvicorn zerobot.api.user_console:app --host 0.0.0.0 --port 8000

# Privileged admin API, gated by X-Admin-Token (port 8002)
uvicorn zerobot.api.admin_console:app --host 0.0.0.0 --port 8002

# Builder Agent over Telegram (long polling)
python -m zerobot.bots.builder_bot.main

# Admin control plane over Telegram (long polling + /events on 8003)
python -m zerobot.bots.manager_bot.main
```

### 5. (Optional) Use the REPL instead of Telegram

Useful for testing the Builder Agent without provisioning a bot:

```bash
python -m zerobot.agents.cli_test --user my-test-user
```

---

## Builder Agent tools

The agent runs every action through its sandbox (`runtime_envs/builder_sessions/{user_id}/workspace`).

| Tool | Purpose |
|------|---------|
| `bash` | Run a shell command in the workspace (timeout 30s, output capped at 8KB). |
| `read_file` | Read a UTF-8 text file (≤64KB). |
| `write_file` | Create or overwrite a UTF-8 text file. |
| `list_dir` | List the entries of a workspace directory. |
| `web_fetch` | HTTP GET a URL (≤64KB body). |

All file paths are resolved through `SandboxManager.resolve`, which rejects
absolute paths, parent escapes, and symlinks that leave the workspace.

---

## Development

```bash
# Install runtime + dev dependencies (ruff, pytest, pre-commit).
make install

# Lint, format-check, and run the test suite — same gate as CI.
make check

# Or invoke the underlying tools directly:
ruff check zerobot tests
ruff format zerobot tests
pytest

# Optional: install the git hook so commits auto-format before they land.
pre-commit install
```

Continuous integration runs `make check` on Python 3.11 and 3.12 for every
push and PR (`.github/workflows/ci.yml`).

### Run the full stack with Docker

A `Dockerfile` and `docker-compose.yml` are provided for one-command bring-up.
Compose starts Postgres, runs the bootstrap migration as a one-shot, then
boots all five services (gateway, user console, admin console, builder bot,
manager bot):

```bash
cp .env.example .env  # fill in MANAGER_BOT_TOKEN, BUILDER_BOT_TOKEN, etc.
docker compose up --build
```

Builder Agent sessions and per-user workspaces are persisted in the named
volume `builder_sessions`.

### Security

See [`SECURITY.md`](SECURITY.md) for the vulnerability-reporting process and
operator-side hardening recommendations (admin token, event signing,
sandbox limits, TLS termination).

See `CONTRIBUTING.md` for the full contributor guide.

---

## نظرة سريعة (بالعربية)

**ZeroBot** منصّة Python لاستضافة بوتات Telegram متعدّدة المستأجرين، مع
عميل برمجة مستقل (Builder Agent) يعتمد Claude. كل بوت يُزرع داخل بيئة
معزولة (venv خاصّة + منفذ مخصّص) ويدخل في وضع السبات تلقائياً عند
الخمول. تُحاسَب العمليّات بعملة "كرستالات" داخل محفظة لكل مستخدم.

### المكوّنات

| الخدمة | المسار | الوصف |
|-------|--------|-------|
| Gateway | `zerobot.core.gateway` | المدخل العامّ لرسائل Telegram. |
| Admin Console | `zerobot.api.admin_console` | واجهة إدارية محميّة بـ `X-Admin-Token`. |
| User Console | `zerobot.api.user_console` | محفظة المستخدم وإدارة بوتاته. |
| Builder Bot | `zerobot.bots.builder_bot.main` | واجهة Builder Agent على Telegram. |
| Manager Bot | `zerobot.bots.manager_bot.main` | لوحة تحكّم إداريّة على Telegram. |

### التشغيل

1. انسخ `.env.example` إلى `.env` واملأ القيم.
2. شغّل `python -m zerobot.main` لإنشاء قاعدة البيانات وتسجيل المنافذ.
3. ابدأ كلّ خدمة في عمليّة منفصلة كما هو موضّح في القسم الإنجليزي أعلاه.
   أو شغّل المنصّة بكاملها بأمر واحد عبر Docker:
   `cp .env.example .env && docker compose up --build`.

### التطوير والاختبار

- `make install` لتثبيت كل المتطلّبات (تشغيل + تطوير).
- `make check` يشغّل فحص التنسيق والاختبارات (نفس بوّابة CI).
- مجموعة اختبارات `pytest` تغطّي: محدّد المعدّل، مخزن الإيقاظ،
  الصندوق الرملي لـ Builder، توقيع الأحداث (HMAC)، تخزين جلسات Builder
  على القرص، ومراقب السبات.

### الأمان

ملف `SECURITY.md` يصف كيفية الإبلاغ عن الثغرات وتوصيات التشغيل الآمن
(توكن المسؤول، توقيع الأحداث، حدود الصندوق الرملي، إنهاء TLS).

---

## License

[MIT](LICENSE) © 2026 iLildev

---

<sub>Powered by [@iLildev](https://t.me/iLildev)</sub>
