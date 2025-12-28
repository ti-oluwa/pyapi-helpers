from src.dependencies import deps_required

deps_required({"cachetools": "cachetools"})

import functools
import time
import typing
import threading
import asyncio
from typing_extensions import ParamSpec
from cachetools import TTLCache, TLRUCache, LRUCache, LFUCache

from src.types import Function, CoroutineFunction


P = ParamSpec("P")
R = typing.TypeVar("R")
T = typing.TypeVar("T")
_KT = typing.TypeVar("_KT")
_VT = typing.TypeVar("_VT")


class _CacheMiss:
    """Sentinel object for cache misses."""

    def __repr__(self) -> str:
        return "<CACHE_MISS>"


CACHE_MISS = _CacheMiss()


class ThreadSafeTTLCache(TTLCache[_KT, _VT]):
    """Thread-safe TTL Cache"""

    def __init__(
        self,
        maxsize: int,
        ttl: float,
        timer: typing.Callable[[], float] = time.monotonic,
        getsizeof: typing.Optional[typing.Callable[[_VT], int]] = None,
    ):
        super().__init__(maxsize, ttl, timer, getsizeof)
        self._lock = threading.RLock()

    def __getitem__(self, key: _KT) -> _VT:
        with self._lock:
            return super().__getitem__(key)

    def __setitem__(self, key: _KT, value: _VT) -> None:
        with self._lock:
            super().__setitem__(key, value)

    def __delitem__(self, key: _KT):
        with self._lock:
            return super().__delitem__(key)

    def clear(self):
        with self._lock:
            return super().clear()

    def get(
        self, key: _KT, default: typing.Optional[_VT] = None
    ) -> typing.Optional[_VT]:
        try:
            return self[key]
        except KeyError:
            return default

    def set(self, key: _KT, value: _VT) -> None:
        self[key] = value


@typing.overload
def ttl_cache(func: Function[P, R]) -> Function[P, R]: ...


@typing.overload
def ttl_cache(
    func: None = None,
    maxsize: int = 128,
    ttl: float = 3600,
    include_args: bool = True,
    include_kwargs: bool = True,
) -> typing.Callable[[Function[P, R]], Function[P, R]]: ...


@typing.overload
def ttl_cache(func: CoroutineFunction[P, R]) -> CoroutineFunction[P, R]: ...  # type: ignore


@typing.overload
def ttl_cache(  # type: ignore
    func: None = None,
    maxsize: int = 128,
    ttl: float = 3600,
    include_args: bool = True,
    include_kwargs: bool = True,
) -> typing.Callable[[CoroutineFunction[P, R]], CoroutineFunction[P, R]]: ...


def ttl_cache(  # type: ignore
    func: typing.Optional[typing.Union[Function[P, R], CoroutineFunction[P, R]]] = None,
    *,
    maxsize: int = 128,
    ttl: float = 3600,
    include_args: bool = True,
    include_kwargs: bool = True,
    getsizeof: typing.Optional[typing.Callable[[R], int]] = None,
):
    """
    Time to Live (TTL) cache decorator with advanced features.

    :param maxsize: Maximum size of the cache
    :param ttl: Time to live in seconds (default: 1 hour)
    :param include_args: Whether to include positional args in cache key
    :param include_kwargs: Whether to include keyword args in cache key
    :param getsizeof: Function to determine size of cache entries
    :returns: Decorated function with caching
    :raises ValueError: If maxsize is less than 0 or ttl is not positive

    Example:
        ```python
        @ttl_cache(maxsize=100, ttl=1800)  # 30 minute cache
        def get_user(user_id: int) -> User:
            return db.query(User).get(user_id)

        @ttl_cache(maxsize=100, ttl=3600, include_kwargs=False)
        async def get_stats(*metrics: str) -> Dict[str, float]:
            return await fetch_metrics(metrics)
        ```
    """
    if maxsize < 0:
        raise ValueError("maxsize must be >= 0")
    if ttl <= 0:
        raise ValueError("ttl must be positive")

    cache = ThreadSafeTTLCache[CacheKey, typing.Any](
        maxsize=maxsize,
        ttl=ttl,
        getsizeof=getsizeof,
    )

    def make_key(*args: P.args, **kwargs: P.kwargs) -> CacheKey:
        """Create cache key from function arguments."""
        key_parts = []
        if include_args:
            key_parts.append(args)
        if include_kwargs:
            key_parts.append(frozenset(kwargs.items()))
        return tuple(key_parts)  # type: ignore

    def decorator(
        func: typing.Union[Function[P, R], CoroutineFunction[P, R]],
    ) -> typing.Union[Function[P, R], CoroutineFunction[P, R]]:
        wrapper = None
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(
                *args: P.args, **kwargs: P.kwargs
            ) -> typing.Optional[R]:
                key = make_key(*args, **kwargs)
                # Using asyncio.to_thread to run blocking code (the thread lock) in a separate thread
                result = await asyncio.to_thread(cache.get, key=key, default=CACHE_MISS)
                if result is CACHE_MISS:
                    result = await func(*args, **kwargs)
                    await asyncio.to_thread(cache.set, key=key, value=result)
                return result

            wrapper = async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> typing.Optional[R]:
                key = make_key(*args, **kwargs)
                result = cache.get(key, default=CACHE_MISS)
                if result is CACHE_MISS:
                    result = func(*args, **kwargs)
                    cache[key] = result
                return result  # type: ignore

            wrapper = sync_wrapper

        wrapper.cache = cache  # type: ignore
        wrapper.cache_info = lambda: {  # type: ignore
            "maxsize": cache.maxsize,
            "currsize": len(cache),
            "ttl": cache.ttl,
            "hits": cache.hits if hasattr(cache, "hits") else 0,  # type: ignore
            "misses": cache.misses if hasattr(cache, "misses") else 0,  # type: ignore
        }
        return wrapper  # type: ignore

    if func is None:
        return decorator
    return decorator(func)


