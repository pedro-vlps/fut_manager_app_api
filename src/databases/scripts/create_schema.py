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
        seasons_sql = (Path(__file__).parent / "migrations/009_group_seasons.sql").read_text(encoding="utf-8-sig")
        await raw.driver_connection.execute(seasons_sql)
        trophies_sql = (Path(__file__).parent / "migrations/010_season_trophies.sql").read_text(encoding="utf-8-sig")
        await raw.driver_connection.execute(trophies_sql)
        schedule_sql = (Path(__file__).parent / "migrations/011_event_schedule.sql").read_text(encoding="utf-8-sig")
        await raw.driver_connection.execute(schedule_sql)
        calendar_sql = (Path(__file__).parent / "migrations/012_season_calendar.sql").read_text(encoding="utf-8-sig")
        await raw.driver_connection.execute(calendar_sql)
        modality_sql = (Path(__file__).parent / "migrations/013_event_modality.sql").read_text(encoding="utf-8-sig")
        await raw.driver_connection.execute(modality_sql)
        goalkeeper_sql = (Path(__file__).parent / "migrations/014_goalkeeper_confirmations.sql").read_text(encoding="utf-8-sig")
        await raw.driver_connection.execute(goalkeeper_sql)
        substitutions_sql = (Path(__file__).parent / "migrations/015_temporary_substitutions.sql").read_text(encoding="utf-8-sig")
        await raw.driver_connection.execute(substitutions_sql)
        draw_sql = (Path(__file__).parent / "migrations/016_draw_settings_and_ratings.sql").read_text(encoding="utf-8-sig")
        await raw.driver_connection.execute(draw_sql)
        championship_sql = (Path(__file__).parent / "migrations/018_cascade_trophies.sql").read_text(encoding="utf-8-sig")
        await raw.driver_connection.execute(championship_sql)
        codes_sql = (Path(__file__).parent / "migrations/019_championship_codes.sql").read_text(encoding="utf-8-sig")
        await raw.driver_connection.execute(codes_sql)
        actions_sql = (Path(__file__).parent / "migrations/020_championship_actions.sql").read_text(encoding="utf-8-sig")
        await raw.driver_connection.execute(actions_sql)
