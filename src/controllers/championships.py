from fastapi import HTTPException
from uuid import UUID
from datetime import datetime, timezone
from src.models.championships import Club, ClubMember, Championship, ChampionshipEntry, ChampionshipPlayer, ChampionshipMatch, ChampionshipStatistic
from src.models.entities import PeladaGroup
from src.schemas.championships import ClubView, Person, InvitationView, ChampionshipView, ChampionshipDetail, EntryView, MatchView, CreatedGroup, ChampionshipAward
from src.services.championships import ChampionshipsService
from src.helpers.championships import initial_fixtures, standings, qualified_pairs, cascade_next, loser
from src.helpers.championship_trophies import CATEGORIES, player_rankings, trophy_winners
from src.schemas.trophies import TrophySchema
from src.schemas.championships import PlayerStatistic


def require_owner(entity, profile):
    if entity.owner_id != profile.id:
        raise HTTPException(403, "Somente o criador pode realizar esta ação.")


async def require_entity(service, model, identifier, lock=False):
    entity = await service.locked(model, identifier) if lock else await service.get(model, identifier)
    if entity is None:
        raise HTTPException(404, "Registro não encontrado.")
    return entity


async def club_view(service, club):
    return ClubView(id=club.id, name=club.name, owner_id=club.owner_id,
        members=[Person(id=p.id, name=p.name, status=m.status) for m, p in await service.members(club.id)])


async def my_clubs(profile, db):
    service = ChampionshipsService(db)
    return [await club_view(service, club) for club in await service.clubs(profile.id)]


async def create_club(payload, profile, db):
    service = ChampionshipsService(db)
    club = Club(name=payload.name, owner_id=profile.id)
    service.add(club)
    await service.flush()
    service.add(ClubMember(club_id=club.id, profile_id=profile.id, status="accepted"))
    await service.flush()
    result = await club_view(service, club)
    await service.commit()
    return result


async def invite(club_id, payload, profile, db):
    service = ChampionshipsService(db)
    club = await require_entity(service, Club, club_id, lock=True)
    require_owner(club, profile)
    target = await service.profile_by_email(payload.email)
    if target is None:
        raise HTTPException(404, "Jogador ativo não encontrado com este e-mail.")
    member = await service.member(club.id, target.id)
    if member is None:
        service.add(ClubMember(club_id=club.id, profile_id=target.id))
    elif member.status == "declined":
        member.status = "pending"
    await service.flush()
    result = await club_view(service, club)
    await service.commit()
    return result


async def invitations(profile, db):
    return [InvitationView(id=m.id, club_id=m.club_id, club_name=name)
            for m, name in await ChampionshipsService(db).invitations(profile.id)]


async def respond(invitation_id, payload, profile, db):
    service = ChampionshipsService(db)
    invitation = await require_entity(service, ClubMember, invitation_id)
    if invitation.profile_id != profile.id:
        raise HTTPException(404, "Convite não encontrado.")
    # Mesmo lock usado pela inscrição: o elenco é capturado atomicamente.
    await require_entity(service, Club, invitation.club_id, lock=True)
    await service.refresh(invitation)
    if invitation.status != "pending":
        raise HTTPException(409, "Este convite já foi respondido.")
    invitation.status = "accepted" if payload.accept else "declined"
    await service.commit()


async def list_championships(profile, db):
    return [ChampionshipView.model_validate(c) for c in await ChampionshipsService(db).championships()]


async def search_by_code(query, profile, db):
    championship = await ChampionshipsService(db).by_code(query.code.upper())
    if championship is None:
        raise HTTPException(404, "Nenhum campeonato encontrado com este código.")
    return ChampionshipView.model_validate(championship)


async def create_championship(payload, profile, db):
    service = ChampionshipsService(db)
    championship = Championship(**payload.model_dump(), owner_id=profile.id)
    service.add(championship)
    await service.flush()
    result = ChampionshipView.model_validate(championship)
    await service.commit()
    return result


