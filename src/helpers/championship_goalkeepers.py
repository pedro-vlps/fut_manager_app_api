"""Titulares e substituições preservam a atribuição de cada gol sofrido."""
from datetime import datetime, timezone
from uuid import UUID


def begin_goalkeeping(match, actor_id):
    if match.started_at is None:
        match.started_at = datetime.now(timezone.utc)
    if not match.goalkeeper_history:
        match.goalkeeper_history = [dict(team_id=str(club), profile_id=str(keeper) if keeper else None,
            changed_at=match.started_at.isoformat(), changed_by=str(actor_id)) for club, keeper in (
                (match.home_id, match.home_goalkeeper_id), (match.away_id, match.away_goalkeeper_id))]


def goal_recipient(match, action):
    if action['action_type'] == 'goal':
        return match.away_id if str(match.home_id) == action['team_id'] else match.home_id
    if action['action_type'] == 'own_goal':
        return UUID(action['team_id'])
    return None


def goalkeeper_totals(match, club_id, conceded):
    history = [record for record in (getattr(match, 'goalkeeper_history', None) or []) if record['team_id'] == str(club_id)]
    current = match.home_goalkeeper_id if club_id == match.home_id else match.away_goalkeeper_id
    starting = history[0]['profile_id'] if history else str(current) if current else None
    participants = {UUID(record['profile_id']) for record in history if record['profile_id']}
    if not history and current:
        participants.add(current)
    totals = {keeper: 0 for keeper in participants}
    recorded = 0
    for action in match.actions:
        if goal_recipient(match, action) != club_id:
            continue
        recorded += 1
        keeper = action.get('goalkeeper_id', starting)
        if keeper:
            identifier = UUID(str(keeper))
            totals[identifier] = totals.get(identifier, 0) + 1
    # Placar legado sem lances: com um único goleiro, conserva a contagem anterior.
    if conceded > recorded and len(totals) == 1:
        keeper = next(iter(totals))
        totals[keeper] += conceded - recorded
    return totals
