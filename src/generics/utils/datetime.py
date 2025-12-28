import typing
import datetime
import re

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo  # type: ignore

from src.dependencies import deps_required, DependencyRequired
from helpers import PYTHON_VERSION


standard_duration_re = re.compile(
    r"^"
    r"(?:(?P<days>-?\d+) (days?, )?)?"
    r"(?P<sign>-?)"
    r"((?:(?P<hours>\d+):)(?=\d+:\d+))?"
    r"(?:(?P<minutes>\d+):)?"
    r"(?P<seconds>\d+)"
    r"(?:[.,](?P<microseconds>\d{1,6})\d{0,6})?"
    r"$"
)

# Support the sections of ISO 8601 date representation that are accepted by
# timedelta
iso8601_duration_re = re.compile(
    r"^(?P<sign>[-+]?)"
    r"P"
    r"(?:(?P<days>\d+([.,]\d+)?)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+([.,]\d+)?)H)?"
    r"(?:(?P<minutes>\d+([.,]\d+)?)M)?"
    r"(?:(?P<seconds>\d+([.,]\d+)?)S)?"
    r")?"
    r"$"
)

# Support PostgreSQL's day-time interval format, e.g. "3 days 04:05:06". The
# year-month and mixed intervals cannot be converted to a timedelta and thus
# aren't accepted.
postgres_interval_re = re.compile(
    r"^"
    r"(?:(?P<days>-?\d+) (days? ?))?"
    r"(?:(?P<sign>[-+])?"
    r"(?P<hours>\d+):"
    r"(?P<minutes>\d\d):"
    r"(?P<seconds>\d\d)"
    r"(?:\.(?P<microseconds>\d{1,6}))?"
    r")?$"
)


def parse_duration(value):
    """Parse a duration string and return a datetime.timedelta.

    The preferred format for durations in Django is '%d %H:%M:%S.%f'.

    Also supports ISO 8601 representation and PostgreSQL's day-time interval
    format.

    Extracted from Django's django.utils.dateparse module.
    """
    match = (
        standard_duration_re.match(value)
        or iso8601_duration_re.match(value)
        or postgres_interval_re.match(value)
    )
    if match:
        kw = match.groupdict()
        sign = -1 if kw.pop("sign", "+") == "-" else 1
        if kw.get("microseconds"):
            kw["microseconds"] = kw["microseconds"].ljust(6, "0")
        kw = {k: float(v.replace(",", ".")) for k, v in kw.items() if v is not None}
        days = datetime.timedelta(kw.pop("days", 0.0) or 0.0)
        if match.re == iso8601_duration_re:
            days *= sign
        return days + sign * datetime.timedelta(**kw)


_ISO_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"
_RFC3339_DATE_FORMAT_0 = "%Y, /-%m-%dT%H:%M:%S.%f%z"
_RFC3339_DATE_FORMAT_1 = "%Y, /-%m-%dT%H:%M:%S%z"


def rfc3339_parse(s: str, /) -> datetime.datetime:
    """
    Parse RFC 3339 datetime string.

    Use `dateutil.parser.parse` for more generic (but slower)
    parsing.

    Source: https://stackoverflow.com/a/30696682
    """
    global _RFC3339_DATE_FORMAT_0, _RFC3339_DATE_FORMAT_1
    try:
        return datetime.datetime.strptime(s, _RFC3339_DATE_FORMAT_0)
    except ValueError:
        # Perhaps the datetime has a whole number of seconds with no decimal
        # point. In that case, this will work:
        return datetime.datetime.strptime(s, _RFC3339_DATE_FORMAT_1)


_has_dateutil = True
try:
    deps_required({"dateutil": "python-dateutil"})
except DependencyRequired:
    _has_dateutil = False


def iso_parse(
    s: str, /, fmt: typing.Optional[typing.Union[str, typing.Iterable[str]]] = None
) -> datetime.datetime:
    """
    Parse ISO 8601 datetime string as fast as possible.

    Reference: https://stackoverflow.com/a/62769371
    """
    global PYTHON_VERSION, _has_dateutil, _ISO_DATE_FORMAT

    if PYTHON_VERSION >= 3.11:
        try:
            return datetime.datetime.fromisoformat(s)
        except ValueError:
            pass
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass

    if _has_dateutil:
        try:
            from dateutil import parser

            return parser.isoparse(s)
        except ValueError:
            pass

    fmt = fmt or _ISO_DATE_FORMAT
    if isinstance(fmt, str):
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            pass
    else:
        for f in fmt:
            try:
                return datetime.datetime.strptime(s, f)
            except ValueError:
                continue

    if _has_dateutil:
        return parser.parse(s)  # type: ignore
    raise ValueError(f"Could not parse datetime string {s}")


