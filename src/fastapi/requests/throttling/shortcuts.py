import asyncio
import functools
import inspect
import typing
from typing_extensions import Unpack, ParamSpec
import fastapi
import fastapi.params
from starlette.requests import HTTPConnection, Request

from .base import (
    _HTTPConnection,
    ConnectionIdentifier,
    ConnectionThrottledHandler,
    default_connection_identifier,
)
from .throttles import BaseThrottle, HTTPThrottle, NoLimit
from src.types import Function, CoroutineFunction
from src.fastapi.utils.sync import sync_to_async
from src.generics.utils.functions import add_parameter_to_signature


P = ParamSpec("P")
Q = ParamSpec("Q")
R = typing.TypeVar("R")
S = typing.TypeVar("S")

Decorated = typing.Union[Function[P, R], CoroutineFunction[P, R]]
Dependency = typing.Union[Function[Q, S], CoroutineFunction[Q, S]]
_Throttle = typing.TypeVar("_Throttle", bound=BaseThrottle)


class ThrottleKwargs(typing.TypedDict, total=False):
    """Keyword arguments for creating a throttle"""

    limit: int
    """Maximum number of times the route can be accessed within specified time period."""
    milliseconds: int
    """Time frame in milliseconds."""
    seconds: int
    """Time frame in seconds."""
    minutes: int
    """Time frame in minutes."""
    hours: int
    """Time frame in hours."""
    connection_throttled: typing.Optional[ConnectionThrottledHandler]
    """Handler to call when the client connection is throttled."""


class DecoratorDepends(
    typing.Generic[P, R, Q, S],
    fastapi.params.Depends,
):
    """
    `fastapi.params.Depends` subclass that allows instances to be used as decorators.

    Instances use `dependency_decorator` to apply the dependency to the decorated object,
    while still allowing usage as regular FastAPI dependencies.

    `dependency_decorator` is a callable that takes the decorated object and an optional dependency
    and returns the decorated object with/without the dependency applied.

    Think of the `dependency_decorator` as a chef that mixes the sauce (dependency)
    with the dish (decorated object), making a dish with the sauce or without it.
    """

    def __init__(
        self,
        dependency_decorator: Function[
            [Decorated[P, R], typing.Optional[Dependency[Q, S]]],
            Decorated[P, R],
        ],
        dependency: typing.Optional[Dependency[Q, S]] = None,
        *,
        use_cache: bool = True,
    ) -> None:
        self.dependency_decorator = dependency_decorator
        super().__init__(dependency, use_cache=use_cache)

    def __call__(self, decorated: Decorated[P, R]):
        return self.dependency_decorator(decorated, self.dependency)


