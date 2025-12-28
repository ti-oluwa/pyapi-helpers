import typing
import asyncio
import importlib
import re
from starlette.types import ASGIApp, Receive, Scope, Send, Message
from starlette.requests import HTTPConnection, empty_send
from starlette.responses import Response
from starlette.datastructures import MutableHeaders, Headers
from starlette.concurrency import run_in_threadpool

from .format import json_httpresponse_formatter, Formatter
from src.logging import log_exception


class FormatJSONResponseMiddleware:
    """
    ASGI Middleware to format JSON response data to a structured and consistent format (as defined by formatter).
    """

    default_formatter: Formatter = json_httpresponse_formatter
    """The default response formatter."""

    def __init__(
        self,
        app: ASGIApp,
        format: bool = True,
        excluded_paths: typing.Optional[typing.List[str]] = None,
        formatter: typing.Union[Formatter, str] = "default",
    ) -> None:
        """
        Initialize the middleware.

        :param app: The ASGI application.
        :param format: Whether to format the response or not.
        :param excluded_paths: List of paths to exclude from formatting.
        :param formatter: The response formatter, can be a callable or an import path.
        """
        self.app = app
        self.formatter = (
            formatter if callable(formatter) else self._load_formatter(formatter)
        )
        self.excluded_paths_patterns = (
            tuple(re.compile(path) for path in excluded_paths)
            if excluded_paths
            else None
        )
        self._format = format

    @classmethod
    def _load_formatter(cls, formatter: str) -> Formatter:
        """Load the response formatter."""
        if formatter.lower() == "default":
            return cls.default_formatter

        imported_formatter = importlib.import_module(formatter)
        if not callable(imported_formatter):
            raise TypeError("Response formatter must be a callable")
        return imported_formatter

    def is_json_response(self, response: Response) -> bool:
        """
        Check if the response is a JSON response.

        :param response: The response object.
        :return: True if the response is a JSON response, False otherwise.
        """
        return "application/json" in response.headers.get("Content-Type", "")

    async def can_format(self, response: Response) -> bool:
        """
        Check if the response can be formatted.

        :param response: The response object.
        :return: True if the response can be formatted, False otherwise.
        """
        return not self._format or not self.is_json_response(response)

    async def format(self, response: Response) -> Response:
        """
        Format the response.

        :param response: The response object.
        :return: The formatted response object.
        """
        if not await self.can_format(response):
            return response

        try:
            if asyncio.iscoroutinefunction(self.formatter):
                return await self.formatter(response)
            else:
                return await run_in_threadpool(self.formatter, response)  # type: ignore
        except Exception as exc:
            log_exception(exc)
            return response

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process the connection."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope, receive)
        if self.excluded_paths_patterns:
            request_path = "/" + connection.url.path.lstrip("/")
            for excluded_path in self.excluded_paths_patterns:
                if excluded_path.match(request_path):
                    await self.app(scope, receive, send)
                    return

        responder = FormatResponder(app=self.app, formatter=self.format)
        await responder(scope, receive, send)


async def encode_headers(
    headers: typing.Mapping[str, str],
) -> typing.Sequence[typing.Tuple[bytes, bytes]]:
    return [(k.encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()]


async def decode_headers(
    headers: typing.Sequence[typing.Tuple[bytes, bytes]],
) -> typing.MutableMapping[str, str]:
    return {k.decode("latin-1"): v.decode("latin-1") for k, v in headers}


class FormatResponder:
    """Formats the response (if necessary) before sending it to the client."""

    def __init__(
        self,
        app: ASGIApp,
        formatter: typing.Callable[[Response], typing.Awaitable[Response]],
    ) -> None:
        self.app = app
        self.formatter = formatter
        self.send = empty_send
        self.response_started = False
        self.initial_message = {}
        self.has_content_encoding = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.send = send
        await self.app(scope, receive, self.send_formatted)

    async def send_formatted(self, message: Message) -> None:
        message_type = message["type"]

        if message_type == "http.response.start":
            self.initial_message = message
            # Check if response has content-encoding (compressed content)
            headers = Headers(raw=message["headers"])
            self.has_content_encoding = "content-encoding" in headers

        elif message_type == "http.response.body" and self.has_content_encoding:
            # If content-encoding is set, we assume the response is already formatted
            # Just send the initial message and the body as is
            if not self.response_started:
                self.response_started = True
                await self.send(self.initial_message)
            await self.send(message)

        elif message_type == "http.response.body" and not self.response_started:
            self.response_started = True
            body = message.get("body", b"")
            more_body = message.get("more_body", False)
            headers = MutableHeaders(raw=self.initial_message["headers"])
            status_code = self.initial_message["status"]

            if not more_body:
                # Format the response if it is not streaming
                response = Response(
                    content=body,
                    status_code=status_code,
                    headers=headers,
                )
                formatted_response = await self.formatter(response)
                # Update the body with the formatted response body
                message["body"] = formatted_response.body

                # Send the initial message with formatted headers
                initial_message = dict(self.initial_message)
                initial_message["headers"] = formatted_response.headers.raw
                await self.send(initial_message)

                # Send the message with the formatted body
                await self.send(message)

            else:
                # If more_body is True, we assume the response is streaming
                response = Response(
                    content=body,
                    status_code=status_code,
                    headers=headers,
                )
                formatted_response = await self.formatter(response)
                # Update the body with the formatted response body
                message["body"] = formatted_response.body

                # Send the initial message with formatted headers
                initial_message = dict(self.initial_message)
                # Delete content length for streaming response
                del formatted_response.headers["content-length"]
                initial_message["headers"] = formatted_response.headers.raw
                await self.send(initial_message)

                # Send the message with the formatted body
                await self.send(message)

        elif message_type == "http.response.body":
            # If the response is already started, just format the response and send it
            body = message.get("body", b"")
            more_body = message.get("more_body", False)
            status_code = self.initial_message["status"]
            headers = MutableHeaders(raw=self.initial_message["headers"])

            response = Response(
                content=body,
                status_code=status_code,
                headers=headers,
            )
            formatted_response = await self.formatter(response)
            message["body"] = formatted_response.body
            await self.send(message)

        # If the message type is not recognized, just send it as is
        else:
            await self.send(message)
