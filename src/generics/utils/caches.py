import logging
import hashlib
import datetime
import json
from typing import (
    Callable,
    Generic,
    Optional,
    Protocol,
    Set,
    Union,
    Dict,
    Any,
    Type,
    runtime_checkable,
    Iterator,
    AsyncIterator,
    TypeVar,
    Tuple,
)
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


class Cache(Protocol):
    """Protocol for a cache interface."""

    def get(self, *args: Any, **kwargs: Any) -> Optional[Any]: ...

    def set(self, *args: Any, **kwargs: Any) -> None: ...

    def clear(self, *args: Any, **kwargs: Any) -> None: ...

    def delete(self, *args: Any, **kwargs: Any) -> None: ...

    def keys(self, *args: Any, **kwargs: Any) -> Iterator[str]: ...

    def values(self, *args: Any, **kwargs: Any) -> Iterator[Any]: ...

    def items(self, *args: Any, **kwargs: Any) -> Iterator[tuple[str, Any]]: ...

    def __contains__(self, key: str, /) -> bool:
        """Return whether a key is present in the cache"""
        ...

    def __len__(self) -> int:
        """
        Returns the number of items in the cache.
        """
        ...

    def __iter__(self) -> Iterator[str]:
        """
        Returns an iterator over the keys in the cache.
        """
        ...

    def __getitem__(self, key: str, /) -> Any:
        """
        Retrieves an item from the cache by its key.
        """
        ...

    def __setitem__(self, key: str, value: Any, /) -> None:
        """
        Sets an item in the cache with the specified key and value.
        """
        ...

    def __delitem__(self, key: str, /) -> None:
        """
        Deletes an item from the cache by its key.
        """
        ...


class AsyncCache(Protocol):
    """Protocol for an asynchronous cache interface."""

    async def get(self, *args: Any, **kwargs: Any) -> Optional[Any]: ...

    async def set(self, *args: Any, **kwargs: Any) -> None: ...

    async def clear(self, *args: Any, **kwargs: Any) -> None: ...

    async def delete(self, *args: Any, **kwargs: Any) -> None: ...

    def keys(self, *args: Any, **kwargs: Any) -> AsyncIterator[str]: ...

    def values(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]: ...

    def items(self, *args: Any, **kwargs: Any) -> AsyncIterator[tuple[str, Any]]: ...

    def __contains__(self, key: str, /) -> bool:
        """Return whether a key is present in the cache"""
        ...

    def __len__(self) -> int:
        """
        Returns the number of items in the cache.
        """
        ...

    def __iter__(self) -> Iterator[str]:
        """
        Returns an iterator over the keys in the cache.
        """
        ...

    async def __aiter__(self) -> AsyncIterator[str]:
        """
        Returns an async iterator over the keys in the cache.
        """
        ...


CacheT = TypeVar("CacheT", bound=Cache)
AsyncCacheT = TypeVar("AsyncCacheT", bound=AsyncCache)


def AsyncCacheFactory(
    cache_type: Type[AsyncCacheT], *args: Any, **kwargs: Any
) -> Callable[[], AsyncCacheT]:
    """
    Factory function to create a asynchronous cache instance of the specified type.

    :param cache_type: The type of cache to create (must implement ``AsyncCache`` protocol)
    :param args: Positional arguments to pass to the cache constructor
    :param kwargs: Keyword arguments to pass to the cache constructor
    :return: A callable that returns an instance of the specified cache type
    """

    def factory() -> AsyncCacheT:
        return cache_type(*args, **kwargs)

    return factory


def CacheFactory(
    cache_type: Type[CacheT], *args: Any, **kwargs: Any
) -> Callable[[], CacheT]:
    """
    Factory function to create a cache instance of the specified type.

    :param cache_type: The type of cache to create (must implement ``Cache`` protocol)
    :param args: Positional arguments to pass to the cache constructor
    :param kwargs: Keyword arguments to pass to the cache constructor
    :return: A callable that returns an instance of the specified cache type
    """

    def factory() -> CacheT:
        return cache_type(*args, **kwargs)

    return factory


def json_encode(value: Any) -> str:  # type: ignore[no-redef]
    """
    Encodes a value to a JSON string.
    """
    return json.dumps(value, indent=2, ensure_ascii=False)


def json_decode(value: Union[str, bytes, bytearray]) -> Any:  # type: ignore[no-redef]
    """
    Decodes a JSON string to a Python object.
    """
    return json.loads(value)


