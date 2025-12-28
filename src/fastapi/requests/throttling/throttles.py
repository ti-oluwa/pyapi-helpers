import typing
import functools
import hashlib
from annotated_types import Ge
from starlette.websockets import WebSocket
from starlette.requests import Request
from starlette.responses import Response
from redis.exceptions import NoScriptError

from .base import (
    APIThrottle,
    _HTTPConnection,
    CoroutineFunction,
    ConnectionIdentifier,
    ConnectionThrottledHandler,
)


class NoLimit(Exception):
    """
    Exception raised when throttling should not be enforced.

    This exception is caught by the throttle and the client is allowed to proceed
    without being throttled.

    In this example, the exception is raised when the request is from a trusted source

    ```python
    import fastapi
    import starlette.requests import HTTPConnection

    TRUSTED_IPS = {...,}

    def get_ip(connection: HTTPConnection):
        ...

    def untrusted_ip_identifier(connection: HTTPConnection):
        client_ip = get_ip(connection)
        if client_ip in TRUSTED_IPS:
            raise NoLimit()

        return connection.client.host

    router = fastapi.APIRouter(
        dependencies=[
            throttle(identifier=untrusted_ip_identifier)
        ]
    )
    ```
    """

    pass


class ThrottleMeta(type):
    def __new__(cls, name, bases, attrs):
        new_cls = super().__new__(cls, name, bases, attrs)
        new_cls.__call__ = cls._capture_no_limit(new_cls.__call__)
        new_cls.get_key = cls._wrap_get_key(new_cls.get_key)  # type: ignore
        return new_cls

    @staticmethod
    def _capture_no_limit(coroutine_func: CoroutineFunction) -> CoroutineFunction:
        """
        Wraps the coroutine function such that NoLimit exceptions are caught
        and ignored, returning None instead.

        :param func: The coroutine function to wrap
        """

        @functools.wraps(coroutine_func)
        async def wrapper(*args, **kwargs):
            try:
                return await coroutine_func(*args, **kwargs)
            except NoLimit:
                return

        return wrapper

    @staticmethod
    def _wrap_get_key(get_key: CoroutineFunction) -> CoroutineFunction:
        """Wraps the `get_key` method to ensure the pattern of the key returned is valid"""

        @functools.wraps(get_key)
        async def wrapper(*args, **kwargs):
            key = await get_key(*args, **kwargs)
            if not isinstance(key, str):
                raise TypeError("Generated throttling key should be a string")

            if not APIThrottle.check_key_pattern(key):
                raise ValueError(
                    "Invalid throttling key pattern. "
                    f"Key must be in the format: {APIThrottle.get_key_pattern()}"
                )
            return key

        return wrapper


