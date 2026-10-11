"""Categorias e desempates iguais aos rankings exibidos no aplicativo."""

CATEGORIES = {
    "season_champion": "Campeão da temporada",
    "goals": "Artilheiro",
    "assists": "Rei das assistências",
    "wins": "Mais vitórias",
    "losses": "Mais derrotas",
    "own_goals": "Mais gols contra",
    "yellow_cards": "Mais cartões amarelos",
    "red_cards": "Mais cartões vermelhos",
    "goals_conceded": "Goleiro menos vazado",
}


def standings_key(row):
    wins, draws = row.get("wins", 0), row.get("draws", 0)
    return (-row.get("points", 3 * wins + draws), -wins, -draws,
            row.get("losses", 0), -row.get("goals", 0))


def season_winners(rankings):
    played = [row for row in rankings if row.get("matches", 0) > 0]
    if played:
        best = min(standings_key(row) for row in played)
        for row in played:
            if standings_key(row) == best and not row.get("is_guest", False):
                yield "season_champion", row["id"], -best[0]
    for category in CATEGORIES:
        if category == "season_champion":
            continue
        goalkeeper = category == "goals_conceded"
        eligible = [row for row in rankings if
                    (row.get("goalkeeper_matches", 0) > 0 if goalkeeper else row.get(category, 0) > 0)]
        if not eligible:
            continue
        best = (min if goalkeeper else max)(row.get(category, 0) for row in eligible)
        for row in eligible:
            # Convidados participam do ranking, mas não têm perfil para receber troféus.
            if row.get(category, 0) == best and not row.get("is_guest", False):
                yield category, row["id"], best
