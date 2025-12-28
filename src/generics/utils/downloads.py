"""Download utilities with robust error handling, retries, and progress tracking.

Features:
- Automatic retries with exponential backoff
- Memory efficient streaming downloads
- Progress tracking
- Response handling/transformation
- Concurrent batch downloads
- Response caching
"""

from src.dependencies import deps_required

deps_required({"httpx": "httpx"})

import typing
import asyncio
import httpx
import time
from pathlib import PurePath
from dataclasses import dataclass
from contextlib import asynccontextmanager
import hashlib
from datetime import datetime, timedelta

from src.logging import log_exception
from src.generics.utils.misc import get_memory_size
from src.types import LoggerLike, T


SyncDownloadHandler = typing.Callable[[httpx.Response], T]
"""Handler for download response"""
AsyncDownloadHandler = typing.Callable[[httpx.Response], typing.Awaitable[T]]
"""Async handler for download response"""
DownloadHandler = typing.Union[SyncDownloadHandler[T], AsyncDownloadHandler[T]]
ProgressCallback = typing.Callable[[int, int], None]
"""Callback for download progress tracking"""


class DownloadFailed(Exception):
    """Exception raised when a download fails"""

    pass


@dataclass(frozen=True, slots=True, eq=True)
class DownloadConfig:
    """Download configuration settings.

    :param max_retries: Number of retry attempts for failed downloads
    :param retry_delay: Base delay between retries in seconds (uses exponential backoff)
    :param timeout: Request timeout in seconds
    :param chunk_size: Size of download chunks in bytes for streaming
    :param request_kwargs: Additional arguments to pass to httpx client
    :param cache_for: Duration to cache successful downloads in seconds
    """

    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: typing.Optional[float] = None
    chunk_size: int = 8192
    request_kwargs: typing.Optional[typing.Dict[str, typing.Any]] = None
    cache_for: float = 300.0


CacheKey = str
CacheEntry = typing.NamedTuple(
    "CacheEntry",
    [
        ("content", bytes),
        ("expires_at", datetime),
        ("metadata", typing.Dict[str, typing.Any]),
    ],
)

Cache = typing.Dict[CacheKey, CacheEntry]

# Global cache storage
_download_cache: Cache = dict()
_CACHE_MAXSIZE: float = 1024 * 1024
_CACHE_MINSIZE: float = 1024


def set_default_cache_size(size: float):
    global _CACHE_MAXSIZE, _CACHE_MINSIZE

    if not size or size < _CACHE_MINSIZE:
        raise ValueError(
            f"Invalid cache size. Size should not be less than {_CACHE_MINSIZE}"
        )
    _CACHE_MAXSIZE = size


def _make_cache_key(url: str, handler_id: typing.Optional[str] = None) -> CacheKey:
    """Generate a cache key from URL and optional handler ID"""
    key = hashlib.sha256(url.encode()).hexdigest()
    if handler_id:
        key += f"_{handler_id}"
    return key


async def clear_expired_entries(cache: Cache) -> None:
    """Remove expired entries from cache"""
    now = datetime.now()
    expired = [k for k, v in cache.items() if v.expires_at <= now]

    lock = asyncio.Lock()
    for key in expired:
        async with lock:
            del cache[key]


async def clear_cache(cache: Cache) -> None:
    """Clear all entries from cache"""
    async with asyncio.Lock():
        cache.clear()


async def cache_value(
    cache: Cache,
    /,
    key: CacheKey,
    value: CacheEntry,
    *,
    maxsize: float,
):
    if get_memory_size(value) >= maxsize:
        return

    lock = asyncio.Lock()
    while (
        get_memory_size(cache) + get_memory_size(key) + get_memory_size(value)
    ) > maxsize:
        # Delete the older items in the cache
        try:
            async with lock:
                oldest = cache.popitem()
                del oldest
        except KeyError:
            return

    async with lock:
        cache[key] = value


@asynccontextmanager
async def get_client(
    config: DownloadConfig,
) -> typing.AsyncGenerator[httpx.AsyncClient, None]:
    """Get HTTP client with proper configuration"""
    request_kwargs = config.request_kwargs or {}
    request_kwargs.pop("timeout", None)
    httpx_timeout = httpx.Timeout(config.timeout)
    async with httpx.AsyncClient(timeout=httpx_timeout, **request_kwargs) as client:
        yield client


