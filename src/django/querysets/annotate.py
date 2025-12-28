from django.db import models
from django.db.models import F, Case, When, Value
from django.db.models.functions import Cast
from typing import TypeVar

M = TypeVar("M", bound=models.Model)


def annotate_with_integer_cast(
    queryset: models.QuerySet[M],
    *,
    field_name: str,
    alias: str = None,
    default_value: int = 0,
) -> models.QuerySet[M]:
    """
    Annotate the queryset to cast the given field to an integer, providing a default value for invalid integers.

    :param queryset: The queryset to annotate.
    :param field_name: The name of the field to cast.
    :param alias: The alias for the annotated field. If not provided, `<field_name>_int` is used.
    :param default_value: The default value to use if the cast fails.
    :return: The annotated queryset.
    """
    alias = alias or f"{field_name}_int"
    return queryset.annotate(
        **{
            alias: Case(
                When(
                    **{
                        f"{field_name}__regex": r"^\d+$"
                    },  # Check if the field contains only digits
                    then=Cast(F(field_name), output_field=models.IntegerField()),
                ),
                default=Value(default_value),  # Default value if casting fails
                output_field=models.IntegerField(),
            )
        }
    )


def annotate_with_string_cast(
    queryset: models.QuerySet[M],
    *,
    field_name: str,
    alias: str = None,
    default_value: int = "",
) -> models.QuerySet[M]:
    """
    Annotate the queryset to cast the given field to a string, providing a default value for invalid casts.

    :param queryset: The queryset to annotate.
    :param field_name: The name of the field to cast.
    :param alias: The alias for the annotated field. If not provided, `<field_name>_str` is used.
    :param default_value: The default value to use if the cast fails.
    :return: The annotated queryset.
    """
    alias = alias or f"{field_name}_str"
    return queryset.annotate(
        **{
            alias: Case(
                When(
                    **{
                        f"{field_name}__isnull": False
                    },  # Check if the field is not null
                    then=Cast(F(field_name), output_field=models.CharField()),
                ),
                default=Value(default_value),  # Default value if casting fails
                output_field=models.CharField(),
            )
        }
    )
