from fastapi import HTTPException
from uuid import UUID
from datetime import datetime, timezone
from src.models.championships import Club, ClubMember, Championship, ChampionshipEntry, ChampionshipPlayer, ChampionshipMatch, ChampionshipStatistic
from src.models.entities import PeladaGroup, Profile
from src.schemas.championships import ClubView, Person, InvitationView, ChampionshipView, ChampionshipDetail, EntryView, MatchView, CreatedGroup, ChampionshipAward, ClubTrophy
from src.services.championships import ChampionshipsService
from src.helpers.championships import initial_fixtures, standings, qualified_pairs, cascade_next, loser
from src.helpers.championship_trophies import CATEGORIES, player_rankings, trophy_winners
from src.schemas.trophies import TrophySchema
from src.schemas.championships import PlayerStatistic
from secrets import SystemRandom
from src.helpers.cards import card_error, sync_championship_cards
from src.helpers.championship_goalkeepers import begin_goalkeeping, goal_recipient


def championship_view(championship, profile):
    result = ChampionshipView.model_validate(championship)
    if profile is None or championship.owner_id != profile.id:
        result.code = None
    return result


async def rotate_code(championship_id, profile, db):
    service = ChampionshipsService(db)
    championship = await require_entity(service, Championship, championship_id, lock=True)
    require_owner(championship, profile)
    championship.code = await service.generate_code('championship')
    await service.commit()
    return championship_view(championship, profile)


async def rotate_club_code(club_id, profile, db):
    service = ChampionshipsService(db)
    club = await require_entity(service, Club, club_id, lock=True)
    require_owner(club, profile)
    club.code = await service.generate_code('club')
    await service.flush()
    result = await club_view(service, club, profile)
    await service.commit()
    return result


async def random_groups(championship_id, profile, db):
    from src.schemas.championships import GroupAssignment
    service = ChampionshipsService(db)
    championship = await require_entity(service, Championship, championship_id, lock=True)
    require_owner(championship, profile)
    ids = [e.club_id for e, _ in await service.entries(championship.id)]
    if championship.format != 'groups_knockout':
        raise HTTPException(409, 'Sorteio disponível somente no formato com grupos.')
    if len(ids) != championship.capacity:
        raise HTTPException(409, 'Preencha todas as vagas antes de sortear os grupos.')
    SystemRandom().shuffle(ids)
    size = 3 if championship.capacity == 12 else 4
    return await assign_groups(championship_id, GroupAssignment(groups=[ids[i:i + size] for i in range(0, len(ids), size)]), profile, db)


async def punish(championship_id, payload, profile, db):
    service = ChampionshipsService(db)
    championship = await require_entity(service, Championship, championship_id, lock=True)
    require_owner(championship, profile)
    if championship.status != 'in_progress':
        raise HTTPException(409, 'Punições estão disponíveis durante o campeonato.')
    entries = [e for e, _ in await service.entries(championship.id)]
    selected = set(payload.club_ids)
    if len(selected) != len(payload.club_ids) or not selected <= {e.club_id for e in entries}:
        raise HTTPException(422, 'Selecione times inscritos uma única vez.')
    if payload.kind == 'points' and (payload.points < 1 or championship.format not in ('league', 'groups_knockout')):
        raise HTTPException(422, 'Perda de pontos exige valor positivo e formato com tabela.')
    if any(e.disqualified for e in entries if e.club_id in selected):
        raise HTTPException(409, 'Um dos times já está desclassificado.')
    if payload.kind == 'disqualification' and not any(not e.disqualified and e.club_id not in selected for e in entries):
        raise HTTPException(409, 'É necessário manter ao menos um time elegível.')
    for entry in entries:
        if entry.club_id in selected:
            if payload.kind == 'disqualification':
                entry.disqualified = True
            if payload.kind == 'points':
                entry.points_deducted += payload.points
            entry.punishments = [*entry.punishments, dict(kind=payload.kind, points=payload.points,
                reason=payload.reason, applied_by=str(profile.id), applied_at=datetime.now(timezone.utc).isoformat())]
    matches = await service.matches(championship.id)
    await progress_championship(service, championship, matches)
    await service.flush()
    result = await detail(championship.id, profile, db)
    await service.commit()
    return result


