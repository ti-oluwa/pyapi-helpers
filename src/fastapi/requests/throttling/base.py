import functools
import sys
import math
import re
import typing
from typing_extensions import Unpack
from contextlib import asynccontextmanager
import redis.asyncio as async_pyredis

import fastapi
from starlette.requests import HTTPConnection
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from src.types import Function, CoroutineFunction
from src.fastapi.utils.requests import get_ip_address


_HTTPConnection = typing.TypeVar("_HTTPConnection", bound=HTTPConnection)
ConnectionIdentifier = typing.Union[
    Function[[_HTTPConnection], typing.Any],
    CoroutineFunction[[_HTTPConnection], typing.Any],
]

_WaitPeriod: typing.TypeAlias = int
if sys.version_info >= (3, 12):
    _Args = typing.Tuple[typing.Any, ...]
    ConnectionThrottledHandler: typing.TypeAlias = typing.Callable[
        [_HTTPConnection, _WaitPeriod, Unpack[_Args]], typing.Any
    ]
else:
    ConnectionThrottledHandler: typing.TypeAlias = typing.Callable[
        [_HTTPConnection, _WaitPeriod], typing.Any
    ]


async def default_connection_identifier(connection: HTTPConnection) -> str:
    client_ip = get_ip_address(connection)
    return f"{client_ip.exploded}:{connection.scope['path']}"


async def default_connection_throttled(
    connection: HTTPConnection, wait_period: _WaitPeriod, *args, **kwargs
):
    """
    Handler for throttled HTTP connections

    :param connection: The HTTP connection
    :param wait_period: The wait period in milliseconds before the next connection can be made
    :return: None
    """
    expire = math.ceil(wait_period / 1000)
    raise fastapi.HTTPException(
        status_code=HTTP_429_TOO_MANY_REQUESTS,
        detail="Too Many Requests",
        headers={"Retry-After": str(expire)},
    )


class APIThrottle(typing.Generic[_HTTPConnection]):
    """APIThrottle configuration"""

    redis = None  # Do not modify after initialization
    prefix: typing.Optional[str] = (
        None  # Be careful with modifying after initialization
    )
    lua_sha: typing.Optional[str] = None
    identifier: typing.Optional[ConnectionIdentifier[_HTTPConnection]] = None
    connection_throttled: typing.Optional[
        ConnectionThrottledHandler[_HTTPConnection]
    ] = None
    lua_script = """local key = KEYS[1]
local limit = tonumber(ARGV[1])
local expire_time = ARGV[2]

local current = tonumber(redis.call('get', key) or "0")
if current > 0 then
 if current + 1 > limit then
 return redis.call("PTTL",key)
 else
        redis.call("INCR", key)
 return 0
 end
else
    redis.call("SET", key, 1,"px",expire_time)
 return 0
end"""

    @classmethod
    async def init(
        cls,
        redis: async_pyredis.Redis,
        prefix: str = "api-throttle",
        identifier: ConnectionIdentifier[
            _HTTPConnection
        ] = default_connection_identifier,
        connection_throttled: ConnectionThrottledHandler[
            _HTTPConnection
        ] = default_connection_throttled,
    ) -> None:
        cls.redis = redis
        cls.prefix = prefix
        cls.identifier = identifier
        cls.connection_throttled = connection_throttled
        cls.lua_sha = await redis.script_load(cls.lua_script)

    @classmethod
    async def close(cls) -> None:
        if not cls.redis:
            return
        await cls.redis.close()

    @classmethod
    @functools.cache
    def get_key_pattern(cls) -> re.Pattern:
        """
        Regular expression pattern for throttling keys

        All rate keys are expected to follow this pattern.
        """
        return re.compile(rf"{cls.prefix}:*")

    @classmethod
    def check_key_pattern(cls, key: str) -> bool:
        """Check if the key matches the throttling key pattern"""
        return re.match(cls.get_key_pattern(), key) is not None


class APIThrottleInitKwargs(typing.TypedDict, total=False):
    """Keyword arguments for initializing APIThrottle."""

    prefix: str
    """Unique prefix to be used for throttling keys in Redis."""
    redis: typing.Union[str, async_pyredis.Redis]
    """Connection to the Redis."""
    identifier: ConnectionIdentifier
    """Connected client identifier generator."""
    connection_throttled: ConnectionThrottledHandler
    """Default handler for throttled HTTP connections."""


@asynccontextmanager
async def configure(
    persistent: bool = True,
    **init_kwargs: Unpack[APIThrottleInitKwargs],
):
    """
    Asynchronous context manager

    Configure API throttling.

    :param persistent: Whether to persist api throttling data across application restarts.
        Defaults to `True`.
    :param init_kwargs: Keyword arguments to be used to initialize the APIThrottle.

    Usage Example:
    ```python
    import fastapi

    from src.fastapi.requests.throttling import configure

    def lifespan(app: fastapi.FastAPI):
        try:
            async configure(
                persistent=app.debug is False,
                # Disables persistent rate limiting in debug mode,
                # Useful in development environments.
                redis="redis://localhost/0"
            ):
                yield
        finally:
            pass

    app = fastapi.FastAPI(lifespan=lifespan)
    ```
    """
    redis = init_kwargs.get("redis")
    if isinstance(redis, str):
        init_kwargs["redis"] = async_pyredis.from_url(redis)

    if not redis:
        raise ValueError("Redis location/connection must be provided")

    try:
        await APIThrottle.init(**init_kwargs)  # type: ignore
        # if not persistent:
        #     # This is to ensure that the prefix is unique across
        #     # multiple instances of FastAPIThrottle and also reduce
        #     # the chances of throttling key conflicts with existing keys in Redis,
        #     # Which may lead to deleting keys that are not related to throttling
        #     # on application restart or shutdown in non-persistent mode.
        #     APIThrottle.prefix += f"-{uuid.uuid4().hex}"
        yield

    finally:
        if not persistent and APIThrottle.redis:
            # Get all keys set by FastAPIThrottle
            keys_set = await APIThrottle.redis.keys(f"{APIThrottle.prefix}:*")
            if keys_set:
                await APIThrottle.redis.delete(*keys_set)

        await APIThrottle.close()


__all__ = [
    "APIThrottle",
    "configure",
    "default_connection_identifier",
    "default_connection_throttled",
]
