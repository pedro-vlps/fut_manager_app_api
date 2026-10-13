"""Backfill/rotação transacional. Execute com a API parada: poetry run python -m scripts.encrypt_personal_data."""
import asyncio
from sqlalchemy import text
from src.configs.db_connection import engine
from src.helpers.privacy import PREFIX, cipher, email_lookup


async def main():
    encryption = cipher()
    async with engine.begin() as db:
        for table, columns in [('profiles', ['name', 'email', 'avatar_url']),
                               ('group_guests', ['name']), ('championship_matches', ['actions']),
                               ('group_seasons', ['archived_rankings'])]:
            # Tabelas e colunas são constantes internas, nunca entrada do usuário.
            rows = (await db.execute(text(f"SELECT id, {', '.join(columns)} FROM {table} FOR UPDATE"))).mappings().all()
            for row in rows:
                values = {}
                for column in columns:
                    value = row[column]
                    if value is None:
                        continue
                    plain = encryption.decrypt(value[len(PREFIX):].encode()).decode() if value.startswith(PREFIX) else value
                    values[column] = PREFIX + encryption.encrypt(plain.encode()).decode()
                    if column == 'email':
                        values['email_lookup'] = email_lookup(plain)
                if values:
                    assignments = ', '.join(f'{column} = :{column}' for column in values)
                    await db.execute(text(f'UPDATE {table} SET {assignments} WHERE id = :id'), dict(values, id=row['id']))
        await db.execute(text('ALTER TABLE profiles ALTER COLUMN email_lookup SET NOT NULL'))
    await engine.dispose()
    print('Dados pessoais migrados. Nenhum dado pessoal ou chave foi exibido.')


if __name__ == '__main__':
    asyncio.run(main())
