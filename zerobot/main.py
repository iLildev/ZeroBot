import asyncio

from database.engine import engine, Base
from config import settings


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def main():
    await init_db()
    print("✅ Database initialized")


if __name__ == "__main__":
    asyncio.run(main())
