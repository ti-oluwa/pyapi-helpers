import fastapi
from inflection import pluralize, humanize, underscore
import pydantic
import typing
import datetime
import sqlalchemy as sa
from annotated_types import Ge, Le

from src.fastapi.sqlalchemy.models import ModelBase
from src.fastapi.utils import timezone

T = typing.TypeVar("T")


@typing.final
class QueryParamNotSet(pydantic.BaseModel):
    """Sentinel class which represent an unset query parameter"""

    def __bool__(self) -> bool:
        return False

    def __or__(self, other: T) -> T:
        return other

    __ror__ = __or__

    def __repr__(self) -> str:
        return "QueryParamNotSet"

    def __class_getitem__(cls, *args):  # type: ignore
        return None

    def __copy__(self):
        return self

    def __iter__(self):  # type: ignore
        return iter([])

    def __deepcopy__(
        self, memo: typing.Optional[typing.Dict[int, typing.Any]] = None
    ) -> "QueryParamNotSet":
        return self


ParamNotSet = QueryParamNotSet()


def clean_params(**params: typing.Any) -> typing.Dict[str, typing.Any]:
    """
    Exclude query parameters that are not set, i.e. instances of `QueryParamNotSet`
    """
    return {
        key: value
        for key, value in params.items()
        if not isinstance(value, QueryParamNotSet)
    }


Limit: typing.TypeAlias = typing.Annotated[
    pydantic.PositiveInt,
    Le(1000),
    Ge(1),
    fastapi.Query(
        description="Maximum number of objects to return",
        example=100,
    ),
]
"""Annotated dependency for a limit query parameter with a value between 1 and 1000"""

Offset: typing.TypeAlias = typing.Annotated[
    int,
    Ge(0),
    fastapi.Query(
        description="Number of objects to skip",
        example=0,
    ),
]
"""Annotated dependency for an offset query parameter with a value of at least 0"""

_T = typing.TypeVar(
    "_T",
    bound=ModelBase,
    covariant=True,
)

OrderingExpressions: typing.TypeAlias = typing.List[sa.UnaryExpression[_T]]
"""Type alias for a list of SQLAlchemy ordering expressions"""

DEFAULT_QUERY_PARSER_DESCRIPTION = "Order '{name_plural}' by field names. Prefix with '-' for descending order. Separate multiple columns with commas"


def query_parser_factory(
    param_name: str,
    description: str,
    process_value: typing.Optional[typing.Callable[[str], T]] = None,
):
    """
    Builds a FastAPI query parameter parser dependency.

    :param param_name: The name of the query parameter to parse.
    :param description: Description of the query parameter.
    :param process_value: Optional function to process the value of the query parameter.
        If provided, it should take a string and return a value of type T.
        If None, the value will be stripped and returned as is.
    :return: A FastAPI dependency function that parses the query parameter.
    """

    async def query_parser(
        value: typing.Annotated[
            typing.Optional[str],
            fastapi.Query(
                description=description,
                alias=param_name,
                alias_priority=1,
            ),
        ] = None,
    ) -> typing.Union[str, T, QueryParamNotSet]:
        if value is None:
            return ParamNotSet
        if process_value is not None:
            return process_value(value)
        return value.strip() or ParamNotSet

    return query_parser


