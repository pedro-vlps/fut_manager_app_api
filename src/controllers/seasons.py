from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from src.helpers.season_calendar import period_end
from src.controllers.group_requests import require_manager
from src.controllers.rankings import calculate_rankings
from src.models.entities import GroupSeason
from src.models.enums import GroupRole, MembershipStatus
from src.schemas.seasons import SeasonSettings, SeasonSchema, SeasonHistory, SeasonRankings
from src.services.seasons import SeasonsService


async def archive(service, group, season):
    if season.archived_rankings is None:
        rows = await calculate_rankings(group, service.db, season)
        season.archived_rankings = [row.model_dump(mode="json") for row in rows]
        await service.flush()

    from src.controllers.trophies import award_season
    await award_season(service.db, group, season)


async def synchronize(service, group_id, now=None):
    """Materializa períodos vencidos sob lock; funciona mesmo após dias sem acessos."""
    now = now or datetime.now(timezone.utc)
    group = await service.locked_group(group_id)
    if group is None:
        raise HTTPException(404, "Grupo não encontrado.")
    last = await service.latest(group.id)
    if not group.seasons_enabled:
        return group, None
    if last is None:
        last = GroupSeason(group_id=group.id, number=1, starts_at=now,
                           ends_at=period_end(group, now))
        service.add(last)
        await service.flush()
    while last.ends_at <= now:
        await archive(service, group, last)
        if group.season_mode == "fixed":
            group.seasons_enabled = False
            return group, None
        last = GroupSeason(group_id=group.id, number=last.number + 1, starts_at=last.ends_at,
                           ends_at=period_end(group, last.ends_at))
        service.add(last)
        await service.flush()
    return group, last


async def settings_result(service, group, season, profile):
    member = await service.membership(group.id, profile.id)
    can_manage = group.created_by_id == profile.id or bool(
        member and member.status == MembershipStatus.ACTIVE
        and member.role in {GroupRole.OWNER, GroupRole.ADMIN}
    )
    return SeasonSettings(mode=group.season_mode, months=group.season_months, day=group.season_day,
                          fixed_end=group.season_fixed_end, timezone=group.season_timezone, enabled=group.seasons_enabled, duration_days=group.season_duration_days,
                          current_season=SeasonSchema.model_validate(season) if season else None,
                          can_manage=can_manage)


async def settings(group, profile, db):
    service = SeasonsService(db)
    group, season = await synchronize(service, group.id)
    result = await settings_result(service, group, season, profile)
    await service.commit()
    return result


async def update_settings(group, payload, profile, db):
    service = SeasonsService(db)
    group = await service.locked_group(group.id)
    await require_manager(service, group, profile)
    now = datetime.now(timezone.utc)
    group, season = await synchronize(service, group.id, now)
    try:
        ZoneInfo(payload.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, "Fuso horário inválido.")
    if payload.enabled and payload.mode == "fixed" and (payload.fixed_end is None or payload.fixed_end <= now):
        raise HTTPException(422, "Escolha uma data de encerramento futura.")
    changed = (group.season_mode, group.season_months, group.season_day, group.season_fixed_end, group.season_timezone) != (
        payload.mode, payload.months, payload.day, payload.fixed_end, payload.timezone)
    was_enabled = group.seasons_enabled
    group.season_mode = payload.mode
    group.season_months = payload.months
    group.season_day = payload.day
    group.season_fixed_end = payload.fixed_end
    group.season_timezone = payload.timezone
    group.season_duration_days = payload.duration_days
    group.seasons_enabled = payload.enabled
    if was_enabled and not payload.enabled and season:
        season.ends_at = max(now, season.starts_at + timedelta(microseconds=1))
        await archive(service, group, season)
        season = None
    elif not was_enabled and payload.enabled:
        last = await service.latest(group.id)
        season = GroupSeason(group_id=group.id, number=last.number + 1 if last else 1,
                             starts_at=now, ends_at=period_end(group, now))
        service.add(season)
    elif payload.enabled and season and changed:
        season.ends_at = period_end(group, now)
    await service.flush()
    result = await settings_result(service, group, season, profile)
    await service.commit()
    return result


async def history(group, db):
    service = SeasonsService(db)
    await synchronize(service, group.id)
    result = SeasonHistory(seasons=[SeasonSchema.model_validate(row) for row in await service.history(group.id)])
    await service.commit()
    return result


async def current_rankings(group, db):
    service = SeasonsService(db)
    group, season = await synchronize(service, group.id)
    result = SeasonRankings(season=SeasonSchema.model_validate(season) if season else None,
                            rankings=await calculate_rankings(group, db, season))
    await service.commit()
    return result


async def historical_rankings(group, season_id, db):
    service = SeasonsService(db)
    await synchronize(service, group.id)
    season = await service.get(GroupSeason, season_id)
    if season is None or season.group_id != group.id or season.archived_rankings is None:
        raise HTTPException(404, "Temporada encerrada não encontrada neste grupo.")
    result = SeasonRankings(season=SeasonSchema.model_validate(season), rankings=season.archived_rankings)
    await service.commit()
    return result