async def detail(championship_id, profile, db):
    service = ChampionshipsService(db)
    championship = await require_entity(service, Championship, championship_id)
    entries = await service.entries(championship.id)
    players = await service.players(championship.id)
    matches = await service.matches(championship.id)
    return ChampionshipDetail(**ChampionshipView.model_validate(championship).model_dump(),
        entries=[EntryView(id=e.id, club_id=e.club_id, name=name, seed=e.seed,
            players=[Person(id=p.profile_id, name=n, status="accepted") for p, n in players if p.entry_id == e.id]) for e, name in entries],
        matches=[MatchView.model_validate(m) for m in matches], standings=standings([e for e, _ in entries], matches),
        player_rankings=player_rankings([e for e, _ in entries], players, await service.statistics(championship.id)),
        statistics_complete=all(m.statistics_complete for m in matches if m.home_score is not None),
        trophies=[ChampionshipAward(**TrophySchema.model_validate(t).model_dump(), profile_id=t.profile_id, name=name)
                  for t, name in await service.awards(championship.id)])


async def register(championship_id, payload, profile, db):
    service = ChampionshipsService(db)
    championship = await require_entity(service, Championship, championship_id, lock=True)
    club = await require_entity(service, Club, payload.club_id, lock=True)
    require_owner(club, profile)
    if championship.status != "registration":
        raise HTTPException(409, "As inscrições estão encerradas.")
    entries = await service.entries(championship.id)
    if any(e.club_id == club.id for e, _ in entries):
        return await detail(championship.id, profile, db)
    if len(entries) >= championship.capacity:
        raise HTTPException(409, "O campeonato está com todas as vagas preenchidas.")
    members = [p for m, p in await service.members(club.id) if m.status == "accepted" and p.is_active]
    if len(members) < 2:
        raise HTTPException(409, "Convide ao menos outro jogador e aguarde o aceite antes de inscrever o time.")
    registered = {p.profile_id for p, _ in await service.players(championship.id)}
    if any(p.id in registered for p in members):
        raise HTTPException(409, "Um jogador deste elenco já está inscrito por outro time neste campeonato.")
    entry = ChampionshipEntry(championship_id=championship.id, club_id=club.id, seed=len(entries) + 1)
    service.add(entry)
    await service.flush()
    for member in members:
        service.add(ChampionshipPlayer(championship_id=championship.id, entry_id=entry.id, profile_id=member.id))
    await service.flush()
    result = await detail(championship.id, profile, db)
    await service.commit()
    return result


async def player_profile(championship_id, club_id, profile_id, profile, db):
    from src.schemas.member_profile import MemberProfile
    from src.controllers.trophies import my_trophies

    service = ChampionshipsService(db)
    await require_entity(service, Championship, championship_id)
    player = await service.registered_profile(championship_id, club_id, profile_id)
    if player is None:
        raise HTTPException(404, "Jogador não encontrado no elenco inscrito deste time.")
    return MemberProfile(id=player.id, name=player.name, positions=player.positions or {},
                         trophies=await my_trophies(player, db), can_rate=False)


async def withdraw(championship_id, club_id, profile, db):
    service = ChampionshipsService(db)
    championship = await require_entity(service, Championship, championship_id, lock=True)
    club = await require_entity(service, Club, club_id, lock=True)
    require_owner(club, profile)
    if championship.status != "registration":
        raise HTTPException(409, "Não é possível retirar um time após o início.")
    entries = await service.entries(championship.id)
    entry = next((e for e, _ in entries if e.club_id == club.id), None)
    if entry:
        await service.delete(entry)
        await service.flush()
        for seed, remaining in enumerate([e for e, _ in entries if e.id != entry.id], 1):
            remaining.seed = seed
        await service.flush()
    result = await detail(championship.id, profile, db)
    await service.commit()
    return result


def add_matches(service, championship_id, fixtures, offset=0):
    for sequence, (stage, round, pool, home, away) in enumerate(fixtures, offset + 1):
        service.add(ChampionshipMatch(championship_id=championship_id, sequence=sequence,
            stage=stage, round=round, pool=pool, home_id=home, away_id=away))


