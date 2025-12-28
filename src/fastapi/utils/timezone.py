import datetime

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo  # type: ignore

from src.fastapi.config import settings


def get_current_timezone() -> zoneinfo.ZoneInfo:
    """Get the project's timezone as defined in settings.TIMEZONE default to 'UTC'"""
    tzname = settings.get("TIMEZONE", "UTC")
    if isinstance(tzname, datetime.timezone):
        tzname = str(tzname)
    return zoneinfo.ZoneInfo(tzname)


def now() -> datetime.datetime:
    """Get the current datetime"""
    return datetime.datetime.now(get_current_timezone())
