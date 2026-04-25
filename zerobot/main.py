import asyncio

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from config import settings
from database.engine import engine, AsyncSessionLocal, Base
import database.models  # noqa: F401  - register tables
from database.port_registry import Port  # noqa: F401  - register ports table


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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


async def main():
    await init_db()
    print("✅ Database initialized")
    await seed_ports()


if __name__ == "__main__":
    asyncio.run(main())
