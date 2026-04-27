<div align="center">

# Arcana

**A multi-tenant Telegram bot platform with hibernating runtimes,
crystal-based wallet billing, and an autonomous coding agent.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Code style: ruff](https://img.shields.io/badge/lint-ruff-orange)](https://docs.astral.sh/ruff/)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](https://docs.pytest.org/)

</div>

---

## ✨ What is Arcana?

Arcana lets users **plant, manage, and pay for their own Telegram bots
from inside another Telegram bot**. Every planted bot is sandboxed in
its own virtual environment, hibernates when idle, and is woken on
demand by an HTTP gateway that fronts the public Telegram webhook
endpoint.

A natural-language **Builder Agent** (Claude-powered) lives in the same
process tree, so users can describe a feature in plain English / Arabic
and watch the agent write, test, and deploy the code into their bot's
isolated workspace.

> 🇸🇦 **بالعربية**: Arcana منصّة Python لاستضافة بوتات Telegram متعدّدة
> المستأجرين، مع نظام محفظة بعملة "كرستالات"، وعميل برمجة مستقل
> (Builder Agent) يكتب الكود نيابةً عن المستخدم. كل بوت يحصل على بيئة
> معزولة (`venv` خاصّة + منفذ مخصّص) ويدخل في وضع السبات تلقائياً عند
> الخمول.

---

## 🚀 Highlights

| Feature                     | Description                                                                                          |
| --------------------------- | ---------------------------------------------------------------------------------------------------- |
| 🤖 **Multi-tenant hosting** | Each bot runs in its own venv on a dedicated port — full process isolation, zero cross-talk.         |
| 😴 **Hibernation**          | Idle bots are reaped automatically; updates are buffered and replayed on the next wake.              |
| 💎 **Crystal wallet**       | Pay-per-action billing; admins can grant or deduct crystals on demand.                               |
| 🧠 **Builder Agent**        | Claude-powered autonomous coder with `bash`, `read_file`, `write_file`, `list_dir`, and `web_fetch`. |
| 🔐 **Identity layer**       | Phone-verified onboarding (Telegram `request_contact`) with AES-GCM encrypted storage.               |
| 🎛 **BotFather automation** | Manage your bot's name, description, and commands without ever opening @BotFather.                   |
| 👑 **Admin control plane**  | Full CRUD over users, bots, ports, and wallets — over Telegram or HTTP.                              |
| 📡 **Signed events**        | Fire-and-forget HMAC-signed events keep the Manager Bot in sync with platform actions.               |

---

## 🏗 Architecture

```
            ┌────────────────────────┐
            │   Telegram update      │
            └───────────┬────────────┘
                        ▼
                ┌───────────────┐         ┌────────────────┐
                │   Gateway     │ ◀────▶ │  Wake Buffer    │
                │ (FastAPI)     │         │  Rate Limiter  │
                └───────┬───────┘         │  Hibernator    │
                        │                  └────────────────┘
                        ▼
            ┌────────────────────────┐
            │     Orchestrator       │
            │  (DB · venv · runtime) │
            └───────────┬────────────┘
                        │
       ┌────────────────┼────────────────┐
       ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Admin        │ │ Builder      │ │ Manager Bot  │
│ Console API  │ │ Agent        │ │ (Telegram)   │
└──────────────┘ └──────────────┘ └──────────────┘
```

**Five long-running services** make up a deployment:

| Service       | Module                       | Default port      | Role                                                         |
| ------------- | ---------------------------- | ----------------- | ------------------------------------------------------------ |
| Gateway       | `arcana.core.gateway:app`    | `8001`            | Public Telegram webhook ingress, dispatches to bot processes |
| User Console  | `arcana.api.user_console:app`| `8000`            | Wallet + bot management for end-users                        |
| Admin Console | `arcana.api.admin_console:app`| `8002`           | Privileged operator API (gated by `ADMIN_TOKEN`)             |
| Builder Bot   | `arcana.bots.builder_bot.main`| Telegram polling | Conversational front-end to the Builder Agent                |
| Manager Bot   | `arcana.bots.manager_bot.main`| Telegram + 8003  | Admin control plane over Telegram + inbound `/events`        |

---

## 📁 Repository layout

```text
arcana/                       # main Python package
├── __init__.py
├── config.py                 # Pydantic settings (env-driven)
├── main.py                   # DB bootstrap + additive migrations + seeding
│
├── agents/                   # Builder Agent
│   ├── builder_agent.py      #   the conversation loop + tool dispatch
│   ├── llm.py                #   Anthropic Claude client wrapper
│   ├── sandbox.py            #   per-user sandboxed workspace
│   ├── tools.py              #   tool schemas exposed to Claude
│   └── cli_test.py           #   interactive REPL for local debugging
│
├── analytics/                # in-memory traffic counters per bot
│
├── api/                      # FastAPI services
│   ├── admin_console.py      #   /admin/* — user, bot, port, wallet CRUD
│   └── user_console.py       #   /users/* /bots/* — end-user surface
│
├── botfather/                # BotFather automation (Bot API self-mgmt)
│   ├── client.py             #   async wrapper around set/get-* endpoints
│   └── service.py            #   ownership checks + audit logging
│
├── bots/                     # standalone first-party Telegram bots
│   ├── builder_bot/main.py   #   Builder Agent's Telegram interface
│   └── manager_bot/main.py   #   Admin control plane over Telegram
│
├── core/                     # platform runtime
│   ├── gateway.py            #   the public webhook entry-point
│   ├── orchestrator.py       #   plant / wake / reap state machine
│   ├── runtime_manager.py    #   per-bot subprocess lifecycle
│   ├── wake_buffer.py        #   updates received during cold start
│   ├── limiter.py            #   per-user / per-bot rate limiting
│   └── delivery.py           #   subprocess → bot HTTP delivery
│
├── database/                 # async SQLAlchemy 2.0 layer
│   ├── engine.py             #   engine + AsyncSessionLocal + Base
│   ├── models.py             #   ORM tables (User, Bot, BotOwnerSession, …)
│   ├── port_registry.py      #   port allocation table
│   └── wallet.py             #   atomic crystal grant / deduct
│
├── events/                   # fire-and-forget event publisher
│
├── hibernation/              # idle-detection watchdog
│
├── identity/                 # Phase 0: phone identity layer
│   ├── phone.py              #   E.164 normalization
│   ├── quota.py              #   per-phone bot quota enforcement
│   └── sessions.py           #   encrypted MTProto session storage
│
├── isolation/                # per-bot virtualenv lifecycle
│
├── security/                 # crypto primitives
│   ├── crypto.py             #   AES-GCM + HMAC-SHA256
│   └── keys.py               #   env-driven key resolver (with dev fallback)
│
└── templates/                # starter templates copied into new bots
    └── base_template/

tests/                        # pytest suite (unit + integration)
docker-compose.yml            # full local stack: postgres + 5 services
Dockerfile                    # single base image used by every service
.env.example                  # documented set of all environment variables
pyproject.toml                # project metadata + ruff config + hatchling
Makefile                      # common dev tasks (install, lint, test, …)
```

---

## ⚡ Quick start

### Prerequisites

- Python **3.11+** (3.12 supported)
- A reachable **PostgreSQL 14+** instance
- Two **Telegram bot tokens** (one for Builder Bot, one for Manager Bot)
- An **Anthropic API key** — provided automatically by Replit's AI Integrations,
  or set `AI_INTEGRATIONS_ANTHROPIC_API_KEY` manually elsewhere.

### 1. Install

```bash
git clone https://github.com/iLildev/arcana.git
cd arcana
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp .env.example .env
$EDITOR .env       # fill in DATABASE_URL, ADMIN_TOKEN, bot tokens, …
```

`.env.example` is the source of truth for every supported variable — it
documents what each key does and what the safe default looks like.

### 3. Bootstrap the database

```bash
python -m arcana.main
```

This creates tables, applies any new additive column migrations, seeds
the port registry from `PORT_RANGE_START..PORT_RANGE_END`, and bootstraps
the admin user defined by `ADMIN_USER_ID`.

The bootstrap is **idempotent**: it is safe — and recommended — to run
on every boot. Only additive `ADD COLUMN IF NOT EXISTS` statements are
issued; primary keys and existing columns are never touched.

### 4. Run the services

Each component is a separate process. Start them in separate terminals
or behind your favourite supervisor:

```bash
# 1. Public Telegram webhook ingress (port 8001)
uvicorn arcana.core.gateway:app --host 0.0.0.0 --port 8001

# 2. End-user wallet + bot management API (port 8000)
uvicorn arcana.api.user_console:app --host 0.0.0.0 --port 8000

# 3. Privileged admin API, gated by X-Admin-Token (port 8002)
uvicorn arcana.api.admin_console:app --host 0.0.0.0 --port 8002

# 4. Builder Agent over Telegram (long polling)
python -m arcana.bots.builder_bot.main

# 5. Admin control plane over Telegram (long polling + /events on 8003)
python -m arcana.bots.manager_bot.main
```

### 5. (Optional) Use the REPL instead of Telegram

Useful for testing the Builder Agent without provisioning a bot:

```bash
python -m arcana.agents.cli_test --user my-test-user
```

### 🐳 ...or run everything with Docker

A `Dockerfile` and `docker-compose.yml` are provided for one-command
bring-up. Compose starts Postgres, runs the bootstrap migration as a
one-shot, then boots all five services:

```bash
cp .env.example .env  # fill in MANAGER_BOT_TOKEN, BUILDER_BOT_TOKEN, etc.
docker compose up --build
```

Builder Agent sessions and per-user workspaces are persisted in the
named volume `builder_sessions`.

---

## 🧠 Builder Agent tools

The agent runs every action through its sandbox at
`runtime_envs/builder_sessions/{user_id}/workspace`.

| Tool         | Purpose                                                          |
| ------------ | ---------------------------------------------------------------- |
| `bash`       | Run a shell command in the workspace (timeout 30s, output ≤ 8KB) |
| `read_file`  | Read a UTF-8 text file (≤ 64KB)                                  |
| `write_file` | Create or overwrite a UTF-8 text file                            |
| `list_dir`   | List the entries of a workspace directory                        |
| `web_fetch`  | HTTP GET a URL (≤ 64KB body)                                     |

All file paths are resolved through `SandboxManager.resolve`, which
rejects absolute paths, parent escapes, and symlinks that leave the
workspace. Bash subprocesses run with `setrlimit` caps on CPU time,
memory, file size, and process count (Linux only — see
`SANDBOX_*` env vars).

> ⚠️ **Trust model**: filesystem-level sandboxing is sufficient for
> trusted users (the platform owner + invited collaborators). For
> untrusted multi-tenant use, layer namespaces / nsjail / containers in
> a follow-up phase.

---

## 🔐 Identity & security (Phase 0)

Arcana enforces a Telegram phone-verification gate before any bot is
created or any Builder Agent turn runs (admins are exempt; can be
globally disabled via `REQUIRE_PHONE_VERIFICATION=false` for tests).

- **`arcana/security/`** — versioned AES-GCM envelopes (with AAD) and
  HMAC-SHA256 helpers. Master keys resolved from env, with a
  deterministic dev fallback **and a loud warning** when unset.
- **`arcana/identity/`** — phone normalization to E.164, HMAC-based
  dedup (so we never store plaintext phones), per-phone bot quota,
  and encrypted MTProto session storage.
- **DB additions** — `User` gained `phone_encrypted` (BYTEA),
  `phone_hash` (unique partial index), `phone_verified_at`, `bot_quota`.
  New tables: `bot_owner_sessions`, `phone_verification_log`,
  `botfather_operations`. All additive — existing deployments upgrade
  cleanly via `python -m arcana.main`.
- **Builder Bot UX** — `request_contact` keyboard on first use;
  `/unlink_phone` for GDPR-style deletion.
- **API contract** — `POST /users/{id}/bots` returns HTTP `403` with
  `phone_verification_required` or `bot_quota_exceeded` when the gate
  fails. Admins can `/unverify`, `/unlink_session`, `/setquota` etc.

See [`SECURITY.md`](SECURITY.md) for the vulnerability-reporting
process and operator hardening checklist.

---

## 🎛 BotFather automation (Phase 1)

End-users manage their planted bots' public profile (name,
descriptions, slash-commands) **from inside Arcana** — without ever
opening @BotFather. Photo uploads, token rotation, and bot deletion
ship in a follow-up phase that needs an MTProto user session.

