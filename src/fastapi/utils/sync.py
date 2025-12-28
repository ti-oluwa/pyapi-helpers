import asyncio
import functools
from starlette.concurrency import run_in_threadpool
import uvloop

from src.types import Function, CoroutineFunction, P, R


def sync_to_async(func: Function[P, R]) -> CoroutineFunction[P, R]:
    """
    Adapts a synchronous function to an asynchronous function.

    Using starlette's `run_in_threadpool` to run the synchronous function in a threadpool.
    """

    @functools.wraps(func)
    async def _wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return await run_in_threadpool(func, *args, **kwargs)

    return _wrapper


def async_to_sync(func: CoroutineFunction[P, R]) -> Function[P, R]:
    """
    Adapts an asynchronous function to a synchronous function.

    This is useful for testing purposes.
    """

    @functools.wraps(func)
    def _wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(func(*args, **kwargs))

    return _wrapper