@typing.overload
def split(
    start: datetime.date,
    end: datetime.date,
    part_factor: datetime.timedelta,
    parts: int,
) -> typing.Generator[typing.Tuple[datetime.date, datetime.date], None, None]: ...


@typing.overload
def split(  # type: ignore
    start: datetime.datetime,
    end: datetime.datetime,
    part_factor: datetime.timedelta,
    parts: int,
) -> typing.Generator[
    typing.Tuple[datetime.datetime, datetime.datetime], None, None
]: ...


def split(
    start: typing.Union[datetime.date, datetime.datetime],
    end: typing.Union[datetime.date, datetime.datetime],
    part_factor: datetime.timedelta = datetime.timedelta(days=1),
    parts: typing.Optional[int] = None,
) -> typing.Generator[
    typing.Tuple[
        typing.Union[datetime.date, datetime.datetime],
        typing.Union[datetime.date, datetime.datetime],
    ],
    None,
    None,
]:
    """
    Generator.

    Yields date/datetime ranges by splitting a given date/datetime range into parts based on a given part factor.

    :param start: The start date/datetime of the range.
    :param end: The end date/datetime of the range.
    :param parts: The number of parts to split the date/datetime range into.
    :param part_factor: The factor to use for splitting the date/datetime range.
        Each part's size will be a multiple of this factor, except in edge case,
        where it may not. However, they cannot be smaller than this factor.
    :return: A generator that yields tuples of date/datetime ranges.
    :raises: ValueError.
    - If the start and end dates/datetimes are the same.
    - If the start date/datetime is greater than the end date/datetime.
    - If `parts` is not a positive integer.
    - If the date/datetime range is too small to split into parts based on the given part factor.
    - If the date/datetime range is too small to split into the specified number of parts based on the given part factor.

    Example:

    ```python

    start = datetime.date(2021, 1, 1)
    end = datetime.date(2021, 1, 11)

    for date_range in split(
        start, end,
        part_factor=datetime.timedelta(days=2)
    ):
        print(date_range)

    # Output:
    # (datetime.date(2021, 1, 1), datetime.date(2021, 1, 3))
    # (datetime.date(2021, 1, 3), datetime.date(2021, 1, 5))
    # (datetime.date(2021, 1, 5), datetime.date(2021, 1, 7))
    # (datetime.date(2021, 1, 7), datetime.date(2021, 1, 11)) # An edge case
    # The last range is 3 days long because the next range will not be a multiple of 2 days
    ```
    """
    if start == end:
        raise ValueError("The start and end dates/datetimes cannot be the same.")
    if start > end:
        raise ValueError(
            "The start date/datetime must be less than the end date/datetime."
        )
    if parts is not None and (not isinstance(parts, int) or parts < 1):
        raise ValueError("parts must be a positive integer.")

    # Get the range/time difference between the start and end dates/datetimes
    date_range = end - start  # type: ignore
    # Calculate the number of possible parts based on the part factor
    possible_parts = date_range // part_factor
    if possible_parts < 1:
        raise ValueError(
            "The date/datetime range is too small to "
            "split into parts based on the given part factor."
        )

    base_part_factor = part_factor
    if parts and possible_parts != parts:
        if possible_parts < parts:
            raise ValueError(
                "The date/datetime range is too small to split into the "
                "specified number of parts based on the given part factor."
            )
        else:
            # If the possible number of parts (using the provided part factor),
            # exceeds the requested number of parts, increase the part factor
            # to its nearest multiple, i.e part_factor * 2, part_factor * 3, etc.
            # and recalculate the possible parts
            multiplier = 2
            while True:
                part_factor = base_part_factor * multiplier
                possible_parts = date_range // part_factor
                remainder = date_range % part_factor
                # If the possible parts are equal to the requested parts
                if possible_parts == parts and remainder == 0:
                    break

                if possible_parts < parts:
                    remainder_is_a_multiple_of_base_part_factor = (
                        remainder % base_part_factor == datetime.timedelta(0)
                    )
                    if remainder_is_a_multiple_of_base_part_factor:
                        possible_parts += 1
                        if possible_parts == parts:
                            break

                    raise ValueError(
                        "The date/datetime range is too small to split "
                        "into the specified number of parts, using on the given part factor. "
                        "Consider reducing the number of parts, providing a larger date/datetime range, "
                        "or changing the part factor."
                    )
                # Possible parts is still greater than the required number of parts
                # Increase the multiplier and try again
                multiplier += 1

    # Start splitting the date/datetime range
    # Start with the start being the lower boundary of the first part
    lower_boundary = start
    # The upper boundary of the first part is unknown at this point
    upper_boundary = None
    for _ in range(possible_parts):
        # Calculate the upper boundary of the current part
        upper_boundary = lower_boundary + part_factor

        remainder = end - upper_boundary  # type: ignore
        # If the difference between the end date/datetime and the upper boundary is less than the part factor
        if remainder < part_factor:
            remainder_is_a_multiple_of_base_part_factor = (
                remainder % base_part_factor == datetime.timedelta(0)
            )
            if remainder_is_a_multiple_of_base_part_factor:
                # If the remainder is a multiple of the base part factor,
                # yield the current lower boundary and next,
                # yield the current upper boundary (as the new lower boundary)
                # and the end date/datetime (as the upper boundary)
                yield (lower_boundary, upper_boundary)
                if upper_boundary != end:
                    yield (upper_boundary, end)

            else:
                # yield the current lower boundary and
                # the end date/datetime as the upper boundary
                yield (lower_boundary, end)
            # Break the loop as the date/datetime range has been fully split
            break
        else:
            # Otherwise, yield the current lower boundary and the current (calculated) upper boundary
            yield (lower_boundary, upper_boundary)

        # The next lower boundary is the current upper boundary
        lower_boundary = upper_boundary


