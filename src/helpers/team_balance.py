"""Balanceamento lexicográfico: posições, avaliações, vitórias.

O tamanho dos times (e as vagas separadas de goleiros) é uma restrição fixa.
Melhorias de nota nunca pioram a distribuição de posições; vitórias nunca
pioram critérios anteriores. Empates continuam aleatórios.
"""
from itertools import combinations, islice


def balanced_teams(players, team_count, features, settings, rng, separate=False):
    positions = sorted({position for item in features.values() for position in item["positions"]}) if settings.use_positions else []
    # 420 é divisível por 1..7: preferências múltiplas recebem frações iguais,
    # representadas como inteiros para comparar prioridades sem erro de float.
    vectors = {}
    for player in players:
        item = features[player.id]
        preferred = item["positions"]
        vector = [420 // len(preferred) if position in preferred else 0 for position in positions]
        if settings.use_ratings:
            vector.append(item["rating"])
        if settings.use_wins:
            vector.append(item["wins"])
        vectors[player.id] = vector
    dimension = len(next(iter(vectors.values())))

    def cost(totals):
        squares = [sum(total[i] ** 2 for total in totals) for i in range(dimension)]
        return (sum(squares[:len(positions)]), *squares[len(positions):])

    def add(a, b, sign=1):
        return [x + sign * y for x, y in zip(a, b)]

    teams = [[] for _ in range(team_count)]
    totals = [[0] * dimension for _ in teams]
    cohorts = [[p for p in players if p.role.value == role] for role in ("player", "goalkeeper")] if separate else [list(players)]
    for cohort in cohorts:
        rng.shuffle(cohort)
        cohort.sort(key=lambda p: (
            -features[p.id]["rating"] if settings.use_ratings else 0,
            -features[p.id]["wins"] if settings.use_wins else 0,
        ))
        sizes = [0] * team_count
        for player in cohort:
            options = [i for i in range(team_count) if sizes[i] == min(sizes)]
            rng.shuffle(options)

            def placement(i):
                updated = list(totals)
                updated[i] = add(totals[i], vectors[player.id])
                return cost(updated)

            selected = min(options, key=placement)
            teams[selected].append(player)
            sizes[selected] += 1
            totals[selected] = add(totals[selected], vectors[player.id])

    # Trocas preservam quantidades e funções e reduzem estritamente o custo.
    # Limite de trabalho mantém o endpoint responsivo mesmo em grupos grandes.
    for _ in range(30):
        current_cost = cost(totals)
        best = None
        people = [(i, p) for i, team in enumerate(teams) for p in team]
        rng.shuffle(people)
        for (i, a), (j, b) in islice(combinations(people, 2), 4000):
            if i == j or (separate and a.role != b.role):
                continue
            updated = list(totals)
            updated[i] = add(add(totals[i], vectors[a.id], -1), vectors[b.id])
            updated[j] = add(add(totals[j], vectors[b.id], -1), vectors[a.id])
            candidate = cost(updated)
            if candidate < current_cost:
                current_cost = candidate
                best = (i, a, j, b, updated)
        if best is None:
            break
        i, a, j, b, totals = best
        teams[i].remove(a)
        teams[j].remove(b)
        teams[i].append(b)
        teams[j].append(a)
    return teams
