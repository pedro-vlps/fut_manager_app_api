from sqlalchemy.ext.asyncio import AsyncSession
from src.models.entities import PeladaGroup
from src.models.enums import TeamPlayerRole
from src.schemas.groups import RankingEntry
from src.services.groups import GroupsService


async def calculate_rankings(group: PeladaGroup, db: AsyncSession, season=None, event_id=None):
    service = GroupsService(db)
    entries = {}

    def entry(profile_id, guest_id, name, guest_name):
        key = ("guest" if guest_id else "profile", profile_id or guest_id)
        if key not in entries:
            entries[key] = RankingEntry(
                id=key[1], name=name or guest_name, is_guest=guest_id is not None
            )
        return entries[key]

    actions = await service.action_totals(group, season, event_id)
    fields = {
        "goal": "goals",
        "own_goal": "own_goals",
        "assist": "assists",
        "yellow_card": "yellow_cards",
        "red_card": "red_cards",
    }
    for player, guest, name, guest_name, action, count in actions:
        person = entry(player, guest, name, guest_name)
        setattr(person, fields[action.value], count)
    lineups = await service.finished_lineups(group, season, event_id)
    for lineup, name, guest_name, result, goals in lineups:
        person = entry(lineup.profile_id, lineup.guest_id, name, guest_name)
        person.matches += 1
        person.wins += int(result == "win")
        person.losses += int(result == "loss")
        if lineup.role == TeamPlayerRole.GOALKEEPER:
            person.goals_conceded += goals
            person.goalkeeper_matches += 1
    return sorted(
        entries.values(), key=lambda p: (-p.goals, p.name.casefold(), str(p.id))
    )
