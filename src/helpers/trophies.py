"""Categorias e desempates iguais aos rankings exibidos no aplicativo."""

CATEGORIES = {
    "goals": "Artilheiro",
    "assists": "Rei das assistências",
    "wins": "Mais vitórias",
    "losses": "Mais derrotas",
    "own_goals": "Mais gols contra",
    "yellow_cards": "Mais cartões amarelos",
    "red_cards": "Mais cartões vermelhos",
    "goals_conceded": "Goleiro menos vazado",
}


def season_winners(rankings):
    for category in CATEGORIES:
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
