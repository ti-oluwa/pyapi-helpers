import enum
import time
import typing
import gzip

try:
    import orjson as json
except ImportError:
    import json
import base64
from starlette.requests import HTTPConnection, empty_send, empty_receive
from starlette.types import ASGIApp, Send, Scope, Receive, Message
from starlette.datastructures import Headers
from sqlalchemy.orm import Mapper
from sqlalchemy.ext.asyncio import AsyncSession

from src.types import P
from src.fastapi.utils.requests import get_ip_address
from src.fastapi.utils.sync import sync_to_async
from src.fastapi.config import settings
from src.fastapi.middleware.core import urlstring_to_re
from src.generics.utils.module_loading import import_string
from src.fastapi.auditing.dependencies import ConnectionEvent


SENSITIVE_HEADERS = {header.lower() for header in settings.SENSITIVE_HEADERS}


def _clean_headers(headers: typing.Mapping[str, str]) -> dict:
    """Remove sensitive headers from the connection or response headers."""
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in SENSITIVE_HEADERS
    }


@sync_to_async
def compress_data(data: typing.Any) -> str:
    """
    Compress data using gzip and encode it to base64.

    :param data: The data to compress.
    :return: The compressed and base64-encoded data.
    """
    if not isinstance(data, (bytes, bytearray)):
        bytes_data = json.dumps(data)
        if isinstance(bytes_data, str):
            bytes_data = bytes_data.encode("utf-8")
    else:
        bytes_data = data

    compressed = gzip.compress(bytes_data)
    return base64.b64encode(compressed).decode("utf-8")


@sync_to_async
def decompress_data(data: str) -> typing.Any:
    """
    Decompress data from base64 and gzip.

    :param data: The base64-encoded compressed data.
    :return: The decompressed data.
    """
    compressed = base64.b64decode(data.encode("utf-8"))
    decompressed = gzip.decompress(compressed)
    return json.loads(decompressed.decode("utf-8"))


class ResponseStatus(enum.Enum):
    """
    Enum for action status.
    """

    OK = "ok"
    ERROR = "error"


class LogCache(typing.Protocol):
    """
    Protocol for a cache that can store log entries.
    """

    async def get(self, key: typing.Hashable) -> typing.Any:
        """Get a value from the cache."""
        ...

    async def set(self, key: typing.Hashable, value: typing.Any) -> None:
        """Set a value in the cache."""
        ...

    async def delete(self, key: typing.Hashable) -> None:
        """Delete a value from the cache."""
        ...


