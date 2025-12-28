from src.dependencies import deps_required

deps_required(
    {
        "attrs": "https://www.attrs.org/en/stable/",
        "cattrs": "https://pypi.org/project/cattrs/",
    }
)

import typing
import attrs
import cattrs

import collections.abc
from src.generics.utils.misc import (
    is_generic_type,
    is_mapping_type,
    is_iterable_type,
)

_AI = typing.TypeVar("_AI", bound=attrs.AttrsInstance)
T = typing.TypeVar("T")


class NoCast(typing.Generic[T]):
    """Wrapper class to indicate that a type should not be cast during structuring and unstructuring."""

    def __init__(self, wrapped_type: typing.Type[T]):
        self.wrapped_type = wrapped_type

    def __repr__(self) -> str:
        return f"NoCast[{self.wrapped_type}]"

    def __eq__(self, other):
        return isinstance(other, NoCast) and self.wrapped_type == other.wrapped_type

    def __hash__(self):
        return hash(self.wrapped_type)

    # This makes NoCast to be considered as a generic type
    @property
    def __origin__(self):
        return self.wrapped_type

    @property
    def __args__(self):
        return (self.wrapped_type,)


def unwrap_nocast_type(attr_type: typing.Type[typing.Any]) -> typing.Type[typing.Any]:
    """
    Return the wrapped type if the type is wrapped in NoCast,
    otherwise return the type as is.
    """
    origin = typing.get_origin(attr_type)
    if origin is NoCast:
        return typing.get_args(attr_type)[0]
    return attr_type


def is_nocast_type(attr_type: typing.Type[typing.Any]) -> bool:
    """
    Check if the type is wrapped in NoCast.
    """
    return typing.get_origin(attr_type) is NoCast


def structure_to_generic_type(
    value: typing.Any, attr_type: typing.Type[typing.Any], converter: cattrs.Converter
) -> typing.Any:
    """
    Recursively handle generic types (List, typing.Dict, Union, Optional, etc.) during structuring.
    If the type is wrapped in NoCast, return the value as is without casting.
    """
    if attr_type is typing.Any:
        return converter.structure(value, type(value))

    if is_nocast_type(attr_type):
        return value  # Skip casting if NoCast is applied

    attr_type = unwrap_nocast_type(attr_type)
    origin = typing.get_origin(attr_type)
    args = typing.get_args(attr_type)

    if origin is None:
        return value

    if origin is typing.Union:
        if value is None and type(None) in args:
            return None

        for arg in args:
            try:
                return (
                    converter.structure(value, arg)
                    if not is_generic_type(arg)
                    else structure_to_generic_type(value, arg, converter)
                )
            except (TypeError, ValueError):
                continue
        return value

    if is_mapping_type(origin) and len(args) == 2:
        _map = {}
        for k, v in value.items():
            _map_key = (
                converter.structure(k, args[0])
                if not is_generic_type(args[0])
                else structure_to_generic_type(k, args[0], converter)
            )
            _map_value = (
                converter.structure(v, args[1])
                if not is_generic_type(args[1])
                else structure_to_generic_type(v, args[1], converter)
            )
            _map[_map_key] = _map_value

        if is_generic_type(origin) or issubclass(origin, collections.abc.Mapping):
            return _map
        else:
            return origin(_map)

    if is_iterable_type(origin, exclude=(str, bytes)) and len(args) == 1:
        _iter = [
            converter.structure(v, args[0])
            if not is_generic_type(args[0])
            else structure_to_generic_type(v, args[0], converter)
            for v in value
        ]

        if is_generic_type(origin) or issubclass(origin, collections.abc.Iterable):
            return _iter
        else:
            return origin(_iter)

    try:
        return origin(value)  # type: ignore
    except (TypeError, ValueError, cattrs.errors.StructureHandlerNotFoundError):
        try:
            return converter.structure(value, type(value))
        except cattrs.errors.StructureHandlerNotFoundError:
            return value


