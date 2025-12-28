import datetime
import typing
import uuid
import sqlalchemy as sa
from sqlalchemy import orm

from src.fastapi.utils import timezone


def uuid7(as_type: typing.Optional[typing.Union[str, type]] = uuid.UUID):
    from uuid_extensions import uuid7  # type: ignore[import]

    return uuid7(as_type=as_type)  # type: ignore


@orm.declarative_mixin
class TimestampMixin:
    """Adds timestamp fields to the database model"""

    created_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sa.DateTime(timezone=True),
        default=timezone.now,
        nullable=False,
        doc="The timestamp of creation",
    )
    updated_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sa.DateTime(timezone=True),
        default=None,
        onupdate=timezone.now,
        nullable=True,
        doc="The timestamp of the last update",
    )


@orm.declarative_mixin
class UUIDPrimaryKeyMixin:
    """Adds a UUID Field, `id`, as the primary key of the database model"""

    id: orm.Mapped[uuid.UUID] = orm.mapped_column(
        sa.UUID,
        primary_key=True,
        index=True,
        default=uuid.uuid4,
        doc="The primary key of the model",
    )


@orm.declarative_mixin
class UUID7PrimaryKeyMixin:
    """Adds a UUID Field, `id`, as the primary key of the database model"""

    id: orm.Mapped[uuid.UUID] = orm.mapped_column(
        sa.UUID,
        primary_key=True,
        index=True,
        default=uuid7,
        doc="The primary key of the model",
    )
