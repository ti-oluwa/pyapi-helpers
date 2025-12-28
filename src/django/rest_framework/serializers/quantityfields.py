from src.dependencies import deps_required

deps_required({"quantities": "quantities"})


from quantities import Quantity
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from src.django.models.quantityfields import to_python, validate_quantity


class SerializerField:
    default_error_messages = {"invalid": _("Enter a valid quantity.")}
    default_validators = [validate_quantity]

    def to_internal_value(self, data):
        if isinstance(data, Quantity):
            quantity = data
        else:
            value = super().to_internal_value(data)
            quantity = to_python(value)
        return quantity


class QuantityField(SerializerField, serializers.CharField):
    
    def __init__(self, **kwargs):
        kwargs.setdefault("trim_whitespace", True)
        super().__init__(**kwargs)


class JSONQuantityField(SerializerField, serializers.JSONField):
    pass