def cast_on_set_factory(
    converter: cattrs.Converter,
) -> typing.Callable[[typing.Any, attrs.Attribute, typing.Any], typing.Any]:
    """
    Factory function to create a casting function for attrs-based attributes.
    Skips casting for attributes wrapped in NoCast.
    """

    def _cast_on_set(
        instance: typing.Any, attribute: attrs.Attribute, value: typing.Any
    ) -> typing.Any:
        attr_type = attribute.type
        if attr_type is None:
            return value

        if is_nocast_type(attr_type):
            return value  # Skip casting if NoCast is applied

        attr_type = unwrap_nocast_type(attr_type)

        if attrs.has(attr_type):
            return converter.structure(value, attr_type)
        elif is_generic_type(attr_type):
            return structure_to_generic_type(value, attr_type, converter)
        else:
            try:
                return converter.structure(value, attr_type)
            except (TypeError, ValueError, cattrs.errors.StructureHandlerNotFoundError):
                try:
                    return converter.structure(value, type(value))
                except cattrs.errors.StructureHandlerNotFoundError:
                    return value

    return _cast_on_set


def structure_with_casting_factory(
    converter: cattrs.Converter,
) -> typing.Callable[[typing.Dict[str, typing.Any], typing.Type[_AI]], _AI]:
    """
    Factory function to create a structuring function that casts values to declared types.
    Considers attribute aliases and uses them to fetch values from the input dictionary.
    """

    cast_on_set = cast_on_set_factory(converter)

    def _structure_with_casting(
        data: typing.Dict[str, typing.Any],
        cls: typing.Type[_AI],
    ) -> _AI:
        """
        Structuring hook for cattrs converters that casts values to the declared type.

        Considers attribute aliases while structuring.
        :param data: The data to structure.
        :param cls: The attrs-based class to structure the data into.
        :return: An instance of the attrs-based class.
        """
        return cls(
            **{
                attr.alias or attr.name: cast_on_set(
                    None,
                    attr,
                    data.get(
                        attr.alias or attr.name  # Use alias if provided
                    ),
                )
                for attr in cls.__attrs_attrs__  # type: ignore
            }
        )

    return _structure_with_casting


def unstructure_as_generic_type(
    value: typing.Any, attr_type: typing.Type[typing.Any], converter: cattrs.Converter
) -> typing.Any:
    """
    Recursively handle unstructuring of generic types (List, typing.Dict, Union, Optional, etc.)
    using cattrs.Converter and applying the unstructure_as argument when appropriate.

    :param value: The value to unstructure.
    :param attr_type: The type to unstructure the value to.
    :param converter: The cattrs Converter instance to use.
    :return: The unstructured value.
    """
    if attr_type is typing.Any:
        return converter.unstructure(value, unstructure_as=type(value))

    if is_nocast_type(attr_type):
        return value  # Skip casting if NoCast is applied

    attr_type = unwrap_nocast_type(attr_type)
    origin = typing.get_origin(attr_type)
    args = typing.get_args(attr_type)

    if origin is None:
        return value

    if origin is typing.Union:
        # Handle Union[T1, T2, ...] or Optional[T] (which is Union[T, None])
        if value is None and type(None) in args:
            return None

        for arg in args:
            try:
                return (
                    converter.unstructure(value, unstructure_as=arg)
                    if not is_generic_type(arg)
                    else unstructure_as_generic_type(value, arg, converter)
                )
            except (TypeError, ValueError):
                continue
        return value  # Return original value if no valid cast

    if is_mapping_type(origin) and len(args) == 2:
        # Handle Mapping[K, V] (like typing.Dict[K, V])
        _map = {}
        for k, v in value.items():
            _map_key = (
                converter.unstructure(k, unstructure_as=args[0])
                if not is_generic_type(args[0])
                else unstructure_as_generic_type(k, args[0], converter)
            )
            _map_value = (
                converter.unstructure(v, unstructure_as=args[1])
                if not is_generic_type(args[1])
                else unstructure_as_generic_type(v, args[1], converter)
            )
            _map[_map_key] = _map_value

        if is_generic_type(origin) or issubclass(origin, collections.abc.Mapping):
            return _map
        else:
            return origin(_map)

    if is_iterable_type(origin, exclude=(str, bytes)) and len(args) == 1:
        # Handle Iterable[T] (like List[T], Set[T], etc.)
        _iter = [
            converter.unstructure(v, unstructure_as=args[0])
            if not is_generic_type(args[0])
            else unstructure_as_generic_type(v, args[0], converter)
            for v in value
        ]

        if is_generic_type(origin) or issubclass(origin, collections.abc.Iterable):
            return _iter
        else:
            return origin(_iter)

    # Fallback for other generic types
    try:
        return converter.unstructure(value, unstructure_as=origin)
    except (TypeError, ValueError):
        return converter.unstructure(value, unstructure_as=type(value))


