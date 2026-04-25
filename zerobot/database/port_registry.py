from datetime import datetime, timedelta
from sqlalchemy import Integer, String, DateTime, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession

from database.engine import Base


class Port(Base):
    __tablename__ = "ports"

    port_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="free")
    last_used: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PortManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def reserve_port(self, bot_id: str) -> int:
        result = await self.session.execute(
            select(Port).where(Port.status == "free")
        )
        port = result.scalar_one_or_none()

        if not port:
            raise RuntimeError("No free ports available")

        port.status = "used"
        port.bot_id = bot_id
        port.last_used = datetime.utcnow()

        await self.session.commit()
        return port.port_number

    async def release_port(self, bot_id: str) -> None:
        result = await self.session.execute(
            select(Port).where(Port.bot_id == bot_id)
        )
        port = result.scalar_one_or_none()

        if not port:
            return

        port.status = "cooldown"
        port.bot_id = None
        port.last_used = datetime.utcnow()

        await self.session.commit()

    async def cleanup(self) -> None:
        threshold = datetime.utcnow() - timedelta(seconds=60)

        result = await self.session.execute(
            select(Port).where(
                Port.status == "cooldown",
                Port.last_used < threshold,
            )
        )

        ports = result.scalars().all()

        for port in ports:
            port.status = "free"

        await self.session.commit()
