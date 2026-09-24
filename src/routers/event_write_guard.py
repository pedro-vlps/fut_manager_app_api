"""Adaptador de dependência das rotas CRUD para o controller de proteção."""

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from src.configs.db_connection import get_db_session
from src.controllers.event_write_guard import check_write


def event_write_guard(model):
    async def guard(request: Request, db: AsyncSession = Depends(get_db_session)):
        return await check_write(model, request, db)

    return guard
