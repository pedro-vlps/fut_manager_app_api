"""Verifica as rotas reais de documentação sem iniciar banco ou lifespan."""
import os
import subprocess
import sys
import unittest


class DocsConfigurationTests(unittest.TestCase):
    def check_docs(self, enabled, debug):
        env = dict(os.environ, FUT_MANAGER_DEBUG=debug,
                   FUT_MANAGER_CREATE_SCHEMA_ON_STARTUP='false')
        env.pop('FUT_MANAGER_DOCS_ENABLED', None)
        if enabled is not None:
            env['FUT_MANAGER_DOCS_ENABLED'] = enabled
        expected = 200 if enabled == 'true' else 404
        code = f'''
import asyncio
import httpx
from src.__main__ import app

async def check():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        for path in ['/docs', '/redoc', '/openapi.json', '/docs/oauth2-redirect']:
            response = await client.get(path)
            assert response.status_code == {expected}, (path, response.status_code)
        assert any(getattr(route, 'path', None) == '/championships' for route in app.routes)

asyncio.run(check())
'''
        result = subprocess.run([sys.executable, '-c', code], env=env,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_enabled_with_debug_off(self):
        self.check_docs('true', 'false')

    def test_disabled_with_debug_on(self):
        self.check_docs('false', 'true')

    def test_disabled_by_default(self):
        self.check_docs(None, 'false')
