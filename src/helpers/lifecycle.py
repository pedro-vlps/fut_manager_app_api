from fastapi import HTTPException
from src.models.enums import EventStatus, MatchStatus


def require_open(event):
    if event.status in [EventStatus.FINISHED, EventStatus.CANCELLED]:
        raise HTTPException(409, "Este evento já foi encerrado ou cancelado.")


def timer_elapsed(match, now):
    elapsed = match.timer_elapsed_ms or 0
    if match.timer_running_since is not None:
        end = (
            match.ended_at
            if match.status == MatchStatus.FINISHED and match.ended_at
            else now
        )
        elapsed += max(0, int((end - match.timer_running_since).total_seconds() * 1000))
    return elapsed
