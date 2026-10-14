"""Cargos da pelada: somente o dono pode promover e remover administradores."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from src.models.enums import GroupRole
from src.schemas.members import GroupMemberRoleRequest
from src.controllers import groups
from src.controllers.lifecycle_support import can_manage


class GroupRoleSchemaTests(unittest.TestCase):
    def test_only_admin_and_member_are_assignable(self):
        for role in ('admin', 'member'):
            self.assertEqual(GroupMemberRoleRequest(role=role).role, role)
        for role in ('owner', '', None, 'ADMIN', 'unknown'):
            with self.subTest(role=role), self.assertRaises(ValidationError):
                GroupMemberRoleRequest(role=role)
        with self.assertRaises(ValidationError):
            GroupMemberRoleRequest()


class GroupRoleControllerTests(unittest.IsolatedAsyncioTestCase):
    def setup_service(self):
        owner = SimpleNamespace(id=uuid4(), name='Dono')
        group = SimpleNamespace(id=uuid4(), created_by_id=owner.id)
        player = SimpleNamespace(id=uuid4(), name='Jogador')
        member = SimpleNamespace(role=GroupRole.MEMBER)
        service = SimpleNamespace(locked_group=AsyncMock(return_value=group), member_for_role=AsyncMock(return_value=member),
                                  flush=AsyncMock(), commit=AsyncMock(), get=AsyncMock(return_value=owner),
                                  active_members=AsyncMock(side_effect=lambda _: [(player, member.role)]))
        return owner, group, player, member, service

    async def test_owner_promotes_and_demotes_with_updated_member_list(self):
        owner, group, player, member, service = self.setup_service()
        with patch.object(groups, 'GroupsService', return_value=service):
            for role in ('admin', 'admin', 'member'):
                result = await groups.update_member_role(group, player.id, GroupMemberRoleRequest(role=role), owner, None)
                self.assertEqual(member.role, GroupRole(role))
                self.assertEqual(next(p.role for p in result if p.id == player.id), role)
                self.assertEqual(next(p.role for p in result if p.id == owner.id), 'owner')
        self.assertEqual(service.commit.await_count, 3)
        service.member_for_role.assert_awaited_with(group.id, player.id)

    async def test_non_owner_cannot_assign_roles(self):
        owner, group, player, member, service = self.setup_service()
        # Administradores, membros e pessoas externas têm IDs diferentes do dono.
        with patch.object(groups, 'GroupsService', return_value=service):
            for actor in (player, SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())):
                with self.assertRaises(HTTPException) as error:
                    await groups.update_member_role(group, player.id, GroupMemberRoleRequest(role='admin'), actor, None)
                self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(member.role, GroupRole.MEMBER)
        service.commit.assert_not_awaited()

    async def test_owner_role_is_protected(self):
        owner, group, _, _, service = self.setup_service()
        with patch.object(groups, 'GroupsService', return_value=service):
            with self.assertRaises(HTTPException) as error:
                await groups.update_member_role(group, owner.id, GroupMemberRoleRequest(role='member'), owner, None)
        self.assertEqual(error.exception.status_code, 422)
        service.member_for_role.assert_not_awaited()
        service.commit.assert_not_awaited()

    async def test_missing_or_non_active_member_cannot_be_promoted(self):
        owner, group, player, _, service = self.setup_service()
        service.member_for_role.return_value = None
        with patch.object(groups, 'GroupsService', return_value=service):
            with self.assertRaises(HTTPException) as error:
                await groups.update_member_role(group, player.id, GroupMemberRoleRequest(role='admin'), owner, None)
        self.assertEqual(error.exception.status_code, 404)
        service.commit.assert_not_awaited()

    async def test_owner_permission_is_rechecked_after_lock(self):
        owner, group, player, _, service = self.setup_service()
        service.locked_group.return_value = SimpleNamespace(id=group.id, created_by_id=uuid4())
        with patch.object(groups, 'GroupsService', return_value=service):
            with self.assertRaises(HTTPException) as error:
                await groups.update_member_role(group, player.id, GroupMemberRoleRequest(role='admin'), owner, None)
        self.assertEqual(error.exception.status_code, 403)
        service.member_for_role.assert_not_awaited()

    async def test_new_role_controls_event_management_on_next_request(self):
        owner, group, player, member, service = self.setup_service()
        permissions = SimpleNamespace(manager_membership=AsyncMock(side_effect=lambda *_: member.role == GroupRole.ADMIN))
        with patch.object(groups, 'GroupsService', return_value=service), \
                patch('src.controllers.lifecycle_support.LifecycleService', return_value=permissions):
            self.assertFalse(await can_manage(None, group, player))
            await groups.update_member_role(group, player.id, GroupMemberRoleRequest(role='admin'), owner, None)
            self.assertTrue(await can_manage(None, group, player))
            await groups.update_member_role(group, player.id, GroupMemberRoleRequest(role='member'), owner, None)
            self.assertFalse(await can_manage(None, group, player))
