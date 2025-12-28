import asyncio
import logging
import typing
import functools
from contextvars import ContextVar
from typing_extensions import ParamSpec
from contextlib import asynccontextmanager


logger = logging.getLogger(__name__)
P = ParamSpec("P")
R = typing.TypeVar("R")


async def _all_tasks_except_current() -> typing.List[asyncio.Task]:
    """
    Returns all tasks except the current task.

    This can be used to cancel all tasks except the current task.
    """
    return [task for task in asyncio.all_tasks() if task != asyncio.current_task()]


async def _cancel_tasks(
    tasks: typing.Optional[typing.Sequence[asyncio.Task]] = None,
) -> None:
    """
    Helper function to cancel tasks and await them.

    This can be used to ensure all tasks are cancelled and awaited,
    on process exit.

    :param tasks: A list of tasks to cancel. If not provided, all tasks except the current task will be cancelled.
    :return: None
    """
    tasks = tasks or await _all_tasks_except_current()
    active_tasks = [t for t in tasks if not (t.done() or t.cancelled())]

    if not active_tasks:
        return

    # Gather all active tasks and cancel them
    gather = asyncio.gather(*active_tasks)
    gather.cancel()

    try:
        await asyncio.wait_for(gather, timeout=0.001)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass


@asynccontextmanager
async def cleanup_tasks_on_exit(
    tasks: typing.Optional[typing.List[asyncio.Task]] = None,
):
    """
    Cleanup all asyncio tasks on exit.

    :param tasks: A list of tasks to cancel. If not provided, all tasks except the current task will be cancelled.
    """
    try:
        yield
    finally:
        logger.debug("Cleaning up active tasks...")
        await _cancel_tasks(tasks)


def to_async(func: typing.Callable[P, R]) -> typing.Callable[P, typing.Awaitable[R]]:
    """
    Adapt a synchronous function to an asynchronous function.
    """

    @functools.wraps(func)
    async def async_executor(*args: P.args, **kwargs: P.kwargs) -> R:
        loop = asyncio.get_running_loop()

        def _run() -> R:
            return func(*args, **kwargs)

        return await loop.run_in_executor(None, _run)

    return async_executor


class RLock:
    """Re-entrant lock for asyncio"""

    __slots__ = ("_lock", "_owner", "_count")

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner = ContextVar[typing.Optional[asyncio.Task[typing.Any]]](
            "lock_owner", default=None
        )
        self._count = 0

    async def acquire(self):
        current_task = asyncio.current_task()

        if self._owner.get() == current_task:
            self._count += 1
            return True

        await self._lock.acquire()
        self._owner.set(current_task)
        self._count = 1

    def release(self) -> None:
        if self._owner.get() == asyncio.current_task():
            self._count -= 1
            if self._count == 0:
                self._owner.set(None)
                self._lock.release()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