async def download_with_retry(
    url: str,
    client: httpx.AsyncClient,
    config: DownloadConfig,
) -> httpx.Response:
    """Download content with automatic retries and streaming.

    :param url: Target URL to download from
    :param client: Configured HTTP client instance
    :param config: Download configuration settings
    :return: Response object with downloaded content
    :raises httpx.RequestError: If download fails after all retries
    :raises asyncio.CancelledError: If download is cancelled
    """
    await clear_expired_entries(cache=_download_cache)
    cache_key = _make_cache_key(url)
    if config.cache_for > 0:
        if cache_entry := _download_cache.get(cache_key):
            if cache_entry.expires_at > datetime.now():
                # Construct fake response from cache entry
                response = httpx.Response(
                    content=cache_entry.content, **cache_entry.metadata
                )
                # Set this to avoid raising ResponseNotRead
                response._content = cache_entry.content  # type: ignore
                return response

    for attempt in range(config.max_retries):
        try:
            # Stream content to avoid memory issues
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                content = bytearray()

                async for chunk in response.aiter_bytes(chunk_size=config.chunk_size):
                    if asyncio.current_task().cancelled():  # type: ignore
                        raise asyncio.CancelledError()
                    content.extend(chunk)

                if config.cache_for > 0:
                    cache_entry = CacheEntry(
                        content=content,
                        expires_at=datetime.now() + timedelta(seconds=config.cache_for),
                        metadata={
                            "headers": dict(response.headers),
                            "status_code": response.status_code,
                            "default_encoding": response.encoding,
                            "extensions": response.extensions,
                            "history": response.history,
                        },
                    )
                    await cache_value(
                        _download_cache, cache_key, cache_entry, maxsize=_CACHE_MAXSIZE
                    )

                response._content = bytes(content)  # type: ignore
                return response

        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            if attempt == config.max_retries - 1:
                raise DownloadFailed(f"Failed to download {url}") from exc

            await asyncio.sleep(config.retry_delay * (attempt + 1))
            continue

        except Exception as exc:
            raise DownloadFailed(exc) from exc
    raise DownloadFailed(f"Failed to download {url}")


@typing.overload
async def async_download(
    url: str,
    handler: AsyncDownloadHandler[T],
    config: typing.Optional[DownloadConfig] = None,
) -> T: ...


@typing.overload
async def async_download(
    url: str,
    handler: None = None,
    config: typing.Optional[DownloadConfig] = None,
) -> bytes: ...


async def async_download(
    url: str,
    handler: typing.Optional[AsyncDownloadHandler[T]] = None,
    config: typing.Optional[DownloadConfig] = None,
) -> typing.Union[T, bytes]:
    """Asynchronously download and optionally process content from a URL.

    :param url: Target URL to download from
    :param handler: Optional async function to process the response
    :param config: Optional download configuration
    :return: Either the raw bytes or the processed result if handler provided
    :raises ValueError: If URL is empty

    Example:
    ```python
    # Simple download
    content = await async_download("https://example.com/file")

    # With response processing
    async def json_handler(response):
        return response.json()

    data = await async_download("https://api.example.com", handler=json_handler)
    ```
    """
    if not url:
        raise ValueError("URL is required")

    config = config or DownloadConfig()
    async with get_client(config) as client:
        response = await download_with_retry(url, client, config)

        if not handler:
            return response.content
        return await handler(response)


def download(
    url: str,
    handler: typing.Optional[DownloadHandler[T]] = None,
    config: typing.Optional[DownloadConfig] = None,
) -> typing.Union[T, bytes]:
    """
    Sync wrapper around `async_download` for synchronous code.

    :param url: Target URL to download from
    :param handler: Optional sync function to process the response
    :param config: Optional download configuration
    :return: Either the raw bytes or the processed result if handler provided
    :raises ValueError: If URL is empty

    Example:
    ```python
    # Simple download
    content = download("https://example.com/file")

    # With response processing
    def json_handler(response):
        return response.json()

    data = download("https://api.example.com", handler=json_handler)
    ```
    """
    if handler is not None and not asyncio.iscoroutinefunction(handler):
        handler = typing.cast(AsyncDownloadHandler[T], _sync_handler_to_async(handler))
    return asyncio.run(async_download(url, handler, config))


