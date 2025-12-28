import typing
from fastapi.params import Depends, Param
from pydantic.fields import FieldInfo
from starlette.requests import HTTPConnection

from src.fastapi.config import settings


class ConnectionEvent(typing.TypedDict):
    event: str
    target: typing.Optional[typing.Any]
    target_uid: typing.Optional[typing.Any]
    description: typing.Optional[str]


def value_to_dependency(
    value: typing.Any,
    /,
    *,
    dependency_name: str,
    dependency_type: typing.Type[Depends],
    dependency_type_args: typing.Tuple = (),
    dependency_type_kwargs: typing.Mapping[str, typing.Any] = {},
) -> Depends:
    """
    Convert a value to a fastapi dependency.
    This is useful for converting a constant value to a dependency that can be used in fastapi routes.

    :param value: The value to convert to a dependency.
    :param dependency_name: The name of the dependency.
    :param dependency_type: The type of the dependency.
    :param dependency_type_args: The arguments to pass to the dependency type.
    :param dependency_type_kwargs: The keyword arguments to pass to the dependency type.
    :return: A fastapi dependency that resolves to the value.
    """

    async def dependency() -> typing.Any:
        return value

    dependency.__name__ = dependency_name
    dependency.__annotations__ = {dependency_name: value.__class__}
    return dependency_type(
        dependency,
        *dependency_type_args,
        **dependency_type_kwargs,
    )


def is_resolvable_dependency(
    value: typing.Any,
    /,
) -> bool:
    """Returns True if the value is a resolvable dependency, False otherwise."""
    return (
        isinstance(value, Param)
        or isinstance(value, Depends)
        or isinstance(value, FieldInfo)
    )


def event(
    event: str,
    /,
    target: typing.Optional[typing.Any] = None,
    target_uid: typing.Optional[typing.Any] = None,
    description: typing.Optional[str] = None,
    event_dependency_suffix: str = "request",
) -> Depends:
    """
    Mark the connection for audit logging by attaching the event data to the connection state.

    Endeavour to make this dependency the first in the chain of dependencies.
    This ensures that the event data is attached to the connection state before any other dependencies are resolved.
    Hence, errors that occur during the resolution of other dependencies can still be logged with the correct event data.

    Example:
    ```python
    @app.post(
        "/users/",
        dependencies=[
            event("user_create", target="user")
        ]
    )
    async def create_user(user: UserCreate) -> User:
        ...

    @app.get(
        "/users/{user_id}/",
        dependencies=[
            event(
                "user_retrieve",
                target="user",
                target_uid=fastapi.Path(
                    alias="user_id",
                    include_in_schema=False,
                ),
            )
        ]
    )
    async def retrieve_user(user_id: str = fastapi.Path(...)) -> User:
        ...
    ```

    :param event: The event or action that occurred. E.g. user_login, user_logout, GET, POST, etc.
    :param target: The target of the event. E.g. user, post, comment, etc.
        This can also be a another fastapi dependency, path, query, etc.
        that resolves to the target.
    :param target_uid: The unique ID of the target. This can also be another fastapi
        dependency, path, query, etc. that resolves to the target ID.
    :param description: A description of the event or action.
    :param event_dependency_suffix: The suffix to use for the dependency name.
        This is useful to avoid naming conflicts with other dependencies.
        Defaults to "request".
    :return: A fastapi dependency that attaches the event data to the connection state.
    """
    if not is_resolvable_dependency(target):
        target = value_to_dependency(
            target,
            dependency_name="target",
            dependency_type=Depends,
        )
    if not is_resolvable_dependency(target_uid):
        target_uid = value_to_dependency(
            target_uid,
            dependency_name="target_uid",
            dependency_type=Depends,
        )

    async def dependency(
        connection: HTTPConnection,
        target: typing.Optional[typing.Any] = target,
        target_uid: typing.Optional[typing.Any] = target_uid,
    ) -> HTTPConnection:
        if not settings.LOG_CONNECTION_EVENTS:
            return connection

        event_data = ConnectionEvent(
            event=event,
            target=target,
            target_uid=target_uid,
            description=description,
        )
        connection_events = typing.cast(
            typing.Sequence[ConnectionEvent], getattr(connection.state, "events", [])
        )
        setattr(connection.state, "events", [*connection_events, event_data])
        return connection

    dependency.__name__ = f"{event}_{event_dependency_suffix}"
    return Depends(dependency)
