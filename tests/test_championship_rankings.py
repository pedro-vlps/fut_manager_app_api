import unittest
from types import SimpleNamespace
from uuid import uuid4

from src.models.championships import ChampionshipMatch
from src.helpers.championship_trophies import player_rankings


class ChampionshipPlayerRankingsTests(unittest.TestCase):
    def test_finished_results_cards_and_goalkeeper_totals(self):
        home, away = uuid4(), uuid4()
        home_entry, away_entry = uuid4(), uuid4()
        scorer, home_keeper, away_keeper = uuid4(), uuid4(), uuid4()
        entries = [SimpleNamespace(id=home_entry, club_id=home), SimpleNamespace(id=away_entry, club_id=away)]
        players = [(SimpleNamespace(profile_id=id, entry_id=entry), name) for id, entry, name in (
            (scorer, home_entry, 'Atacante'), (home_keeper, home_entry, 'Goleiro A'), (away_keeper, away_entry, 'Goleiro B'))]
        stats = [SimpleNamespace(profile_id=scorer, goals=2, assists=1, own_goals=0),
                 SimpleNamespace(profile_id=away_keeper, goals=0, assists=0, own_goals=1)]
        def match(home_score, away_score, actions=(), winner_id=None):
            return ChampionshipMatch(home_id=home, away_id=away, home_score=home_score, away_score=away_score,
                home_goalkeeper_id=home_keeper, away_goalkeeper_id=away_keeper, actions=actions, winner_id=winner_id)
        def action(profile, kind):
            return {'presence_id': str(profile), 'action_type': kind}
        matches = [match(3, 0, [action(scorer, 'yellow_card'), action(scorer, 'yellow_card'), action(away_keeper, 'red_card')]),
                   match(1, 1, winner_id=home),
                   match(None, None, [action(home_keeper, 'red_card')])]
        rows = {row.profile_id: row for row in player_rankings(entries, players, stats, matches)}
        self.assertEqual((rows[scorer].goals, rows[scorer].assists, rows[scorer].yellow_cards), (2, 1, 2))
        self.assertEqual((rows[away_keeper].own_goals, rows[away_keeper].red_cards, rows[away_keeper].losses), (1, 1, 1))
        self.assertEqual((rows[home_keeper].goalkeeper_matches, rows[home_keeper].goals_conceded), (2, 1))
        self.assertEqual((rows[away_keeper].goalkeeper_matches, rows[away_keeper].goals_conceded), (2, 4))
        self.assertEqual(rows[scorer].goalkeeper_matches, 0)
        self.assertEqual(rows[home_keeper].red_cards, 0)
        self.assertTrue(all(row.matches == 2 for row in rows.values()))
        self.assertEqual(rows[home_keeper].losses, 0)

    def test_zero_goals_conceded_and_missing_keeper(self):
        club, other, entry, profile = uuid4(), uuid4(), uuid4(), uuid4()
        entries = [SimpleNamespace(id=entry, club_id=club)]
        players = [(SimpleNamespace(profile_id=profile, entry_id=entry), 'Goleiro')]
        game = ChampionshipMatch(home_id=club, away_id=other, home_score=0, away_score=0,
                               home_goalkeeper_id=profile, away_goalkeeper_id=None, actions=[])
        row = player_rankings(entries, players, [], [game])[0]
        self.assertEqual((row.goalkeeper_matches, row.goals_conceded, row.matches), (1, 0, 1))
        game.home_goalkeeper_id = None
        row = player_rankings(entries, players, [], [game])[0]
        self.assertEqual((row.goalkeeper_matches, row.goals_conceded, row.matches), (0, 0, 1))