async def fast_multi_download(
    urls: typing.Dict[str, typing.Union[str, typing.Tuple[str, DownloadHandler[T]]]],
    default_handler: typing.Optional[DownloadHandler[T]] = None,
    config: typing.Optional[DownloadConfig] = None,
    batch_size: int = 10,
    progress_callback: typing.Optional[ProgressCallback] = None,
    logger: typing.Optional[LoggerLike] = None,
) -> typing.Dict[str, typing.Union[T, bytes]]:
    """Download multiple URLs concurrently with progress tracking.

    :param urls: Dictionary mapping names to either URLs or (URL, handler) tuples
    :param default_handler: Default response handler for URLs without specific handlers
    :param config: Optional download configuration
    :param batch_size: Maximum number of concurrent downloads
    :param progress_callback: Optional function called with (completed, total) counts
    :param logger: Optional logger for error reporting
    :return: Dictionary mapping names to download results

    Example:
    ```python
    urls = {
        "data": ("https://api.example.com/data", json_handler),
        "image": "https://example.com/image.png"
    }
    results = await fast_multi_download(
        urls,
        progress_callback=lambda done, total: print(f"{done}/{total}")
    )
    ```
    """
    if not urls:
        return {}

    config = config or DownloadConfig()
    results = {}
    failed = {}
    total = len(urls)
    completed = 0

    async with get_client(config) as client:
        tasks = []
        handler = default_handler

        for name, url_info in urls.items():
            handler = default_handler
            if isinstance(url_info, tuple):
                url, handler = url_info
            else:
                url = url_info

            task = asyncio.create_task(
                download_with_retry(url, client, config), name=name
            )
            tasks.append(task)

            if len(tasks) >= batch_size:
                batch_result, failed_tasks = await _process_batch_tasks(
                    tasks=tasks,
                    handler=handler,
                    progress_callback=progress_callback,
                    completed=completed,
                    total=total,
                )
                results.update(batch_result)
                failed.update(failed_tasks)
                completed += len(batch_result)
                tasks = []

        if tasks:
            batch_result, failed_tasks = await _process_batch_tasks(
                tasks=tasks,
                handler=handler,
                progress_callback=progress_callback,
                completed=completed,
                total=total,
                logger=logger,
            )
            results.update(batch_result)
            failed.update(failed_tasks)

        # If any downloads failed, retry them with exponential backoff
        if failed and config.max_retries > 1:
            retry_results = await _retry_failed_tasks(
                failed_tasks=failed,
                handler=handler,
                config=config,
                progress_callback=progress_callback,
                completed=completed,
                total=total,
            )
            results.update(retry_results)

    if not results and failed:
        raise DownloadFailed(f"All downloads failed: {failed.keys()}")

    if len(results) != total and progress_callback:
        progress_callback(total, total)
    return results


def _sync_handler_to_async(handler: SyncDownloadHandler[T]) -> AsyncDownloadHandler[T]:
    """Convert a sync handler to async"""

    async def async_handler(response: httpx.Response) -> T:
        return await asyncio.to_thread(handler, response)

    return async_handler


async def _process_batch_tasks(
    tasks: typing.List[asyncio.Task],
    handler: typing.Optional[DownloadHandler[T]],
    progress_callback: typing.Optional[ProgressCallback],
    completed: int,
    total: int,
    logger: typing.Optional[LoggerLike] = None,
) -> typing.Tuple[dict, dict]:
    """Process a batch of download tasks with progress tracking.

    :param tasks: List of download tasks to process
    :param handler: Optional response handler
    :param progress_callback: Optional progress tracking callback
    :param completed: Number of downloads completed so far
    :param total: Total number of downloads
    :return: Tuple of (successful_results, failed_tasks)
    """
    results = {}
    failed = {}

    for index, task in enumerate(asyncio.as_completed(tasks)):
        try:
            name = tasks[index].get_name()
        except AttributeError:
            name = None

        try:
            response = await task
            if name is None:
                continue

            if handler:
                if asyncio.iscoroutinefunction(handler):
                    results[name] = await handler(response)
                else:
                    results[name] = await _sync_handler_to_async(handler)(response)
            else:
                results[name] = response.content

            if progress_callback:
                progress_callback(completed + len(results), total)

        except Exception as exc:
            log_exception(exc, logger=logger)
            if name:
                failed[name] = task

    return results, failed


