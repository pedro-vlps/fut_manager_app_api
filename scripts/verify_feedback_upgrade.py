"""Valida atualização de um banco legado em PostgreSQL local temporário (porta 55439)."""
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4
from secrets import token_urlsafe
import asyncpg
from cryptography.fernet import Fernet


def main():
    database = 'feedback_upgrade_' + uuid4().hex
    os.environ.update({
        'FUT_MANAGER_ENV_FILE': '', 'FUT_MANAGER_APP_NAME': 'Upgrade verification',
        'FUT_MANAGER_DEBUG': 'false', 'FUT_MANAGER_CREATE_SCHEMA_ON_STARTUP': 'false',
        'FUT_MANAGER_DATABASE_HOST': '127.0.0.1', 'FUT_MANAGER_DATABASE_PORT': '55439',
        'FUT_MANAGER_DATABASE_NAME': database, 'FUT_MANAGER_DATABASE_USER': 'postgres',
        'FUT_MANAGER_DATABASE_PASSWORD': 'isolated-test-only', 'FUT_MANAGER_DATABASE_ECHO': 'false',
        'FUT_MANAGER_PERSONAL_DATA_KEYS': json.dumps([Fernet.generate_key().decode()]),
        'FUT_MANAGER_EMAIL_LOOKUP_KEY': token_urlsafe(48),
    })
    from scripts.apply_feedback_migrations import main as migrate
    from src.configs.db_connection import engine, SessionLocal
    from src.models.entities import Profile
    from src.helpers.privacy import email_lookup

    async def verify():
        admin = await asyncpg.connect(host='127.0.0.1', port=55439, user='postgres', database='postgres')
        connection = None
        try:
            # O nome é gerado internamente e pertence somente a este teste.
            await admin.execute(f'CREATE DATABASE {database}')
            connection = await asyncpg.connect(host='127.0.0.1', port=55439, user='postgres', database=database)
            root = Path(__file__).resolve().parents[1]
            filename = 'src/databases/scripts/create_database.sql' if '--fresh' in sys.argv else 'tests/fixtures/pre_feedback_schema.sql'
            baseline = (root / filename).read_text(encoding='utf-8-sig')
            await connection.execute(baseline)
            if '--fresh' in sys.argv:
                from src.models.championships import Club, Championship
                async with SessionLocal() as db:
                    player = Profile(name='Instalação nova', email='fresh@example.test', password=token_urlsafe(24))
                    db.add(player)
                    await db.flush()
                    club = Club(name='Time', owner_id=player.id)
                    edition = Championship(name='Liga', season='2026', owner_id=player.id, format='league', capacity=3)
                    db.add_all([club, edition])
                    await db.flush()
                    assert len(club.code) == len(edition.code) == 6
                    await db.commit()
                print('Bootstrap SQL atual: OK; códigos, liga ímpar e persistência cifrada funcionam.')
                return
            profile, group, guest, season = [uuid4() for _ in range(4)]
            await connection.execute('INSERT INTO profiles(id,name,email,password_hash,avatar_url,is_active) VALUES($1,$2,$3,$4,$5,true)',
                profile, 'Jogador legado', 'legacy@example.test', 'RESET_REQUIRED', 'avatar-legado')
            await connection.execute('INSERT INTO pelada_groups(id,name,created_by_id) VALUES($1,$2,$3)', group, 'Grupo legado', profile)
            await connection.execute('INSERT INTO group_guests(id,group_id,created_by_id,name) VALUES($1,$2,$3,$4)', guest, group, profile, 'Convidado legado')
            await connection.execute("INSERT INTO group_seasons(id,group_id,number,starts_at,ends_at,archived_rankings) VALUES($1,$2,1,now()-interval '2 days',now()-interval '1 day',$3::jsonb)",
                season, group, json.dumps([{'id': str(profile), 'name': 'Jogador legado', 'goals': 2}]))
            await migrate()
            await migrate()  # Reexecução/rotação preserva os dados e o índice.
            stored = await connection.fetchrow('SELECT name,email,avatar_url,email_lookup FROM profiles WHERE id=$1', profile)
            assert all(stored[column].startswith('enc:v1:') for column in ('name','email','avatar_url'))
            assert stored['email_lookup'] == email_lookup('legacy@example.test')
            assert (await connection.fetchval('SELECT archived_rankings FROM group_seasons WHERE id=$1', season)).startswith('enc:v1:')
            async with SessionLocal() as db:
                person = await db.get(Profile, profile)
                assert (person.name, person.email, person.avatar_url) == ('Jogador legado', 'legacy@example.test', 'avatar-legado')
            print('Upgrade legado e reexecução: OK; dados pessoais preservados e cifrados.')
        finally:
            await engine.dispose()
            if connection is not None:
                await connection.close()
            await admin.execute(f'DROP DATABASE IF EXISTS {database}')
            await admin.close()

    asyncio.run(verify())


if __name__ == '__main__':
    main()