try:
    import orjson

    def json_encode(value: Any) -> bytes:
        """
        Encodes a value to a JSON string.
        """
        return orjson.dumps(
            value,
            option=orjson.OPT_SERIALIZE_NUMPY
            | orjson.OPT_INDENT_2
            | orjson.OPT_NON_STR_KEYS
            | orjson.OPT_SERIALIZE_DATACLASS
            | orjson.OPT_SERIALIZE_UUID,
        )

    def json_decode(value: Union[str, bytes, bytearray]) -> Any:
        """
        Decodes a JSON string to a Python object.
        """
        return orjson.loads(value)

except ImportError:
    pass


def build_cache_key(*args: Any, **kwargs: Any) -> str:
    """Builds a cache key using the provided parameters."""
    key_parts = [str(arg) for arg in args]
    key_parts.extend(f"{k}={v}" for k, v in kwargs.items())
    if not key_parts:
        return "*"
    key_parts.sort()  # Sort to ensure consistent ordering
    return hashlib.md5(":".join(key_parts).encode()).hexdigest()


ExpiresAfter = Union[int, datetime.timedelta]


@runtime_checkable
class CacheBackend(Protocol):
    """
    Protocol for cache backends.

    Defines the methods required for cache operations.
    """

    def set(
        self,
        key: str,
        value: Any,
        expire_after: Optional[ExpiresAfter],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        Sets a value in the cache with an expiration time.

        :param key: The cache key
        :param value: The value to cache
        :param expire_after: Expiration time in seconds
        :param args: Additional positional arguments for the backend
        :param kwargs: Additional keyword arguments for the backend
        """
        ...

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieves a value from the cache by its key.

        :param key: The cache key
        :return: The cached value or None if not found
        """
        ...

    def delete(self, key: str) -> None:
        """Deletes a key from the cache."""
        ...

    def clear(self, *args: Any, **kwargs: Any) -> None:
        """Clears the cache."""
        ...


@runtime_checkable
class AsyncCacheBackend(Protocol):
    """
    Protocol for asynchronous cache backends.

    Defines the methods required for cache operations.
    """

    async def set(
        self,
        key: str,
        value: Any,
        expire_after: Optional[ExpiresAfter],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        Sets a value in the cache with an expiration time.

        :param key: The cache key
        :param value: The value to cache
        :param expire_after: Expiration time in seconds
        :param args: Additional positional arguments for the backend
        :param kwargs: Additional keyword arguments for the backend
        """
        ...

    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieves a value from the cache by its key.

        :param key: The cache key
        :return: The cached value or None if not found
        """
        ...

    async def delete(self, key: str) -> None:
        """Deletes a key from the cache."""
        ...

    async def clear(self, *args: Any, **kwargs: Any) -> None:
        """Clears the cache."""
        ...


CacheBackendT = TypeVar("CacheBackendT", bound=CacheBackend)
AsyncCacheBackendT = TypeVar("AsyncCacheBackendT", bound=AsyncCacheBackend)


@dataclass
class CacheManager(Generic[CacheBackendT]):
    """Manages cache operations using a specified backend."""

    backend: CacheBackendT
    """The cache backend to use for storage operations."""
    namespace: Optional[str] = None
    """Optional namespace(prefix) for cache keys to avoid collisions or to namespace keys."""
    max_size: Optional[int] = None
    """Maximum number of keys to store in the cache manager. If set, the manager behaves like a LRU cache."""
    _keys: Set[str] = field(default_factory=set, init=False, repr=False)
    """A set to store cache keys for tracking and management."""

    def get_key(self, namespace: str, *args: Any, **kwargs: Any) -> str:
        """
        Generates a cache key based on the namespace and provided arguments.

        :param namespace: The namespace to use for the cache key
        :param args: Positional arguments to include in the cache key
        :param kwargs: Keyword arguments to include in the cache key
        """
        if not namespace:
            raise ValueError("Namespace must be provided for cache key generation.")

        key = f"{namespace}:{build_cache_key(*args, **kwargs)}"
        if self.namespace is not None:
            key = f"{self.namespace}:{key}"
        return key

    def set(
        self,
        key,
        value: Any,
        expire_after: Optional[ExpiresAfter] = None,
        *args,
        **kwargs,
    ) -> None:
        """
        Sets a value in the cache with an expiration time.

        :param key: The cache key
        :param value: The value to cache
        :param expire_after: Expiration time in seconds
        :param args: Additional positional arguments for the backend
        :param kwargs: Additional keyword arguments for the backend
        """
        if self.max_size is not None:
            if key in self._keys:
                # If the key already exists, remove it from its current position
                self._keys.remove(key)
            elif len(self._keys) >= self.max_size:
                # If the cache is full, remove the oldest key
                oldest_key = next(iter(self._keys))
                self.backend.delete(oldest_key)
        self._keys.add(key)
        self.backend.set(key, value, expire_after, *args, **kwargs)

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieves a value from the cache by its key.

        :param key: The cache key
        :return: The cached value or None if not found
        """
        return self.backend.get(key)

    def delete(self, key: str) -> None:
        """
        Deletes a key from the cache.

        :param key: The cache key
        """
        if key in self._keys:
            self._keys.remove(key)
            self.backend.delete(key)
        return None

    def clear(self, *args: Any, **kwargs: Any) -> None:
        """
        Clears the cache.

        :param args: Positional arguments for the backend
        :param kwargs: Keyword arguments for the backend
        """
        self.backend.clear(*args, **kwargs)

    def keys(self) -> Iterator[str]:
        """
        Returns an iterator of all keys currently in the cache.

        :return: An iterator of cache keys
        """
        return iter(self._keys)

    def values(self) -> Iterator[Any]:
        """
        Returns an iterator of all values currently in the cache.

        :return: An iterator of cached values
        """
        return (self.backend.get(key) for key in self._keys)

    def items(self) -> Iterator[tuple[str, Any]]:
        """
        Returns an iterator of all key-value pairs currently in the cache.

        :return: An iterator of tuples (key, value)
        """
        return ((key, self.backend.get(key)) for key in self._keys)

    def __getitem__(self, key: str, /) -> Any:
        """
        Retrieves a value from the cache using the key.

        :param key: The cache key
        :return: The cached value or None if not found
        """
        return self.backend.get(key)

    def __setitem__(self, key: str, value: Any, /) -> None:
        """
        Sets a value in the cache using the key.

        :param key: The cache key
        :param value: The value to cache
        """
        self.backend.set(key, value, None)

    def __delitem__(self, key: str, /) -> None:
        """
        Deletes a value from the cache using the key.

        :param key: The cache key
        """
        self.backend.delete(key)

    def __contains__(self, key: str, /) -> bool:
        """
        Checks if a key is present in the cache.

        :param key: The cache key
        :return: True if the key exists, False otherwise
        """
        return key in self._keys

    def __len__(self) -> int:
        """
        Returns the number of keys currently in the cache.

        :return: The number of keys in the cache
        """
        return len(self._keys)

    def __iter__(self) -> Iterator[str]:
        """
        Returns an iterator over the keys in the cache.

        :return: An iterator over the cache keys
        """
        return iter(self._keys)


@dataclass
class AsyncCacheManager(Generic[AsyncCacheBackendT]):
    """Manages cache operations using a specified backend."""

    backend: AsyncCacheBackendT
    """The cache backend to use for storage operations."""
    namespace: Optional[str] = None
    """Optional namespace(prefix) for cache keys to avoid collisions or to namespace keys."""
    max_size: Optional[int] = None
    """Maximum number of keys to store in the cache manager. If set, the manager behaves like a LRU cache."""
    _keys: Set[str] = field(default_factory=set, init=False, repr=False)
    """A set to store cache keys for tracking and management."""

    def get_key(self, namespace: str, *args: Any, **kwargs: Any) -> str:
        """
        Generates a cache key based on the namespace and provided arguments.

        :param namespace: The namespace to use for the cache key
        :param args: Positional arguments to include in the cache key
        :param kwargs: Keyword arguments to include in the cache key
        """
        if not namespace:
            raise ValueError("Namespace must be provided for cache key generation.")

        key = f"{namespace}:{build_cache_key(*args, **kwargs)}"
        if self.namespace is not None:
            key = f"{self.namespace}:{key}"
        return key

    async def set(
        self,
        key,
        value: Any,
        expire_after: Optional[ExpiresAfter] = None,
        *args,
        **kwargs,
    ) -> None:
        """
        Sets a value in the cache with an expiration time.

        :param key: The cache key
        :param value: The value to cache
        :param expire_after: Expiration time in seconds
        :param args: Additional positional arguments for the backend
        :param kwargs: Additional keyword arguments for the backend
        """
        if self.max_size is not None:
            if key in self._keys:
                # If the key already exists, remove it from its current position
                self._keys.remove(key)
            elif len(self._keys) >= self.max_size:
                # If the cache is full, remove the oldest key
                oldest_key = next(iter(self._keys))
                await self.backend.delete(oldest_key)
        self._keys.add(key)
        await self.backend.set(key, value, expire_after, *args, **kwargs)

    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieves a value from the cache by its key.

        :param key: The cache key
        :return: The cached value or None if not found
        """
        return await self.backend.get(key)

    async def delete(self, key: str) -> None:
        """
        Deletes a key from the cache.

        :param key: The cache key
        """
        if key in self._keys:
            self._keys.remove(key)
        await self.backend.delete(key)
        return None

    async def clear(self, *args: Any, **kwargs: Any) -> None:
        """
        Clears the cache.

        :param args: Positional arguments for the backend
        :param kwargs: Keyword arguments for the backend
        """
        await self.backend.clear(*args, **kwargs)

    async def keys(self) -> AsyncIterator[str]:
        """
        Returns an iterator of all keys currently in the cache.

        :return: An iterator of cache keys
        """
        for key in self._keys:
            yield key

    async def values(self) -> AsyncIterator[Any]:
        """
        Returns an iterator of all values currently in the cache.

        :return: An iterator of cached values
        """
        for key in self._keys:
            yield await self.backend.get(key)

    async def items(self) -> AsyncIterator[Tuple[str, Any]]:
        """
        Returns an iterator of all key-value pairs currently in the cache.

        :return: An iterator of tuples (key, value)
        """
        for key in self._keys:
            yield (key, await self.backend.get(key))

    def __contains__(self, key: str, /) -> bool:
        """
        Checks if a key is present in the cache.

        :param key: The cache key
        :return: True if the key exists, False otherwise
        """
        return key in self._keys

    def __len__(self) -> int:
        """
        Returns the number of keys currently in the cache.

        :return: The number of keys in the cache
        """
        return len(self._keys)

    def __iter__(self) -> Iterator[str]:
        """
        Returns an iterator over the keys in the cache.

        :return: An iterator over the cache keys
        """
        return iter(self._keys)

    async def __aiter__(self) -> AsyncIterator[str]:
        """
        Returns an asynchronous iterator over the keys in the cache.

        :return: An asynchronous iterator over the cache keys
        """
        return self.keys()


@dataclass
class InMemoryBackend:
    """Implements the `CacheBackend` protocol using an in-memory dictionary as the storage backend."""

    _cache: Dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    """Cache storage using an in-memory dictionary."""

    def set(
        self,
        key: str,
        value: Any,
        expire_after: Optional[ExpiresAfter] = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        Sets a value in the in-memory cache.

        :param key: The cache key
        :param value: The value to cache
        :param expire_after: Expiration time (not implemented for in-memory)
        :param args: Additional positional arguments (not used)
        :param kwargs: Additional keyword arguments (not used)
        """
        self._cache[key] = value

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieves a value from the in-memory cache by its key.

        :param key: The cache key
        :return: The cached value or None if not found
        """
        return self._cache.get(key)

    def delete(self, key: str) -> None:
        """
        Deletes a key from the in-memory cache.

        :param key: The cache key to delete
        """
        self._cache.pop(key, None)

    def clear(self) -> None:
        """
        Clears the in-memory cache.
        """
        self._cache.clear()


@dataclass
class InMemoryAsyncBackend:
    """
    Implements the ``AsyncCacheBackend`` protocol using an in-memory dictionary as the storage backend.

    This uses a simple dictionary to store key-value pairs in memory and the `InMemoryBackend`
    should be preferred as the methods do not do any awaitable operations.
    """

    _cache: Dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    """Cache storage using an in-memory dictionary."""

    async def set(
        self,
        key: str,
        value: Any,
        expire_after: Optional[ExpiresAfter] = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        Sets a value in the in-memory cache.

        :param key: The cache key
        :param value: The value to cache
        :param expire_after: Expiration time (not implemented for in-memory)
        :param args: Additional positional arguments (not used)
        :param kwargs: Additional keyword arguments (not used)
        """
        self._cache[key] = value

    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieves a value from the in-memory cache by its key.

        :param key: The cache key
        :return: The cached value or None if not found
        """
        return self._cache.get(key)

    async def delete(self, key: str) -> None:
        """
        Deletes a key from the in-memory cache.

        :param key: The cache key to delete
        """
        self._cache.pop(key, None)

    async def clear(self) -> None:
        """
        Clears the in-memory cache.
        """
        self._cache.clear()


class RedisCacheBackend:  # type: ignore[no-redef]
    """
    Placeholder for RedisCacheBackend when redis is not installed.
    This class will raise an ImportError if used.
    """

    def __init__(self, *args, **kwargs):
        raise ImportError("RedisCacheBackend requires the 'redis' package.")

    def __init_subclass__(cls) -> None:
        raise ImportError("RedisCacheBackend requires the 'redis' package.")


class RedisAsyncCacheBackend:  # type: ignore[no-redef]
    """
    Placeholder for RedisAsyncCacheBackend when redis is not installed.
    This class will raise an ImportError if used.
    """

    def __init__(self, *args, **kwargs):
        raise ImportError("RedisAsyncCacheBackend requires the 'redis' package.")

    def __init_subclass__(cls) -> None:
        raise ImportError("RedisAsyncCacheBackend requires the 'redis' package.")


try:
    import redis
    import redis.asyncio

    @dataclass
    class RedisCacheBackend:
        """
        Implements the `CacheBackend` protocol using Redis as the storage backend.
        """

        client: redis.Redis
        """Redis client instance for interacting with the Redis server. Ensure `decode_responses` is set to `False`."""
        id: str
        """
        Backend identifier to avoid key collisions. This ensures that only keys
        set by this instance are affected by operations like clear or delete.
        """

        def set(
            self,
            key: str,
            value: Any,
            expire_after: Optional[ExpiresAfter] = None,
            *args: Any,
            **kwargs: Any,
        ) -> None:
            unique_key = f"{self.id}:{key}"
            encoded_value = json_encode(value)
            kwargs.pop(
                "ex", None
            )  # Remove 'ex' if it exists in kwargs to avoid conflicts
            self.client.set(unique_key, encoded_value, ex=expire_after, *args, **kwargs)

        def get(self, key: str) -> Optional[Any]:
            unique_key = f"{self.id}:{key}"
            cached_value = self.client.get(unique_key)
            if cached_value is None:
                return None
            if isinstance(cached_value, bytes):
                return json_decode(cached_value)
            return cached_value

        def delete(self, key: str) -> None:
            unique_key = f"{self.id}:{key}"
            self.client.delete(unique_key)

        def clear(self, pattern: str = "*") -> None:
            unique_pattern = f"{self.id}:{pattern}"
            for key in self.client.scan_iter(unique_pattern):
                self.client.delete(key)

    @dataclass
    class RedisAsyncCacheBackend:
        """
        Implements the `AsyncCacheBackend` protocol using Redis as the storage backend.
        """

        client: redis.asyncio.Redis
        """Redis client instance for interacting with the Redis server. Ensure `decode_responses` is set to `False`."""
        id: str
        """
        Backend identifier to avoid key collisions. This ensures that only keys
        set by this instance are affected by operations like clear or delete.
        """

        async def set(
            self,
            key: str,
            value: Any,
            expire_after: Optional[ExpiresAfter] = None,
            *args: Any,
            **kwargs: Any,
        ) -> None:
            unique_key = f"{self.id}:{key}"
            encoded_value = json_encode(value)
            kwargs.pop(
                "ex", None
            )  # Remove 'ex' if it exists in kwargs to avoid conflicts
            await self.client.set(
                unique_key, encoded_value, ex=expire_after, *args, **kwargs
            )

        async def get(self, key: str) -> Optional[Any]:
            unique_key = f"{self.id}:{key}"
            cached_value = await self.client.get(unique_key)
            if cached_value is None:
                return None
            if isinstance(cached_value, bytes):
                return json_decode(cached_value)
            return cached_value

        async def delete(self, key: str) -> None:
            unique_key = f"{self.id}:{key}"
            await self.client.delete(unique_key)

        async def clear(self, pattern: str = "*") -> None:
            unique_pattern = f"{self.id}:{pattern}"
            async for key in self.client.scan_iter(unique_pattern):
                await self.client.delete(key)

except ImportError:
    pass
