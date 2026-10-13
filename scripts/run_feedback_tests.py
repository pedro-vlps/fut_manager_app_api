"""Suite isolada; exige PostgreSQL de teste na porta 55439. Não lê o banco do projeto."""
import os
import json
import asyncio
import unittest
import sys
from cryptography.fernet import Fernet
from secrets import token_urlsafe


def main():
    os.environ.update({
        'FUT_MANAGER_ENV_FILE': '', 'FUT_MANAGER_APP_NAME': 'Fut Manager isolated tests',
        'FUT_MANAGER_DEBUG': 'false', 'FUT_MANAGER_CREATE_SCHEMA_ON_STARTUP': 'false',
        'FUT_MANAGER_DOCS_ENABLED': 'false',
        'FUT_MANAGER_DATABASE_HOST': '127.0.0.1', 'FUT_MANAGER_DATABASE_PORT': '55439',
        'FUT_MANAGER_DATABASE_NAME': 'postgres', 'FUT_MANAGER_DATABASE_USER': 'postgres',
        'FUT_MANAGER_DATABASE_PASSWORD': 'isolated-test-only', 'FUT_MANAGER_DATABASE_ECHO': 'false',
        'FUT_MANAGER_PERSONAL_DATA_KEYS': json.dumps([Fernet.generate_key().decode()]),
        'FUT_MANAGER_EMAIL_LOOKUP_KEY': token_urlsafe(48),
    })
    from src.databases.scripts.create_schema import create_schema
    from src.configs.db_connection import engine

    async def prepare():
        await create_schema()
        await engine.dispose()

    asyncio.run(prepare())
    suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:]) if len(sys.argv) > 1 else unittest.defaultTestLoader.discover('tests')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