CacheKey = typing.Tuple[
    typing.Tuple[typing.Any, ...], typing.FrozenSet[typing.Tuple[str, typing.Any]]
]
TTUFunc = typing.Callable[[_KT, _VT, float], float]


def default_ttu(key: CacheKey, value: typing.Any, time: float) -> float:
    """Default TTU function that returns 1 hour."""
    return 3600.0


class ThreadSafeTLRUCache(TLRUCache[_KT, _VT]):
    """Thread-safe TLRU Cache"""

    def __init__(
        self,
        maxsize: int,
        ttu: TTUFunc[_KT, _VT],
        timer: typing.Callable[[], float] = time.monotonic,
        getsizeof: typing.Optional[typing.Callable[[_VT], int]] = None,
    ):
        super().__init__(maxsize, ttu, timer, getsizeof)
        self._lock = threading.RLock()  # Reentrant lock for nested operations

    def __getitem__(self, key: _KT) -> _VT:
        with self._lock:
            return super().__getitem__(key)

    def __setitem__(self, key: _KT, value: _VT) -> None:
        with self._lock:
            super().__setitem__(key, value)

    def __delitem__(self, key: _KT):
        with self._lock:
            return super().__delitem__(key)

    def clear(self):
        with self._lock:
            return super().clear()

    def get(
        self, key: _KT, default: typing.Optional[_VT] = None
    ) -> typing.Optional[_VT]:
        try:
            return self[key]
        except KeyError:
            return default

    def set(self, key: _KT, value: _VT) -> None:
        self[key] = value


def _make_ttu_func(ttu: typing.Union[float, TTUFunc[_KT, _VT]]) -> TTUFunc[_KT, _VT]:
    """Convert TTU value to a function if it's a float."""
    if isinstance(ttu, (int, float)):
        return lambda *_: float(ttu)
    return ttu


@typing.overload
def tlru_cache(func: Function[P, R]) -> Function[P, R]: ...


@typing.overload
def tlru_cache(
    func: None = None,
    maxsize: int = 128,
    ttu: typing.Union[float, TTUFunc[CacheKey, R]] = default_ttu,
    include_args: bool = True,
    include_kwargs: bool = True,
    getsizeof: typing.Optional[typing.Callable[[R], int]] = None,
) -> typing.Callable[[Function[P, R]], Function[P, R]]: ...


@typing.overload
def tlru_cache(  # type: ignore
    func: CoroutineFunction[P, R],
) -> CoroutineFunction[P, R]: ...


@typing.overload
def tlru_cache(
    func: None = None,
    maxsize: int = 128,
    ttu: typing.Union[float, TTUFunc[CacheKey, R]] = default_ttu,
    include_args: bool = True,
    include_kwargs: bool = True,
    getsizeof: typing.Optional[typing.Callable[[R], int]] = None,
) -> typing.Callable[[CoroutineFunction[P, R]], CoroutineFunction[P, R]]: ...


