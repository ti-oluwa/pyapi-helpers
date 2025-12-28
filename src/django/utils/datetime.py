import functools
import typing
import datetime
from django.utils import timezone as django_timezone

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from contextlib import contextmanager
from src.generics.utils.datetime import (
    timedelta_code_to_datetime_range as timedelta_code_to_datetime_range_generic,
)


def timedelta_code_to_datetime_range(
    timdelta_code: str,
    *,
    timezone: typing.Optional[typing.Union[str, zoneinfo.ZoneInfo]] = None,
    future: bool = False,
) -> typing.Tuple[typing.Optional[datetime.datetime], datetime.datetime]:
    """
    Parses the timedelta code into a datetime range.

    By default, the datetime range is calculated for the past.
    To calculate the datetime range for the future, set future to True.

    :param timdelta_code: The timedelta code to parse.
    :param timezone: The timezone to use for the datetime objects.
    :param future: Whether to calculate the datetime range for the future.
    :return: A tuple containing the start and end datetime objects.

    Example:

        ```python
        timedelta_code_to_datetime_range("5D") # 5 Days in the past

        # Output:
        # (datetime.datetime(2021, 9, 2, 10, 0, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), datetime.datetime(2021, 9, 7, 10, 0, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')))

        timedelta_code_to_datetime_range("5D", timezone="Africa/Nairobi", future=True) # 5 Days in the future

        # Output:
        # (datetime.datetime(2021, 9, 7, 13, 0, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='Africa/Nairobi')), datetime.datetime(2021, 9, 12, 13, 0, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='Africa/Nairobi')))
        ```
    """
    # Just a wrapper around the generic function
    return functools.partial(
        timedelta_code_to_datetime_range_generic, now=django_timezone.now
    )(timdelta_code, timezone=timezone, future=future)


@contextmanager
def activate_timezone(tz: typing.Union[str, zoneinfo.ZoneInfo]):
    """
    Temporarily activate a timezone in a context.

    :param tz: The timezone to activate.
    """
    tz = zoneinfo.ZoneInfo(tz) if isinstance(tz, str) else tz
    try:
        django_timezone.activate(tz)
        yield
    finally:
        django_timezone.deactivate()


__all__ = [
    "timedelta_code_to_datetime_range",
    "activate_timezone",
]
