"""Exercise the application's generated CRUD contracts with PostgreSQL."""

import unittest
from uuid import uuid4

import httpx

from src.configs.db_connection import get_db_session
from tests.test_auth import AuthTestCase


class CrudIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await AuthTestCase.asyncSetUp(self)
        await self.client.aclose()
        from src.__main__ import app

        self.app = app
        self.previous_overrides = app.dependency_overrides.copy()

        async def database_session():
            yield self.db

        app.dependency_overrides[get_db_session] = database_session
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    async def asyncTearDown(self):
        self.app.dependency_overrides.clear()
        self.app.dependency_overrides.update(self.previous_overrides)
        await AuthTestCase.asyncTearDown(self)

    async def create_group(
        self, name: str = "CRUD integration"
    ) -> dict[str, object]:
        response = await self.client.post(
            "/groups",
            json={
                "name": name,
                "description": "Preserve this description",
                "created_by_id": str(self.user.id),
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    async def test_create_partial_update_read_and_delete(self):
        group = await self.create_group()
        self.assertIsNotNone(group["id"])
        self.assertIsNotNone(group["created_at"])
        self.assertIsNone(group["code"])
        path = f"/groups/{group['id']}"
        updated = await self.client.patch(path, json={"name": "Updated group"})
        self.assertEqual(updated.status_code, 200, updated.text)
        record = updated.json()["data"]
        self.assertEqual(record["name"], "Updated group")
        self.assertEqual(record["description"], group["description"])
        self.assertEqual(record["created_by_id"], group["created_by_id"])
        self.assertEqual((await self.client.get(path)).json()["data"], record)
        empty_patch = await self.client.patch(path, json={})
        self.assertEqual(empty_patch.status_code, 200, empty_patch.text)
        self.assertEqual(empty_patch.json()["data"], record)
        deleted = await self.client.delete(path)
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json(), "Item deleted")
        self.assertEqual((await self.client.get(path)).status_code, 404)
        self.assertEqual((await self.client.delete(path)).status_code, 404)
        # Reads and writes reuse the caller's session after CRUD commits.
        await self.create_group("Another group")

    async def test_single_object_validation_and_missing_identifiers(self):
        payload = {"name": "Rejected", "created_by_id": str(self.user.id)}
        for body in ([payload], [], {}, {**payload, "created_by_id": "invalid"}):
            response = await self.client.post("/groups", json=body)
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual((await self.client.get("/groups")).json(), {"data": []})
        for method in ("GET", "PATCH", "DELETE"):
            # Mutations validate identifiers in the application's write guard.
            invalid_status = 400 if method == "GET" else 422
            for identifier, expected in (
                ("invalid", invalid_status), (str(uuid4()), 404)
            ):
                kwargs = (
                    {"json": {"name": "Missing"}} if method == "PATCH" else {}
                )
                response = await self.client.request(
                    method, f"/groups/{identifier}", **kwargs
                )
                self.assertEqual(response.status_code, expected, response.text)

    async def test_pagination_and_sorting_validation(self):
        await self.create_group("Alpha")
        await self.create_group("Beta")
        params = {
            "page": 1, "items_per_page": 1,
            "order_by": "name", "direction": "desc",
        }
        first = await self.client.get("/groups", params=params)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["data"][0]["name"], "Beta")
        self.assertEqual(first.json()["total_count"], 2)
        self.assertTrue(first.json()["has_more"])
        second = await self.client.get("/groups", params={**params, "page": 2})
        self.assertEqual(second.json()["data"][0]["name"], "Alpha")
        self.assertFalse(second.json()["has_more"])
        for invalid in (
            {"page": 1}, {"items_per_page": 1}, {"order_by": "name"},
            {"order_by": "missing", "direction": "asc"},
            {"order_by": "name", "direction": "invalid"},
        ):
            response = await self.client.get("/groups", params=invalid)
            self.assertEqual(response.status_code, 400, response.text)
        for invalid in ({"page": 0, "items_per_page": 1}, {"items_per_page": 0}):
            response = await self.client.get("/groups", params=invalid)
            self.assertEqual(response.status_code, 422, response.text)

    async def test_foreign_key_conflict_is_safe_and_session_remains_usable(self):
        response = await self.client.post(
            "/groups", json={"name": "Invalid owner", "created_by_id": str(uuid4())}
        )
        self.assertEqual(response.status_code, 409, response.text)
        for private_detail in ("INSERT INTO", "asyncpg", "ForeignKeyViolation"):
            self.assertNotIn(private_detail, response.text)
        listing = await self.client.get("/groups")
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertEqual(listing.json(), {"data": []})

    async def test_openapi_uses_input_schemas_and_profiles_remain_private(self):
        document = self.app.openapi()
        schemas = document["components"]["schemas"]
        for path, post_schema, patch_schema in (
            ("/groups", "PeladaGroupCreateSchema", "PeladaGroupUpdateSchema"),
            ("/guests", "GroupGuestCreateSchema", "GroupGuestUpdateSchema"),
        ):
            for route, method, name in (
                (path, "post", post_schema),
                (path + "/{id_}", "patch", patch_schema),
            ):
                body = document["paths"][route][method]["requestBody"]
                self.assertEqual(
                    body["content"]["application/json"]["schema"]["$ref"],
                    f"#/components/schemas/{name}",
                )
            self.assertFalse(schemas[patch_schema].get("required"))
        for method, path, kwargs in (
            ("GET", "/profiles", {}),
            ("POST", "/profiles", {"json": {}}),
            ("PATCH", f"/profiles/{self.user.id}", {"json": {}}),
        ):
            response = await self.client.request(method, path, **kwargs)
            self.assertEqual(response.status_code, 404, response.text)
