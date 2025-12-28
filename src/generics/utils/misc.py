import copy
from enum import Enum
import sys
import inspect
import collections.abc
import typing
import base64
import functools
from typing_extensions import Buffer, ParamSpec


T = typing.TypeVar("T")
P = ParamSpec("P")
R = typing.TypeVar("R")


def get_memory_size(
    obj: typing.Any, seen: typing.Optional[typing.Set[int]] = None
) -> float:
    """Recursively calculate the total memory size of an object and its references."""
    if seen is None:
        seen = set()

    obj_id = id(obj)
    if obj_id in seen:
        return 0
    seen.add(obj_id)

    size = sys.getsizeof(obj)
    if isinstance(obj, dict):
        size += sum(
            get_memory_size(k, seen) + get_memory_size(v, seen) for k, v in obj.items()
        )
    elif isinstance(obj, (list, tuple, set, frozenset)):
        size += sum(get_memory_size(i, seen) for i in obj)
    return size


def has_method(obj: typing.Any, method_name: str) -> bool:
    """Check if an object or type has a specific method."""
    return callable(getattr(obj, method_name, None))


def type_implements_iter(tp: typing.Type[typing.Any], /) -> bool:
    """Check if the type has an __iter__ method (like lists, sets, etc.)."""
    return has_method(tp, "__iter__")


def is_mapping(obj: typing.Any) -> typing.TypeGuard[collections.abc.Mapping]:
    """Check if an object is a mapping (like dict)."""
    return isinstance(obj, collections.abc.Mapping)


def is_mapping_type(
    tp: typing.Type[typing.Any], /
) -> typing.TypeGuard[typing.Type[collections.abc.Mapping]]:
    """Check if a given type is a mapping (like dict)."""
    return inspect.isclass(type) and issubclass(tp, collections.abc.Mapping)


def is_iterable_type(
    tp: typing.Type[typing.Any],
    /,
    *,
    exclude: typing.Optional[typing.Tuple[typing.Type[typing.Any], ...]] = None,
) -> typing.TypeGuard[typing.Type[collections.abc.Iterable]]:
    """
    Check if a given type is an iterable.

    :param tp: The type to check.
    :param exclude: A tuple of types to return False for, even if they are iterable types.
    """
    is_iter_type = issubclass(tp, collections.abc.Iterable)
    if not is_iter_type:
        return False

    if exclude:
        for _tp in exclude:
            if not is_iterable_type(_tp):
                raise ValueError(f"{_tp} is not an iterable type.")

        is_iter_type = is_iter_type and not issubclass(tp, tuple(exclude))
    return is_iter_type


def is_iterable(
    obj: typing.Any,
    *,
    exclude: typing.Optional[typing.Tuple[typing.Type[typing.Any], ...]] = None,
) -> typing.TypeGuard[collections.abc.Iterable]:
    """Check if an object is an iterable."""
    return is_iterable_type(type(obj), exclude=exclude)


def is_generic_type(o: typing.Any, /) -> bool:
    """Check if an object is a generic type."""
    return typing.get_origin(o) is not None and not isinstance(o, typing._SpecialForm)


def is_exception_class(exc) -> typing.TypeGuard[typing.Type[BaseException]]:
    return inspect.isclass(exc) and issubclass(exc, BaseException)


def str_to_base64(s: str, encoding: str = "utf-8") -> str:
    b = s.encode(encoding=encoding)
    return bytes_to_base64(b)


def bytes_to_base64(b: typing.Union[Buffer, bytes]) -> str:
    """Convert bytes to a base64 encoded string."""
    return base64.b64encode(b).decode()


def str_is_base64(s: str, encoding: str = "utf-8") -> bool:
    try:
        # Encode string to bytes and then decode
        b = s.encode(encoding=encoding)
        decoded = base64.b64decode(b, validate=True)
        # Encode back to base64 to check if it matches original
        return base64.b64encode(decoded).decode() == s.strip()
    except Exception:
        return False


def bytes_is_base64(b: bytes) -> bool:
    try:
        if not isinstance(b, bytes):
            return False
        decoded = base64.b64decode(b, validate=True)
        # Encode back to base64 to check if it matches original
        return base64.b64encode(decoded) == b.strip()
    except Exception:
        return False