async def progress_championship(service, championship, matches):
    """Resolve WOs e dependências sob o mesmo lock da edição, sem premiar gols individuais."""
    entries = [e for e, _ in await service.entries(championship.id)]
    banned = {e.club_id for e in entries if e.disqualified}
    eligible = {e.club_id for e in entries} - banned
    while championship.status == 'in_progress':
        for match in matches:
            if match.home_score is None and banned.intersection((match.home_id, match.away_id)):
                match.walkover = match.statistics_complete = True
                match.actions = []
                match.home_goalkeeper_id = match.away_goalkeeper_id = None
                match.goalkeeper_history = []
                match.home_score = 0 if match.home_id in banned else 3
                match.away_score = 0 if match.away_id in banned else 3
                match.winner_id = match.home_id if match.home_score > match.away_score else match.away_id if match.away_score > match.home_score else None
        if len(eligible) == 1:
            championship.status, championship.champion_id = 'finished', next(iter(eligible))
            break
        if any(m.home_score is None for m in matches):
            return
        if championship.format == 'league':
            championship.status, championship.champion_id = 'finished', standings(entries, matches, general=True)[0].club_id
            break
        latest = matches[-1]
        if championship.format == 'cascade' and latest.stage != 'knockout':
            if latest.stage == 'grand_final':
                fixtures = []
                championship.status, championship.champion_id = 'finished', latest.winner_id
            else:
                fixtures = cascade_next(matches)
        elif latest.stage == 'groups':
            # Preenche as vagas por grupo com os próximos elegíveis. Se um grupo
            # ficou sem candidatos, usa a classificação geral dos demais grupos.
            pools = {}
            per_pool = 1 if len(entries) == 12 else 2
            available = [r.club_id for r in standings(entries, matches, general=True) if not r.disqualified]
            for e in entries:
                pools.setdefault(e.pool or chr(65 + (e.seed - 1) // (3 if len(entries) == 12 else 4)), [])
            for row in standings(entries, matches):
                if not row.disqualified and len(pools[row.pool]) < per_pool:
                    pools[row.pool].append(row.club_id)
            used = {club for clubs in pools.values() for club in clubs}
            for clubs in pools.values():
                while len(clubs) < per_pool:
                    replacement = next((club for club in available if club not in used), None)
                    if replacement is None:
                        break
                    clubs.append(replacement)
                    used.add(replacement)
            groups = list(pools.values())
            if any(len(group) < per_pool for group in groups):
                count = 2 ** (len(eligible).bit_length() - 1)
                clubs = available[:count]
                groups = []
            if not groups:
                pairs = [(clubs[i], clubs[i+1]) for i in range(0, len(clubs), 2)]
            elif len(entries) == 12:
                pairs = [(groups[0][0], groups[1][0]), (groups[2][0], groups[3][0])]
            elif len(groups) == 1:
                pairs = [(groups[0][0], groups[0][1])]
            else:
                pairs = [pair for i in range(0, len(groups), 2) for pair in [(groups[i][0], groups[i+1][1]), (groups[i+1][0], groups[i][1])]]
            fixtures = [('knockout', 1, None, a, b) for a, b in pairs]
        else:
            winners = [m.winner_id for m in matches if m.stage == 'knockout' and m.round == latest.round]
            if len(winners) == 1:
                winner = winners[0]
                if winner not in eligible:
                    winner = next(r.club_id for r in standings(entries, matches, general=True) if not r.disqualified)
                championship.status, championship.champion_id = 'finished', winner
                break
            fixtures = [('knockout', latest.round + 1, None, winners[i], winners[i+1]) for i in range(0, len(winners), 2)]
        if championship.status == 'finished':
            break
        # Ambos punidos: repescagem pela classificação, sem duplicar os times
        # que já conquistaram uma vaga nesta rodada.
        used = {club for f in fixtures for club in f[3:] if club in eligible}
        replacements = [r.club_id for r in standings(entries, matches, general=True) if not r.disqualified and r.club_id not in used]
        resolved = []
        for stage, round, pool, home, away in fixtures:
            pair = []
            for club in (home, away):
                if club not in eligible:
                    if not replacements:
                        pair = []
                        break
                    club = replacements.pop(0)
                pair.append(club)
            if pair:
                resolved.append((stage, round, pool, *pair))
        if len(resolved) != len(fixtures):
            # Chave reduzida: os próximos elegíveis disputam uma nova fase.
            count = 2 ** (len(eligible).bit_length() - 1)
            clubs = [r.club_id for r in standings(entries, matches, general=True) if not r.disqualified][:count]
            resolved = [('knockout', max((m.round for m in matches if m.stage == 'knockout'), default=0) + 1, None, clubs[i], clubs[i+1]) for i in range(0, count, 2)]
        await add_matches(service, championship.id, resolved, len(matches))
        await service.flush()
        matches = await service.matches(championship.id)
    await service.flush()
    if championship.status == 'finished':
        await award_championship(service, championship, matches[-1] if matches else None)


def require_owner(entity, profile):
    if entity.owner_id != profile.id:
        raise HTTPException(403, "Somente o criador pode realizar esta ação.")


async def require_entity(service, model, identifier, lock=False):
    entity = await service.locked(model, identifier) if lock else await service.get(model, identifier)
    if entity is None:
        raise HTTPException(404, "Registro não encontrado.")
    return entity


async def club_view(service, club, profile):
    return ClubView(id=club.id, name=club.name, owner_id=club.owner_id,
        members=[Person(id=p.id, name=p.name, status=m.status, jersey_number=m.jersey_number) for m, p in await service.members(club.id)],
        code=club.code if club.owner_id == profile.id else None, starting_goalkeeper_id=club.starting_goalkeeper_id,
        trophies=[ClubTrophy(championship_id=c.id, name=c.name, season=c.season, category="championship_champion")
                  for c in await service.club_titles(club.id)])


async def club_trophies(club_id, db):
    service = ChampionshipsService(db)
    await require_entity(service, Club, club_id)
    return [ClubTrophy(championship_id=c.id, name=c.name, season=c.season, category='championship_champion')
            for c in await service.club_titles(club_id)]


async def update_entry_goalkeeper(service, championship, entry, goalkeeper):
    entry.starting_goalkeeper_id = goalkeeper
    for match in await service.matches(championship.id):
        if match.home_score is not None or match.started_at or match.actions:
            continue
        for side in ('home', 'away'):
            if getattr(match, f'{side}_id') == entry.club_id and not getattr(match, f'{side}_goalkeeper_override'):
                setattr(match, f'{side}_goalkeeper_id', goalkeeper)


async def set_club_goalkeeper(club_id, payload, profile, db):
    service = ChampionshipsService(db)
    club = await require_entity(service, Club, club_id)
    require_owner(club, profile)
    # Mesma ordem de locks usada na inscrição: edições, depois o clube.
    editions = await service.open_club_editions(club_id)
    club = await require_entity(service, Club, club_id, lock=True)
    if payload.goalkeeper_id is not None:
        member = await service.member(club_id, payload.goalkeeper_id)
        target = await service.get(Profile, payload.goalkeeper_id)
        if member is None or member.status != 'accepted' or target is None or not target.is_active:
            raise HTTPException(422, 'Escolha um jogador ativo que aceitou o convite do próprio time.')
    club.starting_goalkeeper_id = payload.goalkeeper_id
    for championship in editions:
        entry = next(e for e, _ in await service.entries(championship.id) if e.club_id == club_id)
        if payload.goalkeeper_id is None or await service.registered_profile(championship.id, club_id, payload.goalkeeper_id):
            await update_entry_goalkeeper(service, championship, entry, payload.goalkeeper_id)
    await service.flush()
    result = await club_view(service, club, profile)
    await service.commit()
    return result


async def set_entry_goalkeeper(championship_id, club_id, payload, profile, db):
    service = ChampionshipsService(db)
    championship = await require_entity(service, Championship, championship_id, lock=True)
    club = await require_entity(service, Club, club_id, lock=True)
    require_owner(club, profile)
    if championship.status == 'finished':
        raise HTTPException(409, 'O campeonato está encerrado.')
    entry = next((e for e, _ in await service.entries(championship.id) if e.club_id == club_id), None)
    if entry is None:
        raise HTTPException(404, 'Time não inscrito nesta edição.')
    if payload.goalkeeper_id is not None and await service.registered_profile(championship.id, club_id, payload.goalkeeper_id) is None:
        raise HTTPException(422, 'O titular precisa pertencer ao elenco inscrito do próprio time.')
    await update_entry_goalkeeper(service, championship, entry, payload.goalkeeper_id)
    await service.flush()
    result = await detail(championship.id, profile, db)
    await service.commit()
    return result


async def kickoff_match(championship_id, match_id, profile, db):
    service = ChampionshipsService(db)
    championship, match, _ = await editable_match(service, championship_id, match_id, profile)
    begin_goalkeeping(match, profile.id)
    await service.flush()
    result = await detail(championship.id, profile, db)
    await service.commit()
    return result


async def my_clubs(profile, db):
    service = ChampionshipsService(db)
    return [await club_view(service, club, profile) for club in await service.clubs(profile.id)]


async def create_club(payload, profile, db):
    service = ChampionshipsService(db)
    club = Club(name=payload.name, owner_id=profile.id)
    service.add(club)
    await service.flush()
    service.add(ClubMember(club_id=club.id, profile_id=profile.id, status="accepted"))
    await service.flush()
    result = await club_view(service, club, profile)
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
    result = await club_view(service, club, profile)
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
    return [championship_view(c, profile) for c in await ChampionshipsService(db).championships()]


async def search_by_code(query, profile, db):
    championship = await ChampionshipsService(db).by_code(query.code.upper())
    if championship is None:
        raise HTTPException(404, "Nenhum campeonato encontrado com este código.")
    return championship_view(championship, profile)


async def create_championship(payload, profile, db):
    service = ChampionshipsService(db)
    championship = Championship(**payload.model_dump(), owner_id=profile.id)
    service.add(championship)
    await service.flush()
    result = championship_view(championship, profile)
    await service.commit()
    return result


async def set_club_jersey_number(club_id, profile_id, payload, profile, db):
    service = ChampionshipsService(db)
    club = await require_entity(service, Club, club_id, lock=True)
    require_owner(club, profile)
    member = await service.member(club.id, profile_id)
    if member is None or member.status != "accepted":
        raise HTTPException(404, "Jogador confirmado não encontrado neste time.")
    member.jersey_number = payload.jersey_number
    await service.flush()
    result = await club_view(service, club, profile)
    await service.commit()
    return result


async def detail(championship_id, profile, db):
    service = ChampionshipsService(db)
    championship = await require_entity(service, Championship, championship_id)
    entries = await service.entries(championship.id)
    players = await service.players(championship.id)
    matches = await service.matches(championship.id)
    owners = await service.club_owners(championship.id)
    numbers = await service.jersey_numbers(championship.id)
    return ChampionshipDetail(**championship_view(championship, profile).model_dump(),
        entries=[EntryView(id=e.id, club_id=e.club_id, name=name, seed=e.seed,
            disqualified=e.disqualified, points_deducted=e.points_deducted, punishments=e.punishments,
            owner_id=owners[e.club_id], starting_goalkeeper_id=e.starting_goalkeeper_id,
            pool=(e.pool or chr(65 + (e.seed - 1) // (3 if championship.capacity == 12 else 4))) if championship.format == 'groups_knockout' else None,
            players=[Person(id=p.profile_id, name=n, status="accepted", jersey_number=numbers.get((e.club_id, p.profile_id))) for p, n in players if p.entry_id == e.id]) for e, name in entries],
        matches=[MatchView.model_validate(m).model_copy(update={'bracket_size':
            2 * sum(other.stage == 'knockout' and other.round == m.round for other in matches)
            if m.stage == 'knockout' else None}) for m in matches], standings=standings([e for e, _ in entries], matches),
        general_standings=standings([e for e, _ in entries], matches, general=True),
        player_rankings=player_rankings([e for e, _ in entries], players, await service.statistics(championship.id), matches, championship.champion_id),
        statistics_complete=all(m.statistics_complete for m in matches if m.home_score is not None),
        trophies=await edition_awards(service, championship, entries, players, matches))


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
    if championship.format != "league" and len(entries) >= championship.capacity:
        raise HTTPException(409, "O campeonato está com todas as vagas preenchidas.")
    members = [p for m, p in await service.members(club.id) if m.status == "accepted" and p.is_active]
    if len(members) < 2:
        raise HTTPException(409, "Convide ao menos outro jogador e aguarde o aceite antes de inscrever o time.")
    registered = {p.profile_id for p, _ in await service.players(championship.id)}
    if any(p.id in registered for p in members):
        raise HTTPException(409, "Um jogador deste elenco já está inscrito por outro time neste campeonato.")
    entry = ChampionshipEntry(championship_id=championship.id, club_id=club.id, seed=len(entries) + 1,
        starting_goalkeeper_id=club.starting_goalkeeper_id if club.starting_goalkeeper_id in {p.id for p in members} else None)
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
            remaining.pool = None
        await service.flush()
    result = await detail(championship.id, profile, db)
    await service.commit()
    return result


async def add_matches(service, championship_id, fixtures, offset=0):
    goalkeepers = {e.club_id: e.starting_goalkeeper_id for e, _ in await service.entries(championship_id)}
    for sequence, (stage, round, pool, home, away) in enumerate(fixtures, offset + 1):
        service.add(ChampionshipMatch(championship_id=championship_id, sequence=sequence,
            stage=stage, round=round, pool=pool, home_id=home, away_id=away,
            home_goalkeeper_id=goalkeepers.get(home), away_goalkeeper_id=goalkeepers.get(away)))


async def assign_groups(championship_id, payload, profile, db):
    service = ChampionshipsService(db)
    championship = await require_entity(service, Championship, championship_id, lock=True)
    require_owner(championship, profile)
    if championship.format != "groups_knockout":
        raise HTTPException(409, "A edição de grupos está disponível somente para grupos + mata-mata.")
    matches = await service.matches(championship.id)
    if championship.status == "finished" or any(
        m.home_score is not None or m.actions or m.started_at or m.home_goalkeeper_override or m.away_goalkeeper_override for m in matches
    ):
        raise HTTPException(409, "Não é possível alterar os grupos após registrar um jogo, lance ou goleiro.")
    entries = [e for e, _ in await service.entries(championship.id)]
    size = 3 if championship.capacity == 12 else 4
    ids = [club for group in payload.groups for club in group]
    if (len(entries) != championship.capacity or len(payload.groups) != championship.capacity // size
            or any(len(group) != size for group in payload.groups)
            or len(set(ids)) != len(ids) or set(ids) != {e.club_id for e in entries}):
        raise HTTPException(422, f"Distribua todos os times inscritos uma única vez em grupos de {size}.")
    assignment = {club: chr(65 + i) for i, group in enumerate(payload.groups) for club in group}
    for entry in entries:
        entry.pool = assignment[entry.club_id]
    if championship.status == "in_progress":
        for match in matches:
            await service.delete(match)
        await service.flush()
        await add_matches(service, championship.id, initial_fixtures(entries, championship.format))
    await service.flush()
    result = await detail(championship.id, profile, db)
    await service.commit()
    return result


async def start(championship_id, profile, db):
    service = ChampionshipsService(db)
    championship = await require_entity(service, Championship, championship_id, lock=True)
    require_owner(championship, profile)
    if championship.status != "registration":
        raise HTTPException(409, "Este campeonato já começou.")
    if championship.format == "cascade" and championship.capacity != 4:
        raise HTTPException(409, "Cascata permite somente 4 times. Crie uma edição com 4 vagas.")
    entries = [e for e, _ in await service.entries(championship.id)]
    if (championship.format == "league" and len(entries) < 2) or (championship.format != "league" and len(entries) != championship.capacity):
        raise HTTPException(409, "Inscreva pelo menos dois times na liga ou preencha as vagas dos demais formatos.")
    if championship.format == "league":
        championship.capacity = len(entries)
    await add_matches(service, championship.id, initial_fixtures(entries, championship.format, championship.home_and_away))
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
        reason = card_error([a['action_type'] for a in match.actions if a['presence_id'] == body['presence_id']], body['action_type'])
        if reason:
            raise HTTPException(409, reason)
        updated = sync_championship_cards(match.id,
            [*match.actions, {**body, 'player_name': player.name, 'minute': None}])
        if len(updated) > 5000:
            raise HTTPException(422, 'Limite de lances da partida atingido, incluindo o vermelho automático.')
        begin_goalkeeping(match, profile.id)
        recipient = goal_recipient(match, body)
        if recipient is not None:
            keeper = match.home_goalkeeper_id if recipient == match.home_id else match.away_goalkeeper_id
            updated = [{**a, 'goalkeeper_id': str(keeper) if keeper else None} if a['id'] == body['id'] else a for a in updated]
        match.actions = updated
    await service.flush()
    result = await detail(championship.id, profile, db)
    await service.commit()
    return result


async def remove_action(championship_id, match_id, action_id, profile, db):
    service = ChampionshipsService(db)
    championship, match, _ = await editable_match(service, championship_id, match_id, profile)
    if any(a['id'] == str(action_id) and a.get('auto_generated', False) for a in match.actions):
        raise HTTPException(409, 'O vermelho é automático. Remova um dos amarelos para corrigir a expulsão.')
    match.actions = sync_championship_cards(match.id, [a for a in match.actions if a['id'] != str(action_id)])
    await service.flush()
    result = await detail(championship.id, profile, db)
    await service.commit()
    return result


async def set_goalkeepers(championship_id, match_id, payload, profile, db):
    service = ChampionshipsService(db)
    championship, match, _ = await editable_match(service, championship_id, match_id, profile)
    for field, club_id in [('home_goalkeeper_id', match.home_id), ('away_goalkeeper_id', match.away_id)]:
        if field not in payload.model_fields_set:
            continue
        goalkeeper = getattr(payload, field)
        if goalkeeper is not None and await service.registered_profile(championship.id, club_id, goalkeeper) is None:
            raise HTTPException(422, "O goleiro deve pertencer ao elenco inscrito do próprio time.")
        if (match.started_at or match.actions) and goalkeeper is None and getattr(match, field) != goalkeeper:
            raise HTTPException(422, 'Durante a partida, escolha o jogador que entra no gol.')
    if match.started_at or match.actions:
        begin_goalkeeping(match, profile.id)
    for side, club_id in [('home', match.home_id), ('away', match.away_id)]:
        field = f'{side}_goalkeeper_id'
        if field not in payload.model_fields_set or getattr(match, field) == getattr(payload, field):
            continue
        keeper = getattr(payload, field)
        if match.started_at:
            match.goalkeeper_history = [*match.goalkeeper_history, dict(team_id=str(club_id),
                profile_id=str(keeper), changed_at=datetime.now(timezone.utc).isoformat(), changed_by=str(profile.id))]
        setattr(match, field, keeper)
        setattr(match, f'{side}_goalkeeper_override', True)
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
    if payload.walkover:
        if payload.winner_id not in (match.home_id, match.away_id):
            raise HTTPException(422, "Escolha o vencedor por WO.")
        if match.actions or match.started_at:
            raise HTTPException(409, "WO deve ser registrado antes de iniciar a partida ou lançar a súmula.")
        home = 3 if payload.winner_id == match.home_id else 0
        payload = payload.model_copy(update={'home_score': home, 'away_score': 3 - home, 'statistics': None, 'action_ids': None})
        match.walkover = True
        match.home_goalkeeper_id = match.away_goalkeeper_id = None
        match.goalkeeper_history = []
    else:
        begin_goalkeeping(match, profile.id)
        if not match.actions and len({s['profile_id'] for s in match.goalkeeper_history if s['team_id'] == str(match.home_id)}) > 1 and payload.away_score > 0:
            raise HTTPException(422, 'Registre os gols na súmula para atribuí-los ao goleiro que atuava no momento.')
        if not match.actions and len({s['profile_id'] for s in match.goalkeeper_history if s['team_id'] == str(match.away_id)}) > 1 and payload.home_score > 0:
            raise HTTPException(422, 'Registre os gols na súmula para atribuí-los ao goleiro que atuava no momento.')
    if match.actions or payload.action_ids is not None:
        payload = payload.model_copy(update={'statistics': statistics_from_actions(match, payload)})
    home, away = payload.home_score, payload.away_score
    winner = match.home_id if home > away else match.away_id if away > home else None
    if home == away and match.stage not in ("groups", "league"):
        if payload.winner_id not in (match.home_id, match.away_id):
            raise HTTPException(422, "Informe o vencedor do desempate.")
        winner = payload.winner_id
    elif payload.winner_id is not None and payload.winner_id != winner:
        raise HTTPException(422, "O vencedor informado não corresponde ao placar.")
    if match.walkover:
        match.statistics_complete = True
    else:
        await save_statistics(service, championship.id, match, payload)
    match.home_score, match.away_score, match.winner_id = home, away, winner
    await progress_championship(service, championship, matches)
    await service.flush()
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
    rankings = player_rankings(entries, await service.players(championship.id), await service.statistics(championship.id),
                               await service.matches(championship.id), championship.champion_id)
    complete = all(m.statistics_complete for m in await service.matches(championship.id))
    runner_up = loser(final) if final is not None else None
    if any(e.club_id == runner_up and e.disqualified for e in entries):
        runner_up = None
    if championship.format == "league":
        eligible_table = [r for r in standings(entries, await service.matches(championship.id), general=True) if not r.disqualified]
        runner_up = eligible_table[1].club_id if len(eligible_table) > 1 else None
    now = datetime.now(timezone.utc)
    winners = list(trophy_winners(rankings, championship.champion_id, runner_up, complete))
    await service.prune_individual_awards(championship.id,
        [(category, profile_id) for category, profile_id, _ in winners if category not in ('championship_champion', 'championship_runner_up')])
    await service.insert_awards([dict(championship_id=championship.id, profile_id=profile_id,
        category=category, value=value, awarded_at=now,
        title=f"{CATEGORIES[category]} · {championship.name} · {championship.season}")
        for category, profile_id, value in winners])


async def create_group(payload, profile, db):
    service = ChampionshipsService(db)
    group = PeladaGroup(name=payload.name, created_by_id=profile.id)
    service.add(group)
    await service.flush()
    result = CreatedGroup(id=group.id)
    await service.commit()
    return result


async def edition_awards(service, championship, entries, players, matches):
    rankings = player_rankings([e for e, _ in entries], players, await service.statistics(championship.id), matches, championship.champion_id)
    expected = {(category, profile_id) for category, profile_id, _ in trophy_winners(rankings, championship.champion_id, None, True)}
    result, collective = [], set()
    roster = {p.profile_id: p.entry_id for p, _ in players}
    teams = {e.id: (e.club_id, name) for e, name in entries}
    for trophy, name in await service.awards(championship.id):
        if trophy.category in ('championship_champion', 'championship_runner_up'):
            if trophy.category in collective:
                continue
            collective.add(trophy.category)
            name = teams[roster[trophy.profile_id]][1]
        elif (trophy.category, trophy.profile_id) not in expected:
            continue
        result.append(ChampionshipAward(**TrophySchema.model_validate(trophy).model_dump(), profile_id=trophy.profile_id, name=name))
    return result


async def join_club(query, profile, db):
    service = ChampionshipsService(db)
    club = await service.club_by_code(query.code)
    if club is None:
        raise HTTPException(404, 'Time não encontrado com este código.')
    member = await service.member(club.id, profile.id)
    if member is None:
        service.add(ClubMember(club_id=club.id, profile_id=profile.id, status='requested'))
    elif member.status == 'declined':
        member.status = 'requested'
    await service.commit()
    return {'id': club.id}


async def approve_club_member(club_id, profile_id, payload, profile, db):
    service = ChampionshipsService(db)
    club = await require_entity(service, Club, club_id, lock=True)
    require_owner(club, profile)
    member = await service.member(club.id, profile_id)
    if member is None or member.status != 'requested':
        raise HTTPException(409, 'Pedido pendente não encontrado.')
    member.status = 'accepted' if payload.accept else 'declined'
    await service.flush()
    result = await club_view(service, club, profile)
    await service.commit()
    return result
