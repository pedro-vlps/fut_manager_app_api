"""Integração com PostgreSQL: todos os registros são revertidos ao final.

Execute no ambiente da API: python -m unittest discover -s tests -v
"""

import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.configs.db_connection import engine, get_db_session
from src.models.entities import GroupMember, PeladaGroup, Profile
from src.models.enums import GroupRole, MembershipStatus
from src.routers.auth import _sessions, router


class AuthTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connection = await engine.connect()
        self.transaction = await self.connection.begin()
        self.db = AsyncSession(bind=self.connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
        self.app = FastAPI()
        self.app.include_router(router)

        async def db_override():
            yield self.db

        self.app.dependency_overrides[get_db_session] = db_override
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )
        self.user = Profile(name="Teste A", email=f"{uuid4()}@example.test", is_active=True)
        self.user.password = "test-password-123"
        self.other = Profile(name="Teste B", email=f"{uuid4()}@example.test", is_active=True)
        self.other.password = "test-password-456"
        self.db.add_all([self.user, self.other])
        await self.db.flush()

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.db.close()
        await self.transaction.rollback()
        await self.connection.close()
        await engine.dispose()
        _sessions.clear()

    async def login(self, user=None, password="test-password-123"):
        user = user or self.user
        return await self.client.post("/auth/login", json={
            "email": f" {user.email.upper()} ", "password": password,
        })

class AuthIntegrationTests(AuthTestCase):
    async def test_login_logout_expiry_and_invalid_credentials(self):
        result = await self.login()
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("password_hash", result.text)
        token = result.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        self.assertEqual((await self.client.get("/auth/me/groups", headers=headers)).json(), [])
        self.assertEqual((await self.login(password="incorrect")).status_code, 401)
        missing = await self.client.post("/auth/login", json={"email": "missing@example.test", "password": "incorrect"})
        self.assertEqual(missing.status_code, 401)
        self.assertEqual((await self.client.get("/auth/me/groups")).status_code, 401)
        self.assertEqual((await self.client.get("/auth/me/groups", headers={"Authorization": "Bearer forged"})).status_code, 401)
        await self.client.post("/auth/logout", headers=headers)
        self.assertEqual((await self.client.get("/auth/me/groups", headers=headers)).status_code, 401)
        token = (await self.login()).json()["access_token"]
        _sessions[token] = (self.user.id, datetime.now(timezone.utc) - timedelta(seconds=1))
        self.assertEqual((await self.client.get("/auth/me/groups", headers={"Authorization": f"Bearer {token}"})).status_code, 401)

    async def test_inactive_account_is_denied(self):
        token = (await self.login()).json()["access_token"]
        self.user.is_active = False
        await self.db.flush()
        self.assertEqual((await self.login()).status_code, 401)
        self.assertEqual((await self.client.get("/auth/me/groups", headers={"Authorization": f"Bearer {token}"})).status_code, 401)

    async def test_only_owned_and_active_membership_groups_are_returned(self):
        owned = PeladaGroup(name="A owned", created_by_id=self.user.id)
        active = PeladaGroup(name="B active", created_by_id=self.other.id)
        invited = PeladaGroup(name="C invited", created_by_id=self.other.id)
        blocked = PeladaGroup(name="D blocked", created_by_id=self.other.id)
        unrelated = PeladaGroup(name="E unrelated", created_by_id=self.other.id)
        self.db.add_all([owned, active, invited, blocked, unrelated])
        await self.db.flush()
        for group, status in [(active, MembershipStatus.ACTIVE), (invited, MembershipStatus.INVITED), (blocked, MembershipStatus.BLOCKED)]:
            self.db.add(GroupMember(group_id=group.id, profile_id=self.user.id, role=GroupRole.MEMBER, status=status))
        await self.db.flush()
        token = (await self.login()).json()["access_token"]
        result = await self.client.get("/auth/me/groups", headers={"Authorization": f"Bearer {token}"}, params={"profile_id": str(self.other.id)})
        self.assertEqual(result.status_code, 200)
        self.assertEqual([g["id"] for g in result.json()], [str(owned.id), str(active.id)])
        self.assertEqual([g["role"] for g in result.json()], ["owner", "member"])
        other_token = (await self.login(self.other, "test-password-456")).json()["access_token"]
        other_result = await self.client.get("/auth/me/groups", headers={"Authorization": f"Bearer {other_token}"})
        self.assertNotIn(str(owned.id), [g["id"] for g in other_result.json()])


if __name__ == "__main__":
    unittest.main()
