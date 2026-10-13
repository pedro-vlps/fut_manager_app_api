from src.schemas.championships import PlayerRanking
from uuid import UUID
from src.helpers.championship_goalkeepers import goalkeeper_totals

CATEGORIES = {
    "championship_champion": "Campeão do campeonato",
    "championship_runner_up": "Vice-campeão do campeonato",
    "championship_goals": "Artilheiro do campeonato",
    "championship_assists": "Líder de assistências do campeonato",
    "championship_goals_conceded": "Melhor goleiro do campeonato",
}


def player_rankings(entries, players, statistics, matches=(), champion_id=None):
    clubs = {e.id: e.club_id for e in entries}
    rows = {p.profile_id: PlayerRanking(profile_id=p.profile_id, name=name, club_id=clubs[p.entry_id])
            for p, name in players}
    for stat in statistics:
        row = rows[stat.profile_id]
        row.goals += stat.goals
        row.assists += stat.assists
        row.own_goals += stat.own_goals
    rosters = {}
    for row in rows.values():
        rosters.setdefault(row.club_id, []).append(row)
    for match in matches:
        if getattr(match, 'walkover', False) or match.home_score is None or match.away_score is None:
            continue
        for club, scored, conceded, goalkeeper in (
            (match.home_id, match.home_score, match.away_score, match.home_goalkeeper_id),
            (match.away_id, match.away_score, match.home_score, match.away_goalkeeper_id),
        ):
            keeper_totals = goalkeeper_totals(match, club, conceded)
            for row in rosters.get(club, []):
                row.matches += 1
                row.losses += int(scored < conceded)
                if row.profile_id in keeper_totals:
                    row.goalkeeper_matches += 1
                    row.goals_conceded += keeper_totals[row.profile_id]
        for action in match.actions:
            field = {'yellow_card': 'yellow_cards', 'red_card': 'red_cards'}.get(action['action_type'])
            if field:
                row = rows[UUID(action['presence_id'])]
                setattr(row, field, getattr(row, field) + 1)
    from src.helpers.championships import standings
    from types import SimpleNamespace
    ordered_entries = [SimpleNamespace(club_id=e.club_id, seed=getattr(e, 'seed', index + 1),
        disqualified=getattr(e, 'disqualified', False), points_deducted=getattr(e, 'points_deducted', 0)) for index, e in enumerate(entries)]
    clubs_in_edition = {e.club_id for e in entries}
    table = standings(ordered_entries, [m for m in matches if m.home_id in clubs_in_edition and m.away_id in clubs_in_edition], general=True)
    # A colocação esportiva precede os pontos gerais em fases eliminatórias.
    depth = {e.club_id: 0 for e in entries}
    for match in matches:
        if getattr(match, 'stage', None) in ('knockout', 'winners', 'losers', 'grand_final'):
            level = match.sequence if match.stage != 'knockout' else match.round
            for club in (match.home_id, match.away_id):
                depth[club] = max(depth.get(club, 0), level)
    banned = {e.club_id for e in entries if getattr(e, 'disqualified', False)}
    order = sorted(table, key=lambda r: (r.club_id in banned, r.club_id != champion_id, -depth[r.club_id], table.index(r)))
    positions = {r.club_id: index + 1 for index, r in enumerate(order)}
    for row in rows.values():
        row.team_position = positions[row.club_id]
    return sorted((r for r in rows.values() if r.club_id not in banned), key=lambda r: (-r.goals, r.team_position, str(r.profile_id)))


def trophy_winners(rankings, champion_id, runner_up_id, complete):
    for row in rankings:
        if row.club_id == champion_id:
            yield "championship_champion", row.profile_id, 1
        elif row.club_id == runner_up_id:
            yield "championship_runner_up", row.profile_id, 1
    # Não premia rankings incompletos de placares enviados por clientes antigos.
    if complete:
        for field in ("goals", "assists", "goals_conceded"):
            goalkeeper = field == 'goals_conceded'
            eligible = [r for r in rankings if r.goalkeeper_matches > 0] if goalkeeper else [r for r in rankings if getattr(r, field) > 0]
            if eligible:
                first = min(eligible, key=lambda r: (getattr(r, field) if goalkeeper else -getattr(r, field),
                    r.team_position or (1 if r.club_id == champion_id else 2 if r.club_id == runner_up_id else 3), str(r.profile_id)))
                yield f"championship_{field}", first.profile_id, getattr(first, field)
