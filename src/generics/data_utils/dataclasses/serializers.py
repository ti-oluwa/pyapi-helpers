from collections import OrderedDict
import typing
import functools

from .exceptions import SerializationError
from .dataclass import DataClass, get_field


@functools.lru_cache(maxsize=128)
def aggregate_field_names(
    cls: typing.Type["DataClass"],
    include: typing.Optional[typing.Iterable[str]] = None,
    exclude: typing.Optional[typing.Iterable[str]] = None,
) -> typing.Set[str]:
    if not include and not exclude:
        return set(cls.__fields__.keys())

    aggregate = []
    if include:
        for field_name in include:
            field = get_field(cls, field_name)
            if field is None:
                raise ValueError(f"Field '{field_name}' not found in {cls.__name__}.")
            aggregate.append(field_name)
    if exclude:
        for field_name in exclude:
            field = get_field(cls, field_name)
            if field is None:
                raise ValueError(f"Field '{field_name}' not found in {cls.__name__}.")
            aggregate.append(field_name)
    return set(aggregate)


def _serialize_instance(
    fmt: str,
    fields: typing.Iterable[str],
    instance: "DataClass",
    depth: int = 0,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.OrderedDict[str, typing.Any]:
    """
    Serialize a dataclass instance to a dictionary.

    :param fmt: The format for serialization (e.g., "python", "json").
    :param fields: The fields to include in the serialization.
    :param instance: The dataclass instance to serialize.
    :param depth: Depth for nested serialization.
    :param context: Additional context for serialization.
    :return: A dictionary representation of the dataclass instance.
    """
    serialized_data = OrderedDict()
    for name in fields:
        field = instance.__fields__[name]
        key = field.effective_name
        try:
            value = field.__get__(instance, owner=type(instance))
            if depth <= 0:
                serialized_data[key] = value
                continue

            if isinstance(value, DataClass):
                serialized_data[key] = _serialize_instance(
                    fmt=fmt,
                    fields=value.__fields__,
                    instance=value,
                    depth=depth - 1,
                    context=context,
                )
            else:
                updated_context = {**(context or {}), "depth": depth}
                serialized_data[key] = field.serialize(
                    value,
                    fmt=fmt,
                    context=updated_context,
                )
        except (TypeError, ValueError) as exc:
            raise SerializationError(
                f"Failed to serialize '{type(instance).__name__}.{key}'.",
                key,
            ) from exc
    return serialized_data


@typing.overload
def serialize(
    obj: DataClass,
    *,
    fmt: typing.Literal["python", "json"],
    depth: int = 0,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    include: typing.Optional[typing.Iterable[str]] = None,
    exclude: typing.Optional[typing.Iterable[str]] = None,
) -> typing.Dict[str, typing.Any]: ...


@typing.overload
def serialize(
    obj: DataClass,
    *,
    fmt: str,
    depth: int = 0,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    include: typing.Optional[typing.Iterable[str]] = None,
    exclude: typing.Optional[typing.Iterable[str]] = None,
) -> typing.Any: ...


@typing.overload
def serialize(
    obj: DataClass,
    *,
    fmt: str = "python",
    depth: int = 0,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    include: typing.Optional[typing.Iterable[str]] = None,
    exclude: typing.Optional[typing.Iterable[str]] = None,
) -> typing.Any: ...


def serialize(
    obj: DataClass,
    *,
    fmt: str = "python",
    depth: int = 0,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    include: typing.Optional[typing.Iterable[str]] = None,
    exclude: typing.Optional[typing.Iterable[str]] = None,
) -> typing.Any:
    """Return a serialized representation of the dataclass."""
    context = context or {}
    try:
        if not (include or exclude):
            fields = obj.__fields__.keys()
        else:
            fields = aggregate_field_names(
                obj.__class__,
                include=frozenset(include) if include else None,
                exclude=frozenset(exclude) if exclude else None,
            )
            context["__targets__"] = {obj.__class__.__name__: fields}
        return _serialize_instance(fmt, fields, obj, depth, context)
    except (TypeError, ValueError) as exc:
        raise SerializationError(
            f"Failed to serialize '{obj.__class__.__name__}'.", exc
        ) from exc