def tlru_cache(  # type: ignore
    func: typing.Optional[typing.Union[Function[P, R], CoroutineFunction[P, R]]] = None,
    *,
    maxsize: int = 128,
    ttu: typing.Union[float, TTUFunc[CacheKey, R]] = default_ttu,
    include_args: bool = True,
    include_kwargs: bool = True,
    getsizeof: typing.Optional[typing.Callable[[R], int]] = None,
):
    """
    Time-aware Least Recently Used (LRU) cache decorator with advanced features.

    :param maxsize: Maximum size of the cache
    :param ttu: Time to update in seconds or function(key, value, time) -> float
    :param include_args: Whether to include positional args in cache key
    :param include_kwargs: Whether to include keyword args in cache key
    :param getsizeof: Function to determine size of cache entries
    :returns: Decorated function with caching
    :raises ValueError: If maxsize is less than 0

    Example:
        ```python
        # Basic usage with 1 hour TTU
        @tlru_cache(maxsize=100)
        def get_user(user_id: int) -> User:
            return db.query(User).get(user_id)

        # Custom TTU function
        def dynamic_ttu(key, value, time):
            return 3600 if isinstance(value, User) else 1800

        @tlru_cache(maxsize=100, ttu=dynamic_ttu)
        async def get_user_async(user_id: int) -> User:
            return await db.query(User).get(user_id)
        ```
    """
    if maxsize < 0:
        raise ValueError("maxsize must be >= 0")

    cache = ThreadSafeTLRUCache[CacheKey, typing.Any](
        maxsize=maxsize,
        ttu=_make_ttu_func(ttu),
        getsizeof=getsizeof,
    )

    def make_key(*args: P.args, **kwargs: P.kwargs) -> CacheKey:
        """Create cache key from function arguments."""
        key_parts = []
        if include_args:
            key_parts.append(args)
        if include_kwargs:
            key_parts.append(frozenset(kwargs.items()))
        return tuple(key_parts)  # type: ignore

    def decorator(
        func: typing.Union[Function[P, R], CoroutineFunction[P, R]],
    ) -> typing.Union[Function[P, R], CoroutineFunction[P, R]]:
        wrapper = None
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(
                *args: P.args, **kwargs: P.kwargs
            ) -> typing.Optional[R]:
                key = make_key(*args, **kwargs)
                result = await asyncio.to_thread(cache.get, key=key, default=CACHE_MISS)
                if result is CACHE_MISS:
                    result = await func(*args, **kwargs)
                    await asyncio.to_thread(cache.set, key=key, value=result)
                return result

            wrapper = async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> typing.Optional[R]:
                key = make_key(*args, **kwargs)
                result = cache.get(key, default=CACHE_MISS)
                if result is CACHE_MISS:
                    result = func(*args, **kwargs)
                    cache[key] = result
                return result  # type: ignore

            wrapper = sync_wrapper

        wrapper.cache = cache  # type: ignore
        wrapper.cache_info = lambda: {  # type: ignore
            "maxsize": cache.maxsize,
            "currsize": len(cache),
            "hits": cache.hits if hasattr(cache, "hits") else 0,  # type: ignore
            "misses": cache.misses if hasattr(cache, "misses") else 0,  # type: ignore
        }
        return wrapper  # type: ignore

    if func is None:
        return decorator
    return decorator(func)


class ThreadSafeLRUCache(LRUCache[_KT, _VT]):
    """Thread-safe LRU Cache"""

    def __init__(
        self,
        maxsize: int,
        getsizeof: typing.Optional[typing.Callable[[_VT], int]] = None,
    ):
        super().__init__(maxsize, getsizeof)
        self._lock = threading.RLock()

    def __getitem__(self, key: _KT) -> _VT:
        with self._lock:
            return super().__getitem__(key)

    def __setitem__(self, key: _KT, value: _VT) -> None:
        with self._lock:
            super().__setitem__(key, value)

    def __delitem__(self, key: _KT):
        with self._lock:
            return super().__delitem__(key)

    def clear(self):
        with self._lock:
            return super().clear()

    def get(
        self, key: _KT, default: typing.Optional[_VT] = None
    ) -> typing.Optional[_VT]:
        try:
            return self[key]
        except KeyError:
            return default

    def set(self, key: _KT, value: _VT) -> None:
        self[key] = value


