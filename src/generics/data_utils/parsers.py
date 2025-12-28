import datetime


def cleanString(value: str) -> str:
    """Clean a string by removing leading and trailing whitespaces."""
    if not value:
        return ""
    return value.strip()


def toCamelCase(snake_str: str) -> str:
    """
    Convert a snake_case string to camelCase.

    :param snake_str: The snake_case string to convert.
    :return: The camelCase string.
    """
    if not snake_str:
        return snake_str
    components = snake_str.split("_")
    if len(components) == 1:
        return components[0]
    return components[0] + "".join(x.title() for x in components[1:])


def covertAnsToBool(value: str) -> bool:
    """Convert a string 'Yes' or 'No' to a boolean value."""
    if not value:
        return False
    return value.lower() == "yes"


def strToDateTime(
    value: str, *, format: str = "%Y-%m-%dT%H:%M:%S.%fZ"
) -> datetime.datetime | None:
    """Converts datetime string in the specified format to a datetime.datetime object"""
    if not value:
        return None
    try:
        dt_object = datetime.datetime.strptime(value, format).astimezone()
        return dt_object
    except ValueError:
        return None


def strToDate(value: str, *, format="%Y-%m-%d") -> datetime.date | None:
    """Converts datetime/date string in the specified format to a datetime.date object"""
    if not value:
        return None
    try:
        date_object = datetime.datetime.strptime(value, format).date()
        return date_object
    except ValueError:
        return None
