import asyncio
import re
import typing
import functools
import inspect
import fastapi
from collections.abc import Mapping
from starlette.types import ASGIApp, Receive, Scope, Send, Message
from starlette.requests import HTTPConnection
from starlette.websockets import WebSocketClose
from starlette import status
from starlette.responses import Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.fastapi.config import settings
from src.fastapi.utils.requests import get_ip_address
from src.generics.utils.module_loading import import_string


url_path_string_re = (
    r"[\w\-.~:/?#\[\]@!$&'()*+,;=]+"  # regex pattern for possible url path string
)
ALLOWED_CONNECTION_TYPES = {"http", "websocket"}


def urlstring_to_re(urlstring: str) -> re.Pattern[str]:
    """
    Converts a wildcard url string pattern into a regex `Pattern` object.

    For example:
      "*.example.com" -> r"^.*\\.example\\.com$"
    """
    # check if its a proper regex string
    if urlstring.startswith("^") and urlstring.endswith("$"):
        return re.compile(urlstring)

    if urlstring == "*":
        return re.compile(url_path_string_re)  # Match everything
    urlstring = re.escape(urlstring).replace(r"\*", url_path_string_re)
    return re.compile(rf"^{urlstring}$")


class AllowedHostsMiddleware(TrustedHostMiddleware):
    """
    Middleware to check if the client host is allowed.
    """

    def __init__(
        self,
        app: ASGIApp,
        allowed_hosts: typing.Optional[typing.Sequence[str]] = None,
        www_redirect: bool = True,
    ):
        allowed_hosts_settings = getattr(settings, "ALLOWED_HOSTS", None)
        allowed_hosts = allowed_hosts or allowed_hosts_settings
        super().__init__(app, allowed_hosts=allowed_hosts, www_redirect=www_redirect)


class AllowedIPsMiddleware:
    """
    Middleware to check if the client IP is allowed.
    """

    def __init__(self, app: ASGIApp):
        self.app = app
        self.allowed_ips = [
            urlstring_to_re(ip) for ip in getattr(settings, "ALLOWED_IPS", [])
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ALLOWED_CONNECTION_TYPES:
            await self.app(scope, receive, send)
            return

        client_ip = get_ip_address(HTTPConnection(scope, receive))
        if not (self.allowed_ips and client_ip):
            await self.app(scope, receive, send)
            return

        for ip in self.allowed_ips:
            if ip.match(client_ip.exploded):
                await self.app(scope, receive, send)
                return

        if scope["type"] == "websocket":
            websocket_close = WebSocketClose(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Access disallowed!",
            )
            await websocket_close(scope, receive, send)
        else:
            response = Response(
                "Access disallowed!",
                status_code=status.HTTP_403_FORBIDDEN,
            )
            await response(scope, receive, send)


class HostBlacklistMiddleware:
    """
    Middleware to check if the client host is blacklisted.
    """

    def __init__(self, app: ASGIApp):
        self.app = app
        self.blacklisted_hosts = [
            urlstring_to_re(host) for host in getattr(settings, "BLACKLISTED_HOSTS", [])
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ALLOWED_CONNECTION_TYPES:
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope, receive)
        hostname = connection.client.host if connection.client else None
        if not (self.blacklisted_hosts and hostname):
            await self.app(scope, receive, send)
            return

        for host in self.blacklisted_hosts:
            if not host.match(hostname):
                continue
            
            if scope["type"] == "websocket":
                websocket_close = WebSocketClose(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason="Access disallowed!",
                )
                await websocket_close(scope, receive, send)
            else:
                response = Response(
                    "Access disallowed!",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


class IPBlacklistMiddleware:
    """
    Middleware to check if the client IP is blacklisted.
    """

    def __init__(self, app: ASGIApp):
        self.app = app
        self.blacklisted_ips = [
            urlstring_to_re(ip) for ip in getattr(settings, "BLACKLISTED_IPS", [])
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ALLOWED_CONNECTION_TYPES:
            await self.app(scope, receive, send)
            return

        client_ip = get_ip_address(HTTPConnection(scope, receive))
        if not (self.blacklisted_ips and client_ip):
            await self.app(scope, receive, send)
            return

        for ip in self.blacklisted_ips:
            if not ip.match(client_ip.exploded):
                continue

            if scope["type"] == "websocket":
                websocket_close = WebSocketClose(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason="Access disallowed!",
                )
                await websocket_close(scope, receive, send)
            else:
                response = Response(
                    "Access disallowed!",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


class RequestProcessTimeMiddleware:
    """
    Middleware to calculate the time taken to process the client request.

    Adds an `x-process-time` header to the response.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        loop = asyncio.get_running_loop()
        start_time = loop.time()

        @functools.wraps(send)
        async def _send(message: Message) -> None:
            nonlocal start_time, loop
            if message["type"] == "http.response.start":
                process_time = loop.time() - start_time
                message["headers"].append(
                    (b"x-process-time", str(process_time).encode())
                )
            await send(message)

        await self.app(scope, receive, _send)


MiddlewareList: typing.TypeAlias = typing.List[
    typing.Union[str, typing.Tuple[str, typing.Dict[str, typing.Any]]]
]


class InvalidMiddlewareError(Exception):
    """Exception raised for invalid middleware definitions."""

    pass


def middleware_stack() -> typing.Iterator[
    typing.Tuple[typing.Callable, typing.Dict[str, typing.Any]]
]:
    """
    Yield all middleware defined in the settings.

    Middleware can be defined as a string or a tuple of the form (str, dict).
    where the string is the middleware class path and the dict is the kwargs to pass to the middleware.

    The order of the middleware is reversed so that the first middleware in the list is applied last.
    Such that the first middleware in the list is the outermost middleware.

    :raises InvalidMiddlewareError: If the middleware definition is invalid.
    """
    middleware_list: typing.Optional[MiddlewareList] = settings.get("MIDDLEWARE", None)
    if not middleware_list:
        return

    for middleware_def in reversed(middleware_list):
        if isinstance(middleware_def, str):
            middleware_obj = import_string(middleware_def)

            if not callable(middleware_obj):
                raise InvalidMiddlewareError(
                    f"Invalid middleware definition: {middleware_def}"
                )
            yield middleware_obj, {}

        elif isinstance(middleware_def, tuple) and len(middleware_def) == 2:
            middleware_obj = import_string(middleware_def[0])
            if not (
                callable(middleware_obj)
                and inspect.isclass(middleware_obj)
                and isinstance(middleware_def[1], Mapping)
            ):
                raise InvalidMiddlewareError(
                    f"Invalid middleware definition: {middleware_def}"
                )
            yield middleware_obj, middleware_def[1]
        else:
            raise InvalidMiddlewareError(
                f"Invalid middleware definition: {middleware_def}"
            )


def apply_middleware(app: fastapi.FastAPI) -> fastapi.FastAPI:
    """
    Apply all middleware to the FastAPI app.
    """
    for middleware, kwargs in middleware_stack():
        if inspect.isclass(middleware):
            app.add_middleware(middleware, **kwargs)  # type: ignore
        else:
            app.middleware("http")(middleware)
    return app
