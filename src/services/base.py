"""Persistência compartilhada; sem regras de negócio ou respostas HTTP."""

from sqlalchemy.ext.asyncio import AsyncSession


class DatabaseService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, model, identifier):
        return await self.db.get(model, identifier)

    def add(self, entity):
        self.db.add(entity)

    async def delete(self, entity):
        await self.db.delete(entity)

    async def flush(self):
        await self.db.flush()

    async def refresh(self, entity):
        await self.db.refresh(entity)

    async def commit(self):
        await self.db.commit()

    async def rollback(self):
        await self.db.rollback()
