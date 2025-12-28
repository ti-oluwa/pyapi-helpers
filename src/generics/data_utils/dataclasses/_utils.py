import typing
import inspect
import textwrap
import types
from collections import defaultdict

from .exceptions import SerializationError

P = typing.ParamSpec("P")
R = typing.TypeVar("R")


class caseinsensitive(typing.NamedTuple):
    s: str

    def __hash__(self) -> int:
        return hash(self.s.upper())


iexact: typing.TypeAlias = caseinsensitive


def is_concrete_type(o: typing.Any, /) -> bool:
    """Check if an object is a concrete type."""
    if isinstance(o, typing._SpecialForm):
        return False
    return isinstance(o, type)


def is_valid_type(o: typing.Any, /) -> bool:
    """Check if an object is a valid type that can be used in an instance check."""
    if isinstance(o, tuple):
        return all(is_concrete_type(obj) for obj in o)
    return is_concrete_type(o)


def is_slotted_cls(cls: typing.Type[typing.Any], /) -> bool:
    """Check if a class has __slots__ defined."""
    return "__slots__" in cls.__dict__


def freeze_iterable(
    values: typing.Iterable[typing.Any],
) -> typing.Union[typing.FrozenSet[typing.Any], typing.Tuple[typing.Any, ...]]:
    """
    Make an iterable immutable.
    """
    try:
        return frozenset(values)
    except TypeError:
        return tuple(values)


def precompile_function(
    func: typing.Callable[P, R],
    *,
    transform_source: typing.Optional[typing.Callable[[str], str]] = None,
    globals_context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    func_getter: typing.Optional[
        typing.Callable[[str, typing.Dict[str, typing.Any]], typing.Any]
    ] = None,
) -> typing.Callable[P, R]:
    """
    Recompile a function or method using exec, with optional source transformation.

    :param func: The function to recompile.
    :param transform_source: Optional function to transform the source code.
    :param globals_context: Optional dictionary to use as the global context for exec.
    :param func_getter: Optional function to retrieve the compiled function from the local namespace.
    :return: The recompiled function.
    :raises ValueError: If the source code cannot be retrieved or compiled.
    """
    func_name = func.__name__

    try:
        # Attempt to retrieve the source code
        src = inspect.getsource(func)
    except (OSError, TypeError):
        try:
            # Fallback to getsourcelines
            src_lines, _ = inspect.getsourcelines(func)
            src = "".join(src_lines)
        except Exception as exc:
            raise ValueError(
                f"Cannot retrieve source for function: {func_name}. "
                f"Ensure the function is defined in an accessible source file."
            ) from exc

    src = textwrap.dedent(src)
    if transform_source:
        src = transform_source(src)

    globals_context = {**globals(), **(globals_context or {})}

    localns = {}
    try:
        exec(src, globals_context, localns)
    except Exception as exc:
        raise ValueError(
            f"Failed to compile or execute the source for function: {func_name}."
        ) from exc

    # Retrieve the recompiled function
    if func_getter:
        recompiled_func = func_getter(func_name, localns)
    else:
        recompiled_func = localns.get(func_name)

    if not callable(recompiled_func):
        raise ValueError(
            f"Recompiled function '{func_name}' is not callable. "
            f"Ensure the source code is valid."
        )
    return typing.cast(typing.Callable[P, R], recompiled_func)


def make_cell(value):
    """Create a real closure cell containing the value."""

    # This trick creates a cell object using an inner function.
    def inner():
        return value

    return inner.__closure__[0]  # type: ignore