# Is this worth it? Just because of the `throttle` decorator?
def _wrap_route(
    route: Decorated[P, R],
    throttle: BaseThrottle,
) -> Decorated[P, R]:
    """
    Create an wrapper that applies throttling to an route
    by wrapping the route such that the route depends on the throttle.

    :param route: The route to wrap.
    :param throttle: The throttle to apply to the route.
    :return: The wrapper that enforces the throttle on the route.
    """
    # * This approach is necessary because FastAPI does not support dependencies
    # * that are not in the signature of the route function.

    # Use unique (throttle) dependency parameter name to avoid conflicts
    # with other dependencies that may be applied to the route, or in the case
    # of nested use of this wrapper function.
    throttle_dep_param_name = f"_{id(throttle)}_throttle"

    # We need the throttle dependency to be the first parameter of the route
    # So that the rate limit check is done before any other operations or dependencies
    # are resolved/executed, improving the efficiency of implementation.
    if asyncio.iscoroutinefunction(route):
        wrapper_code = f"""
async def route_wrapper(
    {throttle_dep_param_name}: typing.Annotated[typing.Any, fastapi.Depends(throttle)],
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    return await route(*args, **kwargs)
"""
    else:
        wrapper_code = f"""
def route_wrapper(
    {throttle_dep_param_name}: typing.Annotated[typing.Any, fastapi.Depends(throttle)],
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    return route(*args, **kwargs)
"""

    local_namespace = {
        "throttle": throttle,
    }
    global_namespace = {
        **globals(),
        "route": route,
    }
    exec(
        wrapper_code,
        global_namespace,
        local_namespace,
    )
    route_wrapper = local_namespace["route_wrapper"]
    route_wrapper = functools.wraps(route)(route_wrapper)
    # The resulting function from applying `functools.wraps(route)` on `route_wrapper`
    # would not have the throttle dependency in its signature, although it is present in `route_wrapper`'s definition,
    # because the result of `functools.wraps` assumes the signature of the original function (route in this case).

    # Since the original/wrapped function does not have the throttle dependency in its signature,
    # the throttle dependency will not be recognized/regarded by FastAPI, as FastAPI
    # uses the signature of the function to determine the params, hence the dependencies of the function.

    # So, we update the signature of the wrapper to include the throttle dependency
    route_wrapper = add_parameter_to_signature(
        func=route_wrapper,
        parameter=inspect.Parameter(
            name=throttle_dep_param_name,
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=typing.Annotated[typing.Any, fastapi.Depends(throttle)],
        ),
        index=0,  # Since the throttle dependency was added as the first parameter
    )
    return route_wrapper


def _throttle_route(
    route: Decorated[P, R],
    throttle: BaseThrottle,
) -> Decorated[P, R]:
    """
    Returns wrapper that applies throttling to the given route
    by wrapping the route such that the route depends on the throttle.

    :param route: The route to be throttled.
    :param throttle: The throttle to apply to the route.
    """
    wrapper = _wrap_route(route, throttle)
    return wrapper


@typing.overload
def throttle(
    route: typing.Optional[Decorated[P, R]] = None,
    /,
    *,
    identifier: typing.Optional[ConnectionIdentifier[_HTTPConnection]] = None,
    throttle_type: typing.Type[_Throttle] = HTTPThrottle,
    **throttle_kwargs: Unpack[ThrottleKwargs],
) -> DecoratorDepends[P, R, typing.Any, typing.Any]: ...


@typing.overload
def throttle(
    route: Decorated[P, R],
    /,
    *,
    identifier: typing.Optional[ConnectionIdentifier[_HTTPConnection]] = None,
    throttle_type: typing.Type[_Throttle] = HTTPThrottle,
    **throttle_kwargs: Unpack[ThrottleKwargs],
) -> Decorated[P, R]: ...


def throttle(
    route: typing.Optional[Decorated[P, R]] = None,
    /,
    *,
    identifier: typing.Optional[ConnectionIdentifier[_HTTPConnection]] = None,
    throttle_type: typing.Type[_Throttle] = HTTPThrottle,
    **throttle_kwargs: Unpack[ThrottleKwargs],
):
    """
    Route dependency/decorator that throttles connections to a route
    based on the defined client identifier.

    :param route: Decorated route to throttle.
    :param identifier: A callable that generates a unique identifier for the client. Defaults to the client IP.
    :param throttle_type: The throttle type to use. Defaults to `HTTPThrottle`.
    :param throttle_kwargs: Keyword arguments to be used to instantiate the throttle type.

    Usage Examples:
    ```python
    import fastapi

    router = fastapi.APIRouter(
        dependencies=[
            throttle(limit=1, seconds=3)
        ]
    )

    @router.get("/limited1")
    async def limited_route1():
        return {"message": "Limited route"}

    @router.get("/limited2")
    async def limited_route2():
        return {"message": "Limited route 2"}
    ```

    Or;

    ```python
    import fastapi

    router = fastapi.APIRouter()

    @router.get(
        "/limited",
        dependencies=[
            throttle(limit=1, seconds=3),
        ]
    )
    async def limited_route():
        return {"message": "Limited route"}
    ```

    Or;

    ```python
    import fastapi

    router = fastapi.APIRouter()

    @router.get("/limited")
    @throttle(limit=1, seconds=3)
    async def limited_route():
        return {"message": "Limited route"}
    ```
    """
    connection_throttled = throttle_kwargs.pop("connection_throttled", None)
    if connection_throttled and not asyncio.iscoroutinefunction(connection_throttled):
        throttle_kwargs["connection_throttled"] = sync_to_async(connection_throttled)

    if identifier and not asyncio.iscoroutinefunction(identifier):
        identifier = sync_to_async(identifier)

    throttle = throttle_type(identifier=identifier, **throttle_kwargs)
    decorator_dependency = DecoratorDepends[P, R, typing.Any, typing.Any](
        dependency_decorator=_throttle_route,  # type: ignore
        dependency=throttle,
    )
    if route is not None:
        decorated = decorator_dependency(route)
        return decorated
    return decorator_dependency


