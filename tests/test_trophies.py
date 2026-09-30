import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import select, func
from src.controllers.trophies import award_season
from src.helpers.trophies import season_winners
from src.models.entities import GroupSeason, PeladaGroup, SeasonTrophy, GroupMember, PeladaEvent, EventTeam, Match, MatchTeam, MatchLineup, GameAction
from src.models.enums import EventStatus, MatchStatus, MatchResult, TeamPlayerRole, GameActionType, MembershipStatus
from src.routers.trophies import router as trophies_router
from tests.test_auth import AuthTestCase


class TrophyWinnersTests(unittest.TestCase):
    def test_ties_zero_scores_and_goalkeeper_eligibility(self):
        rows = [
            {"id": "a", "goals": 5, "assists": 1, "goalkeeper_matches": 0, "goals_conceded": 0},
            {"id": "b", "goals": 5, "assists": 3, "goalkeeper_matches": 2, "goals_conceded": 0},
            {"id": "c", "goals": 2, "assists": 3, "goalkeeper_matches": 1, "goals_conceded": 0},
        ]
        winners = list(season_winners(rows))
        self.assertEqual(winners, [("goals", "a", 5), ("goals", "b", 5),
                                   ("assists", "b", 3), ("assists", "c", 3),
                                   ("goals_conceded", "b", 0), ("goals_conceded", "c", 0)])
        self.assertEqual(list(season_winners([])), [])
        self.assertEqual(list(season_winners([{"id":"a", "goals":0}])), [])

    def test_guests_do_not_promote_runners_up_and_all_categories_are_awarded(self):
        rows = [{"id":"guest", "is_guest":True, "goals":5},
                {"id":"a", "goals":4, "wins":2, "losses":1, "own_goals":1, "yellow_cards":3, "red_cards":1}]
        winners = list(season_winners(rows))
        self.assertFalse(any(category == 'goals' for category, _, _ in winners))
        self.assertEqual({category for category, _, _ in winners}, {'wins','losses','own_goals','yellow_cards','red_cards'})
        rows[1]['goals'] = 5
        self.assertIn(('goals', 'a', 5), list(season_winners(rows)))


class TrophyIntegrationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = AuthTestCase.asyncSetUp
    asyncTearDown = AuthTestCase.asyncTearDown
    login = AuthTestCase.login

    async def test_backfill_is_idempotent_titles_persist_and_profiles_are_isolated(self):
        self.app.include_router(trophies_router)
        group = PeladaGroup(name='Pelada de Domingo', created_by_id=self.user.id)
        self.db.add(group)
        await self.db.flush()
        now = datetime.now(timezone.utc)
        season = GroupSeason(group_id=group.id, number=2, starts_at=now-timedelta(days=8), ends_at=now-timedelta(days=1),
            archived_rankings=[{'id':str(self.user.id),'name':self.user.name,'goals':3},
                               {'id':str(self.other.id),'name':self.other.name,'goals':3}])
        self.db.add(season)
        await self.db.flush()
        headers = {'Authorization': 'Bearer ' + (await self.login()).json()['access_token']}
        self.assertEqual((await self.client.get('/auth/me/trophies')).status_code, 401)
        first = await self.client.get('/auth/me/trophies', headers=headers)
        self.assertEqual(first.status_code, 200, first.text)
        result = first.json()
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['summary'], [{'category':'goals','name':'Artilheiro','count':1}])
        self.assertEqual(result['trophies'][0]['title'], 'Artilheiro - Temporada 2 - Pelada de Domingo')
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(SeasonTrophy).where(SeasonTrophy.profile_id.in_([self.user.id, self.other.id]))), 2)
        group.name = 'Novo nome'
        await self.db.flush()
        again = await self.client.get('/auth/me/trophies', params={'profile_id':str(self.other.id)}, headers=headers)
        self.assertEqual(again.json(), result)
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(SeasonTrophy).where(SeasonTrophy.profile_id.in_([self.user.id, self.other.id]))), 2)
        other_headers = {'Authorization':'Bearer ' + (await self.login(self.other, 'test-password-456')).json()['access_token']}
        other = (await self.client.get('/auth/me/trophies', headers=other_headers)).json()
        self.assertEqual(other['total'], 1)
        self.assertNotEqual(other['trophies'][0]['id'], result['trophies'][0]['id'])
        current = GroupSeason(group_id=group.id, number=3, starts_at=now, ends_at=now+timedelta(days=7))
        self.db.add(current)
        await self.db.flush()
        await award_season(self.db, group, current)
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(SeasonTrophy).where(SeasonTrophy.profile_id.in_([self.user.id, self.other.id]))), 2)

    async def test_profile_access_closes_expired_season_and_awards_once(self):
        self.app.include_router(trophies_router)
        now = datetime.now(timezone.utc)
        group = PeladaGroup(name='Virada automática', created_by_id=self.other.id, seasons_enabled=True, season_duration_days=7)
        self.db.add(group)
        await self.db.flush()
        season = GroupSeason(group_id=group.id, number=1, starts_at=now-timedelta(days=8), ends_at=now-timedelta(days=1))
        event = PeladaEvent(group_id=group.id, created_by_id=self.other.id, title='Jogo', scheduled_at=now-timedelta(days=2), status=EventStatus.FINISHED)
        self.db.add_all([season, event])
        await self.db.flush()
        team = EventTeam(event_id=event.id, name='A')
        match = Match(event_id=event.id, sequence=1, status=MatchStatus.FINISHED, ended_at=now-timedelta(days=2))
        self.db.add_all([team, match])
        await self.db.flush()
        self.db.add_all([
            MatchLineup(match_id=match.id, team_id=team.id, profile_id=self.user.id, role=TeamPlayerRole.PLAYER),
            MatchTeam(match_id=match.id, team_id=team.id, goals=1, result=MatchResult.WIN),
            GameAction(match_id=match.id, team_id=team.id, player_id=self.user.id, action_type=GameActionType.GOAL),
        ])
        await self.db.flush()
        # Mesmo tendo saído do grupo, o jogador mantém os troféus das partidas disputadas.
        headers = {'Authorization':'Bearer ' + (await self.login()).json()['access_token']}
        first = await self.client.get('/auth/me/trophies', headers=headers)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['total'], 2)
        self.assertEqual({t['category'] for t in first.json()['trophies']}, {'goals','wins'})
        self.assertIsNotNone(season.archived_rankings)
        second = (await self.client.get('/auth/me/trophies', headers=headers)).json()
        self.assertEqual(second, first.json())
