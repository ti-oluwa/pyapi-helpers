"""
HTTP connection and user access control dependencies
"""

import typing
import inspect
import asyncio
import fastapi
import fastapi.params
from typing_extensions import Annotated
from starlette.requests import HTTPConnection

from src.fastapi.utils.sync import sync_to_async
from src.fastapi.exceptions.utils import raise_http_exception

from src.fastapi.dependencies.connections import (
    connected_user,
    AnyDBSession,
    _DBSession,
    _UserModel,
)
from src.fastapi.dependencies import Dependency


T = typing.TypeVar("T")
R = typing.TypeVar("R")
AccessChecker = typing.Callable[
    [T, typing.Optional[_DBSession]],
    typing.Union[bool, typing.Awaitable[bool]],
]
Handler = typing.Callable[
    [T],
    typing.Union[
        typing.Union[T, R],
        typing.Awaitable[typing.Union[T, R]],
    ],
]
RaiseAccessDenied = typing.Callable[
    [HTTPConnection, int, str, typing.Optional[typing.Dict[str, str]]],
    typing.Awaitable[typing.NoReturn],
]


def cls_to_func_dependency(cls: typing.Type[T]) -> typing.Callable[[T], T]:
    """
    Convert a class dependency to a function dependency.

    :param cls: The class dependency.
    :return: A function dependency that returns an instance of the class.
    """

    def _cls_to_func_dependency(_cls: cls) -> T:  # type: ignore
        return _cls

    return fastapi.Depends(_cls_to_func_dependency)


def access_control(
    access_info: typing.Union[
        fastapi.params.Depends,
        typing.Type[T],
        typing.Callable[
            ...,
            typing.Union[T, typing.Awaitable[T]],
        ],
    ],
    /,
    access_checker: AccessChecker[T, _DBSession],
    *,
    status_code: int = 403,
    message: str = "Access Denied!",
    headers: typing.Optional[typing.Dict[str, str]] = None,
    raise_access_denied: typing.Union[
        RaiseAccessDenied,
        typing.Literal[False],
        None,
    ] = raise_http_exception,
    return_handler: typing.Optional[Handler[HTTPConnection, R]] = None,
) -> fastapi.params.Depends:
    """
    Connection access control dependency factory.

    Returns a dependency that checks if the http connection is allowed to access to the resource
    based on the provided `access_info` and the `access_checker` function.

    Usage Example:
    ```python
    from fastapi.security.api_key import APIKeyHeader
    from sqlalchemy.ext.asyncio import AsyncSession

    def check_api_key(api_key: str, session: AsyncSession) -> bool:
        # Check if the api_key is valid
        return True

    async def check_access(
        api_key: typing.Optional[str],
        session: typing.Optional[AsyncSession]
    ) -> bool:
        if not api_key:
            return False
        return check_api_key(api_key, session)

    client_api_key = APIKeyHeader(name="X-API-KEY", auto_error=False)
    # Use auto_error=False to prevent default HTTPException from being raised
    # when the header is not provided. This allows the dependency to return None
    # instead of raising an exception. and then enables the access control dependency
    # to raise the proper http exception (regular http exception or websocket disconnect)
    # when the access is denied. This allows the access control dependeny to be used
    # with websocket connections as well.
    authorized_api_client_only = access_control(client_api_key, check_access, message="Unauthorized API client!")

    # In a route
    @app.get("/api/protected")
    async def protected_route(
        connection: HTTPConnection = Depends(authorized_api_client_only)
    ):
        return {"message": "You are authorized!"}
    ```
    In the example above, the `authorized_api_client_only` dependency checks if the connection
    is made by an authorized API client by checking the `X-API-KEY` header in the connection.
    If the header is not provided, the dependency returns `None` instead of raising an exception.
    The access control dependency then raises the proper http exception (regular http exception or websocket disconnect)
    when the access is denied.

    :param access_info: A resolveable type, callable or dependency that returns
        the necessary information (about a client) to be used to check access, by the `access_checker` function.
        This can be an `HTTPConnection` type, a `SecurityBase` instance, a `Security` or `Depends` dependency,
        a regular callable or a type that can be resolved by fastapi's dependency injection system (`fastapi.Depends`).
    :param access_checker: A callable that takes the connection object and returns a boolean
        indicating if it is allowed access or not.

    :param status_code: The status code to return if the connection is disallowed access.
        Default is `HTTP_403_FORBIDDEN`.

    :param message: The message to return if the connection is disallowed access.
    :param headers: Optional headers to include in the response when access is denied.
    :param raise_access_denied: A callable that raises an exception with the provided status code and message.
        If not provided or falsy, no exception is raised and the connection is returned by the dependency.

        Setting this to falsy value can be useful when you want changes made to be made to the connection object
        by the access checker to remain if the connection is allowed, but not if it is denied,
        without raising an exception. There by allowing the connection to be served, with or without the required access.

    :param return_handler: A callable that takes the connection object and returns a result - the modified connection object or another object.
        If provided, the dependency returns the result of the handler instead of the connection object.

    :return: A dependency that checks if the connection is allowed access to the resource.
    """
    if inspect.isclass(access_info):
        access_info = cls_to_func_dependency(access_info)

    async def dependency(
        connection: HTTPConnection,
        access_info: Annotated[T, Dependency(access_info)],
        session: AnyDBSession[_DBSession],
    ):
        if access_info is not None:
            if not asyncio.iscoroutinefunction(access_checker):
                has_access = await sync_to_async(access_checker)(access_info, session)
            else:
                has_access = await access_checker(access_info, session)
        else:
            has_access = False

        if not has_access and raise_access_denied:
            await raise_access_denied(connection, status_code, message, headers)

        if return_handler:
            if not asyncio.iscoroutinefunction(return_handler):
                return await sync_to_async(return_handler)(connection)
            else:
                return await return_handler(connection)
        return connection

    return fastapi.Depends(dependency)