def ordering_query_parser_factory(
    ordered: typing.Type[_T],
    *,
    allowed_columns: typing.Optional[typing.Set[str]] = None,
    description: typing.Optional[str] = None,
) -> typing.Callable[
    [str],
    typing.Awaitable[typing.Union[OrderingExpressions[_T], QueryParamNotSet]],
]:
    """
    Dependency factory.

    Builds an ordering query parameter parser.

    :param ordered: The SQLAlchemy model class to order on.
    :param allowed_columns: Allowed columns for ordering on the entity/model.
        If None, all columns of the model are allowed.
        If an empty set, no columns are allowed.
    :param description: Description of the query parameter.
        If None, a default description is used.
    :return: Dependency function to parse ordering query parameter

    Example Usage:

    ```python
    # query.py
    from .models import Item
    from src.fastapi.requests.query import ordering_query_parser_factory, OrderingExpressions

    # Build a query parser for fields on Item
    # This will allow ordering on the 'name' and 'created_at' columns
    # and will raise an error if any other column is used
    # in the query parameter.
    item_ordering_query_parser = ordering_query_parser_factory(
        Item,
        allowed_columns={"name", "created_at"},
    )

    # Define a type alias for the ordering query parameter
    ItemOrdering: typing.TypeAlias = typing.Annotated[
        typing.Union[OrderingExpressions[Item], QueryParamNotSet],
        fastapi.Depends(item_ordering_query_parser),
    ]

    # endpoints.py
    from .query import ItemOrdering
    from src.fastapi.requests.query import Limit, Offset, ParamNotSet

    @router.get(
        "/items/",
        response_model=typing.List[Item],
    )
    async def list_items(
        session: DBSession,
        limit: Limit = 100,
        offset: Offset = 0,
        ordering: ItemOrdering = ParamNotSet,
    ):
        query = session.query(Item)
        if isinstance(ordering, list):
            query = query.order_by(*ordering)
        return await query.offset(offset).limit(limit).all()
    ```
    """
    if allowed_columns is not None and not allowed_columns:
        raise ValueError("allowed_columns must not be an empty set")

    if allowed_columns is None:
        allowed_columns = {column.name for column in ordered.__table__.columns}  # type: ignore
    else:
        table_columns = ordered.__table__.columns  # type: ignore
        for column in allowed_columns:
            if column not in table_columns:
                raise ValueError(
                    f"Column {column} not found in ordered model '{ordered.__name__}'"
                )

    name_plural = pluralize(humanize(underscore(ordered.__name__)))
    description = description or DEFAULT_QUERY_PARSER_DESCRIPTION

    async def query_parser(
        ordering: typing.Annotated[
            typing.Optional[str],
            fastapi.Query(
                description=description.format(name_plural=name_plural),
                examples=list(allowed_columns),
            ),
        ] = None,
    ) -> typing.Union[OrderingExpressions[_T], QueryParamNotSet]:
        if ordering is None:
            return ParamNotSet

        if isinstance(ordering, str):
            ordering_columns = ordering.split(",")
        else:
            ordering_columns = ordering

        check_columns = allowed_columns is not None
        if check_columns and not allowed_columns:
            raise ValueError("allowed_columns must not be an empty set")

        result = []
        for column in ordering_columns:
            is_desc = column.startswith("-")
            clean_column = column[1:] if is_desc else column

            if check_columns and clean_column not in allowed_columns:
                raise fastapi.HTTPException(
                    status_code=422,
                    detail=f"Invalid column name: {clean_column!r}. Allowed columns: {', '.join(allowed_columns)}",
                )

            # Use SQLAlchemy's column reference instead of raw string
            # to prevent SQL injection attacks
            col = sa.column(clean_column)
            result.append(sa.desc(col) if is_desc else sa.asc(col))

        return result

    return query_parser


def timestamp_query_parser(query_param: str):
    """
    Dependency factory.

    Builds a dependency that parses a timestamp query parameter
    into a (timezone-aware) datetime object

    :param query_param: The name of the query parameter to parse
    :return: A dependency function that parses the query parameter into a datetime object


    Example Usage:
    ```python
    # query.py
    from src.fastapi.requests.query import timestamp_query_parser
    from src.fastapi.requests.query import QueryParamNotSet

    # Define a type alias for the timestamp query parameter
    TimestampGte: typing.TypeAlias = typing.Annotated[
        typing.Union[datetime.datetime, QueryParamNotSet],
        fastapi.Depends(timestamp_query_parser("timestamp_gte")),
    ]

    # endpoints.py
    from .models import Item
    from .query import TimestampGte
    from src.fastapi.requests.query import Limit, Offset, ParamNotSet

    @router.get(
        "/items/",
        response_model=typing.List[Item],
    )
    async def list_items(
        session: DBSession,
        limit: Limit = 100,
        offset: Offset = 0,
        timestamp_gte: TimestampGte = ParamNotSet,
    ):
        query = session.query(Item)
        if isinstance(timestamp_gte, datetime.datetime):
            query = query.filter(Item.timestamp >= timestamp_gte)
        return await query.offset(offset).limit(limit).all()
    ```
    """

    def _query_parser(
        timestamp: typing.Annotated[
            typing.Optional[str],
            fastapi.Query(
                description="String representing a datetime, preferably in ISO 8601 format",
                example="2023-10-01T12:00:00Z",
                alias=query_param,
                alias_priority=1,
            ),
        ] = None,
    ) -> typing.Union[datetime.datetime, QueryParamNotSet]:
        if timestamp is None:
            return ParamNotSet
        return (
            pydantic.TypeAdapter(pydantic.AwareDatetime)
            .validate_python(timestamp, strict=False)
            .astimezone(timezone.get_current_timezone())
        )

    _query_parser.__name__ = f"parse_{query_param}_query"
    return _query_parser


__all__ = [
    "Limit",
    "Offset",
]