# ---------- CLIENT IDENTIFIERS ---------- #


def get_referrer(connection: HTTPConnection) -> str:
    return (
        (connection.headers.get("referer", "") or connection.headers.get("origin", ""))
        .split("?")[0]
        .strip("/")
        .lower()
    )


async def connection_user_agent_identifier(connection: HTTPConnection) -> str:
    user_agent = connection.headers.get("user-agent", "")
    return f"{user_agent}:{connection.scope['path']}"


async def anonymous_connection_identifier(connection: HTTPConnection) -> str:
    connected_user = getattr(connection.state, "user", None)
    if connected_user and getattr(connected_user, "is_authenticated", False):
        raise NoLimit()

    identifier = await default_connection_identifier(connection)
    return f"anonymous:{identifier}"


async def authenticated_connection_identifier(connection: HTTPConnection) -> str:
    connected_user = getattr(connection.state, "user", None)
    if connected_user and not getattr(connected_user, "is_authenticated", False):
        raise NoLimit()

    pk = getattr(connected_user, "pk", None) or getattr(connected_user, "id", None)
    if pk is not None:
        identifier = f"{str(pk)}:{connection.scope['path']}"

    identifier = await default_connection_identifier(connection)
    return f"authenticated:{identifier}"


# ---------- CUSTOM THROTTLES ---------- #


def referrer_throttle(
    referrer: typing.Union[str, typing.List[str]],
    **throttle_kwargs: Unpack[ThrottleKwargs],
):
    """
    Throttles request connections based on the referrer of the request.

    This throttle is useful for limiting request connections referred from specific sources/origins.

    :param referrer: The referrer/origin(s) to limit connections from.
    :param throttle_kwargs: Keyword arguments to be used to instantiate the throttle type.
    """
    if isinstance(referrer, str):
        referrer = [
            referrer,
        ]
    referrers = set(referrer)

    async def referrer_identifier(request: Request) -> str:
        nonlocal referrers

        referrer = get_referrer(request)
        if referrer not in referrers:
            raise NoLimit()
        return f"referer:{referrer}:{request.scope['path']}"

    return throttle(
        identifier=referrer_identifier,
        throttle_type=HTTPThrottle,
        **throttle_kwargs,
    )


user_agent_throttle = functools.partial(
    throttle, identifier=connection_user_agent_identifier
)
"""Throttle route connections based on the HTTP connection user agent."""

anonymous_connection_throttle = functools.partial(
    throttle, identifier=anonymous_connection_identifier
)
"""Throttle for anonymous/unauthenticated HTTP connections"""

authenticated_connection_throttle = functools.partial(
    throttle, identifier=authenticated_connection_identifier
)
"""Throttle for authenticated HTTP connections"""


__all__ = [
    "throttle",
    "referrer_throttle",
    "user_agent_throttle",
    "anonymous_connection_throttle",
    "authenticated_connection_throttle",
]