def unstructure_with_casting_factory(
    converter: cattrs.Converter,
) -> typing.Callable[[typing.Any], typing.Dict[str, typing.Any]]:
    """
    Factory function to create an unstructuring function that casts values to declared types.
    Considers attribute aliases when unstructuring.
    """

    def _unstructure_with_casting(instance: typing.Any) -> typing.Dict[str, typing.Any]:
        """
        Unstructures the attrs-based class instance and casts values to their declared types.
        Considers attribute aliases while unstructuring.
        """
        if not attrs.has(instance.__class__):
            # Fallback to converter's default unstructuring for non-attrs classes
            return converter.unstructure(instance)

        data = {}
        for attr in instance.__attrs_attrs__:
            value = getattr(instance, attr.name)
            attr_type = attr.type

            if attr_type is None:
                # Skip if the attribute has no type
                data[attr.alias or attr.name] = value
            elif is_nocast_type(attr_type):
                # Skip casting if NoCast is applied
                data[attr.alias or attr.name] = value
            elif is_generic_type(attr_type):
                data[attr.alias or attr.name] = unstructure_as_generic_type(
                    value, attr_type, converter
                )
            else:
                try:
                    data[attr.alias or attr.name] = converter.unstructure(
                        value, unstructure_as=attr_type
                    )
                except (TypeError, ValueError):
                    data[attr.alias or attr.name] = converter.unstructure(
                        value, unstructure_as=type(value)
                    )

        return data

    return _unstructure_with_casting


@typing.overload
def type_cast(
    converter: cattrs.Converter,
) -> typing.Callable[[typing.Type[_AI]], typing.Type[_AI]]: ...


@typing.overload
def type_cast(
    converter: cattrs.Converter,
    cls: typing.Type[_AI],
) -> typing.Type[_AI]: ...


def type_cast(
    converter: cattrs.Converter,
    cls: typing.Optional[typing.Type[_AI]] = None,
) -> typing.Union[
    typing.Callable[[typing.Type[_AI]], typing.Type[_AI]],
    typing.Type[_AI],
]:
    """
    Attrs class decorator.

    Registers structure and unstructure hooks for attrs-based classes on the
    provided cattrs converter instance, casting values to their declared types
    on structure and unstructure.

    :param converter: The cattrs converter instance to register hooks on
    :param cls: The class to register the hooks for (optional, if provided, will register hooks immediately)
    :return: The class with the hooks registered or a decorator function

    Example Usage:
    ```python
    import cattrs
    import attrs

    converter = cattrs.Converter()

    @type_cast(converter)
    @attrs.define(auto_attribs=True)
    class MyClass:
        name: str
        age: int
    ```
    """
    if cls is None:
        return lambda cls: type_cast(converter, cls)  # type: ignore

    # Ensures that the class is an attrs-based class
    if not attrs.has(cls):
        raise TypeError(
            f"{cls.__name__} is not an attrs-based class. typing.Type casting is only supported for attrs classes."
        )

    # Pass the specific converter to both structure and unstructure hooks for attrs-based classes
    converter.register_structure_hook(cls, structure_with_casting_factory(converter))
    converter.register_unstructure_hook(
        cls, unstructure_with_casting_factory(converter)
    )

    return cls  # type: ignore