def user_access_control(
    access_checker: AccessChecker[typing.Optional[_UserModel], _DBSession],
    *,
    get_user: typing.Union[
        fastapi.params.Depends,
        typing.Callable[
            ...,
            typing.Union[
                typing.Optional[_UserModel],
                typing.Optional[typing.Awaitable[_UserModel]],
            ],
        ],
    ] = connected_user,
    status_code: int = 403,
    message: str = "Access Denied!",
    headers: typing.Optional[typing.Dict[str, str]] = None,
    raise_access_denied: typing.Union[
        RaiseAccessDenied,
        typing.Literal[False],
        None,
    ] = raise_http_exception,
    return_handler: typing.Optional[Handler[_UserModel, R]] = None,
):
    """
    Connection access control dependency factory.

    Returns a dependency that checks if the connected user is allowed access to the resource
    based on the provided user `access_checker` function.

    :param access_checker: A callable that takes the connected user object and returns a boolean
        indicating if the user has access to the resource or not.

    :param get_user: A callable or dependency that returns the connected user object,
        usually from the request/connection.
        Default is `connected_user`. This is used as dependency to get the connected user.

    :param status_code: The status code to return if the user is disallowed access.
        Default is `HTTP_403_FORBIDDEN`.

    :param message: The message to return if the user is disallowed access.
    :param headers: Optional headers to include in the response when access is denied.
    :param raise_access_denied: A callable that raises an exception with the provided status code and message.
        If not provided or falsy, no exception is raised and the user is returned by the dependency.

        Setting this to a falsy value be can useful when you want changes made to be made to the user object
        by the access checker to remain if the user is allowed, but not if it is denied,
        without raising an exception. There by allowing the user to be served, with or without the required access.

    :param result_handler: A callable that takes the user object and returns a result - the modified user object or another object.
        If provided, the dependency returns the result of the handler instead of the user object.

    :return: A dependency that checks if the user is allowed access to the resource.
    """
    cached_user = None
    if return_handler and not asyncio.iscoroutinefunction(return_handler):
        return_handler = sync_to_async(return_handler)  # type: ignore

    async def _get_user(
        user: Annotated[typing.Optional[_UserModel], Dependency(get_user)],
    ):
        nonlocal cached_user
        cached_user = user
        return user

    async def _return_handler(_: HTTPConnection):
        nonlocal cached_user

        if cached_user and return_handler:
            return await return_handler(cached_user)  # type: ignore
        return cached_user

    return access_control(
        _get_user,
        access_checker,
        status_code=status_code,
        message=message,
        headers=headers,
        raise_access_denied=raise_access_denied,
        return_handler=_return_handler,
    )


