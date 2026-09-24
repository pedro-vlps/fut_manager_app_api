"""Contrato do código gerado no PostgreSQL, sem persistir dados de teste."""

import asyncio
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from src.configs.db_connection import engine
from src.models.entities import PeladaGroup
from tests.test_auth import AuthTestCase


class GroupCodeTests(AuthTestCase):
    async def test_same_name_generated_codes_and_constraints(self):
        groups = [
            PeladaGroup(name="Mesmo nome", created_by_id=self.user.id)
            for _ in range(40)
        ]
        self.db.add_all(groups)
        await self.db.flush()
        codes = [group.code for group in groups]
        self.assertEqual(len(set(codes)), 40)
        for code in codes:
            self.assertRegex(code, r"^[A-Z0-9]{6}$")
        for invalid in [codes[0], "abc", "ABC!12", None]:
            with self.assertRaises(IntegrityError):
                async with self.db.begin_nested():
                    await self.db.execute(
                        text("UPDATE pelada_groups SET code=:code WHERE id=:id"),
                        {"code": invalid, "id": groups[1].id},
                    )
        token = (await self.login()).json()["access_token"]
        response = await self.client.get(
            "/auth/me/groups", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual({item["code"] for item in response.json()}, set(codes))

    async def test_backfill_and_repeated_migration(self):
        group = PeladaGroup(name="Legado", created_by_id=self.user.id)
        self.db.add(group)
        await self.db.flush()
        await self.db.execute(
            text("ALTER TABLE pelada_groups ALTER COLUMN code DROP NOT NULL")
        )
        await self.db.execute(
            text("UPDATE pelada_groups SET code=NULL WHERE id=:id"), {"id": group.id}
        )
        sql = Path(
            "src/databases/scripts/migrations/007_group_alpha_numeric_code.sql"
        ).read_text(encoding="utf-8-sig")
        raw = await self.connection.get_raw_connection()
        await raw.driver_connection.execute(sql)
        await self.db.refresh(group)
        self.assertRegex(group.code, r"^[A-Z0-9]{6}$")
        code = group.code
        await raw.driver_connection.execute(sql)
        await self.db.refresh(group)
        self.assertEqual(group.code, code)

    async def test_concurrent_inserts_without_supplied_code(self):
        async def insert_group():
            async with engine.connect() as connection:
                transaction = await connection.begin()
                try:
                    profile_id = uuid4()
                    await connection.execute(
                        text(
                            "INSERT INTO profiles (id,name,email,password_hash,is_active) VALUES (:id,:name,:email,:hash,true)"
                        ),
                        {
                            "id": profile_id,
                            "name": "Teste concorrência",
                            "email": f"{profile_id}@test.invalid",
                            "hash": "test-only",
                        },
                    )
                    return await connection.scalar(
                        text(
                            "INSERT INTO pelada_groups (id,name,created_by_id) VALUES (:id,:name,:owner) RETURNING code"
                        ),
                        {"id": uuid4(), "name": "Nome repetido", "owner": profile_id},
                    )
                finally:
                    await transaction.rollback()

        codes = await asyncio.gather(*(insert_group() for _ in range(12)))
        self.assertEqual(len(set(codes)), 12)
        self.assertTrue(all(len(code) == 6 and code.isalnum() for code in codes))
