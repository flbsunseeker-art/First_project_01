"""Calendar dates safe for closing-price valuations."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")
NEW_YORK = ZoneInfo("America/New_York")


def us_closed_through(now: datetime | None = None) -> date:
    eastern = (now or datetime.now(NEW_YORK)).astimezone(NEW_YORK)
    return eastern.date() if eastern.time() >= time(16) else eastern.date() - timedelta(days=1)


def portfolio_closed_through(now: datetime | None = None) -> date:
    moment = now or datetime.now(SHANGHAI)
    previous_local_day = moment.astimezone(SHANGHAI).date() - timedelta(days=1)
    return min(previous_local_day, us_closed_through(moment))
