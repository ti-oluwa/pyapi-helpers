import typing
from typing_extensions import ParamSpec
from itertools import islice
import functools


P = ParamSpec("P")
R = typing.TypeVar("R")
T = typing.TypeVar("T")


def batched(
    i: typing.Union[typing.Iterator[T], typing.Iterable[T]], /, batch_size: int
):
    """
    Create batches of size n from the given iterable.

    :param iterable: The iterable to split into batches.
    :param batch_size: The batch size.
    :yield: Batches of the iterable as lists.
    """
    iterator = iter(i)
    while batch := list(islice(iterator, batch_size)):
        yield batch


class _async_batched(typing.AsyncIterator[typing.Sequence[typing.Union[T, R]]]):
    """
    Implements an asynchronous batcher that splits an async iterable into batches.

    The batcher can optionally apply a converter function to each item in the batch.

    Example:
    ```python

    async def converter(item):
        return item * 2

    async def async_iter():
        for i in range(10):
            yield i

    batcher = _async_batched(async_iter(), 3, converter)
    async for batch in batcher:
        print(batch)

    # Or;
    await anext(batcher) # [1, 2, 3]
    await anext(batcher) # [4, 5, 6]
    ```
    """

    def __init__(
        self,
        async_iter: typing.AsyncIterable[T],
        batch_size: int,
        converter: typing.Optional[typing.Callable[[T], typing.Awaitable[R]]] = None,
    ) -> None:
        """
        Initialize the batcher.

        :param async_iter: The async iterable to split into batches.
        :param batch_size: The batch size.
        :param converter: An optional converter function to apply to each item in the batch.
        """
        self.async_iter = async_iter
        self.batch_size = batch_size
        self.converter = converter
        self._batcher = None

    async def __aiter__(
        self,
    ) -> typing.AsyncIterator[typing.Sequence[typing.Union[T, R]]]:
        """Initialize and return batches."""
        self._batcher = self._create_batcher(
            self.async_iter, self.batch_size, self.converter
        )
        try:
            async for batch in self._batcher:
                yield batch
        finally:
            await self.aclose()

    async def __anext__(self) -> typing.Sequence[typing.Union[T, R]]:
        """Return the next batch."""
        if not self._batcher:
            self._batcher = self._create_batcher(
                self.async_iter, self.batch_size, self.converter
            )
        return await self._batcher.__anext__()

    @typing.overload
    def _create_batcher(
        self,
        async_iter: typing.AsyncIterable[T],
        batch_size: int,
        converter: typing.Callable[[T], typing.Awaitable[R]],
    ) -> typing.AsyncGenerator[typing.Sequence[R], None]: ...

    @typing.overload
    def _create_batcher(
        self,
        async_iter: typing.AsyncIterable[T],
        batch_size: int,
        converter: None,
    ) -> typing.AsyncGenerator[typing.Sequence[T], None]: ...

    def _create_batcher(
        self,
        async_iter: typing.AsyncIterable[T],
        batch_size: int,
        converter: typing.Optional[typing.Callable[[T], typing.Awaitable[R]]],
    ) -> typing.AsyncGenerator[typing.Sequence[typing.Union[T, R]], None]:
        """Factory function that creates the appropriate batch generator based on the presence of a converter."""

        if batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")

        if not converter:

            async def batch_without_converter() -> typing.AsyncGenerator[
                typing.Sequence[T], None
            ]:
                batch: typing.Sequence[T] = []
                async for item in async_iter:
                    batch.append(item)
                    if len(batch) == batch_size:
                        yield batch
                        batch = []
                if batch:
                    yield batch

            return batch_without_converter()

        async def batch_with_converter() -> typing.AsyncGenerator[
            typing.Sequence[R], None
        ]:
            batch: typing.Sequence[R] = []
            async for item in async_iter:
                batch.append(await converter(item))  # type: ignore
                if len(batch) == batch_size:
                    yield batch
                    batch = []
            if batch:
                yield batch

        return batch_with_converter()

    async def aclose(self):
        """Properly close both the generator and async iterable."""
        try:
            if self._batcher:
                await self._batcher.aclose()
        except RuntimeError:
            pass

        if hasattr(self.async_iter, "aclose"):
            try:
                await self.async_iter.aclose()  # type: ignore
            except RuntimeError:
                pass


