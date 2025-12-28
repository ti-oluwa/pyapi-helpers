from typing import Union
import datetime
from django.db import models


def get_objects_within_datetime_range(
    model_or_qs: Union[type[models.Model], models.QuerySet],
    /,
    start: Union[datetime.datetime, datetime.date],
    end: Union[datetime.datetime, datetime.date],
    dt_field: str,
):
    """
    Get objects with a date/datetime attribute within a specified date range.

    :param start: The start date/datetime of the date range.
    :param end: The end date/datetime of the date range.
    :param dt_field: The date/datetime field to filter on.
    :return: The objects within the specified date range.
    """
    kwargs = {
        f"{dt_field}__range": [start, end],
    }
    if issubclass(model_or_qs, models.Model):
        return model_or_qs.objects.filter(**kwargs)
    return model_or_qs.filter(**kwargs)