class LogWriter(typing.Protocol, typing.Generic[P]):
    """
    Protocol for a log writer that can write log entries to a storage/database.
    """

    async def __call__(
        self,
        __logs: typing.Sequence[typing.MutableMapping[str, typing.Any]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        """Write log entries to the log storage/database."""
        ...


LogEntry: typing.TypeAlias = typing.Dict[str, typing.Any]
Logger: typing.TypeAlias = typing.Callable[
    [typing.Sequence[LogEntry]], typing.Awaitable[None]
]
LogBuilder: typing.TypeAlias = typing.Callable[
    [
        HTTPConnection,
        typing.Sequence[ConnectionEvent],
        ResponseStatus,
        typing.Dict[str, typing.Any],
    ],
    typing.Awaitable[typing.Sequence[LogEntry]],
]
DBSessionFactory: typing.TypeAlias = typing.Callable[
    ..., typing.AsyncContextManager[AsyncSession]
]


async def sqlalchemy_database_log_writer(
    logs: typing.Sequence[typing.Dict[str, typing.Any]],
    session_factory: DBSessionFactory,
    table_mapper: Mapper[typing.Any],
):
    """
    Log Writer for SQLAlchemy databases. Writes log entries to the database.

    :param logs: The log entries to write.
    :param session_factory: The factory function to create a database session.
    :param table_mapper: SQLAlchemy mapper for table to write logs to.
    """
    if not logs:
        return
    async with session_factory() as session:
        await session.run_sync(
            lambda s: s.bulk_insert_mappings(table_mapper, logs, render_nulls=True)
        )
        await session.commit()


async def write_logs_to_cache(
    logs: typing.Sequence[typing.Dict[str, typing.Any]],
    cache: LogCache,
    cache_key: typing.Hashable,
) -> None:
    """
    Write log entries to the log storage/database.

    :param connection_events: The connection events to log.
    :param metadata: The metadata to log.
    :param status: The status of the connection.
    :param user_agent: The user agent of the connection.
    :param ip_address: The IP address of the connection.
    :param api_client: The API client associated with the connection.
    :param account: The account associated with the connection.
    """
    if not logs:
        return
    try:
        existing_entries = await cache.get(cache_key)
    except KeyError:
        await cache.set(cache_key, logs)
    else:
        if existing_entries:
            updated_entries = [*json.loads(existing_entries), *logs]
            await cache.set(cache_key, json.dumps(updated_entries))
        else:
            await cache.set(cache_key, json.dumps(logs))


def logger_factory(
    writer: LogWriter[P],
    cache: typing.Optional[LogCache] = None,
    cache_key: typing.Optional[typing.Hashable] = None,
    should_flush_cache: typing.Optional[
        typing.Callable[[LogCache], typing.Awaitable[bool]]
    ] = None,
    *writer_args: P.args,
    **writer_kwargs: P.kwargs,
) -> Logger:
    """
    Builds a logger function that can write logs to a cache and log storage/database.

    The built logger function will write logs to the cache first,
    and then flush the cache to the log storage/database if the
    `should_flush_cache` condition is met.

    :param writer: The log writer (callable) to use to write logs to the log storage/database.
    :param cache: The cache object to write logs to. Optional. If not provided,
        the logger will write logs immediately to the log storage/database.
    :param cache_key: The key to use for the cache. Only required if `cache` is provided.
    :param should_flush_cache: A function to determine if the cache should be flushed to the storage/database.
        This function should accept a `LogCache` instance and return a boolean indicating.
        Only required if `cache` is provided.
    :param writer_args: Additional positional arguments to pass to the log writer.
    :param writer_kwargs: Additional keyword arguments to pass to the log writer.
    :return: A function that writes logs to the cache and log storage/database.
    """

    async def logger(logs: typing.Sequence[typing.Dict[str, typing.Any]]) -> None:
        if not logs:
            return

        if cache is None or cache_key is None:
            await writer(logs, *writer_args, **writer_kwargs)
            return

        await write_logs_to_cache(logs, cache, cache_key)
        if should_flush_cache is None or await should_flush_cache(cache):
            try:
                entries_bytes = await cache.get(cache_key)
                entries = json.loads(entries_bytes)
            except KeyError:
                # The cache key does not exist, nothing to flush
                return
            await writer(entries, *writer_args, **writer_kwargs)
            await cache.delete(cache_key)

    return logger


def batched_logger_factory(
    writer: LogWriter[P],
    cache: LogCache,
    cache_key: typing.Hashable,
    batch_size: int = 100,
    *writer_args: P.args,
    **writer_kwargs: P.kwargs,
) -> Logger:
    """
    Builds a version of the logger function that writes logs in batches to the log storage/database.
    This requires a cache to store the logs temporarily before flushing them to the log storage/database.

    :param writer: The log writer (callable) to use to write logs to the log storage/database.
    :param cache: The cache object to write logs to.
    :param cache_key: The key to use for the cache.
    :param batch_size: The size of the batch to write to the database.
        If the cache size reaches this limit, it will be flushed to the database.
    :param writer_args: Additional positional arguments to pass to the log writer.
    :param writer_kwargs: Additional keyword arguments to pass to the log writer.
    :return: A function that writes logs to the cache and log storage/database in batches.
    """

    async def should_flush_cache(cache: LogCache) -> bool:
        try:
            entries_bytes = await cache.get(cache_key)
            entries = json.loads(entries_bytes)
        except KeyError:
            return False

        cache_size = len(entries)
        return cache_size >= batch_size

    return logger_factory(
        writer=writer,
        *writer_args,
        **writer_kwargs,
        cache=cache,
        cache_key=cache_key,
        should_flush_cache=should_flush_cache,
    )


def timed_logger_factory(
    writer: LogWriter[P],
    cache: LogCache,
    cache_key: typing.Hashable,
    interval: float = 60,
    *writer_args: P.args,
    **writer_kwargs: P.kwargs,
) -> Logger:
    """
    Builds a version of the logger function that writes logs to the log storage/database
    at regular intervals. This requires a cache to store the logs temporarily before flushing them
    to the log storage/database.

    :param writer: The log writer (callable) to use to write logs to the log storage/database.
    :param cache: The cache object to write logs to.
    :param cache_key: The key to use for the cache.
    :param interval: The time interval in seconds to flush the cache to the database.
        If the cache has not been flushed for this duration, it will be flushed to the database.
    :param writer_args: Additional positional arguments to pass to the log writer.
    :param writer_kwargs: Additional keyword arguments to pass to the log writer.
    :return: A function that writes logs to the cache and log storage/database at regular intervals.
    """
    if interval <= 0:
        raise ValueError("Interval must be greater than 0 seconds.")
    last_flushed_at = 0

    async def should_flush_cache(_: LogCache) -> bool:
        nonlocal last_flushed_at
        if time.monotonic() - last_flushed_at >= interval:
            last_flushed_at = time.monotonic()
            return True
        return False

    return logger_factory(
        writer=writer,
        *writer_args,
        **writer_kwargs,
        cache=cache,
        cache_key=cache_key,
        should_flush_cache=should_flush_cache,
    )


def timed_batched_logger_factory(
    writer: LogWriter[P],
    cache: LogCache,
    cache_key: typing.Hashable,
    batch_size: int = 100,
    interval: float = 60,
    *writer_args: P.args,
    **writer_kwargs: P.kwargs,
) -> Logger:
    """
    Builds a logger function that writes logs to the log storage/database
    in batches and at regular intervals.

    The logger writes given log data to a cache and flushes the cache to the log storage/database
    when the batch size is reached or at the specified interval.

    :param writer: The log writer (callable) to use to write logs to the log storage/database.
    :param cache: The cache object to write logs to.
    :param cache_key: The key to use for the cache.
    :param batch_size: The size of the batch to write to the log storage/database.
        If the cache size reaches this limit, it will be flushed to the log storage/database.
    :param interval: The time interval in seconds to flush the cache to the log storage/database.
    :param writer_args: Additional positional arguments to pass to the log writer.
    :param writer_kwargs: Additional keyword arguments to pass to the log writer.
    :return: A function that writes logs to the cache and log storage/database in batches
        and at regular intervals.
    """
    if interval <= 0:
        raise ValueError("Interval must be greater than 0.")

    last_flushed_at = 0

    async def should_flush_cache(cache: LogCache) -> bool:
        nonlocal last_flushed_at
        if time.monotonic() - last_flushed_at >= interval:
            last_flushed_at = time.monotonic()
            return True
        try:
            entries_bytes = await cache.get(cache_key)
            entries = json.loads(entries_bytes)
        except KeyError:
            return False

        cache_size = len(entries)
        return cache_size >= batch_size

    return logger_factory(
        writer=writer,
        *writer_args,
        **writer_kwargs,
        cache=cache,
        cache_key=cache_key,
        should_flush_cache=should_flush_cache,
    )


async def build_log_entries(
    connection: HTTPConnection,
    connection_events: typing.Sequence[ConnectionEvent],
    status: ResponseStatus,
    metadata: typing.Dict[str, typing.Any],
) -> typing.List[LogEntry]:
    """
    Log builder function that creates log entries from connection events.
    This function extracts relevant information from the connection and
    connection events, including the status, IP address, user agent, and metadata.

    :param connection: The HTTP connection object.
    :param connection_events: The connection events to log.
    :param status: The status of the connection (OK or ERROR).
    :param metadata: Additional metadata to include in the log entries.
    :return: A list of log entries.
    """
    entries = []
    ip_address = get_ip_address(connection)
    user_agent = connection.headers.get("user-agent")
    for connection_event in connection_events:
        entry = {
            **connection_event,
            "status": status.value,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "metadata": metadata,
        }
        entries.append(entry)
    return entries


class ConnectionEventLogMiddleware:
    """
    Middleware to log connection events attached to the connection.
    """

    def __init__(
        self,
        app: ASGIApp,
        logger: typing.Union[str, Logger],
        log_builder: typing.Optional[typing.Union[str, LogBuilder]] = None,
        excluded_paths: typing.Optional[typing.Sequence[str]] = None,
        included_paths: typing.Optional[typing.Sequence[str]] = None,
        include_request: bool = True,
        include_response: bool = True,
        compress_body: bool = False,
    ):
        """
        Initialize the middleware.

        :param app: The ASGI application.
        :param logger: Logger or string path to the logger.
            This awaitable accepts a list of log entries and write
            them to the log storage/database.
        :param log_builder: Log builder or string path to the log builder.
            This awaitable should accept a connection, connection events,
            metadata, and status, and return a list of log entries.
        :param excluded_paths: List of (regex type) paths to exclude from logging.
        :param included_paths: List of (regex type) paths to include in logging.
        :param compress_body: Whether to compress the request and response body in log data.
            This is useful for making log data for larger payloads smaller.
        :param include_request: Whether to include the request data in the log.
        :param include_response: Whether to include the response data in the log.
        """
        if excluded_paths and included_paths:
            raise ValueError("Cannot specify both 'exclude' and 'include' paths.")

        if isinstance(logger, str):
            logger = typing.cast(Logger, import_string(logger))
        if isinstance(log_builder, str):
            log_builder = typing.cast(LogBuilder, import_string(log_builder))

        self.app = app
        self.logger = logger
        self.log_builder = log_builder or build_log_entries
        self.included_paths_patterns = (
            [urlstring_to_re(path) for path in included_paths] if included_paths else []
        )
        self.excluded_paths_patterns = (
            [urlstring_to_re(path) for path in excluded_paths] if excluded_paths else []
        )
        self.include_request = include_request
        self.include_response = include_response
        self.compress_body = compress_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if self.excluded_paths_patterns and any(
            pattern.match(path) for pattern in self.excluded_paths_patterns
        ):
            await self.app(scope, receive, send)
            return
        if self.included_paths_patterns and not any(
            pattern.match(path) for pattern in self.included_paths_patterns
        ):
            await self.app(scope, receive, send)
            return

        responder = ConnectionEventLogMiddlewareResponder(
            app=self.app,
            logger=self.logger,
            log_builder=self.log_builder,
            include_request=self.include_request,
            include_response=self.include_response,
            compress_body=self.compress_body,
        )
        await responder(scope, receive, send)


class ConnectionEventLogMiddlewareResponder:
    """
    Middleware responder class to handle connection events and log them.
    """

    def __init__(
        self,
        app: ASGIApp,
        logger: Logger,
        log_builder: LogBuilder,
        include_request: bool = True,
        include_response: bool = True,
        compress_body: bool = False,
    ) -> None:
        """
        Initialize the responder.

        :param app: The ASGI application.
        :param logger: Awaitable that accepts a list of log entries and writes
            them to the log storage/database.
        :param log_builder: Log builder or string path to the log builder.
            This awaitable should accept a connection, connection events,
            metadata, and status, and return a list of log entries.
        :param include_request: Whether to include the request data in the log.
        :param include_response: Whether to include the response data in the log.
        :param compress_body: Whether to compress the request and response body in log data.
        """
        self.app = app
        self.logger = logger
        self.builder = log_builder
        self.send = empty_send
        self.receive = empty_receive
        self.status = ResponseStatus.ERROR  # Assume error until proven otherwise
        self.metadata = {
            "request": {},
            "response": {},
            "error": None,
        }
        self.exception = None
        self.include_request = include_request
        self.include_response = include_response
        self.compress_body = compress_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.send = send
        self.receive = receive
        if settings.LOG_CONNECTION_EVENTS is False:
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        path = scope["path"]
        connection = HTTPConnection(scope, receive)
        if self.include_request:
            headers = _clean_headers(connection.headers)
            query_params = dict(connection.query_params)
            self.metadata["request"] = {
                "method": method,
                "url": path,
                "query_params": query_params,
                "headers": headers,
                "body": None,
            }

        if self.include_response:
            self.metadata["response"] = {
                "status_code": None,
                "headers": None,
                "body": None,
            }

        try:
            await self.app(scope, self.receive_request, self.send_response)
        except Exception as exc:
            self.exception = exc
            self.metadata["error"] = str(exc)

        connection_events: typing.Optional[typing.Sequence[ConnectionEvent]] = getattr(
            connection.state, "events", None
        )
        if not connection_events:
            connection_events = [
                ConnectionEvent(
                    event=method,
                    target=path,
                    target_uid=None,
                    description=f"{method} connection to {path}",
                ),
            ]

        log_entries = await self.builder(
            connection, connection_events, self.status, self.metadata
        )
        await self.logger(log_entries)

        if self.exception:
            raise self.exception

    async def receive_request(self) -> Message:
        message = await self.receive()
        if not self.include_request:
            return message

        if message["type"] == "http.request":
            body = message.get("body", b"")
            if body:
                if self.compress_body:
                    body_data = await compress_data(body)
                else:
                    body_data = body.decode("utf-8")

                if self.metadata["request"].get("body", None) is None:
                    self.metadata["request"]["body"] = [body_data]
                else:
                    self.metadata["request"]["body"].append(body_data)
        return message

    async def send_response(self, message: Message) -> None:
        if not self.include_response:
            await self.send(message)
            return

        message_type = message["type"]
        if message_type == "http.response.start":
            self.metadata["response"]["status_code"] = message["status"]
            self.metadata["response"]["headers"] = _clean_headers(
                dict(Headers(raw=message["headers"]))
            )
            self.status = (
                ResponseStatus.OK
                if 200 <= message["status"] < 400
                else ResponseStatus.ERROR
            )

        elif message_type == "http.response.body":
            body = message.get("body", b"")
            if not body or "response" not in self.metadata:
                await self.send(message)
                return

            if self.compress_body:
                body_data = await compress_data(body)
            else:
                body_data = body.decode("utf-8")

            if self.metadata["response"].get("body", None) is None:
                self.metadata["response"]["body"] = [body_data]
            else:
                self.metadata["response"]["body"].append(body_data)

        await self.send(message)
