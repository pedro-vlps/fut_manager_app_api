"""Cria o esquema inicial em ambientes novos.

Em produção, a evolução do esquema deve ser feita por migrations versionadas.
"""

from src.configs.db_connection import engine
from src.models import Base


async def create_schema() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