@typing.overload
def lru_cache(func: Function[P, R]) -> Function[P, R]: ...


@typing.overload
def lru_cache(
    func: None = None,
    maxsize: int = 128,
    include_args: bool = True,
    include_kwargs: bool = True,
    getsizeof: typing.Optional[typing.Callable[[R], int]] = None,
) -> typing.Callable[[Function[P, R]], Function[P, R]]: ...


@typing.overload
def lru_cache(func: CoroutineFunction[P, R]) -> CoroutineFunction[P, R]: ...  # type: ignore


@typing.overload
def lru_cache(
    func: None = None,
    maxsize: int = 128,
    include_args: bool = True,
    include_kwargs: bool = True,
    getsizeof: typing.Optional[typing.Callable[[R], int]] = None,
) -> typing.Callable[[CoroutineFunction[P, R]], CoroutineFunction[P, R]]: ...


def lru_cache(  # type: ignore
    func: typing.Optional[typing.Union[Function[P, R], CoroutineFunction[P, R]]] = None,
    *,
    maxsize: int = 128,
    include_args: bool = True,
    include_kwargs: bool = True,
    getsizeof: typing.Optional[typing.Callable[[R], int]] = None,
):
    """
    Least Recently Used (LRU) cache decorator with thread safety.

    :param maxsize: Maximum size of the cache
    :param include_args: Whether to include positional args in cache key
    :param include_kwargs: Whether to include keyword args in cache key
    :param getsizeof: Function to determine size of cache entries
    :returns: Decorated function with caching
    :raises ValueError: If maxsize is less than 0

    Example:
        ```python
        @lru_cache(maxsize=100)
        def get_user(user_id: int) -> User:
            return db.query(User).get(user_id)

        @lru_cache(maxsize=100)
        async def get_stats(*metrics: str) -> Dict[str, float]:
            return await fetch_metrics(metrics)
        ```
    """
    if maxsize < 0:
        raise ValueError("maxsize must be >= 0")

    cache = ThreadSafeLRUCache[CacheKey, typing.Any](
        maxsize=maxsize,
        getsizeof=getsizeof,
    )

    def make_key(*args: P.args, **kwargs: P.kwargs) -> CacheKey:
        """Create cache key from function arguments."""
        key_parts = []
        if include_args:
            key_parts.append(args)
        if include_kwargs:
            key_parts.append(frozenset(kwargs.items()))
        return tuple(key_parts)  # type: ignore

    def decorator(
        func: typing.Union[Function[P, R], CoroutineFunction[P, R]],
    ) -> typing.Union[Function[P, R], CoroutineFunction[P, R]]:
        wrapper = None

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(
                *args: P.args, **kwargs: P.kwargs
            ) -> typing.Optional[R]:
                key = make_key(*args, **kwargs)
                result = await asyncio.to_thread(cache.get, key=key, default=CACHE_MISS)
                if result is CACHE_MISS:
                    result = await func(*args, **kwargs)
                    await asyncio.to_thread(cache.set, key=key, value=result)
                return result

            wrapper = async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> typing.Optional[R]:
                key = make_key(*args, **kwargs)
                result = cache.get(key, default=CACHE_MISS)
                if result is CACHE_MISS:
                    result = func(*args, **kwargs)
                    cache[key] = result
                return result  # type: ignore

            wrapper = sync_wrapper

        wrapper.cache = cache  # type: ignore
        wrapper.cache_info = lambda: {  # type: ignore
            "maxsize": cache.maxsize,
            "currsize": len(cache),
            "hits": cache.hits if hasattr(cache, "hits") else 0,  # type: ignore
            "misses": cache.misses if hasattr(cache, "misses") else 0,  # type: ignore
        }
        return wrapper  # type: ignore

    if func is None:
        return decorator
    return decorator(func)


