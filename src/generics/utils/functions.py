import inspect
from typing import Any, Callable, Dict


class _NOT_SET:
    """Sentinel object to indicate that a value was not provided."""

    def __bool__(self):
        return False

    def __repr__(self):
        return "NOT_SET"


NOT_SET = _NOT_SET()


def get_function_params_details(func: Callable) -> Dict[str, Any]:
    """
    Returns details of the function's expected args and kwargs, with
    information about their types, defaults, and kind.

    :param func: The function to analyze.
    :return: A dictionary with details of the function's args and kwargs.

    Example:
    ```python

    def my_func(a: int, b: str = "default", *args, **kwargs):
        pass

    print(get_function_params_details(my_func))
    >>> {
        "args": {
            "a": {
                "name": "a",
                "type": int,
                "default": NOT_SET,
                "kind": "POSITIONAL_ONLY",
            },
        },
        "kwargs": {
            "b": {
                "name": "b",
                "type": str,
                "default": "default",
                "kind": "POSITIONAL_OR_KEYWORD",
            },
        },
        "variadic": {
            "args": {
                "name": "args",
                "type": None,
                "default": None,
                "kind": "VAR_POSITIONAL",
            },
            "kwargs": {
                "name": "kwargs",
                "type": None,
                "default": None,
                "kind": "VAR_KEYWORD",
            },
        },
    }
    """
    details = {"args": {}, "kwargs": {}, "variadic": {}}

    sig = inspect.signature(func)
    for name, param in sig.parameters.items():
        param_info = {
            "name": name,
            "type": param.annotation
            if param.annotation is not inspect.Parameter.empty
            else NOT_SET,
            "default": param.default
            if param.default is not inspect.Parameter.empty
            else NOT_SET,
            "kind": param.kind.name,
        }

        # Classify based on kind
        if param.kind == inspect.Parameter.POSITIONAL_ONLY:
            details["args"][name] = param_info
        elif param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD:
            if param.default is inspect.Parameter.empty:
                details["args"][name] = param_info
            else:
                details["kwargs"][name] = param_info
        elif param.kind == inspect.Parameter.KEYWORD_ONLY:
            details["kwargs"][name] = param_info
        elif param.kind == inspect.Parameter.VAR_POSITIONAL:
            details["variadic"]["args"] = param_info
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            details["variadic"]["kwargs"] = param_info

    return details


def add_parameter_to_signature(
    func: Callable, parameter: inspect.Parameter, index: int = -1
) -> Callable:
    """
    Adds a parameter to the function's signature at the specified index.

    This may be useful when you need to modify the signature of a function
    dynamically, such as when adding a new parameter to a function (via a decorator/wrapper).

    :param func: The function to update.
    :param parameter: The parameter to add.
    :param index: The index at which to add the parameter. Negative indices are supported.
        Default is -1, which adds the parameter at the end.
        If the index greater than the number of parameters, a ValueError is raised.
    :return: The updated function.

    Example Usage:
    ```python
    import inspect
    import typing
    import functools
    from typing_extensions import ParamSpec

    P = ParamSpec("P")
    R = TypeVar("R")


    def my_func(a: int, b: str = "default"):
        pass

    def decorator(func: typing.Callable[P, R]) -> typing.Callable[P, R]:
        def _wrapper(new_param: str, *args: P.args, **kwargs: P.kwargs) -> R:
            return func(*args, **kwargs)

        return functools.wraps(func)(_wrapper)

    wrapped_func = decorator(my_func) # returns wrapper function
    assert "new_param" in inspect.signature(wrapped_func).parameters
    >>> False

    # This will fail because the signature of the wrapper function is overridden by the original function's signature,
    # when functools.wraps is used. To fix this, we can use the `add_parameter_to_signature` function.

    wrapped_func = add_parameter_to_signature(
        func=wrapped_func,
        parameter=inspect.Parameter(
            name="new_param",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=str
        ),
        index=0 # Add the new parameter at the beginning
    )
    assert "new_param" in inspect.signature(wrapped_func).parameters
    >>> True

    # This way any new parameters added to the wrapper function will be preserved and logic using the
    # function's signature will respect the new parameters.
    """
    sig = inspect.signature(func)
    params = list(sig.parameters.values())

    # Check if the index is valid
    if index < 0:
        index = len(params) + index + 1
    elif index > len(params):
        raise ValueError(
            f"Index {index} is out of bounds for the function's signature. Maximum index is {len(params)}. "
            "Use a '-1' index to add the parameter at the end, if needed."
        )

    params.insert(index, parameter)
    new_sig = sig.replace(parameters=params)
    func.__signature__ = new_sig  # type: ignore
    return func


__all__ = [
    "get_function_params_details",
    "add_parameter_to_signature",
]