class BaseThrottle(typing.Generic[_HTTPConnection], metaclass=ThrottleMeta):
    """Base class for throttles"""

    def __init__(
        self,
        limit: typing.Annotated[int, Ge(0)] = 1,
        milliseconds: typing.Annotated[int, Ge(-1)] = 0,
        seconds: typing.Annotated[int, Ge(-1)] = 0,
        minutes: typing.Annotated[int, Ge(-1)] = 0,
        hours: typing.Annotated[int, Ge(-1)] = 0,
        identifier: typing.Optional[ConnectionIdentifier[_HTTPConnection]] = None,
        connection_throttled: typing.Optional[
            ConnectionThrottledHandler[_HTTPConnection]
        ] = None,
    ):
        """
        Initialize the throttle

        :param limit: Maximum number of times the route can be accessed within specified time period
        :param milliseconds: Time period in milliseconds
        :param seconds: Time period in seconds
        :param minutes: Time period in minutes
        :param hours: Time period in hours
        :param identifier: Connected client identifier generator.
        :param connection_throttled: Handler to call when the client connection is throttled
        """
        self.limit = limit
        self.milliseconds = (
            milliseconds + 1000 * seconds + 60000 * minutes + 3600000 * hours
        )
        self.identifier = identifier
        self.connection_throttled = connection_throttled

    async def get_wait_period(self, key: str) -> int:
        """
        Evaluates the throttling lua script to get the wait period
        for the throttling key.

        :param key: the throttling key
        :return: The time in milliseconds the client with the key would have to wait before the next route access.
            That is, if the time is 0, the client will not not throttled, otherwise the client
            will be throttled for the time returned and would have to wait for the time to elapse.
        """
        redis = APIThrottle.redis
        if not redis:
            raise Exception(
                "APIThrottle has not been initialized. Call `APIThrottle.init` on FastAPI application startup"
            )
        try:
            wait_period = await redis.evalsha(
                APIThrottle.lua_sha or "",
                1,
                key,
                str(self.limit),
                str(self.milliseconds),
            )  # type: ignore
        except NoScriptError:
            APIThrottle.lua_sha = await redis.script_load(APIThrottle.lua_script)
            wait_period = await self.get_wait_period(key)
        return int(wait_period)

    async def __call__(self, connection: _HTTPConnection, *args, **kwargs):
        if not APIThrottle.redis:
            raise Exception(
                "APIThrottle has not been initialized. Call `APIThrottle.init` on FastAPI application startup"
            )

        key = await self.get_key(connection, *args, **kwargs)
        wait_period = await self.get_wait_period(key)
        connection_throttled = (
            self.connection_throttled or APIThrottle.connection_throttled
        )
        if wait_period != 0 and connection_throttled:
            return await connection_throttled(connection, wait_period, *args, **kwargs)
        return None

    async def get_key(self, connection: _HTTPConnection, *args, **kwargs) -> str:
        """
        Returns the unique throttling key for the client.

        Key returned must match the pattern returned by `APIThrottle.get_key_pattern`,
        otherwise a ValueError is raised on key generation.
        """
        raise NotImplementedError


class HTTPThrottle(BaseThrottle[Request]):
    """Generic throttle for HTTP connections"""

    async def get_key(self, request: Request, response: Response) -> str:
        route_index = 0
        dependency_index = 0
        for i, route in enumerate(request.app.routes):
            if route.path == request.scope["path"] and request.method in route.methods:
                route_index = i
                for j, dependency in enumerate(route.dependencies):
                    if self is dependency.dependency:
                        dependency_index = j
                        break

        identifier = self.identifier or APIThrottle.identifier
        if not identifier:
            raise ValueError("No identifier provided for throttle")

        rate_key = await identifier(request)
        key_suffix = f"{rate_key}:{route_index}:{dependency_index}:{id(self)}"
        key_suffix_hash = hashlib.md5(key_suffix.encode()).hexdigest()
        key = f"{APIThrottle.prefix}:http:{key_suffix_hash}"
        # Added id(self) to ensure unique key for each throttle instance
        # in the advent that the dependency index is not unique. Especially when
        # used with the `throttle` decorator.
        return key

    async def __call__(self, connection: Request, response: Response):
        return await super().__call__(connection, response=response)


class WebSocketThrottle(BaseThrottle[WebSocket]):
    """Throttle for WebSocket connections"""

    async def get_key(self, connection: WebSocket, context_key="") -> str:
        identifier = self.identifier or APIThrottle.identifier
        if not identifier:
            raise ValueError("No identifier provided for throttle")
        rate_key = await identifier(connection)
        key_suffix = f"{rate_key}:{connection.url.path}:{id(self)}:{context_key}"
        key_suffix_hash = hashlib.md5(key_suffix.encode()).hexdigest()
        key = f"{APIThrottle.prefix}:ws:{key_suffix_hash}"
        # Added id(self) to ensure unique key for each throttle instance
        # in the advent that the context key is not unique. Especially when
        # used with the `throttle` decorator.
        return key

    async def __call__(self, connection: WebSocket, context_key=""):
        return await super().__call__(connection, context_key=context_key)


__all__ = [
    "HTTPThrottle",
    "WebSocketThrottle",
    "NoLimit",
]