@typing.overload
def async_batched(
    async_iter: typing.AsyncIterable[T],
    batch_size: int,
    converter: typing.Callable[[T], typing.Awaitable[R]],
) -> typing.AsyncIterator[typing.Sequence[R]]: ...


@typing.overload
def async_batched(
    async_iter: typing.AsyncIterable[T],
    batch_size: int,
    converter: None = None,
) -> typing.AsyncIterator[typing.Sequence[T]]: ...


async def async_batched(
    async_iter: typing.AsyncIterable[T],
    batch_size: int,
    converter: typing.Optional[typing.Callable[[T], typing.Awaitable[R]]] = None,
) -> typing.AsyncIterator[typing.Sequence[typing.Union[T, R]]]:
    """
    Create batches of size batch_size from the given async iterable.

    :param async_iter: The async iterable to split into batches.
    :param batch_size: The batch size.
    :yield: Batches of the async iterable as lists.
    """
    batched = _async_batched(async_iter, batch_size, converter)
    try:
        async for batch in batched:
            yield batch
    finally:
        await batched.aclose()


def shift(i: typing.Sequence[T], /, *, step: int = 1) -> typing.Sequence[T]:
    """
    Shifts the elements of an iterable by the given step

    Use a negative step to shift the elements in the backwards direction.
    """
    return [*i[-step:], *i[:-step]]


@typing.overload
def suppress_once_yielded(
    async_iter_func: typing.Callable[P, typing.AsyncIterator[T]],
    *,
    exc_type: typing.Optional[
        typing.Union[typing.Type[Exception], typing.Tuple[typing.Type[Exception]]]
    ] = None,
) -> typing.Callable[P, typing.AsyncIterator[T]]: ...


@typing.overload
def suppress_once_yielded(
    async_iter_func: None = None,
    *,
    exc_type: typing.Optional[
        typing.Union[typing.Type[Exception], typing.Tuple[typing.Type[Exception]]]
    ] = None,
) -> typing.Callable[
    [typing.Callable[P, typing.AsyncIterator[T]]],
    typing.Callable[P, typing.AsyncIterator[T]],
]: ...


def suppress_once_yielded(
    async_iter_func: typing.Optional[
        typing.Callable[P, typing.AsyncIterator[T]]
    ] = None,
    *,
    exc_type: typing.Optional[
        typing.Union[typing.Type[Exception], typing.Tuple[typing.Type[Exception]]]
    ] = None,
) -> typing.Union[
    typing.Callable[
        [typing.Callable[P, typing.AsyncIterator[T]]],
        typing.Callable[P, typing.AsyncIterator[T]],
    ],
    typing.Callable[P, typing.AsyncIterator[T]],
]:
    """
    Decorator to suppress exceptions raised in the middle of an iteration of an async iterator.

    If an exception is raised in the middle of an iteration, the exception is caught and the iterator is stopped.
    Else, the exception is allowed to propagate.

    :param async_iter_func: The async iterator function to decorate.
    :param exc_type: The exception type to catch and suppress. If None, all exceptions are caught.
    :return: The decorated async iterator function.
    """

    def decorator(
        async_iter_func: typing.Callable[P, typing.AsyncIterator[T]],
    ) -> typing.Callable[P, typing.AsyncIterator[T]]:
        @functools.wraps(async_iter_func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> typing.AsyncIterator[T]:
            async_iter = async_iter_func(*args, **kwargs)
            yielded = 0
            try:
                async for value in async_iter:
                    yielded += 1
                    yield value

            except exc_type or Exception:
                # If no values have been yielded yet then just let the exception propagate
                if yielded == 0:
                    raise

                # Else, suppress the exception and stop the iterator
                if hasattr(async_iter, "aclose"):
                    try:
                        await async_iter.aclose()  # type: ignore
                    except RuntimeError:
                        pass
                return

        return wrapper

    if async_iter_func:
        return decorator(async_iter_func)
    return decorator
