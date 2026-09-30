from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import func, select
from tests.test_auth import AuthTestCase
from src.models import CRUD_MODELS
from src.models.entities import (EventPresence, EventTeam, EventTeamPlayer, GroupDrawSettings, GroupGuest, GroupMember, GroupPlayerRating,
                                 Match, MatchLineup, MatchTeam, PeladaEvent, PeladaGroup, Profile)
from src.models.enums import EventStatus, GroupRole, MembershipStatus, MatchResult, MatchStatus, PresenceStatus, TeamPlayerRole
from src.routers.draw import router as draw_router
from src.routers.groups import router as groups_router
from src.routers.lifecycle import router as lifecycle_router
from src.schemas.draw import DrawSettings
from src.services.team_balance import draw_features


class DrawTests(AuthTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        for router in (draw_router, groups_router, lifecycle_router):
            self.app.include_router(router)
        self.group = PeladaGroup(name="Sorteio privado", created_by_id=self.user.id)
        self.admin = Profile(name="Admin", email=f"{uuid4()}@example.test", password="admin-test-123", is_active=True)
        self.db.add_all([self.group, self.admin])
        await self.db.flush()
        self.member = GroupMember(group_id=self.group.id, profile_id=self.other.id, role=GroupRole.MEMBER, status=MembershipStatus.ACTIVE)
        self.admin_member = GroupMember(group_id=self.group.id, profile_id=self.admin.id, role=GroupRole.ADMIN, status=MembershipStatus.ACTIVE)
        self.db.add_all([self.member, self.admin_member])
        await self.db.flush()
        self.owner_headers = {"Authorization": "Bearer " + (await self.login()).json()["access_token"]}
        self.member_headers = {"Authorization": "Bearer " + (await self.login(self.other, "test-password-456")).json()["access_token"]}
        self.admin_headers = {"Authorization": "Bearer " + (await self.login(self.admin, "admin-test-123")).json()["access_token"]}
        self.base = f"/my-groups/{self.group.id}"
        self.rating_url = self.base + f"/members/{self.other.id}/rating"

    async def test_owner_admin_can_create_edit_clear_rating_without_duplicates(self):
        for value, headers in [(0, self.owner_headers), (10, self.admin_headers), (7.5, self.owner_headers)]:
            response = await self.client.post(self.rating_url, json={"rating": value}, headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {"rating": value})
        response = await self.client.get(self.rating_url, headers=self.admin_headers)
        self.assertEqual(response.json(), {"rating": 7.5})
        self.assertEqual(response.headers["cache-control"], "no-store")
        count = await self.db.scalar(select(func.count()).select_from(GroupPlayerRating).where(GroupPlayerRating.group_id == self.group.id))
        self.assertEqual(count, 1)
        await self.client.post(self.rating_url, json={"rating": None}, headers=self.owner_headers)
        self.assertEqual((await self.client.get(self.rating_url, headers=self.owner_headers)).json(), {"rating": None})

    async def test_rating_range_and_decimal_precision_are_enforced(self):
        for value in (-0.1, 10.1, 7.55, "NaN", "Infinity"):
            response = await self.client.post(self.rating_url, json={"rating": value}, headers=self.owner_headers)
            self.assertEqual(response.status_code, 422, response.text)

    async def test_members_cannot_read_or_write_any_rating(self):
        await self.client.post(self.rating_url, json={"rating": 8.7}, headers=self.owner_headers)
        for target in (self.other, self.user, self.admin):
            url = self.base + f"/members/{target.id}/rating"
            self.assertEqual((await self.client.get(url, headers=self.member_headers)).status_code, 403)
            self.assertEqual((await self.client.post(url, json={"rating": 10}, headers=self.member_headers)).status_code, 403)
        self.assertEqual((await self.client.get(self.rating_url)).status_code, 401)

    async def test_managers_can_read_and_edit_their_own_rating(self):
        for target, headers in ((self.user, self.owner_headers), (self.admin, self.admin_headers)):
            url = self.base + f"/members/{target.id}/rating"
            self.assertEqual((await self.client.post(url, json={"rating": 9.5}, headers=headers)).status_code, 200)
            self.assertEqual((await self.client.get(url, headers=headers)).json(), {"rating": 9.5})
            response = await self.client.get(self.base + f"/members/{target.id}", headers=headers)
            self.assertTrue(response.json()["can_rate"])

    async def test_private_models_and_public_profiles_do_not_expose_ratings(self):
        self.assertFalse(any(item["model_class"] in {GroupPlayerRating, GroupDrawSettings} for item in CRUD_MODELS))
        await self.client.post(self.rating_url, json={"rating": 8.7}, headers=self.owner_headers)
        for suffix in ("/members", f"/members/{self.other.id}", "/rankings"):
            response = await self.client.get(self.base + suffix, headers=self.member_headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertNotIn('"rating"', response.text)
            self.assertNotIn('8.7', response.text)
        member = await self.client.get(self.base + f"/members/{self.other.id}", headers=self.owner_headers)
        self.assertTrue(member.json()["can_rate"])
        own = await self.client.get(self.base + f"/members/{self.other.id}", headers=self.member_headers)
        self.assertFalse(own.json()["can_rate"])

    async def test_scope_and_revoked_admin_access(self):
        other_group = PeladaGroup(name="Outro grupo", created_by_id=self.admin.id)
        self.db.add(other_group)
        await self.db.flush()
        self.db.add(GroupMember(group_id=other_group.id, profile_id=self.other.id, role=GroupRole.MEMBER, status=MembershipStatus.ACTIVE))
        await self.db.flush()
        url = f"/my-groups/{other_group.id}/members/{self.other.id}/rating"
        self.assertEqual((await self.client.get(url, headers=self.owner_headers)).status_code, 404)
        await self.client.post(self.rating_url, json={"rating": 9}, headers=self.owner_headers)
        self.assertEqual((await self.client.get(url, headers=self.admin_headers)).json(), {"rating": None})
        outsider = self.base + f"/members/{uuid4()}/rating"
        self.assertEqual((await self.client.post(outsider, json={"rating": 9}, headers=self.owner_headers)).status_code, 404)
        self.admin_member.role = GroupRole.MEMBER
        await self.db.flush()
        self.assertEqual((await self.client.get(self.rating_url, headers=self.admin_headers)).status_code, 403)

    async def test_draw_settings_are_independent_and_manager_only(self):
        url = self.base + "/draw-settings"
        self.assertEqual((await self.client.get(url, headers=self.owner_headers)).json(), DrawSettings().model_dump())
        for payload in ({"use_positions": True}, {"use_ratings": True}, {"use_wins": True},
                        {"use_positions": True, "use_ratings": True, "use_wins": True}):
            result = await self.client.post(url, json=payload, headers=self.admin_headers)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json(), DrawSettings(**payload).model_dump())
        self.assertEqual((await self.client.post(url, json={}, headers=self.member_headers)).status_code, 403)

    async def test_team_ratings_are_current_private_and_include_manager_self(self):
        event = PeladaEvent(group_id=self.group.id, created_by_id=self.user.id, title="Notas nos times",
            scheduled_at=datetime.now(timezone.utc), status=EventStatus.REGISTRATION_OPEN)
        self.db.add(event)
        await self.db.flush()
        team = EventTeam(event_id=event.id, name="Time de teste")
        guest = GroupGuest(group_id=self.group.id, created_by_id=self.user.id, name="Convidado sem nota")
        self.db.add_all([team, guest])
        await self.db.flush()
        url = self.base + f"/events/{event.id}/team-ratings"
        self.assertEqual((await self.client.get(url, headers=self.owner_headers)).json(), {})
        for person, rating in ((self.user, 9.4), (self.other, 8.5), (self.admin, 7.2)):
            self.db.add(GroupPlayerRating(group_id=self.group.id, profile_id=person.id,
                rating=Decimal(str(rating)), updated_by_id=self.user.id))
        # Admin não foi escalado e, portanto, sua nota não pertence à resposta.
        self.db.add_all([EventTeamPlayer(team_id=team.id, profile_id=self.user.id, role=TeamPlayerRole.PLAYER),
                         EventTeamPlayer(team_id=team.id, profile_id=self.other.id, role=TeamPlayerRole.PLAYER),
                         EventTeamPlayer(team_id=team.id, guest_id=guest.id, role=TeamPlayerRole.PLAYER)])
        await self.db.flush()
        response = await self.client.get(url, headers=self.owner_headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {str(self.user.id): 9.4, str(self.other.id): 8.5, str(guest.id): None})
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual((await self.client.get(url, headers=self.member_headers)).json(), {})
        admin_response = await self.client.get(url, headers=self.admin_headers)
        self.assertEqual(admin_response.json()[str(self.user.id)], 9.4)
        self.assertEqual((await self.client.get(url)).status_code, 401)
        changed = await self.client.post(self.rating_url, json={"rating": 0}, headers=self.owner_headers)
        self.assertEqual(changed.status_code, 200)
        self.assertEqual((await self.client.get(url, headers=self.owner_headers)).json()[str(self.other.id)], 0)
        event.status = EventStatus.FINISHED
        await self.db.flush()
        self.assertEqual((await self.client.get(url, headers=self.owner_headers)).json()[str(self.other.id)], 0)
        wrong_group = PeladaGroup(name="Sem acesso", created_by_id=self.admin.id)
        self.db.add(wrong_group)
        await self.db.flush()
        wrong_url = f"/my-groups/{wrong_group.id}/events/{event.id}/team-ratings"
        self.assertEqual((await self.client.get(wrong_url, headers=self.owner_headers)).status_code, 404)
        self.assertEqual((await self.client.get(wrong_url, headers=self.admin_headers)).status_code, 404)

    async def test_random_draw_uses_latest_ratings_without_leaking_them(self):
        people = [self.user, self.other, self.admin]
        for i in range(3):
            person = Profile(name=f"Jogador {i}", email=f"{uuid4()}@example.test", password="test-password")
            self.db.add(person)
            people.append(person)
        await self.db.flush()
        event = PeladaEvent(group_id=self.group.id, created_by_id=self.user.id, title="Sorteio",
            scheduled_at=datetime.now(timezone.utc) + timedelta(days=1), modality="campo",
            min_confirmed_players=6, status=EventStatus.REGISTRATION_OPEN)
        self.db.add(event)
        await self.db.flush()
        for person, rating in zip(people, [10, 9, 8, 2, 1, 0]):
            self.db.add(EventPresence(event_id=event.id, profile_id=person.id, status=PresenceStatus.CONFIRMED))
            self.db.add(GroupPlayerRating(group_id=self.group.id, profile_id=person.id, rating=Decimal(rating), updated_by_id=self.user.id))
        self.db.add(GroupDrawSettings(group_id=self.group.id, use_ratings=True))
        await self.db.flush()
        ratings = dict(zip([str(p.id) for p in people], [10, 9, 8, 2, 1, 0]))
        url = self.base + f"/events/{event.id}/teams"
        result = await self.client.post(url, json={"mode": "random", "team_count": 3}, headers=self.owner_headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual([sum(ratings[p["person_id"]] for p in team["players"]) for team in result.json()["teams"]], [10] * 3)
        self.assertNotIn('"rating"', result.text)
        await self.client.post(self.rating_url, json={"rating": 0}, headers=self.owner_headers)
        presences = (await self.db.scalars(select(EventPresence).where(EventPresence.event_id == event.id))).all()
        features = await draw_features(self.db, event, presences, DrawSettings(use_ratings=True))
        other_presence = next(p for p in presences if p.profile_id == self.other.id)
        self.assertEqual(features[other_presence.id]["rating"], 0)
        # Os parâmetros nunca substituem uma formação manual explícita.
        manual_teams = [{"name": f"Manual {i}", "players": [
            {"presence_id": str(p.id), "role": "player"} for p in presences[i * 2:i * 2 + 2]
        ]} for i in range(3)]
        manual = await self.client.post(url, json={"mode": "manual", "teams": manual_teams}, headers=self.owner_headers)
        self.assertEqual(manual.status_code, 200, manual.text)
        for expected, actual in zip(manual_teams, manual.json()["teams"]):
            self.assertEqual({p["presence_id"] for p in expected["players"]}, {p["presence_id"] for p in actual["players"]})
        event.status = EventStatus.FINISHED
        await self.db.flush()
        updated = await self.client.post(self.rating_url, json={"rating": 6.5}, headers=self.owner_headers)
        self.assertEqual(updated.status_code, 200, updated.text)

    async def test_enabled_parameters_preserve_guest_and_keeper_slots(self):
        event = PeladaEvent(group_id=self.group.id, created_by_id=self.user.id, title="Goleiros e convidados",
            scheduled_at=datetime.now(timezone.utc) + timedelta(days=1), modality="futsal",
            min_confirmed_players=6, max_confirmed_players=6, min_confirmed_goalkeepers=2,
            max_confirmed_goalkeepers=2, status=EventStatus.REGISTRATION_OPEN)
        self.db.add(event)
        self.db.add(GroupDrawSettings(group_id=self.group.id, use_positions=True, use_ratings=True, use_wins=True))
        await self.db.flush()
        for index in range(8):
            guest = GroupGuest(group_id=self.group.id, created_by_id=self.user.id, name=f"Convidado {index}")
            self.db.add(guest)
            await self.db.flush()
            self.db.add(EventPresence(event_id=event.id, guest_id=guest.id, status=PresenceStatus.CONFIRMED,
                                     role=TeamPlayerRole.GOALKEEPER if index < 2 else TeamPlayerRole.PLAYER))
        await self.db.flush()
        result = await self.client.post(self.base + f"/events/{event.id}/teams",
            json={"mode": "random", "team_count": 3}, headers=self.owner_headers)
        self.assertEqual(result.status_code, 200, result.text)
        teams = result.json()["teams"]
        self.assertEqual([sum(p["role"] == "player" for p in t["players"]) for t in teams], [2] * 3)
        self.assertEqual(sorted(sum(p["role"] == "goalkeeper" for p in t["players"]) for t in teams), [0, 1, 1])
        self.assertEqual(len({p["presence_id"] for t in teams for p in t["players"]}), 8)
        self.assertNotIn('"rating"', result.text)

    async def test_features_use_group_wins_active_lineups_and_event_modality(self):
        self.other.positions = {"campo": ["meia", "atacante"], "futsal": ["fixo"]}
        event = PeladaEvent(group_id=self.group.id, created_by_id=self.user.id, title="Histórico",
            scheduled_at=datetime.now(timezone.utc), modality="campo", status=EventStatus.REGISTRATION_OPEN)
        self.db.add(event)
        await self.db.flush()
        team = EventTeam(event_id=event.id, name="Time A")
        presence = EventPresence(event_id=event.id, profile_id=self.other.id, status=PresenceStatus.CONFIRMED)
        self.db.add_all([team, presence])
        await self.db.flush()
        for i, (status, result, active) in enumerate([
            (MatchStatus.FINISHED, MatchResult.WIN, True),
            (MatchStatus.FINISHED, MatchResult.WIN, False),
            (MatchStatus.FINISHED, MatchResult.DRAW, True),
            (MatchStatus.IN_PROGRESS, MatchResult.WIN, True),
        ]):
            match = Match(event_id=event.id, sequence=i + 1, status=status)
            self.db.add(match)
            await self.db.flush()
            self.db.add_all([MatchTeam(match_id=match.id, team_id=team.id, result=result),
                MatchLineup(match_id=match.id, team_id=team.id, profile_id=self.other.id,
                            role=TeamPlayerRole.PLAYER, is_active=active)])
        await self.db.flush()
        settings = DrawSettings(use_positions=True, use_ratings=True, use_wins=True)
        features = await draw_features(self.db, event, [presence], settings)
        self.assertEqual(features[presence.id], {"positions": {"meia", "atacante"}, "rating": 50, "wins": 1})
        event.status = EventStatus.CANCELLED
        await self.db.flush()
        self.assertEqual((await draw_features(self.db, event, [presence], settings))[presence.id]["wins"], 0)