- **`arcana/botfather/client.py`** — async wrapper over the Telegram
  Bot API self-management endpoints (`getMe`, `set/getMyName`,
  `set/getMyDescription`, `set/getMyShortDescription`,
  `set/getMyCommands`, `deleteMyCommands`). Local validation matches
  Telegram's documented limits so we fail fast.
- **`arcana/botfather/service.py`** — `fetch_bot_profile()` and
  `update_bot_profile()` enforce ownership (`bot.user_id == caller`)
  and write a `BotFatherOperation` audit row per attempted op. Partial
  updates only hit the fields the caller passes.
- **HTTP** — `GET/PATCH /users/{uid}/bots/{bid}/profile` accept any
  subset of `{name, description, short_description, commands}`.
- **Telegram** — `/mybots`, `/profile <bot_id>`, `/setname <bot_id>
  <name>`, `/setdesc <bot_id> <desc>`, `/setabout <bot_id> <about>`.

---

## 🛠 Development

```bash
# Install runtime + dev dependencies (ruff, pytest, pre-commit).
make install

# Lint, format-check, and run the test suite — same gate as CI.
make check

# Or invoke the underlying tools directly:
ruff check arcana tests
ruff format arcana tests
pytest

# Optional: install the git hook so commits auto-format before they land.
pre-commit install
```

