"""Atualiza um banco existente. Execute com backup e API parada; chaves já configuradas."""
import asyncio
import re
from pathlib import Path
from src.configs.db_connection import engine
from src.helpers.privacy import cipher, email_lookup
from scripts.encrypt_personal_data import main as encrypt_data
from scripts.reconcile_championship_awards import main as reconcile_awards


async def main():
    cipher()
    email_lookup('configuration-check')
    folder = Path(__file__).resolve().parents[1] / 'src/databases/scripts/migrations'
    async with engine.begin() as connection:
        raw = await connection.get_raw_connection()
        for filename in ('025_championship_feedback.sql', '026_personal_data_encryption.sql', '027_starting_goalkeepers.sql'):
            sql = (folder / filename).read_text(encoding='utf-8-sig')
            sql = re.sub(r'(?m)^(BEGIN|COMMIT);\s*$', '', sql)
            await raw.driver_connection.execute(sql)
    await encrypt_data()
    await reconcile_awards()
    print('Migrações, criptografia e premiações atualizadas.')


if __name__ == '__main__':
    asyncio.run(main())
