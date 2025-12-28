import typing

try:
    from typing import ParamSpec, Self  # type: ignore[import]
except ImportError:
    from typing_extensions import ParamSpec, Self

import time
from contextlib import ContextDecorator
import cProfile
import pstats
import io


P = ParamSpec("P")
R = typing.TypeVar("R")


class Timer(ContextDecorator):
    """Context manager/decorator to measure the time taken to execute a function or block of code."""

    def __init__(
        self,
        identifier: typing.Optional[str] = None,
        output: typing.Optional[typing.Callable] = None,
        use_perf_counter: bool = True,
    ) -> None:
        """
        Create a new instance of the Timer class.

        :param identifier: A unique identifier for the function or block.
        :param output: The output/writer function to use. This defaults to `print`.
        :param use_perf_counter: If True, use time.perf_counter() for higher precision timing.
        """
        self.identifier = identifier
        self.output = output or print
        self.timer_func = time.perf_counter if use_perf_counter else time.monotonic
        self.start = None
        self.end = None

    def __enter__(self) -> Self:
        self.start = self.timer_func()
        return self

    def __exit__(self, *exc) -> None:
        if self.start:
            self.end = self.timer_func()
            time_taken = self.end - self.start
            if self.identifier:
                self.output(f"'{self.identifier}' executed in {time_taken} seconds.\n")
            else:
                self.output(f"Execution took {time_taken} seconds.\n")

    def __call__(self, func: typing.Callable[P, R]) -> typing.Callable[P, R]:
        self.identifier = self.identifier or func.__name__
        return super().__call__(func)


@typing.overload
def timeit(
    identifier: str,
    *,
    output: typing.Optional[typing.Callable] = None,
    use_perf_counter: bool = True,
) -> Timer: ...


@typing.overload
def timeit(
    identifier: str,
    func: typing.Optional[typing.Callable[P, R]] = None,
    *,
    output: typing.Optional[typing.Callable] = None,
    use_perf_counter: bool = True,
) -> typing.Union[Timer, typing.Callable[P, R]]: ...


@typing.overload
def timeit(
    func: typing.Optional[typing.Callable[P, R]] = None,
    *,
    identifier: typing.Optional[str] = None,
    output: typing.Optional[typing.Callable] = None,
    use_perf_counter: bool = True,
) -> typing.Union[Timer, typing.Callable[P, R]]: ...


def timeit(  # type: ignore
    func: typing.Optional[typing.Callable[P, R]] = None,
    identifier: typing.Optional[str] = None,
    output: typing.Optional[typing.Callable] = None,
    use_perf_counter: bool = True,
) -> typing.Union[Timer, typing.Callable[P, R]]:
    """
    Measure the time taken to execute a function or block of code.

    :param func: The function to be measured.
    :param identifier: A unique identifier for the function or block.
    :param output: The output/writer function to use. This defaults to `print`.
    :param use_perf_counter: If True, use time.perf_counter() for higher precision timing.

    Example:
    ```python
    # Usage as a context manager
    with timeit("Block identifier"):
        # Code block

    # Usage as a decorator
    @timeit
    def my_function():
        # Function code
    ```
    """
    if isinstance(func, str):
        timer = Timer(
            identifier=func,
            output=output,
            use_perf_counter=use_perf_counter,
        )
        if identifier:
            return timer(identifier)  # type: ignore
        return timer

    timer = Timer(
        identifier=identifier,
        output=output,
        use_perf_counter=use_perf_counter,
    )
    if func:
        return timer(func)
    return timer


StatsData: typing.TypeAlias = typing.Dict[
    typing.Tuple[str, int, str],
    typing.Tuple[int, int, float, float, typing.List[typing.Tuple[str, int]]],
]
StatOutput: typing.TypeAlias = typing.Union[
    typing.Callable[
        [
            typing.Optional[str],
            StatsData,
        ],
        None,
    ],
    typing.Literal["rich", "simple"],
]