async def start(championship_id, profile, db):
    service = ChampionshipsService(db)
    championship = await require_entity(service, Championship, championship_id, lock=True)
    require_owner(championship, profile)
    if championship.status != "registration":
        raise HTTPException(409, "Este campeonato já começou.")
    if championship.format == "cascade" and championship.capacity != 4:
        raise HTTPException(409, "Cascata permite somente 4 times. Crie uma edição com 4 vagas.")
    entries = [e for e, _ in await service.entries(championship.id)]
    if len(entries) != championship.capacity:
        raise HTTPException(409, "Preencha todas as vagas antes de iniciar o campeonato.")
    add_matches(service, championship.id, initial_fixtures(entries, championship.format))
    championship.status = "in_progress"
    await service.flush()
    result = await detail(championship.id, profile, db)
    await service.commit()
    return result


async def editable_match(service, championship_id, match_id, profile):
    championship = await require_entity(service, Championship, championship_id, lock=True)
    require_owner(championship, profile)
    if championship.status != "in_progress":
        raise HTTPException(409, "O campeonato não está em andamento.")
    matches = await service.matches(championship.id)
    match = next((m for m in matches if m.id == match_id), None)
    if match is None:
        raise HTTPException(404, "Partida não encontrada neste campeonato.")
    if match.home_score is not None:
        raise HTTPException(409, "O resultado desta partida já foi registrado.")
    if championship.format == "cascade" and any(m.sequence < match.sequence and m.home_score is None for m in matches):
        raise HTTPException(409, "Na cascata, respeite a ordem dos jogos para preservar o descanso dos times.")
    return championship, match, matches


async def add_action(championship_id, match_id, payload, profile, db):
    service = ChampionshipsService(db)
    championship, match, _ = await editable_match(service, championship_id, match_id, profile)
    body = payload.model_dump(mode='json')
    existing = next((a for a in match.actions if a['id'] == body['id']), None)
    if existing:
        if any(existing[key] != value for key, value in body.items()):
            raise HTTPException(409, "Este identificador já pertence a outro lance.")
    else:
        if payload.team_id not in (match.home_id, match.away_id):
            raise HTTPException(422, "Escolha um time desta partida.")
        player = await service.registered_profile(championship.id, payload.team_id, payload.presence_id)
        if player is None:
            raise HTTPException(422, "Escolha um jogador do elenco inscrito deste time.")
        if len(match.actions) >= 5000:
            raise HTTPException(422, "Limite de lances da partida atingido.")
        match.actions = [*match.actions, {**body, 'player_name': player.name, 'minute': None}]
    await service.flush()
    result = await detail(championship.id, profile, db)
    await service.commit()
    return result


async def remove_action(championship_id, match_id, action_id, profile, db):
    service = ChampionshipsService(db)
    championship, match, _ = await editable_match(service, championship_id, match_id, profile)
    match.actions = [a for a in match.actions if a['id'] != str(action_id)]
    await service.flush()
    result = await detail(championship.id, profile, db)
    await service.commit()
    return result


def statistics_from_actions(match, payload):
    if payload.action_ids is None or [str(i) for i in payload.action_ids] != [a['id'] for a in match.actions]:
        raise HTTPException(409, "A súmula mudou. Atualize a tela e confira os lances antes de finalizar.")
    totals = {str(match.home_id): 0, str(match.away_id): 0}
    stats = {}
    for action in match.actions:
        player_id = action['presence_id']
        stat = stats.setdefault(player_id, PlayerStatistic(profile_id=UUID(player_id)))
        kind = action['action_type']
        if kind == 'goal':
            stat.goals += 1
            totals[action['team_id']] += 1
        elif kind == 'own_goal':
            stat.own_goals += 1
            opponent = str(match.away_id) if action['team_id'] == str(match.home_id) else str(match.home_id)
            totals[opponent] += 1
        elif kind == 'assist':
            stat.assists += 1
    if (payload.home_score, payload.away_score) != (totals[str(match.home_id)], totals[str(match.away_id)]):
        raise HTTPException(422, "O placar deve corresponder aos lances da súmula.")
    return list(stats.values())


