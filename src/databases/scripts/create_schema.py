"""Cria o esquema inicial em ambientes novos.

Em produção, a evolução do esquema deve ser feita por migrations versionadas.
"""

from src.configs.db_connection import engine
from src.models import Base
from pathlib import Path


async def create_schema() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        # create_all não instala funções/defaults SQL. Garante o mesmo comportamento
        # do código do grupo em bancos novos; a migration é idempotente.
        sql = (
            Path(__file__).parent / "migrations/007_group_alpha_numeric_code.sql"
        ).read_text(encoding="utf-8-sig")
        raw = await connection.get_raw_connection()
        await raw.driver_connection.execute(sql)