def get_value_by_traversal_path(
    data: typing.Mapping[str, typing.Any], path: str, delimiter: str = "."
) -> typing.Union[typing.Any, None]:
    """
    Get the value from a nested mapping using a traversal path.

    :param data: The mapping to traverse.
    :param path: The traversal path to the value.
    :param delimiter: The delimiter used in the traversal path.
    :return: The value at the end of the traversal path.
        Returns None if the path does not exist in the mapping or
        a non-mapping value is encountered before the end of the path.
    """
    parts = path.split(delimiter)
    value = data
    for key in parts:
        if not isinstance(value, collections.abc.Mapping):
            return None
        value = value.get(key, None)
        if value is None:
            return None
    return value


def get_attr_by_traversal_path(
    obj: typing.Any, path: str, delimiter: str = "."
) -> typing.Union[typing.Any, None]:
    """
    Get the attribute from an object using a traversal path.

    :param obj: The object to traverse.
    :param path: The traversal path to the attribute.
    :param delimiter: The delimiter used in the traversal path.
    :return: The attribute at the end of the traversal path.
    """
    parts = path.split(delimiter)
    value = obj
    for key in parts:
        value = getattr(value, key, None)
        if value is None:
            return None
    return value


def get_mapping_diff(
    dict1: typing.Mapping[typing.Any, typing.Any],
    dict2: typing.Mapping[typing.Any, typing.Any],
) -> typing.Dict[typing.Any, typing.Any]:
    """
    Get the changes between two mappings.

    Compares two mappings and returns a new dictionary containing the keys
    and values that are different between the two mappings.

    If a key exists in both mappings and its value is a mapping, it will
    recursively compare the nested mappings and include the differences.
    """
    diff_dict = {}
    for key, value in dict1.items():
        if isinstance(value, collections.abc.Mapping):
            diff = get_mapping_diff(value, dict2.get(key, {}))
            if diff:
                diff_dict[key] = diff
            continue

        dict2_value = dict2.get(key)
        if value == dict2_value:
            continue
        diff_dict[key] = dict2_value
    return diff_dict


MutableMappingT = typing.TypeVar(
    "MutableMappingT", bound=collections.abc.MutableMapping[typing.Any, typing.Any]
)


def merge_mappings(
    *mappings: MutableMappingT,
    merge_nested: bool = True,
    merger: typing.Optional[
        typing.Callable[[MutableMappingT, MutableMappingT], MutableMappingT]
    ] = None,
    copier: typing.Optional[
        typing.Callable[[MutableMappingT], MutableMappingT]
    ] = copy.copy,
) -> MutableMappingT:
    """
    Merges two or more mappings into a single mapping.
    Starting from the right to left, each mapping is merged into the penultimate mapping.

    For example, merging `{"a": 1, "b": 2}`, `{"b": 3, "c": 4}`, `{"c": 5, "d": 6}`
    would result in `{"a": 1, "b": 3, "c": 5, "d": 6}`.

    :param mappings: The mappings to merge.
    :param merge_nested: Whether to merge nested mappings. If set to `False`, nested mappings
        will be overridden by the source mapping. Defaults to `True`.
    :param merger: The function to use for merging nested mappings. If not provided, nested mappings
        will be merged recursively using this function. Defaults to `None`.
        An important not is that the merger should only use generic mapping properties when merging
        E.g. merger's should use `value = mapping[key]`, instead of `mapping.get(key)`.
        Except you are sure that the mapping all support the `get` method.
    :param copier: The function to use for copying mappings.
        Should return a new mapping with the same keys and values as the input mapping.
        Defaults to `copy.copy`. Set to `None` to avoid copying, Although this is not recommended,
        as modifications to the returned mapping may affect the input mappings and vice versa.
    :return: A new mapping containing all the keys and values from the provided mappings.

    Example Usage:
    ```python
    import collections

    merged = merge_mappings(
        {"a": 1, "b": 2},
        {"b": 3, "c": 4},
        {"c": 5, "d": {"e": 6}},
        {"d": {"e": 7, "f": 8}},
        merge_nested=True,
        merger=collections.ChainMap,
    )

    print(merged)
    # Output: {'a': 1, 'b': 3, 'c': 5, 'd': ChainMap({'e': 6}, {'e': 7, 'f': 8})}
    ```
    """
    if not mappings:
        raise ValueError("At least one mapping must be provided")

    if not all(isinstance(mapping, collections.abc.Mapping) for mapping in mappings):
        raise TypeError("All arguments must be mappings")

    copier = copier or (
        lambda x: x
    )  # Just return the input mapping if no copier is provided
    if len(mappings) == 1:
        return copier(mappings[0])

    merger = merger or _default_mappings_merger

    # Start from the back and merge each mapping into the penultimate mapping
    target = copier(mappings[-2])
    source = mappings[-1]
    for key, source_value in source.items():
        if merge_nested is False or key not in target:
            target[key] = source_value
            continue
        # From here on merging of nested mappings is allowed and the
        # source key has been confirmed to be in the target mapping

        #  If the source and target values are both mappings, recursively merge
        #  the source value into the target value
        if isinstance(target[key], collections.abc.Mapping) and isinstance(
            source_value, collections.abc.Mapping
        ):
            target[key] = merger(target[key], source_value)  # type: ignore
        else:
            # Otherwise, just override the target value with the source value
            target[key] = source_value

    return merge_mappings(
        *mappings[:-2],
        target,
        merge_nested=merge_nested,
        merger=merger,
        copier=copier,
    )


