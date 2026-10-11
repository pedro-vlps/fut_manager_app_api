import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from src.controllers.rankings import calculate_rankings, general_standings
from src.helpers.championships import initial_fixtures, standings
from src.schemas.groups import RankingEntry


class LeagueFixturesTests(unittest.TestCase):
    def test_return_leg_inverts_home_away_and_preserves_one_game_per_team(self):
        for size in (4, 8, 16):
            entries = [SimpleNamespace(club_id=uuid4(), seed=i + 1) for i in range(size)]
            fixtures = initial_fixtures(entries, 'league', home_and_away=True)
            self.assertEqual(len(fixtures), size * (size - 1))
            half = len(fixtures) // 2
            for first, second in zip(fixtures[:half], fixtures[half:]):
                stage, round, pool, home, away = first
                self.assertEqual(second, (stage, round + size - 1, pool, away, home))
            self.assertEqual(len({(home, away) for _, _, _, home, away in fixtures}), len(fixtures))
            for round in range(1, 2 * (size - 1) + 1):
                teams = [team for _, r, _, home, away in fixtures if r == round for team in (home, away)]
                self.assertEqual(len(teams), size)
                self.assertEqual(len(set(teams)), size)

    def test_every_pair_once_and_each_team_once_per_round(self):
        for size in (4, 8, 16):
            entries = [SimpleNamespace(club_id=uuid4(), seed=i + 1) for i in range(size)]
            fixtures = initial_fixtures(entries, 'league')
            self.assertEqual(len(fixtures), size * (size - 1) // 2)
            self.assertEqual(len({frozenset((a, b)) for _, _, _, a, b in fixtures}), len(fixtures))
            for round in range(1, size):
                teams = [team for _, r, _, a, b in fixtures if r == round for team in (a, b)]
                self.assertEqual(len(teams), size)
                self.assertEqual(len(set(teams)), size)

    def test_team_table_uses_wins_before_goal_balance_and_goals(self):
        ids = [uuid4() for _ in range(4)]
        entries = [SimpleNamespace(club_id=id, seed=i + 1) for i, id in enumerate(ids)]
        def game(a, b, home, away):
            return SimpleNamespace(stage='league', pool=None, home_id=ids[a], away_id=ids[b], home_score=home, away_score=away)
        games = [game(0, 1, 1, 0), game(0, 2, 0, 10), game(0, 3, 0, 10),
                 game(1, 2, 0, 0), game(1, 3, 0, 0), game(2, 3, 0, 0)]
        rows = standings(entries, games)
        self.assertEqual([r.club_id for r in rows], [ids[2], ids[3], ids[0], ids[1]])
        self.assertEqual((rows[2].points, rows[2].wins, rows[2].draws, rows[2].losses), (3, 1, 0, 2))
        # Equal points: one win beats three draws despite a much worse balance.
        games.append(game(1, 2, 0, 0))
        rows = standings(entries, games, general=True)
        self.assertEqual(next(r.points for r in rows if r.club_id == ids[0]), next(r.points for r in rows if r.club_id == ids[1]))
        self.assertLess(next(i for i, r in enumerate(rows) if r.club_id == ids[0]), next(i for i, r in enumerate(rows) if r.club_id == ids[1]))

    def test_general_table_accumulates_groups_and_knockout(self):
        ids = [uuid4(), uuid4()]
        entries = [SimpleNamespace(club_id=id, seed=i + 1) for i, id in enumerate(ids)]
        matches = [SimpleNamespace(stage=stage, pool='A' if stage == 'groups' else None,
                   home_id=ids[0], away_id=ids[1], home_score=home, away_score=away)
                   for stage, home, away in [('groups', 2, 0), ('knockout', 1, 1)]]
        table = standings(entries, matches, general=True)
        self.assertEqual((table[0].played, table[0].points, table[0].wins, table[0].draws), (2, 4, 1, 1))
        self.assertEqual((table[1].points, table[1].losses, table[1].draws), (1, 1, 1))
        self.assertEqual(standings(entries, matches)[0].played, 1)

    def test_more_goals_break_equal_results_then_seed(self):
        ids = [uuid4(), uuid4()]
        entries = [SimpleNamespace(club_id=id, seed=i + 1) for i, id in enumerate(ids)]
        def game(a, b, goals):
            return SimpleNamespace(stage='league', pool=None, home_id=ids[a], away_id=ids[b], home_score=goals, away_score=0)
        table = standings(entries, [game(0, 1, 1), game(1, 0, 3)])
        self.assertEqual(table[0].club_id, ids[1])
        table = standings(entries, [game(0, 1, 1), game(1, 0, 1)])
        self.assertEqual(table[0].club_id, ids[0])


class PlayerStandingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_tiebreakers_and_zero_point_players(self):
        def player(name, **stats):
            return RankingEntry(id=uuid4(), name=name, matches=4, **stats)
        rows = [player('Gols', points=4, wins=1, draws=1, losses=2, goals=9),
                player('Menos derrotas', points=4, wins=1, draws=1, losses=1),
                player('Empates', points=4, wins=1, draws=2, losses=2),
                player('Vitorias', points=4, wins=2), player('Pontos', points=5),
                player('Derrotas', losses=4), RankingEntry(id=uuid4(), name='Sem jogos')]
        service = SimpleNamespace(commit=AsyncMock())
        group, season = SimpleNamespace(id=uuid4()), SimpleNamespace()
        with patch('src.controllers.rankings.calculate_rankings', new=AsyncMock(return_value=rows)) as calculate, \
                patch('src.controllers.seasons.synchronize', new=AsyncMock(return_value=(group, season))), \
                patch('src.services.seasons.SeasonsService', return_value=service):
            result = await general_standings(group, None)
        calculate.assert_awaited_once_with(group, None, season)
        service.commit.assert_awaited_once()
        self.assertEqual([r.name for r in result], ['Pontos', 'Vitorias', 'Empates', 'Menos derrotas', 'Gols', 'Derrotas'])

    async def test_draws_award_one_point_and_guests_are_included(self):
        profile, guest = uuid4(), uuid4()
        def lineup(profile_id=None, guest_id=None):
            return SimpleNamespace(profile_id=profile_id, guest_id=guest_id, role='player')
        service = SimpleNamespace(action_totals=AsyncMock(return_value=[]), finished_lineups=AsyncMock(return_value=[
            (lineup(profile_id=profile), 'Jogador', None, 'win', 0),
            (lineup(profile_id=profile), 'Jogador', None, 'draw', 1),
            (lineup(guest_id=guest), None, 'Convidado', 'loss', 2)]))
        with patch('src.controllers.rankings.GroupsService', return_value=service):
            rows = await calculate_rankings(SimpleNamespace(), None)
        person = next(r for r in rows if r.id == profile)
        self.assertEqual((person.points, person.wins, person.draws, person.matches), (4, 1, 1, 2))
        self.assertTrue(next(r for r in rows if r.id == guest).is_guest)
