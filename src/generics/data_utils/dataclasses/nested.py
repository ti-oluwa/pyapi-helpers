import typing
from typing_extensions import Unpack

from .fields import Field, FieldInitKwargs
from .dataclass import DataClass
from .serializers import _serialize_instance


_DataClass = typing.TypeVar("_DataClass", bound=DataClass)
_DataClass_co = typing.TypeVar("_DataClass_co", bound=DataClass, covariant=True)


def nested_json_serializer(
    instance: _DataClass_co,
    field: Field[_DataClass_co],
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Dict[str, typing.Any]:
    """Serialize a nested dataclass instance to a dictionary."""
    if context:
        depth = context.get("depth", 0)
        fields = context.get("__targets__", None)
        serializable_fields = (
            fields.get(instance.__class__.__name__, None) if fields else None
        )
    else:
        depth = 0
        serializable_fields = None

    return _serialize_instance(
        fmt="json",
        fields=serializable_fields or instance.__fields__,
        instance=instance,
        depth=depth,
        context=context,
    )


def nested_python_serializer(
    instance: _DataClass_co,
    field: Field[_DataClass_co],
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Dict[str, typing.Any]:
    """Serialize a nested dataclass instance to a dictionary."""
    if context:
        depth = context.get("depth", 0)
        fields = context.get("__targets__", None)
        serializable_fields = (
            fields.get(instance.__class__.__name__, None) if fields else None
        )
    else:
        depth = 0
        serializable_fields = None

    return _serialize_instance(
        fmt="python",
        fields=serializable_fields or instance.__fields__,
        instance=instance,
        depth=depth,
        context=context,
    )


class NestedField(Field[_DataClass]):
    """Nested DataClass field."""

    default_serializers = {
        "python": nested_python_serializer,
        "json": nested_json_serializer,
    }

    def __init__(
        self,
        dataclass_: typing.Type[_DataClass],
        **kwargs: Unpack[FieldInitKwargs[_DataClass]],
    ) -> None:
        super().__init__(dataclass_, **kwargs)

    def post_init_validate(self):
        super().post_init_validate()
        self.field_type = typing.cast(typing.Type[_DataClass], self.field_type)
        if not issubclass(self.field_type, DataClass):
            raise TypeError(
                f"{self.field_type} must be a subclass of {DataClass.__name__}."
            )