def rich_output(
    identifier: typing.Optional[str],
    stats_data: StatsData,
) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(
        title=f"Profiling Stats: {identifier or 'Code Block'}",
        show_lines=True,
        expand=True,
        border_style="blue",
    )
    table.add_column("Function", justify="left", style="cyan", overflow="fold")
    table.add_column("Total Calls", justify="right", style="magenta")
    table.add_column("Primitive Calls", justify="right", style="magenta")
    table.add_column("Total Time (s)", justify="right", style="green")
    table.add_column("Time/Call (Total)", justify="right", style="green")
    table.add_column("Cumulative Time (s)", justify="right", style="yellow")
    table.add_column("Time/Call (Cumulative)", justify="right", style="yellow")
    table.add_column(
        "File:Line(Function)", justify="left", style="white", overflow="fold"
    )

    for func, (cc, nc, tt, ct, callers) in stats_data.items():
        file_line_func = f"{func[0]}:{func[1]}({func[2]})"
        table.add_row(
            func[2],  # Function name
            str(cc),  # Total calls
            str(nc),  # Primitive calls
            f"{tt:.8f}",  # Total time
            f"{tt / nc if nc else 0:.8f}",  # Per call (total)
            f"{ct:.8f}",  # Cumulative time
            f"{ct / cc if cc else 0:.8f}",  # Per call (cumulative)
            file_line_func,  # File:Line(Function)
        )

    console.print(table)


def simple_output(
    identifier: typing.Optional[str],
    stats_data: StatsData,
    timeunit: float = 1.0,
) -> None:
    print(f"\n=== Profiling Stats: {identifier or 'Code Block'} ===\n")

    headers = [
        "Function Name",
        "Total Calls",
        "Primitive Calls",
        "Total Time (s)",
        "Time/Call (Total)",
        "Cumulative Time (s)",
        "Time/Call (Cumulative)",
        "File:Line",
    ]

    col_format = "{:<30} {:>12} {:>16} {:>16} {:>20} {:>22} {:>26}  {:<}"
    print(col_format.format(*headers))
    print("-" * 140)

    for func, (cc, nc, tt, ct, callers) in stats_data.items():
        tt *= timeunit
        ct *= timeunit
        per_call_tt = tt / nc if nc else 0.0
        per_call_ct = ct / cc if cc else 0.0

        print(
            col_format.format(
                func[2][:30],  # Function name
                cc,
                nc,
                f"{tt:.6f}",
                f"{per_call_tt:.6f}",
                f"{ct:.6f}",
                f"{per_call_ct:.6f}",
                f"{func[0]}:{func[1]}",
            )
        )
        print()


def get_stats_data(
    stats: pstats.Stats,
    timeunit: float = 0,
    max_rows: typing.Optional[int] = None,
) -> StatsData:
    """
    Extracts and formats profiling stats data from pstats.Stats.

    :param stats: The pstats.Stats object containing profiling data.
    :param timeunit: Multiplier for converting profiler timer measurements to seconds.
    :param max_rows: Maximum number of rows to display in the output.
    :return: A dictionary containing formatted profiling stats.
    """
    count = 0
    if max_rows:
        count = max_rows
    elif stats.total_calls > 0:  # type: ignore
        count = stats.total_calls  # type: ignore
    elif stats.total_calls == 0:  # type: ignore
        count = len(stats.stats)  # type: ignore
    if count == 0:
        raise ValueError("No profiling data available.")

    stats_data: StatsData = {}
    for func in stats.fcn_list:  # type: ignore
        if count <= 0:
            break
        if func in stats.stats:  # type: ignore
            filename, lineno, funcname = func
            cc, nc, tt, ct, callers = stats.stats[func]  # type: ignore
            if timeunit:
                tt *= timeunit or 1
                ct *= timeunit or 1
            stats_data[(filename, lineno, funcname)] = (cc, nc, tt, ct, callers)
            count -= 1
    return stats_data


