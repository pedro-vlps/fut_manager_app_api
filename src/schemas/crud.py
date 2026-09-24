"""Compatibilidade dos imports antigos. Schemas definidos por contexto."""

from src.schemas.profiles import ProfileSchema, ProfileCreateSchema, ProfileUpdateSchema
from src.schemas.groups import (
    PeladaGroupSchema,
    PeladaGroupCreateSchema,
    PeladaGroupUpdateSchema,
)
from src.schemas.members import (
    GroupMemberSchema,
    GroupMemberCreateSchema,
    GroupMemberUpdateSchema,
)
from src.schemas.guests import (
    GroupGuestSchema,
    GroupGuestCreateSchema,
    GroupGuestUpdateSchema,
)
from src.schemas.events import (
    PeladaEventSchema,
    PeladaEventCreateSchema,
    PeladaEventUpdateSchema,
)
from src.schemas.presences import (
    EventPresenceSchema,
    EventPresenceCreateSchema,
    EventPresenceUpdateSchema,
)
from src.schemas.teams import (
    EventTeamSchema,
    EventTeamCreateSchema,
    EventTeamUpdateSchema,
)
from src.schemas.team_players import (
    EventTeamPlayerSchema,
    EventTeamPlayerCreateSchema,
    EventTeamPlayerUpdateSchema,
)
from src.schemas.team_queue import (
    EventTeamQueueEntrySchema,
    EventTeamQueueEntryCreateSchema,
    EventTeamQueueEntryUpdateSchema,
)
from src.schemas.matches import MatchSchema, MatchCreateSchema, MatchUpdateSchema
from src.schemas.match_teams import (
    MatchTeamSchema,
    MatchTeamCreateSchema,
    MatchTeamUpdateSchema,
)
from src.schemas.lineups import (
    MatchLineupSchema,
    MatchLineupCreateSchema,
    MatchLineupUpdateSchema,
)
from src.schemas.actions import (
    GameActionSchema,
    GameActionCreateSchema,
    GameActionUpdateSchema,
)