_default_mappings_merger = functools.partial(merge_mappings, copier=None)


# Deprecated: Use `merge_mappings` instead.
def merge_dicts(
    *dicts: typing.Dict[typing.Any, typing.Any],
    **kwargs,
):
    """
    Merges two or more dictionaries into a single dictionary.

    Deprecated: Use `merge_mappings` instead.
    """
    return merge_mappings(*dicts, **kwargs)


def merge_enums(name: str, *enums: typing.Type[Enum]) -> typing.Type[Enum]:
    """
    Merges multiple Enum types into a single Enum type.

    :param name: The name of the new Enum type.
    :param enums: The Enum types to merge.
    :return: A new Enum type containing all the members from the provided Enum types.
    """
    members: typing.Dict[str, typing.Any] = {}
    for enum in enums:
        for member in enum.__members__.values():  # type: ignore
            if member.name in members:
                raise ValueError(f"Duplicate enum name found: {member.name}")
            members[member.name] = member.value

    return Enum(name, members)  # type: ignore


def underscore_dict_keys(
    _dict: typing.Dict[str, typing.Any],
) -> typing.Dict[str, typing.Any]:
    """Replaces all hyphens in the dictionary keys with underscores"""
    return {key.replace("-", "_"): value for key, value in _dict.items()}


def comma_separated_to_int_float(value: str) -> typing.Union[str, int, float]:
    """Convert a comma-separated string into a single integer or float by concatenating the numbers."""
    if not value:
        return 0

    try:
        stripped_value = "".join(value.split(","))
        if "." in stripped_value:
            return float(stripped_value)
        return int(stripped_value)
    except ValueError:
        return value


def python_type_to_html_input_type(py_type: type) -> str:
    """
    Maps a Python type to the appropriate HTML input type.

    Args:
        py_type (type): The Python type to be mapped.

    Returns:
        str: The corresponding HTML input type as a string.

    - `NoneType`: mapped to "text"
    - `str`: mapped to "text"
    - `int`: mapped to "number"
    - `float`: mapped to "number"
    - `bool`: mapped to "checkbox"
    - `list` or `tuple`: mapped to "text" (assuming comma-separated values)
    - `dict`: mapped to "text"
    - `bytes`: mapped to "file"
    - Default type: mapped to "text"
    """
    if py_type is type(None):
        return "text"
    if issubclass(py_type, str):
        return "text"
    if issubclass(py_type, int):
        return "number"
    if issubclass(py_type, float):
        return "number"
    if issubclass(py_type, bool):
        return "checkbox"
    if issubclass(py_type, (list, tuple)):
        return "text"  # Assuming you may want a comma-separated list
    if issubclass(py_type, dict):
        return "text"  # Handling complex types can vary
    if issubclass(py_type, bytes):
        return "file"

    # Default case for unsupported types
    return "text"


__all__ = [
    "is_iterable_type",
    "is_iterable",
    "is_generic_type",
    "is_mapping_type",
    "is_exception_class",
    "str_to_base64",
    "bytes_to_base64",
    "str_is_base64",
    "bytes_is_base64",
    "get_value_by_traversal_path",
    "get_attr_by_traversal_path",
    "merge_dicts",
    "merge_mappings",
    "merge_enums",
    "get_mapping_diff",
    "underscore_dict_keys",
    "python_type_to_html_input_type",
]
