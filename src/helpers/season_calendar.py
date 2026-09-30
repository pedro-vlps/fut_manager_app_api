from calendar import monthrange
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def period_end(group, start):
    if group.season_mode == "fixed":
        return group.season_fixed_end
    if group.season_mode == "days":
        return start + timedelta(days=group.season_duration_days)
    local = start.astimezone(ZoneInfo(group.season_timezone))
    month_index = local.year * 12 + local.month - 1 + group.season_months
    year, month = divmod(month_index, 12)
    month += 1
    day = min(group.season_day, monthrange(year, month)[1])
    return datetime(year, month, day, tzinfo=ZoneInfo(group.season_timezone))
