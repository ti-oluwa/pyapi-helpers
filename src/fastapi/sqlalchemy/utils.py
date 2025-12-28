import typing
import re
import sqlalchemy as sa
from sqlalchemy.orm import InstrumentedAttribute, DeclarativeMeta, MappedColumn

from src.fastapi.sqlalchemy.models import ModelBase


def text_to_tsvector(
    text: typing.Union[str, InstrumentedAttribute[str]], language: str = "english"
):
    """Convert text to a tsvector for full-text search."""
    return sa.func.to_tsvector(language, text)


def text_to_tsquery(
    text: typing.Union[str, InstrumentedAttribute[str]], language: str = "english"
):
    """Convert text to a tsquery for full-text search."""
    return sa.func.websearch_to_tsquery(language, text)


def fuzzy_text_search(
    column: typing.Any, search_term: str, threshold: float = 0.3
) -> sa.ColumnElement[bool]:
    """Create fuzzy search condition using trigram similarity."""
    return sa.func.similarity(column, search_term) > threshold


def enhanced_text_search(column: typing.Any, search_term: str) -> sa.ColumnElement[bool]:
    """Combine exact, fuzzy, and full-text search."""
    tsquery = text_to_tsquery(search_term)

    return sa.or_(
        # Exact match (highest priority)
        column.ilike(f"%{search_term}%"),
        # Full-text search
        sa.func.to_tsvector("english", column).op("@@")(tsquery),
        # Fuzzy match (lowest priority)
        fuzzy_text_search(column, search_term, 0.2),
    )


def query_to_regex_pattern(query: str) -> str:
    """Convert search query to a flexible regex pattern.
    Handles spaces, hyphens, and other word separators flexibly."""
    cleaned = query.strip().lower()
    escaped = re.escape(cleaned)
    words = escaped.split(r"\ ")
    pattern = r".*".join(words)
    return f".*{pattern}.*"


def build_conditions(
    filters: typing.Mapping[str, typing.Any],
    model: typing.Union[typing.Type[DeclarativeMeta], typing.Type[ModelBase]],
    in_for_iterable: bool = False,
) -> typing.List[sa.BinaryExpression[typing.Any]]:
    """
    Build SQLAlchemy conditions from a dictionary of filters.

    Each key-value pair in the dictionary corresponds to a column
    in the model. The value can be a single value, a list of values,
    or a boolean indicating the condition.

    :param filters: A dictionary of filters to apply.
    :param model: The SQLAlchemy model to apply the filters to.
    :param in_for_iterable: If True, use `in_` for iterable values.
    :return: A list of SQLAlchemy conditions.
    :raises AttributeError: If a filter key does not correspond to a column in the model.
    """
    conditions: typing.List[sa.BinaryExpression[typing.Any]] = []
    if not filters:
        return conditions

    for key, value in filters.items():
        column: typing.Union[sa.Column, MappedColumn] = getattr(model, key)
        if in_for_iterable and isinstance(value, (list, tuple, set)):
            conditions.append(column.in_(value))
        elif isinstance(value, bool):
            conditions.append(column.is_(value))
        else:
            conditions.append(column == value)
    return conditions
