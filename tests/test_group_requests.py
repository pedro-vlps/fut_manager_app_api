import unittest
from uuid import uuid4
from fastapi import Depends
from api_crud_generate_libary.routers.router import Router
from src.models import CRUD_MODELS
from src.models.entities import GroupMember, PeladaGroup, Profile
from src.models.enums import GroupRole, MembershipStatus
from src.routers.group_requests import router as requests_router
from src.routers.groups import router as groups_router
from src.routers.event_write_guard import event_write_guard
from tests.test_auth import AuthTestCase


class GroupRequestsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = AuthTestCase.asyncSetUp
    asyncTearDown = AuthTestCase.asyncTearDown
    login = AuthTestCase.login

    async def setup_group(self):
        self.app.include_router(requests_router)
        self.app.include_router(groups_router)
        group = PeladaGroup(name="Grupo de pedidos", created_by_id=self.other.id)
        self.db.add(group)
        await self.db.flush()
        self.applicant_headers = {"Authorization": "Bearer " + (await self.login()).json()["access_token"]}
        self.owner_headers = {"Authorization": "Bearer " + (await self.login(self.other, "test-password-456")).json()["access_token"]}
        return group

    async def test_request_is_private_idempotent_and_owner_approval_grants_access(self):
        group = await self.setup_group()
        search_url = "/group-discovery/search"
        self.assertEqual((await self.client.get(search_url, params={"code": group.code})).status_code, 401)
        self.assertEqual((await self.client.get(search_url, params={"code": "bad"}, headers=self.applicant_headers)).status_code, 422)
        result = await self.client.get(search_url, params={"code": group.code.lower()}, headers=self.applicant_headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["membership"], "none")
        self.assertNotIn("created_by_id", result.json())
        base = f"/my-groups/{group.id}"
        url = f"/group-discovery/{group.id}/requests"
        first = await self.client.post(url, headers=self.applicant_headers)
        self.assertEqual(first.status_code, 200, first.text)
        second = await self.client.post(url, headers=self.applicant_headers)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual((await self.client.get(base, headers=self.applicant_headers)).status_code, 404)
        self.assertEqual((await self.client.get(base + "/requests", headers=self.applicant_headers)).status_code, 404)
        pending = await self.client.get(base + "/requests", headers=self.owner_headers)
        self.assertEqual(len(pending.json()), 1)
        review_url = base + "/requests/" + first.json()["id"]
        approved = await self.client.post(review_url, json={"decision": "approve"}, headers=self.owner_headers)
        self.assertEqual(approved.status_code, 200, approved.text)
        groups = (await self.client.get('/auth/me/groups', headers=self.applicant_headers)).json()
        self.assertEqual(groups[0]["role"], "member")
        self.assertFalse((await self.client.get(base, headers=self.applicant_headers)).json()["can_manage"])
        self.assertEqual((await self.client.get(base + "/requests", headers=self.applicant_headers)).status_code, 403)
        self.assertEqual((await self.client.post(review_url, json={"decision": "approve"}, headers=self.applicant_headers)).status_code, 403)
        self.assertEqual((await self.client.post(review_url, json={"decision": "approve"}, headers=self.owner_headers)).status_code, 409)
        self.assertEqual((await self.client.post(url, headers=self.applicant_headers)).status_code, 409)

    async def test_admin_can_reject_and_approve_but_blocked_admin_cannot(self):
        group = await self.setup_group()
        admin = Profile(name="Admin", email=f"{uuid4()}@example.test", password="test-password-123")
        self.db.add(admin)
        await self.db.flush()
        membership = GroupMember(group_id=group.id, profile_id=admin.id, role=GroupRole.ADMIN, status=MembershipStatus.ACTIVE)
        self.db.add(membership)
        await self.db.flush()
        headers = {"Authorization": "Bearer " + (await self.login(admin)).json()["access_token"]}
        url = f"/group-discovery/{group.id}/requests"
        item = (await self.client.post(url, headers=self.applicant_headers)).json()
        review_url = f"/my-groups/{group.id}/requests/{item['id']}"
        rejected = await self.client.post(review_url, json={"decision": "reject"}, headers=headers)
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["status"], "rejected")
        self.assertEqual((await self.client.get('/auth/me/groups', headers=self.applicant_headers)).json(), [])
        self.assertEqual((await self.client.post(url, headers=self.applicant_headers)).json()["id"], item["id"])
        membership.status = MembershipStatus.BLOCKED
        await self.db.flush()
        self.assertEqual((await self.client.post(review_url, json={"decision": "approve"}, headers=headers)).status_code, 404)
        membership.status = MembershipStatus.ACTIVE
        await self.db.flush()
        self.assertEqual((await self.client.post(review_url, json={"decision": "approve"}, headers=headers)).status_code, 200)

    async def test_cross_group_requests_blocked_players_and_crud_bypass(self):
        group = await self.setup_group()
        item = (await self.client.post(f"/group-discovery/{group.id}/requests", headers=self.applicant_headers)).json()
        another = PeladaGroup(name="Outro grupo", created_by_id=self.other.id)
        self.db.add(another)
        self.db.add(GroupMember(group_id=group.id, profile_id=self.user.id, role=GroupRole.MEMBER, status=MembershipStatus.BLOCKED))
        await self.db.flush()
        self.assertEqual((await self.client.post(f"/my-groups/{another.id}/requests/{item['id']}", json={"decision":"approve"}, headers=self.owner_headers)).status_code, 404)
        self.assertEqual((await self.client.post(f"/group-discovery/{group.id}/requests", headers=self.applicant_headers)).status_code, 403)
        self.assertEqual((await self.client.post(f"/my-groups/{group.id}/requests/{item['id']}", json={"decision":"approve"}, headers=self.owner_headers)).status_code, 409)
        config = next(c for c in CRUD_MODELS if c['model_class'] is GroupMember)
        self.app.include_router(Router(**{k:v for k,v in config.items() if k not in {'prefix','tags'}}).router,
                                prefix=config['prefix'], dependencies=[Depends(event_write_guard(GroupMember))])
        writes = [r for r in self.app.routes if getattr(r, 'path', '').startswith('/group-members') and 'POST' in getattr(r, 'methods', set())]
        self.assertTrue(writes)
        for route in writes:
            url = route.path.replace('{id_}', str(uuid4()))
            response = await self.client.post(url, json={'group_id':str(group.id), 'profile_id':str(self.user.id), 'role':'owner', 'status':'active'}, headers=self.applicant_headers)
            self.assertEqual(response.status_code, 403, response.text)
