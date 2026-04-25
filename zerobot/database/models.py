from datetime import datetime
from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.engine import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    bots = relationship("Bot", back_populates="owner")
    wallet = relationship("Wallet", back_populates="user", uselist=False)


class Bot(Base):
    __tablename__ = "bots"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))

    token: Mapped[str] = mapped_column(String)

    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_hibernated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)

    name: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    port: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    owner = relationship("User", back_populates="bots")


class Wallet(Base):
    __tablename__ = "wallets"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    balance: Mapped[int] = mapped_column(Integer, default=0)

    user = relationship("User", back_populates="wallet")
