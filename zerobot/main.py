import asyncio

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from config import settings
from database.engine import engine, AsyncSessionLocal, Base
import database.models  # noqa: F401  - register tables
from database.models import User
from database.port_registry import Port  # noqa: F401  - register ports table


# Idempotent additive column migrations. Safe to run on every boot:
# PostgreSQL's `ADD COLUMN IF NOT EXISTS` is non-destructive and skips
# columns that already exist. Primary keys are never touched.
ADDITIVE_MIGRATIONS = [
    "ALTER TABLE bots  ADD COLUMN IF NOT EXISTS is_official BOOLEAN DEFAULT FALSE",
    "ALTER TABLE bots  ADD COLUMN IF NOT EXISTS name        VARCHAR",
    "ALTER TABLE bots  ADD COLUMN IF NOT EXISTS description VARCHAR",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin    BOOLEAN DEFAULT FALSE",
]


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def apply_additive_migrations():
    async with engine.begin() as conn:
        for stmt in ADDITIVE_MIGRATIONS:
            await conn.execute(text(stmt))


async def seed_ports():
    """Seed the ports table from PORT_RANGE_START..PORT_RANGE_END (idempotent)."""
    rows = [
        {"port_number": p, "bot_id": None, "status": "free", "last_used": None}
        for p in range(settings.PORT_RANGE_START, settings.PORT_RANGE_END + 1)
    ]

    async with AsyncSessionLocal() as session:
        stmt = pg_insert(Port).values(rows).on_conflict_do_nothing(
            index_elements=["port_number"]
        )
        await session.execute(stmt)
        await session.commit()

        result = await session.execute(select(Port))
        total = len(result.scalars().all())

    print(f"✅ Seeded ports: {total} total in registry")


async def bootstrap_admin():
    """If ADMIN_USER_ID is set, ensure that user exists and is flagged admin."""
    if not settings.ADMIN_USER_ID:
        print("ℹ️  ADMIN_USER_ID not set — skipping admin bootstrap")
        return

    async with AsyncSessionLocal() as session:
        user = await session.get(User, settings.ADMIN_USER_ID)
        if not user:
            session.add(User(id=settings.ADMIN_USER_ID, is_admin=True))
            await session.commit()
            print(f"✅ Admin user created: {settings.ADMIN_USER_ID}")
        elif not user.is_admin:
            user.is_admin = True
            await session.commit()
            print(f"✅ Admin flag promoted on existing user: {settings.ADMIN_USER_ID}")
        else:
            print(f"✅ Admin user already configured: {settings.ADMIN_USER_ID}")


async def main():
    await init_db()
    print("✅ Database initialized")
    await apply_additive_migrations()
    print("✅ Additive column migrations applied")
    await seed_ports()
    await bootstrap_admin()


if __name__ == "__main__":
    asyncio.run(main())