async def score(championship_id, match_id, payload, profile, db):
    service = ChampionshipsService(db)
    championship, match, matches = await editable_match(service, championship_id, match_id, profile)
    if match.actions or payload.action_ids is not None:
        payload = payload.model_copy(update={'statistics': statistics_from_actions(match, payload)})
    home, away = payload.home_score, payload.away_score
    winner = match.home_id if home > away else match.away_id if away > home else None
    if home == away and match.stage != "groups":
        if payload.winner_id not in (match.home_id, match.away_id):
            raise HTTPException(422, "Informe o vencedor do desempate.")
        winner = payload.winner_id
    elif payload.winner_id is not None and payload.winner_id != winner:
        raise HTTPException(422, "O vencedor informado não corresponde ao placar.")
    await save_statistics(service, championship.id, match, payload)
    match.home_score, match.away_score, match.winner_id = home, away, winner
    if championship.format == "cascade":
        if match.stage == "grand_final":
            championship.status, championship.champion_id = "finished", winner
        else:
            add_matches(service, championship.id, cascade_next(matches), len(matches))
    elif all(m.home_score is not None for m in matches):
        if match.stage == "groups":
            entries = [e for e, _ in await service.entries(championship.id)]
            pairs = qualified_pairs(entries, matches)
            add_matches(service, championship.id, [("knockout", 1, None, a, b) for a, b in pairs], len(matches))
        else:
            winners = [m.winner_id for m in matches if m.stage == "knockout" and m.round == match.round]
            if len(winners) == 1:
                championship.status, championship.champion_id = "finished", winners[0]
            else:
                add_matches(service, championship.id, [("knockout", match.round + 1, None, winners[i], winners[i + 1])
                    for i in range(0, len(winners), 2)], len(matches))
    await service.flush()
    if championship.status == "finished":
        await award_championship(service, championship, matches[-1])
    result = await detail(championship.id, profile, db)
    await service.commit()
    return result


async def save_statistics(service, championship_id, match, payload):
    stats = payload.statistics
    if stats is None:
        match.statistics_complete = payload.home_score == payload.away_score == 0
        return
    entries = {e.id: e.club_id for e, _ in await service.entries(championship_id)}
    roster = {p.profile_id: entries[p.entry_id] for p, _ in await service.players(championship_id)}
    if len({s.profile_id for s in stats}) != len(stats):
        raise HTTPException(422, "Informe cada jogador apenas uma vez.")
    totals = {team: {"goals": 0, "assists": 0, "own_goals": 0} for team in (match.home_id, match.away_id)}
    for stat in stats:
        club = roster.get(stat.profile_id)
        if club not in totals:
            raise HTTPException(422, "As estatísticas devem pertencer ao elenco inscrito dos times desta partida.")
        for field in ("goals", "assists", "own_goals"):
            totals[club][field] += getattr(stat, field)
    for team, opponent, score in [(match.home_id, match.away_id, payload.home_score), (match.away_id, match.home_id, payload.away_score)]:
        total = totals[team]
        if total['goals'] + totals[opponent]['own_goals'] != score:
            raise HTTPException(422, "Gols dos jogadores e gols contra do adversário devem corresponder ao placar.")
        if total['assists'] > total['goals']:
            raise HTTPException(422, "As assistências não podem exceder os gols do próprio time.")
        if any(s.assists > total['goals'] - s.goals for s in stats if roster[s.profile_id] == team):
            raise HTTPException(422, "Um jogador não pode dar assistência para o próprio gol.")
    for stat in stats:
        service.add(ChampionshipStatistic(match_id=match.id, **stat.model_dump()))
    match.statistics_complete = True


async def award_championship(service, championship, final):
    entries = [e for e, _ in await service.entries(championship.id)]
    rankings = player_rankings(entries, await service.players(championship.id), await service.statistics(championship.id))
    complete = all(m.statistics_complete for m in await service.matches(championship.id))
    now = datetime.now(timezone.utc)
    await service.insert_awards([dict(championship_id=championship.id, profile_id=profile_id,
        category=category, value=value, awarded_at=now,
        title=f"{CATEGORIES[category]} · {championship.name} · {championship.season}")
        for category, profile_id, value in trophy_winners(rankings, championship.champion_id, loser(final), complete)])


async def create_group(payload, profile, db):
    service = ChampionshipsService(db)
    group = PeladaGroup(name=payload.name, created_by_id=profile.id)
    service.add(group)
    await service.flush()
    result = CreatedGroup(id=group.id)
    await service.commit()
    return result
