import typing
import functools
from rest_framework import serializers

from src.generics.utils.misc import merge_dicts


MS = typing.TypeVar("MS", bound=serializers.ModelSerializer)


class MergeUpdateMixin:
    """
    ModelSerializer mixin that allows for merging of fields on update

    Usage:
    ```python
    class MySerializer(MergeUpdateMixin, serializers.ModelSerializer):
        class Meta:
            model = MyModel
            fields = "__all__"
            merge = ["field1", "field2"]
    ```

    The above will merge the existing values of 'field1' and 'field2' with the new values.
    Supported field types are list, set, tuple and dict.
    """

    @functools.cached_property
    def mergeable_field_names(self: MS) -> typing.List[str]:
        """Returns the list of fields that can be merged"""
        field_names: typing.List[str] = getattr(self.Meta, "merge", [])
        for field_name in field_names:
            if field_name not in self.fields:
                raise ValueError(f"Invalid serializer field, '{field_name}'")
        return field_names

    def update(self, instance, validated_data: typing.Dict[str, typing.Any]):
        for field_name in self.mergeable_field_names:
            if field_name not in validated_data:
                continue
            value = validated_data[field_name]
            previous_value = getattr(instance, field_name, None)

            if value:
                if isinstance(value, (list, set, tuple)):
                    if isinstance(previous_value, (list, set, tuple)):
                        validated_data[field_name] = [*(previous_value or []), *value]
                elif isinstance(value, dict):
                    if isinstance(previous_value, dict):
                        validated_data[field_name] = merge_dicts(
                            previous_value or {}, value
                        )
                else:
                    raise ValueError(
                        f"Cannot merge field value of type '{type(value).__name__}'"
                    )
        return super().update(instance, validated_data)