def timedelta_code_to_timedelta(timedelta_code: str):
    """
    Parses the timedelta code into a timedelta object.

    A timedelta code is a string that represents a time period.
    The code is a number followed by a letter representing the unit of time.
    The following are the valid units of time:
    - D: Days
    - W: Weeks
    - M: Months
    - Y: Years

    The following are the valid timedelta codes:
    - 5D: 5 Days
    - 1W: 1 Week,
    - YTD: Year to Date (365 Days), etc.

    :param timedelta_code: The timedelta code to parse.
    :return: The timedelta object.
    :raises ValueError: If the timedelta code is invalid.

    Example:

        ```python
        timedelta_code_to_timedelta("5D")

        # Output:
        # datetime.timedelta(days=5)
        ```
    """
    if timedelta_code == "YTD":
        return datetime.timedelta(days=365)

    number, unit = timedelta_code[:-1], timedelta_code[-1]
    if not number.isdigit():
        raise ValueError("Invalid timedelta code")

    number = float(number)
    if unit.upper() == "D":
        return datetime.timedelta(days=number)
    elif unit.upper() == "W":
        return datetime.timedelta(weeks=number)
    elif unit.upper() == "M":
        return datetime.timedelta(days=number * 30)
    elif unit.upper() == "Y":
        return datetime.timedelta(days=number * 365)
    else:
        raise ValueError("Invalid timedelta code")


def timedelta_code_to_datetime_range(
    timdelta_code: str,
    *,
    now: typing.Callable[[], datetime.datetime] = datetime.datetime.now,
    timezone: typing.Optional[typing.Union[str, zoneinfo.ZoneInfo]] = None,
    future: bool = False,
) -> typing.Tuple[typing.Optional[datetime.datetime], datetime.datetime]:
    """
    Parses the timedelta code into a datetime range.

    By default, the datetime range is calculated for the past.
    To calculate the datetime range for the future, set future to True.

    :param timdelta_code: The timedelta code to parse.
    :param now: A callable that returns the current datetime.
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
    delta = timedelta_code_to_timedelta(timdelta_code)
    tz = zoneinfo.ZoneInfo(timezone) if isinstance(timezone, str) else timezone
    now_in_tz = now().astimezone(tz)

    if future:
        start = now_in_tz
        end = now_in_tz + delta
    else:
        start = now_in_tz - delta
        end = now_in_tz
    return start, end


# From display_timedelta Python package https://pypi.org/project/display-timedelta/
def display_timedelta(delta: datetime.timedelta):
    """Display a timedelta in a human-readable format."""
    if delta < datetime.timedelta(0):
        raise ValueError("cannot display negative time delta {}".format(delta))

    def plural(number):
        """Return 's' if number is not 1."""
        if number == 1:
            return ""
        return "s"

    result = []
    seconds = int(delta.total_seconds())
    days, seconds = seconds // (3600 * 24), seconds % (3600 * 24)

    if days > 0:
        result.append("{} day{}".format(days, plural(days)))
    hours, seconds = seconds // 3600, seconds % 3600

    if hours > 0:
        result.append("{} hour{}".format(hours, plural(hours)))
    minutes, seconds = seconds // 60, seconds % 60

    if minutes > 0:
        result.append("{} minute{}".format(minutes, plural(minutes)))

    if seconds > 0:
        result.append("{} second{}".format(seconds, plural(seconds)))

    if len(result) >= 3:
        return ", ".join(result[:-1]) + ", and " + result[-1]

    if len(result) == 2:
        return " and ".join(result)

    if len(result) == 1:
        return result[0]

    return "right now"


__all__ = [
    "split",
    "timedelta_code_to_timedelta",
    "timedelta_code_to_datetime_range",
    "display_timedelta",
]