def rebind_class_cell(
    func: typing.Callable[P, R], cls: typing.Type[typing.Any]
) -> typing.Union[typing.Callable[P, R], types.FunctionType]:
    """Rebind __class__ into the function's closure."""
    if func.__closure__ is None:
        # If there is no closure, return the function as is.
        return func

    # Get the current free variables of the function
    freevars = func.__code__.co_freevars

    # If '__class__' is not in the freevars, we shouldn't modify the closure
    if "__class__" not in freevars:
        return func

    # Recreate the closure with the new __class__ cell
    cells = list(func.__closure__)

    # Find the index of the `__class__` free variable
    index = freevars.index("__class__")

    # Replace the cell at the `__class__` index with a new one containing `cls`
    cells[index] = make_cell(cls)

    # Rebuild the function with the new closure
    new_func = types.FunctionType(
        func.__code__,
        func.__globals__,
        name=func.__name__,
        argdefs=func.__defaults__,
        closure=tuple(cells),  # Rebuilt closure with the updated `__class__`
    )
    new_func.__kwdefaults__ = func.__kwdefaults__  # Preserve keyword defaults
    return new_func


def precompile_method(
    method: typing.Callable[P, R],
    cls: typing.Type[typing.Any],
    *,
    transform_source: typing.Optional[typing.Callable[[str], str]] = None,
    globals_context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Callable[P, R]:
    """
    Precompile a method using exec, with optional source transformation.

    :param method: The method to precompile.
    :param transform_source: Optional function to transform the source code.
    :param globals_context: Optional dictionary to use as the global context for exec.
    :return: The precompiled method.
    """

    def create_cls_namespace(
        src: str,
    ) -> str:
        """Wrap the source code in a class namespace."""
        nonlocal transform_source
        if transform_source:
            src = transform_source(src)
        return f"class {cls.__name__}:\n{textwrap.indent(src, '    ')}"

    def cls_namespace_getter(
        func_name: str,
        localns: typing.Dict[str, typing.Any],
    ) -> typing.Any:
        """Retrieve the method from the class namespace."""
        return localns[cls.__name__].__dict__.get(func_name)

    precompiled_method = precompile_function(
        method,
        transform_source=create_cls_namespace,
        globals_context=globals_context,
        func_getter=cls_namespace_getter,
    )

    if "__class__" in method.__code__.co_freevars:
        precompiled_method = rebind_class_cell(precompiled_method, cls)
    return precompiled_method


def precompile_methods(
    cls: typing.Type[typing.Any],
    method_names: typing.Optional[typing.Iterable[str]] = None,
    *,
    transform_source: typing.Optional[typing.Callable[[str], str]] = None,
    globals_context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> None:
    """
    Precompile all methods of a class using exec, with optional source transformation.

    :param cls: The class whose methods to precompile.
    :param method_names: Optional list of method names to precompile. If None, all methods are precompiled.
    :param transform_source: Optional function to transform the source code.
    :param globals_context: Optional dictionary to use as the global context for exec.
    """
    if not inspect.isclass(cls):
        raise ValueError("The provided object is not a class.")

    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if method.__qualname__.split(".")[0] != cls.__name__:
            continue
        if method_names is not None and name not in method_names:
            continue

        compiled_method = precompile_method(
            method,
            cls,
            transform_source=transform_source,
            globals_context=globals_context,
        )
        setattr(cls, name, compiled_method)


_Serializer: typing.TypeAlias = typing.Callable[..., typing.Any]


def _unsupported_serializer(*args, **kwargs) -> None:
    """Raise an error for unsupported serialization."""
    raise SerializationError(
        "Unsupported serialization format. Register a serializer for this format."
    )


def _unsupported_serializer_factory():
    """Return a function that raises an error for unsupported serialization."""
    return _unsupported_serializer


class SerializerRegistry(typing.NamedTuple):
    """
    Serializer registry class to handle different serialization formats.

    :param serializer_map: A dictionary mapping format names to their respective serializer functions.
    """

    serializer_map: typing.DefaultDict[str, _Serializer] = defaultdict(
        _unsupported_serializer_factory
    )

    def __call__(self, fmt: str, *args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        """
        Serialize data using the specified format.

        :param fmt: The format to serialize to (e.g., 'json', 'xml').
        :param args: Positional arguments to pass to the format's serializer.
        :param kwargs: Keyword arguments to pass to the format's serializer.
        :return: Serialized data in the specified format.
        """
        return self.serializer_map[fmt](*args, **kwargs)
