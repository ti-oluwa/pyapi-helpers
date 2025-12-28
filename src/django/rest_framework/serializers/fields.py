import typing
from rest_framework import serializers


SerializerField = typing.TypeVar("SerializerField", bound=serializers.Field)


class CompositeField(serializers.Field):
    """
    Composes two fields.

    One for read operations, the other for write operations.

    Example:
    ```python
    class MySerializer(serializers.Serializer):
        my_field = CompositeField(
            read_field=serializers.CharField(),
            write_field=serializers.IntegerField(),
            **kwargs
        )
    ```
    """

    def __init__(
        self, *, read_field: SerializerField, write_field: SerializerField, **kwargs
    ):
        """
        Initialize the CompositeField.

        :param read_field: The field to use for read operations.
        :param write_field: The field to use for write operations.
        :param kwargs: Additional arguments to pass to the parent Field class.
        """
        kwargs.pop("read_only", None)
        kwargs.pop("write_only", None)
        super().__init__(**kwargs)

        self.read_field = read_field
        self.read_field.read_only = True
        self.write_field = write_field
        self.write_field.write_only = True

        if not getattr(read_field, "source", None):
            self.read_field.source = self.source
        if getattr(read_field, "default", None) is serializers.empty:
            self.read_field.default = self.default
        if not getattr(write_field, "source", None):
            self.write_field.source = self.source
        if getattr(write_field, "default", None) is serializers.empty:
            self.write_field.default = self.default

        # Transfer the validators from the parent field to the write_field
        self.write_field.validators = [*self.validators, *self.write_field.validators]

        # The parent field should only be required if the write_field is required
        self.required = self.write_field.required

    def bind(self, field_name, parent):
        # Bind the nested fields to the parent serializer
        super().bind(field_name, parent)
        self.read_field.bind(field_name, parent)
        self.write_field.bind(field_name, parent)

    def to_representation(self, value):
        # Perfrom representation using the read_field
        return self.read_field.to_representation(value)

    def to_internal_value(self, data):
        # Perform internal/native value conversion using the write_field
        return self.write_field.to_internal_value(data)

    def run_validation(self, data=serializers.empty):
        (is_empty_value, data) = self.validate_empty_values(data)
        if is_empty_value:
            return data

        value = self.to_internal_value(data)
        # Run the write_field's validation instead of the parent's validation
        return self.write_field.run_validation(value)


# From Stackoverflow: https://stackoverflow.com/a/64274128
class WritableSerializerMethodField(serializers.SerializerMethodField):
    def __init__(self, **kwargs):
        self.setter_method_name = kwargs.pop('setter_method_name', None)
        self.deserializer_field = kwargs.pop('deserializer_field')

        super().__init__(**kwargs)

        self.read_only = False

    def bind(self, field_name, parent):
        retval = super().bind(field_name, parent)
        if not self.setter_method_name:
            self.setter_method_name = f'set_{field_name}'

        return retval

    def get_default(self):
        default = super().get_default()

        return {
            self.field_name: default
        }

    def to_internal_value(self, data):
        value = self.deserializer_field.to_internal_value(data)
        method = getattr(self.parent, self.setter_method_name)
        return {self.field_name: self.deserializer_field.to_internal_value(method(value))}
