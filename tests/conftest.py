"""Shared pytest fixtures.

Sets a few env vars to safe defaults *before* any ``arcana`` module is
imported, so unit tests don't accidentally depend on the developer's
local ``.env``.
"""

import os

# Defensive defaults so importing ``arcana.config`` never crashes in CI.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/test",
)
os.environ.setdefault("ADMIN_TOKEN", "test-token")
