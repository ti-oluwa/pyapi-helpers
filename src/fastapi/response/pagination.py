import typing
from annotated_types import Ge

import pydantic
from starlette.requests import Request

from src.fastapi.response import DataSchema

T = typing.TypeVar("T")


@typing.final
class Page(pydantic.BaseModel, typing.Generic[T]):
    """Schema for paginated data response."""

    count: typing.Annotated[int, Ge(0)]
    total: typing.Annotated[typing.Optional[int], Ge(0)] = None
    limit: int
    offset: int
    next: typing.Optional[pydantic.StrictStr]
    previous: typing.Optional[pydantic.StrictStr]
    data: T


def as_page(
    request: Request,
    data: T,
    limit: int,
    offset: int,
    total: typing.Optional[int] = None,
    query_params: typing.Optional[typing.Dict[str, typing.Any]] = None,
    count: typing.Optional[typing.Union[typing.Callable[[T], int], int]] = None,
) -> Page[T]:
    """
    Convert data resulting from pagination
    to structured data with necessary page info.

    :param request: FastAPI request of the route/endpoint.
    :param data: An iterable of data items resulting from pagination.
    :param limit: The limit value used for pagination.
    :param offset: The offset value used for pagination.
    :param total: The total number of items available for pagination.
    :param query_params: Additional query parameters to include in the pagination links.
        This overrides any existing query parameters in the request URL, excluding `offset`.
    :param count: Optional callable or integer to determine the count of items.
    :return: A dictionary representing the structured paginated data.
    """
    next_offset = offset + limit
    prev_offset = offset - limit
    next_url = None
    prev_url = None

    if count is None and hasattr(data, "__len__"):
        count = len(data)  # type: ignore
    elif callable(count):
        count = count(data)
    else:
        count = len(list(data))  # type: ignore

    request_query_params = dict(request.query_params)
    if query_params:
        request_query_params.update(query_params)

    request_query_params.pop("offset", None)
    if total:
        # If we have the total number of items, we can determine if there are more
        # items to fetch by checking if the next offset is less than the total.
        # If it is, then there are more items to fetch.
        if next_offset < total:
            next_url = request.url.replace_query_params(
                **request_query_params, offset=next_offset
            )
    else:
        # If we get exactly the number of items we requested, there might be more
        # items to fetch. So we can add a next link.
        if count == limit:
            next_url = request.url.replace_query_params(
                **request_query_params, offset=next_offset
            )
        # Else, if we get less than the number of items we requested, then it
        # mostlikely means that we have reached the end of the list.

    if prev_offset >= 0:
        prev_url = request.url.replace_query_params(
            **request_query_params, offset=prev_offset
        )

    return Page(
        count=count,
        total=total,
        limit=limit,
        offset=offset,
        next=str(next_url) if next_url else None,
        previous=str(prev_url) if prev_url else None,
        data=data,
    )


PageResponse: typing.TypeAlias = DataSchema[Page[T]]


__all__ = [
    "as_page",
    "Page",
    "PageResponse",
]