The CI workflow runs `make check` against Python 3.11 and 3.12 on every
push and PR (`.github/workflows/ci.yml`).

### Running the test suite

Tests live under `tests/` at the repo root and use an **in-memory
SQLite database** (`aiosqlite`) so no external services are required.
Telegram and HTTP clients are stubbed via `httpx.MockTransport`, so the
suite is fully hermetic.

```bash
pytest                         # full suite (~6s)
pytest tests/test_crypto.py    # one file
pytest -k "phone"              # filter by name
```

---

## 🌍 Internationalisation

Arcana ships with first-class Arabic support:

- The **Builder Agent** accepts Arabic prompts and answers in Arabic.
- The **Manager Bot** menu and the **Builder Bot** keyboards are
  bilingual.
- All user-facing error messages are translated; see the `_ar()`
  helpers inside `arcana/bots/`.

Code-level docstrings stay in English (the lingua franca of Python),
but **non-trivial design decisions are annotated in Arabic** explaining
*why* the code is shaped the way it is. PRs that add new modules are
welcome to follow the same convention.

---

## 🧭 Roadmap

| Phase | Status | Theme                                                              |
| ----- | ------ | ------------------------------------------------------------------ |
| 0     | ✅ done | Identity layer: phone verification + encrypted storage             |
| 1.أ   | ✅ done | Wallet + crystal billing                                           |
| 1.ب   | ✅ done | Hibernation + wake buffer + rate limiting                          |
| 1.ج   | ✅ done | BotFather automation (Bot API portion)                             |
| 2     | 🚧 wip | MTProto user-session: photo upload, token rotation, bot deletion   |
| 3     | 🔜 next | Namespace-level sandboxing for untrusted multi-tenant use          |
| 4     | 🔜 next | Web admin dashboard (read-only first, then mutations)              |

