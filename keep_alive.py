"""Tiny Flask "keep-alive" server used with external uptime monitors.

Some hosts (Replit free tier, Glitch, etc.) idle a project's process
when there's been no inbound HTTP traffic for a while. Pinging
``/health`` from an uptime monitor (Better Uptime, UptimeRobot,
healthchecks.io, …) every few minutes keeps the project warm.

Run this file as its own process **alongside** the main bot — never
inside it — so a Flask exception can never crash aiogram, and vice
versa::

    python keep_alive.py

Configurable via environment:

* ``KEEPALIVE_HOST`` — bind address (default ``0.0.0.0``)
* ``KEEPALIVE_PORT`` — port to listen on (default ``8000``)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from flask import Flask, jsonify

_BOOT_AT = datetime.now(UTC).isoformat()


def create_app() -> Flask:
    """Build the Flask app. Factory pattern so tests can call it freely."""
    app = Flask(__name__)

    @app.route("/")
    @app.route("/health")
    def health():
        """Return a 200 with a tiny JSON payload — enough for any monitor."""
        return jsonify(
            {
                "status": "ok",
                "service": "arcana-keep-alive",
                "started_at": _BOOT_AT,
            }
        )

    return app


app = create_app()


def main() -> None:
    """Start the Flask dev server. Production users typically run via gunicorn."""
    host = os.environ.get("KEEPALIVE_HOST", "0.0.0.0")
    port = int(os.environ.get("KEEPALIVE_PORT", "8000"))
    # ``debug=False`` so Flask doesn't try to spawn the reloader subprocess
    # in an environment where stdin is closed (e.g. systemd, PM2).
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
