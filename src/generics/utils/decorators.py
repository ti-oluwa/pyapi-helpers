import time
import typing
import asyncio
import functools

from src.logging import log_exception
from src.types import Function, CoroutineFunction, LoggerLike, P, R, T


Rco = typing.TypeVar("Rco", covariant=True)
BackOffFunction = typing.Callable[[int], float]


@typing.overload
def retry(  # type: ignore
    func: typing.Optional[Function[P, R]] = None,
    *,
    exc_type: typing.Optional[
        typing.Union[
            typing.Tuple[typing.Type[BaseException], ...], typing.Type[BaseException]
        ]
    ] = None,
    count: int = 1,
    backoff: typing.Optional[typing.Union[BackOffFunction, float]] = None,
    logger: typing.Optional[LoggerLike] = None,
) -> typing.Union[
    typing.Callable[[Function[P, R]], Function[P, R]], Function[P, R]
]: ...


@typing.overload
def retry(  # type: ignore
    func: typing.Optional[CoroutineFunction[P, R]] = None,
    *,
    exc_type: typing.Optional[
        typing.Union[
            typing.Tuple[typing.Type[BaseException], ...], typing.Type[BaseException]
        ]
    ] = None,
    count: int = 1,
    backoff: typing.Optional[typing.Union[BackOffFunction, float]] = None,
    logger: typing.Optional[LoggerLike] = None,
) -> typing.Union[
    typing.Callable[[CoroutineFunction[P, R]], CoroutineFunction[P, R]],
    CoroutineFunction[P, R],
]: ...


def retry(  # type: ignore
    func: typing.Optional[typing.Union[Function[P, R], CoroutineFunction[P, R]]] = None,
    *,
    exc_type: typing.Optional[
        typing.Union[
            typing.Tuple[typing.Type[BaseException], ...], typing.Type[BaseException]
        ]
    ] = None,
    count: int = 1,
    backoff: typing.Optional[typing.Union[BackOffFunction, float]] = None,
    logger: typing.Optional[LoggerLike] = None,
) -> typing.Union[
    typing.Callable[
        [typing.Union[Function[P, R], CoroutineFunction[P, R]]],
        typing.Union[Function[P, R], CoroutineFunction[P, R]],
    ],
    typing.Union[Function[P, R], CoroutineFunction[P, R]],
]:
    """
    Decorator to retry a function on a specified exception.
    The function will be retried for the specified number of times,
    after which the exception will be allowed to propagate.

    :param func: The function to decorate.
    :param exc_type: The target exception type(s) to catch.
    :param count: The number of times to retry the function.
    :param backoff: The backoff function or constant value to apply between retries.
    :return: The decorated function.
    """

    def decorator(
        func: typing.Union[Function[P, R], CoroutineFunction[P, R]],
    ) -> typing.Union[Function[P, R], CoroutineFunction[P, R]]:
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                for i in range(count):
                    try:
                        return await func(*args, **kwargs)
                    except exc_type or Exception as exc:
                        log_exception(exc, logger=logger)

                        if backoff is not None:
                            if callable(backoff):
                                await asyncio.sleep(backoff(i))
                            else:
                                await asyncio.sleep(backoff)
                        continue
                return await func(*args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            for _ in range(count):
                try:
                    return func(*args, **kwargs)  # type: ignore
                except exc_type or Exception as exc:
                    log_exception(exc, logger=logger)
                    if backoff is not None:
                        if callable(backoff):
                            time.sleep(backoff(_))
                        else:
                            time.sleep(backoff)
                    continue
            return func(*args, **kwargs)  # type: ignore

        return sync_wrapper

    if func is None:
        return decorator
    return decorator(func)


class classorinstancemethod(typing.Generic[T, P, Rco]):
    """
    Method decorator.

    Allows a method to be accessed from both the class and the instance.

    Example:
    ```python
    class Example:
        @classorinstancemethod
        def example(cls_or_self) -> int:
            return cls_or_self

    assert Example.example() == Example
    instance = Example()
    assert instance.example() == instance
    ```
    """

    __name__: str
    __qualname__: str
    __doc__: typing.Optional[str]

    @property
    def __func__(
        self,
    ) -> typing.Callable[typing.Concatenate[typing.Union[T, typing.Type[T]], P], Rco]:
        return self.func

    def __init__(
        self,
        func: typing.Callable[
            typing.Concatenate[typing.Union[T, typing.Type[T]], P], Rco
        ],
        /,
    ):
        self.func = func

    @typing.overload
    def __get__(
        self, instance: T, owner: typing.Optional[typing.Type[T]] = None, /
    ) -> typing.Callable[P, Rco]: ...

    @typing.overload
    def __get__(
        self, instance: None, owner: typing.Type[T], /
    ) -> typing.Callable[P, Rco]: ...

    def __get__(
        self,
        instance: typing.Optional[T],
        owner: typing.Optional[typing.Type[T]] = None,
        /,
    ) -> typing.Callable[P, Rco]:
        if instance is None:  # Accessed from the class
            return classmethod(self.func).__get__(None, owner)  # type: ignore
        # Accessed from the instance
        return functools.partial(self.func, instance)