---

## 🤝 Contributing

Pull requests, bug reports, and design discussions are welcome — see
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the full guide.

A few things to keep in mind:

1. Keep PRs **focused**: one logical change per PR.
2. Match the existing style. `ruff` is the source of truth — run
   `make check` before pushing.
3. Don't break public APIs (`/admin/*`, `/users/*`, `/bots/*`)
   without an issue discussion first.

---

## 📜 License

[MIT](LICENSE) © 2026 iLildev — use it, fork it, ship it.

---

## 🇸🇦 نظرة سريعة بالعربية

**Arcana** منصّة Python لاستضافة بوتات Telegram متعدّدة المستأجرين، مع
عميل برمجة مستقل (Builder Agent) يعتمد Claude. كل بوت يُزرع داخل بيئة
معزولة (`venv` خاصّة + منفذ مخصّص) ويدخل في وضع السبات تلقائياً عند
الخمول. تُحاسَب العمليّات بعملة *كرستالات* داخل محفظة لكل مستخدم.

### المكوّنات الخمسة

| الخدمة         | المسار                            | الوصف                                          |
| -------------- | --------------------------------- | ---------------------------------------------- |
| Gateway        | `arcana.core.gateway`             | المدخل العامّ لرسائل Telegram.                 |
| User Console   | `arcana.api.user_console`         | محفظة المستخدم وإدارة بوتاته.                  |
| Admin Console  | `arcana.api.admin_console`        | واجهة إدارية محميّة بـ `X-Admin-Token`.        |
| Builder Bot    | `arcana.bots.builder_bot.main`    | واجهة Builder Agent على Telegram.              |
| Manager Bot    | `arcana.bots.manager_bot.main`    | لوحة تحكّم إداريّة على Telegram.               |

### التشغيل السريع

1. انسخ `.env.example` إلى `.env` واملأ القيم.
2. شغّل `python -m arcana.main` لإنشاء قاعدة البيانات وتسجيل المنافذ.
3. ابدأ كلّ خدمة في عمليّة منفصلة كما هو موضّح أعلاه. أو شغّل المنصّة
   بكاملها بأمر واحد عبر Docker:
   ```bash
   cp .env.example .env && docker compose up --build
   ```

### التطوير

- `make install` لتثبيت كل المتطلّبات (تشغيل + تطوير).
- `make check` يشغّل فحص التنسيق والاختبارات (نفس بوّابة CI).
- مجموعة اختبارات `pytest` تغطّي: محدّد المعدّل، مخزن الإيقاظ،
  الصندوق الرملي لـ Builder، توقيع الأحداث (HMAC)، تخزين جلسات Builder
  على القرص، مراقب السبات، طبقة الهوية، وأتمتة BotFather.

### الأمان

ملف [`SECURITY.md`](SECURITY.md) يصف كيفية الإبلاغ عن الثغرات وتوصيات
التشغيل الآمن (توكن المسؤول، توقيع الأحداث، حدود الصندوق الرملي،
إنهاء TLS).

---

<sub>صُنع بحبٍّ بواسطة [@iLildev](https://t.me/iLildev) — Powered by
[Anthropic Claude](https://www.anthropic.com/) and the open-source
Python ecosystem.</sub>
