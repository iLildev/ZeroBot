"""Top-level WSGI entry point.

This is a thin Flask wrapper that exposes a status / landing page for the
Arcana platform on the public web preview port. The actual platform
services (the FastAPI gateway, admin console, user console, manager bot,
builder bot, etc.) are long-running async processes — see ``arcana/`` and
the README for how to launch them.

Keeping a small WSGI ``app`` here lets ``gunicorn main:app`` succeed on
hosts (like Replit's web preview) that expect a single WSGI callable, so
the project surfaces a useful page instead of a 502.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from flask import Flask, jsonify, render_template_string

_BOOT_AT = datetime.now(UTC).isoformat()


def create_app() -> Flask:
    """Build the landing-page Flask app."""
    app = Flask(__name__)

    @app.get("/health")
    @app.get("/healthz")
    def health():
        return jsonify(
            {
                "status": "ok",
                "service": "arcana-landing",
                "started_at": _BOOT_AT,
            }
        )

    @app.get("/")
    def index():
        return render_template_string(_LANDING_HTML, started_at=_BOOT_AT)

    return app


_LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Arcana — Multi-tenant Telegram bot platform</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b0c10;
      --card: #14161d;
      --fg: #e7e9ee;
      --muted: #9aa3b2;
      --accent: #7c5cff;
      --border: #232634;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      background: radial-gradient(1200px 800px at 20% -10%, #1a1538 0%, var(--bg) 60%);
      color: var(--fg);
      min-height: 100vh;
    }
    .wrap { max-width: 880px; margin: 0 auto; padding: 64px 24px; }
    header { display: flex; align-items: center; gap: 14px; margin-bottom: 28px; }
    .logo {
      width: 44px; height: 44px; border-radius: 12px;
      background: linear-gradient(135deg, #7c5cff, #34d1bf);
      display: grid; place-items: center;
      font-weight: 800; color: #0b0c10;
    }
    h1 { font-size: 28px; margin: 0; letter-spacing: -0.01em; }
    .tag { color: var(--muted); margin-top: 4px; font-size: 14px; }
    .card {
      background: var(--card); border: 1px solid var(--border);
      border-radius: 16px; padding: 22px 24px; margin-top: 18px;
    }
    .card h2 { margin: 0 0 8px; font-size: 16px; letter-spacing: 0.02em; text-transform: uppercase; color: var(--muted); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 10px; }
    .pill {
      padding: 10px 12px; border-radius: 10px; background: #1b1e29;
      border: 1px solid var(--border); font-size: 14px;
    }
    .k { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }
    .v { font-weight: 600; margin-top: 2px; }
    code { background: #1b1e29; padding: 2px 6px; border-radius: 6px; font-size: 13px; }
    a { color: var(--accent); }
    footer { color: var(--muted); margin-top: 28px; font-size: 13px; }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="logo">A</div>
      <div>
        <h1>Arcana</h1>
        <div class="tag">Multi-tenant platform for hibernating Telegram bots, with a wallet-based billing layer and an autonomous coding agent.</div>
      </div>
    </header>

    <div class="card">
      <h2>Status</h2>
      <div class="grid">
        <div class="pill"><div class="k">Landing</div><div class="v">running</div></div>
        <div class="pill"><div class="k">Started at</div><div class="v">{{ started_at }}</div></div>
        <div class="pill"><div class="k">Health</div><div class="v"><a href="/health">/health</a></div></div>
      </div>
    </div>

    <div class="card">
      <h2>Platform services</h2>
      <p style="margin: 6px 0 14px; color: var(--muted);">
        The Telegram-facing services are long-running async processes and are not started by this landing page.
        Configure the required environment variables (see <code>.env.example</code>) and launch them separately.
      </p>
      <div class="grid">
        <div class="pill"><div class="k">Gateway</div><div class="v">arcana.core.gateway:app</div></div>
        <div class="pill"><div class="k">Admin console</div><div class="v">arcana.api.admin_console:app</div></div>
        <div class="pill"><div class="k">User console</div><div class="v">arcana.api.user_console:app</div></div>
        <div class="pill"><div class="k">Bot platform</div><div class="v">arcana.api.bot_platform:app</div></div>
      </div>
    </div>

    <footer>
      See the <code>README.md</code> for setup, architecture, and deployment notes.
    </footer>
  </div>
</body>
</html>
"""


app = create_app()


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=False)