class Profiler(ContextDecorator):
    """
    Context manager/decorator to profile a function or block of code using cProfile.
    """

    def __init__(
        self,
        identifier: typing.Optional[str] = None,
        output: StatOutput = "simple",
        timeunit: typing.Optional[float] = None,
        subcalls: bool = False,
        builtins: bool = False,
        max_rows: typing.Optional[int] = None,
    ) -> None:
        """
        Initialize the profiler.

        :param identifier: A unique identifier for the function or block.
        :param output: The output/writer function to use. This defaults to `print`.
        :param timeunit: Multiplier for converting profiler timer measurements to seconds.
                          For example, 1e-6 for microseconds.
        :param subcalls: If True, profile subcalls as well.
        :param builtins: If True, profile built-in functions.
        :param max_rows: Maximum number of rows to display in the output.
            If None, all rows will be displayed. Else, the top N rows will be shown.
        """
        self.identifier = identifier
        if callable(output):
            self.output = output
        elif output == "rich":
            self.output = rich_output
        elif output == "simple":
            self.output = simple_output
        else:
            raise ValueError("Output must be 'rich', 'simple', or a callable function.")

        self.timeunit = timeunit or 0
        self.subcalls = subcalls
        self.builtins = builtins
        self.profiler = cProfile.Profile(
            timeunit=self.timeunit,
            builtins=self.builtins,
            subcalls=self.subcalls,
        )
        self.max_rows = max_rows

    def __enter__(self) -> Self:
        self.profiler.enable(
            builtins=self.builtins,
            subcalls=self.subcalls,
        )
        return self

    def __exit__(self, *exc) -> None:
        self.profiler.disable()
        stream = io.StringIO()
        stats = pstats.Stats(self.profiler, stream=stream).sort_stats(
            pstats.SortKey.TIME, pstats.SortKey.CALLS
        )
        stats_data = get_stats_data(
            stats,
            timeunit=self.timeunit,
            max_rows=self.max_rows,
        )
        self.output(self.identifier, stats_data)
        self.profiler.clear()

    def __call__(self, func: typing.Callable[P, R]) -> typing.Callable[P, R]:
        self.identifier = self.identifier or func.__name__
        return super().__call__(func)


@typing.overload
def profileit(
    identifier: str,
    *,
    output: StatOutput = ...,
    timeunit: typing.Optional[float] = None,
    subcalls: bool = False,
    builtins: bool = False,
    max_rows: typing.Optional[int] = None,
) -> Profiler: ...


@typing.overload
def profileit(
    identifier: str,
    func: typing.Optional[typing.Callable[P, R]] = None,
    *,
    output: StatOutput = ...,
    timeunit: typing.Optional[float] = None,
    subcalls: bool = False,
    builtins: bool = False,
    max_rows: typing.Optional[int] = None,
) -> typing.Union[Profiler, typing.Callable[P, R]]: ...


@typing.overload
def profileit(
    func: typing.Optional[typing.Callable[P, R]] = None,
    *,
    identifier: typing.Optional[str] = None,
    output: StatOutput = ...,
    timeunit: typing.Optional[float] = None,
    subcalls: bool = False,
    builtins: bool = False,
    max_rows: typing.Optional[int] = None,
) -> typing.Union[Profiler, typing.Callable[P, R]]: ...


def profileit(  # type: ignore
    func: typing.Optional[typing.Callable[P, R]] = None,
    identifier: typing.Optional[str] = None,
    output: StatOutput = "simple",
    timeunit: typing.Optional[float] = None,
    subcalls: bool = False,
    builtins: bool = False,
    max_rows: typing.Optional[int] = None,
) -> typing.Union[Profiler, typing.Callable[P, R]]:
    """
    Profile a function or block of code. Can be used as a decorator or context manager,
    similar to 'timeit'.

    :param func: The function to be profiled.
    :param identifier: A unique identifier for the function or block.
    :param output: The output/writer function to use. This defaults to `print`.
    :param timeunit: Multiplier for converting profiler timer measurements to seconds.
    :param subcalls: If True, profile subcalls as well.
    :param builtins: If True, profile built-in functions.
    :return: A profiler instance or a decorated function.

    Example:
    ```python
    # Usage as a decorator
    @profileit
    def my_func():
        ...

    # Usage as a context manager
    with profileit("search-operation", max_count=20, output="rich"):
        ...
    ```
    """
    if isinstance(func, str):
        profiler = Profiler(
            identifier=func,
            output=output,
            timeunit=timeunit,
            builtins=builtins,
            subcalls=subcalls,
            max_rows=max_rows,
        )
        if identifier:
            return profiler(identifier)  # type: ignore
        return profiler

    profiler = Profiler(
        identifier=identifier,
        output=output,
        timeunit=timeunit,
        builtins=builtins,
        subcalls=subcalls,
        max_rows=max_rows,
    )
    if func:
        return profiler(func)
    return profiler
