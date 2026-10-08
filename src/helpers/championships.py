"""Regras determinísticas da tabela e do chaveamento de cada edição."""
from itertools import combinations
from src.schemas.championships import Standing


def initial_fixtures(entries, format):
    ids = [e.club_id for e in entries]
    if format == "cascade":
        if len(ids) != 4:
            raise ValueError("Cascata permite somente 4 times.")
        return [("winners", 1, None, ids[0], ids[3]), ("winners", 1, None, ids[1], ids[2])]
    if format == "knockout":
        return [("knockout", 1, None, ids[i], ids[i + 1]) for i in range(0, len(ids), 2)]
    if format == "groups_knockout":
        return [("groups", 1, chr(65 + i // 4), a, b)
                for i in range(0, len(ids), 4) for a, b in combinations(ids[i:i + 4], 2)]
    raise ValueError("Formato inválido.")


def loser(match):
    return match.away_id if match.winner_id == match.home_id else match.home_id


def cascade_next(matches):
    """W1, W2, final W, semi L, final L, final geral (sem reset).

    A semi L entre as finais protege o perdedor da final W de três jogos seguidos.
    Só gera a próxima dependência depois de todos os resultados disponíveis.
    """
    if any(m.home_score is None for m in matches):
        return []
    if len(matches) == 2:
        a, b = matches
        return [("winners", 2, None, a.winner_id, b.winner_id),
                ("losers", 1, None, loser(a), loser(b))]
    if len(matches) == 4:
        return [("losers", 2, None, loser(matches[2]), matches[3].winner_id)]
    if len(matches) == 5:
        return [("grand_final", 1, None, matches[2].winner_id, matches[4].winner_id)]
    return []


def standings(entries, matches):
    seeds = {e.club_id: e.seed for e in entries}
    rows = {}
    for match in matches:
        if match.stage != "groups":
            continue
        for club_id in (match.home_id, match.away_id):
            rows.setdefault(club_id, Standing(club_id=club_id, pool=match.pool,
                played=0, points=0, goals_for=0, goals_against=0, seed=seeds[club_id]))
        if match.home_score is None:
            continue
        for club_id, scored, conceded in [(match.home_id, match.home_score, match.away_score),
                                         (match.away_id, match.away_score, match.home_score)]:
            row = rows[club_id]
            row.played += 1
            row.goals_for += scored
            row.goals_against += conceded
            row.points += 3 if scored > conceded else 1 if scored == conceded else 0
    return sorted(rows.values(), key=lambda r: (r.pool, -r.points, -(r.goals_for - r.goals_against), -r.goals_for, r.seed))


def qualified_pairs(entries, matches):
    pools = {}
    for row in standings(entries, matches):
        pools.setdefault(row.pool, []).append(row.club_id)
    groups = list(pools.values())
    if len(groups) == 1:
        return [(groups[0][0], groups[0][1])]
    return [pair for i in range(0, len(groups), 2)
            for pair in [(groups[i][0], groups[i + 1][1]), (groups[i + 1][0], groups[i][1])]]
