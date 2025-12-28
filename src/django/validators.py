import enum
from typing import Any, Optional, Union
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    MinLengthValidator,
    MaxLengthValidator,
)


def max_file_size_validator_factory(maxsize: float | int):
    """
    Factory function. Creates a file size validator function

    :param maxsize: Maximum allowed file size in kilobytes
    """

    def max_file_size_validator(file: File) -> None:
        file_size = file.size / 1024
        if file_size > maxsize:
            raise ValidationError(
                f"File size exceeds the maximum allowed size of {maxsize} kilobytes"
            )
        return None

    max_file_size_validator.__name__ = f"file_size_does_not_exceed_{maxsize}KB"
    return max_file_size_validator


class CheckType(enum.Enum):
    LENGTH = "length"
    VALUE = "value"


def min_max_validator_factory(
    min_value: Optional[Union[int, float]] = None,
    max_value: Optional[Union[int, float]] = None,
    check: CheckType = "length",
):
    """
    Factory function for creating a minimum and maximum validator

    :param min_value: The minimum limit
    :param max_value: The maximum limit
    :param check: what quantity to validate. Can be any of `CheckType`
    """
    if not (max_value or min_value):
        raise ValueError("At least one of min_value or max_value is required.")

    check = CheckType(check)
    min_validator_class = None
    max_validator_class = None
    if check == CheckType.LENGTH:
        min_validator_class = MinLengthValidator
        max_validator_class = MaxLengthValidator
    else:
        min_validator_class = MinValueValidator
        max_validator_class = MaxValueValidator

    def min_max_validator(value: Any) -> Any:
        nonlocal min_validator_class
        nonlocal max_validator_class
        error_list = []
        validators = []
        if min_value:
            validators.append(min_validator_class(min_value))
        if max_value:
            validators.append(max_validator_class(max_value))

        for validator in validators:
            try:
                validator(value)
            except ValidationError as exc:
                error_list.extend(exc.error_list)
                continue

        if error_list:
            raise ValidationError(error_list, code="min_max_value")
        return

    return min_max_validator
