from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Wallet, User
from config import settings


class WalletService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_wallet(self, user_id: str) -> Wallet:
        result = await self.session.execute(
            select(Wallet).where(Wallet.user_id == user_id)
        )
        wallet = result.scalar_one_or_none()

        if not wallet:
            wallet = await self.create_wallet(user_id)

        return wallet

    async def create_wallet(self, user_id: str) -> Wallet:
        wallet = Wallet(
            user_id=user_id,
            balance=settings.INITIAL_CRYSTALS,
        )
        self.session.add(wallet)
        await self.session.commit()
        return wallet

    async def charge(self, user_id: str, amount: int) -> None:
        wallet = await self.get_wallet(user_id)

        if wallet.balance < amount:
            raise RuntimeError("Insufficient crystals")

        wallet.balance -= amount
        await self.session.commit()

    async def add(self, user_id: str, amount: int) -> None:
        wallet = await self.get_wallet(user_id)
        wallet.balance += amount
        await self.session.commit()
