import unittest
from random import Random
from types import SimpleNamespace
from src.helpers.team_balance import balanced_teams
from src.models.enums import TeamPlayerRole
from src.schemas.draw import DrawSettings


class TeamBalanceTests(unittest.TestCase):
    def draw(self, ratings, positions=None, wins=None, settings=None, keepers=0, count=3, seed=17):
        players = [SimpleNamespace(id=i, role=TeamPlayerRole.GOALKEEPER if i < keepers else TeamPlayerRole.PLAYER) for i in range(len(ratings))]
        features = {i: {"rating": rating * 10, "positions": set(positions[i]) if positions else set(), "wins": wins[i] if wins else 0} for i, rating in enumerate(ratings)}
        teams = balanced_teams(players, count, features, settings or DrawSettings(use_ratings=True), Random(seed), separate=keepers > 0)
        self.assertEqual(sorted(p.id for team in teams for p in team), list(range(len(players))))
        return [[p.id for p in team] for team in teams]

    def test_ratings_balance_strong_and_weak_players(self):
        ratings = [10, 9, 8, 2, 1, 0]
        for seed in range(10):
            teams = self.draw(ratings, seed=seed)
            self.assertEqual([sum(ratings[i] for i in team) for team in teams], [10, 10, 10])

    def test_positions_take_priority_over_better_rating_totals(self):
        positions = [["defesa"]] * 3 + [["ataque"]] * 3
        ratings = [10, 0, 5, 5, 5, 5]
        teams = self.draw(ratings, positions, settings=DrawSettings(use_positions=True, use_ratings=True))
        for team in teams:
            self.assertEqual(sum(i < 3 for i in team), 1)
        self.assertEqual(sorted(sum(ratings[i] for i in team) for team in teams), [5, 10, 15])
        without_positions = self.draw(ratings)
        self.assertEqual([sum(ratings[i] for i in team) for team in without_positions], [10] * 3)

    def test_ratings_take_priority_over_wins(self):
        ratings = [10, 0, 5, 5, 5, 5]
        wins = [10, 10, 0, 0, 5, 5]
        teams = self.draw(ratings, wins=wins, settings=DrawSettings(use_ratings=True, use_wins=True))
        self.assertEqual([sum(ratings[i] for i in team) for team in teams], [10] * 3)

    def test_wins_work_alone_when_other_parameters_are_disabled(self):
        wins = [10, 9, 8, 2, 1, 0]
        teams = self.draw([5] * 6, wins=wins, settings=DrawSettings(use_wins=True))
        self.assertEqual([sum(wins[i] for i in team) for team in teams], [10] * 3)

    def test_multiple_positions_and_unknown_positions(self):
        teams = self.draw([5] * 12, positions=[["defesa", "ataque"]] * 6 + [[]] * 6,
                          settings=DrawSettings(use_positions=True))
        self.assertEqual([sum(i < 6 for i in team) for team in teams], [2] * 3)

    def test_uneven_sizes_and_keeper_slots_remain_valid(self):
        for count in (3, 4):
            teams = self.draw([5] * 20, keepers=2, count=count)
            field_counts = [sum(i >= 2 for i in team) for team in teams]
            self.assertLessEqual(max(field_counts) - min(field_counts), 1)
            self.assertTrue(all(sum(i < 2 for i in team) <= 1 for team in teams))

    def test_ties_keep_randomness(self):
        results = {tuple(tuple(sorted(team)) for team in self.draw([5] * 12, seed=seed)) for seed in range(5)}
        self.assertGreater(len(results), 1)
