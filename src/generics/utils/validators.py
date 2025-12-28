import typing
import re

_T = typing.TypeVar("_T")

NOT_SET = object()


def min_length_validator(min_length: int, value: _T = NOT_SET) -> _T:
    """
    Validates the minimum length of a string

    :param value: The value to validate
    :param min_length: The minimum length of the string
    :return: The value if it is valid
    :raises ValueError: If the value is not valid
    """
    if value is NOT_SET:
        return lambda v: min_length_validator(min_length, v)  # type: ignore

    if len(value) < min_length:  # type: ignore
        raise ValueError(f"Value must be at least {min_length} characters long")
    return value


def max_length_validator(max_length: int, value: _T = NOT_SET) -> _T:
    """
    Validates the maximum length of a string

    :param value: The value to validate
    :param max_length: The maximum length of the string
    :return: The value if it is valid
    :raises ValueError: If the value is not valid
    """
    if value is NOT_SET:
        return lambda v: max_length_validator(max_length, v)  # type: ignore

    if len(value) > max_length:  # type: ignore
        raise ValueError(f"Value must be at most {max_length} characters long")
    return value


email_regex = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$")


def email_validator(value: str) -> str:
    """
    Validates an email address

    :param value: The email address to validate
    :return: The email address if it is valid
    :raises ValueError: If the email address is not valid
    """
    if not email_regex.match(value):
        raise ValueError("Invalid email address")
    return value