async def _retry_failed_tasks(
    failed_tasks: typing.Dict[str, asyncio.Task],
    handler: typing.Optional[DownloadHandler[T]],
    config: DownloadConfig,
    progress_callback: typing.Optional[ProgressCallback] = None,
    completed: int = 0,
    total: int = 0,
) -> typing.Dict[str, typing.Any]:
    """Retry failed downloads with exponential backoff.

    :param failed_tasks: Dictionary of failed download tasks
    :param handler: Optional response handler
    :param config: Download configuration
    :param progress_callback: Optional progress tracking callback
    :param completed: Number of successful downloads
    :param total: Total number of downloads
    :return: Dictionary of successfully retried downloads
    """
    results = {}

    for attempt in range(config.max_retries):
        if not failed_tasks:
            break

        delay = config.retry_delay * (2**attempt)
        await asyncio.sleep(delay)

        retry_tasks = list(failed_tasks.values())
        retry_results, still_failed = await _process_batch_tasks(
            tasks=retry_tasks,
            handler=handler,
            progress_callback=progress_callback,
            completed=completed,
            total=total,
        )

        results.update(retry_results)
        failed_tasks = still_failed
        completed += len(retry_results)

    return results


def multi_download(
    urls: typing.Dict[str, typing.Union[str, typing.Tuple[str, DownloadHandler[T]]]],
    default_handler: typing.Optional[DownloadHandler[T]] = None,
    config: typing.Optional[DownloadConfig] = None,
    progress_callback: typing.Optional[ProgressCallback] = None,
    logger: typing.Optional[LoggerLike] = None,
) -> typing.Dict[str, typing.Union[T, bytes]]:
    """Synchronous version of concurrent downloads with progress tracking.

    :param urls: Dictionary mapping names to either URLs or (URL, handler) tuples
    :param default_handler: Default response handler for URLs without specific handlers
    :param config: Optional download configuration
    :param progress_callback: Optional callback for tracking download progress
    :return: Dictionary mapping names to download results
    :raises Exception: Propagates any exceptions from failed downloads if no handler

    Example:
    ```python
    def show_progress(done: int, total: int):
        print(f"Downloaded {done}/{total} files ({done/total*100:.1f}%)")

    results = multi_download({
        "data": ("https://api.example.com/data", json_handler),
        "image": "https://example.com/image.png"
    }, progress_callback=show_progress)
    ```
    """
    if not urls:
        return {}

    config = config or DownloadConfig()
    results: typing.Dict[str, typing.Any] = {}
    errors: typing.Dict[str, typing.Dict[str, typing.Any]] = {}
    total = len(urls)
    completed = 0

    # Process each URL sequentially with progress tracking
    for name, url_info in urls.items():
        handler = default_handler
        if isinstance(url_info, tuple):
            url, handler = url_info
        else:
            url = url_info

        try:
            results[name] = download(url, handler=handler, config=config)
            completed += 1
            if progress_callback:
                progress_callback(completed, total)
        except Exception as exc:
            errors[name] = {
                "error": exc,
                "handler": handler,
            }
            log_exception(exc, logger=logger)

    # If any download still failed, retry them once
    if errors and config.max_retries > 1:
        retry_delay = config.retry_delay
        for name, data in list(errors.items()):
            url_info = urls[name]
            handler = data.get("handler", default_handler)
            if isinstance(url_info, tuple):
                url = url_info[0]
            else:
                url = url_info

            try:
                # Wait before retrying
                time.sleep(retry_delay)
                results[name] = download(url, handler=handler, config=config)
                del errors[name]
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)
            except Exception as exc:
                # Keep original error if retry also fails
                log_exception(exc, logger=logger)
                continue

    # If all downloads failed and no handler, raise DownloadFailed from first error
    if not results and errors:
        raise DownloadFailed(f"All downloads failed: {errors.keys()}") from next(
            iter(errors.values())
        )["error"]

    if len(results) != total and progress_callback:
        progress_callback(total, total)
    return results


def save_download(
    response: httpx.Response, path: typing.Union[str, PurePath], chunk_size: int = 8192
) -> None:
    """Save downloaded content to a file.

    :param response: HTTP response containing downloaded content
    :param path: File path to save content to
    :param chunk_size: Max size of each content chunk written to the file

    Example:
    ```python
    response = await async_download("https://example.com/file")
    save_download(response, "downloaded_file.txt")
    ```
    """
    with open(path, "wb") as file:
        for chunk in response.iter_bytes(chunk_size=chunk_size):
            file.write(chunk)


__all__ = [
    "DownloadConfig",
    "DownloadFailed",
    "async_download",
    "download",
    "fast_multi_download",
    "multi_download",
    "save_download",
]
