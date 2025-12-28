import typing
import re
import string
import fastapi

from ..config import settings
from src.generics.utils.module_loading import import_string

COMMON_PASSWORDS = [
    "password",
    "123456",
    "123456789",
    "12345678",
    "12345",
    "123123",
    "qwerty",
    "abc123",
    "iloveyou",
    "admin",
    "welcome",
    "monkey",
    "football",
    "letmein",
    "111111",
    "sunshine",
    "000000",
    "master",
    "login",
    "passw0rd",
]


def common_password_validator(value: str) -> str:
    """
    Validates that the password is not a common password

    :param value: The value to validate
    :return: The value if it is valid
    :raises ValueError: If the value is not valid
    """
    if value.lower() in COMMON_PASSWORDS:
        raise ValueError("Password is too common")
    return value


def mixed_case_validator(value: str) -> str:
    """
    Validates that the password contains both upper and lower case characters

    :param value: The value to validate
    :return: The value if it is valid
    :raises ValueError: If the value is not valid
    """
    if not any(char.isupper() for char in value) or not any(
        char.islower() for char in value
    ):
        raise ValueError("Password must contain both upper and lower case characters")
    return value


def special_characters_validator(value: str) -> str:
    """
    Validates that the password contains special characters

    :param value: The value to validate
    :return: The value if it is valid
    :raises ValueError: If the value is not valid
    """
    if not any(char in string.punctuation for char in value):
        raise ValueError("Password must contain special characters")
    return value


def digit_validator(value: str) -> str:
    """
    Validates that the password contains a digit

    :param value: The value to validate
    :return: The value if it is valid
    :raises ValueError: If the value is not valid
    """
    if not any(char.isdigit() for char in value):
        raise ValueError("Password must contain a digit")
    return value


def whitespace_validator(value: str) -> str:
    """
    Validates that the password contains whitespace

    :param value: The value to validate
    :return: The value if it is valid
    :raises ValueError: If the value is not valid
    """
    if not any(char.isspace() for char in value):
        raise ValueError("Password must not contain whitespace")
    return value


def consecutive_characters_validator(value: str) -> str:
    """
    Validates that the password does not contain consecutive characters

    :param value: The value to validate
    :return: The value if it is valid
    :raises ValueError: If the value is not valid
    """
    if re.search(r"(.)\1", value):
        raise ValueError("Password must not contain consecutive characters")
    return value


PASSWORD_STRENGTH_VALIDATORS = [
    common_password_validator,
    mixed_case_validator,
    special_characters_validator,
    digit_validator,
]


def password_strength_validator(
    value: str,
    min_strength: float = 0.7,
    password_validators: typing.List[typing.Callable] = PASSWORD_STRENGTH_VALIDATORS,
) -> str:
    """
    Validates the strength of a password

    :param value: The value to validate
    :param min_strength: The minimum strength of the password
    :param password_validators: The list of password validators to use
    :return: The value if it is valid
    :raises ValueError: If the value is not valid
    """
    possible_weight = len(password_validators)
    weight = 0

    errors = []
    for validator in password_validators:
        try:
            validator(value)
            weight += 1
        except ValueError as exc:
            errors.append(str(exc))
            pass

    strength = weight / possible_weight
    if strength < min_strength:
        raise ValueError("Password is too weak.\n" + "\n".join(errors))
    return value


def password_validators():
    """Yield all password validators defined in the settings"""
    for path in settings.PASSWORD_VALIDATORS:
        if not isinstance(path, str):
            raise ValueError(
                "Entry in PASSWORD_VALIDATORS must be a string path to the validator function"
            )
        validator = import_string(path)
        yield validator


def validate_password(
    password: str,
    validators: typing.Union[
        typing.Callable[[], typing.Iterable[typing.Callable]],
        typing.Iterable[typing.Callable],
    ] = password_validators,
) -> str:
    """
    Run all password validators on the password

    :param password: The password to validate
    :param validators: The list or iterator of password validators to use
    """
    errors = []
    if callable(validators):
        validators = validators()

    for validator in validators:
        try:
            validator(password)
        except ValueError as exc:
            errors.append(str(exc))
        except fastapi.exceptions.ValidationException as exc:
            errors.extend(exc.errors())
    if errors:
        raise fastapi.exceptions.ValidationException(errors=errors)
    return password


__all__ = [
    "common_password_validator",
    "mixed_case_validator",
    "special_characters_validator",
    "digit_validator",
    "whitespace_validator",
    "consecutive_characters_validator",
    "PASSWORD_STRENGTH_VALIDATORS",
    "password_strength_validator",
    "password_validators",
    "validate_password",
]