class ThreadSafeLFUCache(LFUCache[_KT, _VT]):
    """Thread-safe LFU Cache"""

    def __init__(
        self,
        maxsize: int,
        getsizeof: typing.Optional[typing.Callable[[_VT], int]] = None,
    ):
        super().__init__(maxsize, getsizeof)
        self._lock = threading.RLock()

    def __getitem__(self, key: _KT) -> _VT:
        with self._lock:
            return super().__getitem__(key)

    def __setitem__(self, key: _KT, value: _VT) -> None:
        with self._lock:
            super().__setitem__(key, value)

    def __delitem__(self, key: _KT):
        with self._lock:
            return super().__delitem__(key)

    def clear(self):
        with self._lock:
            return super().clear()

    def get(
        self, key: _KT, default: typing.Optional[_VT] = None
    ) -> typing.Optional[_VT]:
        try:
            return self[key]
        except KeyError:
            return default

    def set(self, key: _KT, value: _VT) -> None:
        self[key] = value


@typing.overload
def lfu_cache(func: Function[P, R]) -> Function[P, R]: ...


@typing.overload
def lfu_cache(
    func: None = None,
    maxsize: int = 128,
    include_args: bool = True,
    include_kwargs: bool = True,
    getsizeof: typing.Optional[typing.Callable[[R], int]] = None,
) -> typing.Callable[[Function[P, R]], Function[P, R]]: ...


@typing.overload
def lfu_cache(func: CoroutineFunction[P, R]) -> CoroutineFunction[P, R]: ...  # type: ignore


@typing.overload
def lfu_cache(
    func: None = None,
    maxsize: int = 128,
    include_args: bool = True,
    include_kwargs: bool = True,
    getsizeof: typing.Optional[typing.Callable[[R], int]] = None,
) -> typing.Callable[[CoroutineFunction[P, R]], CoroutineFunction[P, R]]: ...


def lfu_cache(  # type: ignore
    func: typing.Optional[typing.Union[Function[P, R], CoroutineFunction[P, R]]] = None,
    *,
    maxsize: int = 128,
    include_args: bool = True,
    include_kwargs: bool = True,
    getsizeof: typing.Optional[typing.Callable[[R], int]] = None,
):
    """
    Least Frequently Used (LFU) cache decorator with thread safety.

    :param maxsize: Maximum size of the cache
    :param include_args: Whether to include positional args in cache key
    :param include_kwargs: Whether to include keyword args in cache key
    :param getsizeof: Function to determine size of cache entries
    :returns: Decorated function with caching
    :raises ValueError: If maxsize is less than 0

    Example:
        ```python
        @lfu_cache(maxsize=100)
        def get_user(user_id: int) -> User:
            return db.query(User).get(user_id)

        @lfu_cache(maxsize=100)
        async def get_stats(*metrics: str) -> Dict[str, float]:
            return await fetch_metrics(metrics)
        ```
    """
    if maxsize < 0:
        raise ValueError("maxsize must be >= 0")

    cache = ThreadSafeLFUCache[CacheKey, typing.Any](
        maxsize=maxsize,
        getsizeof=getsizeof,
    )

    def make_key(*args: P.args, **kwargs: P.kwargs) -> CacheKey:
        key_parts = []
        if include_args:
            key_parts.append(args)
        if include_kwargs:
            key_parts.append(frozenset(kwargs.items()))
        return tuple(key_parts)  # type: ignore

    def decorator(
        func: typing.Union[Function[P, R], CoroutineFunction[P, R]],
    ) -> typing.Union[Function[P, R], CoroutineFunction[P, R]]:
        wrapper = None
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(
                *args: P.args, **kwargs: P.kwargs
            ) -> typing.Optional[R]:
                key = make_key(*args, **kwargs)
                result = await asyncio.to_thread(cache.get, key=key, default=CACHE_MISS)
                if result is CACHE_MISS:
                    result = await func(*args, **kwargs)
                    await asyncio.to_thread(cache.set, key=key, value=result)
                return result

            wrapper = async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> typing.Optional[R]:
                key = make_key(*args, **kwargs)
                result = cache.get(key, default=CACHE_MISS)
                if result is CACHE_MISS:
                    result = func(*args, **kwargs)
                    cache[key] = result
                return result  # type: ignore

            wrapper = sync_wrapper

        wrapper.cache = cache  # type: ignore
        wrapper.cache_info = lambda: {  # type: ignore
            "maxsize": cache.maxsize,
            "currsize": len(cache),
            "hits": cache.hits if hasattr(cache, "hits") else 0,  # type: ignore
            "misses": cache.misses if hasattr(cache, "misses") else 0,  # type: ignore
        }
        return wrapper  # type: ignore

    if func is None:
        return decorator
    return decorator(func)