async def is_authenticated(user: typing.Optional[_UserModel], _) -> bool:
    """
    Check if the connected user is authenticated.

    :param user: The connected user.
    :return: True if the connected user is authenticated, False otherwise.
    """
    if user is None:
        return False
    return user.is_authenticated


authenticated_user_only = user_access_control(
    is_authenticated, message="Authentication Required!"
)
"""
Connection access control dependency that requires the connected user to be authenticated.

:raises HTTPException/WebSocketDisconnect: If the connected user is not authenticated.
:return: The connected user if authenticated.
"""
AuthenticatedUser = Annotated[_UserModel, authenticated_user_only]
"""
Annotated connection access control dependency type that requires the connected user to be authenticated.

:raises HTTPException/WebSocketDisconnect: If the connected user is not authenticated.
:return: The connected user if authenticated.
"""


async def is_active(user: typing.Optional[_UserModel], _) -> bool:
    """
    Check if the connected user is active.

    :param user: The connected user.
    :return: True if the connected user is active, False otherwise.
    """
    if user is None:
        return False
    return getattr(user, "is_active", False)


active_user_only = user_access_control(is_active, get_user=authenticated_user_only)
"""
Access control dependency that requires the connected user to be (authenticated and) active.

:raises HTTPException/WebSocketDisconnect: If the connected user is not active.
:return: The connected user if active.
"""
ActiveUser = Annotated[_UserModel, active_user_only]
"""
Annotated connection access control dependency type that requires the connected user to be (authenticated and) active.

:raises HTTPException/WebSocketDisconnect: If the connected user is not active.
:return: The connected user if active.
"""


async def is_admin(user: typing.Optional[_UserModel], _) -> bool:
    """
    Check if the connected user is an admin.

    :param user: The connected user.
    :return: True if the connected user is an admin, False otherwise.
    """
    if user is None:
        return False
    return getattr(user, "is_admin", False)


admin_user_only = user_access_control(is_admin, get_user=active_user_only)
"""
Access control dependency that requires the connected user to be (authenticated and) an admin.

:raises HTTPException/WebSocketDisconnect: If the connected user is not an admin.
:return: The connected user if an admin.
"""
AdminUser = Annotated[_UserModel, admin_user_only]
"""
Annotated connection access control dependency type that requires the connected user to be (authenticated and) an admin.

:raises HTTPException/WebSocketDisconnect: If the connected user is not an admin.
:return: The connected user if an admin.
"""


async def is_staff(user: typing.Optional[_UserModel], _) -> bool:
    """
    Check if the connected user is a staff.

    :param user: The connected user.
    :return: True if the connected user is a staff, False otherwise.
    """
    if user is None:
        return False
    return getattr(user, "is_staff", False)


staff_user_only = user_access_control(is_staff, get_user=active_user_only)
"""
Access control dependency that requires the connected user to be (authenticated and) a staff.

:raises HTTPException/WebSocketDisconnect: If the connected user is not a staff.
:return: The connected user if a staff.
"""
StaffUser = Annotated[_UserModel, staff_user_only]
"""
Annotated dependency type that requires the connected user to be (authenticated and) a staff.

:raises HTTPException/WebSocketDisconnect: If the connected user is not a staff.
:return: The connected user if a staff.
"""
