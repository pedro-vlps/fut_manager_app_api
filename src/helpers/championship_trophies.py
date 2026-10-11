from src.schemas.championships import PlayerRanking
from uuid import UUID

CATEGORIES = {
    "championship_champion": "Campeão do campeonato",
    "championship_runner_up": "Vice-campeão do campeonato",
    "championship_goals": "Artilheiro do campeonato",
    "championship_assists": "Líder de assistências do campeonato",
}


def player_rankings(entries, players, statistics, matches=()):
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
        if match.home_score is None or match.away_score is None:
            continue
        for club, scored, conceded, goalkeeper in (
            (match.home_id, match.home_score, match.away_score, match.home_goalkeeper_id),
            (match.away_id, match.away_score, match.home_score, match.away_goalkeeper_id),
        ):
            for row in rosters.get(club, []):
                row.matches += 1
                row.losses += int(scored < conceded)
                if row.profile_id == goalkeeper:
                    row.goalkeeper_matches += 1
                    row.goals_conceded += conceded
        for action in match.actions:
            field = {'yellow_card': 'yellow_cards', 'red_card': 'red_cards'}.get(action['action_type'])
            if field:
                row = rows[UUID(action['presence_id'])]
                setattr(row, field, getattr(row, field) + 1)
    return sorted(rows.values(), key=lambda r: (-r.goals, -r.assists, r.name, str(r.profile_id)))


def trophy_winners(rankings, champion_id, runner_up_id, complete):
    for row in rankings:
        if row.club_id == champion_id:
            yield "championship_champion", row.profile_id, 1
        elif row.club_id == runner_up_id:
            yield "championship_runner_up", row.profile_id, 1
    # Não premia rankings incompletos de placares enviados por clientes antigos.
    if complete:
        for field in ("goals", "assists"):
            best = max((getattr(r, field) for r in rankings), default=0)
            if best > 0:
                for row in rankings:
                    if getattr(row, field) == best:
                        yield f"championship_{field}", row.profile_id, best
