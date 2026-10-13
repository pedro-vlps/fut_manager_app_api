"""Dois amarelos por pessoa e partida geram uma única expulsão automática."""
from uuid import UUID, uuid5

SECOND_YELLOW_NOTE = 'automatic:second_yellow'


def automatic_red_id(match_id, person_id):
    return uuid5(UUID(str(match_id)), f'second-yellow:{person_id}')


def card_error(kinds, new_kind):
    if new_kind not in ('yellow_card', 'red_card'):
        return None
    if 'red_card' in kinds or kinds.count('yellow_card') >= 2:
        return 'Este jogador já foi expulso nesta partida. Remova o cartão incorreto antes de registrar outro.'
    return None


def sync_championship_cards(match_id, actions):
    """Reconstrói somente os vermelhos automáticos; mantém cartões diretos."""
    result = [a for a in actions if not a.get('auto_generated', False)]
    people = {}
    for action in result:
        people.setdefault(action['presence_id'], []).append(action)
    for person_id, records in people.items():
        yellows = [a for a in records if a['action_type'] == 'yellow_card']
        if len(yellows) >= 2 and not any(a['action_type'] == 'red_card' for a in records):
            second = yellows[1]
            result.append({**second, 'id': str(automatic_red_id(match_id, person_id)),
                           'action_type': 'red_card', 'auto_generated': True})
    return result
