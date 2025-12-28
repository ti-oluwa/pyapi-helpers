import typing
import fastapi
from starlette.requests import HTTPConnection

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from src.fastapi.models.users import AbstractBaseUser
from src.fastapi.exceptions.utils import raise_http_exception


_UserModel = typing.TypeVar("_UserModel", bound=AbstractBaseUser)
_DBSession = typing.TypeVar("_DBSession", Session, AsyncSession)


def any_db_session(connection: HTTPConnection) -> typing.Optional[_DBSession]:
    """
    Returns the database session for the HTTP connection, if any.

    This is meant be used along with the `SessionMiddleware` or `AsyncSessionMiddleware` middleware.
    """
    return getattr(connection.state, "db_session", None)


AnyDBSession = typing.Annotated[
    typing.Optional[_DBSession], fastapi.Depends(any_db_session)
]
"""FastAPI dependency annotation used to inject the HTTP connection's database session, if any."""


async def db_session(db_session: AnyDBSession, connection: HTTPConnection) -> Session:
    """
    Returns the database session for the HTTP connection.

    Ensures that the session is synchronous, an instance of `sqlalchemy.orm.Session`.

    :param db_session: The database session.
    :param connection: The HTTP connection.
    :return: The synchronous database session.
    :raises HTTPException: If the session is not synchronous.
    """
    if not isinstance(db_session, Session):
        return await raise_http_exception(
            connection,
            status_code=500,
            detail="Synchronous database connection unavailable",
        )
    return db_session


DBSession = typing.Annotated[Session, fastapi.Depends(db_session)]
"""
FastAPI dependency annotation used to inject the HTTP connection's synchronous database session.

This is meant to be used when the database session is expected to be synchronous.
Raises an HTTP 500 exception if the session is not synchronous.
"""


async def async_db_session(
    db_session: AnyDBSession, connection: HTTPConnection
) -> AsyncSession:
    """
    Returns the database session for the HTTP connection.

    Ensures that the session is asynchronous, an instance of `sqlalchemy.ext.asyncio.AsyncSession`.

    :param db_session: The database session.
    :param connection: The HTTP connection.
    :return: The asynchronous database session.
    :raises HTTPException: If the session is not asynchronous
    """
    if not isinstance(db_session, AsyncSession):
        return await raise_http_exception(
            connection,
            status_code=500,
            detail="Asynchronous database connection unavailable",
        )
    return db_session


AsyncDBSession = typing.Annotated[AsyncSession, fastapi.Depends(async_db_session)]
"""
FastAPI dependency annotation used to inject the HTTP connection's asynchronous database session.

This is meant to be used when the database session is expected to be asynchronous.
Raises an HTTP 500 exception if the session is not asynchronous.
"""


def connected_user(connection: HTTPConnection) -> typing.Optional[AbstractBaseUser]:
    """
    Returns the user associated with the connection.

    This is meant be used along with the `ConnectedUserMiddleware` middleware.
    """
    return getattr(connection.state, "user", None)


User = typing.Annotated[typing.Optional[_UserModel], fastapi.Depends(connected_user)]
"""FastAPI dependency annotation used to inject the HTTP connection user."""
