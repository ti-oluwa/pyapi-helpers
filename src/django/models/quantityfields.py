from src.dependencies import deps_required

deps_required({"quantities": "quantities"})


import warnings
import typing
from quantities import Quantity

from django.db import models
from django.utils.translation import gettext_lazy as _
from django import forms
from django.core.exceptions import ValidationError

from src.logging import log_exception


def _asdict(quantity: Quantity):
    return {"magnitude": quantity.magnitude, "unit": str(quantity.units)}


def _aslist(quantity: Quantity):
    return [quantity.magnitude, str(quantity.units)]


def validate_quantity(value: typing.Any) -> None:
    """Validates that the input is a valid quantity in the form of a string, list, tuple, or dict."""
    if isinstance(value, Quantity):
        return
    
    try:
        if isinstance(value, (list, tuple)):
            if len(value) != 2:
                raise ValidationError(
                    "Quantity should contain exactly 2 values - (magnitude, unit)."
                )
            Quantity(value[0], value[1])
        elif isinstance(value, dict):
            try:
                Quantity(value["magnitude"], value["unit"])
            except KeyError:
                raise ValidationError(
                    "Quantity should contain keys 'magnitude' and 'unit'."
                )
        elif isinstance(value, str):
            magnitude, unit = value.split(" ", maxsplit=1)
            Quantity(magnitude, unit) # type: ignore
        else:
            raise ValueError("Unsupported value type")

    except (ValueError, IndexError, SyntaxError) as exc:
        log_exception(exc)
        raise ValidationError(_("Invalid quantity value.")) from exc


def validate_unit(value: str):
    """Validates that the input is a valid unit string."""
    try:
        Quantity(1.0, value)
    except ValueError as exc:
        raise ValidationError("Invalid unit value.") from exc


EMPTY_VALUES = (None, "", [], (), {})

def to_python(value: typing.Any):
    if isinstance(value, Quantity):
        return value
    
    if value in EMPTY_VALUES:
        return value

    try:
        if isinstance(value, (list, tuple)):
            quantity = Quantity(*value)
        elif isinstance(value, dict):
            quantity = Quantity(value["magnitude"], value["unit"])
        elif isinstance(value, str):
            magnitude, unit = value.split(" ", maxsplit=1)
            quantity = Quantity(magnitude, unit) # type: ignore
        else:
            raise ValueError("Unsupported value type")
    except SyntaxError:
        # SyntaxError is raised when the unit is not recognized
        # Return the value as is
        return value
    
    except (ValueError, KeyError) as exc:
        log_exception(exc)
        raise ValidationError(_("Invalid quantity value")) from exc

    return quantity


class QuantityDescriptor:
    
    def __init__(self, field):
        self.field = field

    def __get__(self, instance, owner):
        if instance is None:
            return self

        # The instance dict contains whatever was originally assigned in
        # __set__.
        if self.field.name in instance.__dict__:
            value = instance.__dict__[self.field.name]
        else:
            instance.refresh_from_db(fields=[self.field.name])
            value = getattr(instance, self.field.name)
        return value

    def __set__(self, instance, value):
        instance.__dict__[self.field.name] = to_python(value)


class QuantityField(models.CharField):
    attr_class = Quantity
    default_validators = [validate_quantity]
    descriptor_class = QuantityDescriptor

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("max_length", 100)
        if kwargs.get("unique", False):
            warnings.warn(f"{type(self).__name__} does not support unique=True.")

        kwargs["unique"] = False
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        return to_python(value)
    
    def get_prep_value(self, value: typing.Any):
        value = to_python(value)
        if isinstance(value, Quantity):
            prep_value = str(value)
        else:
            prep_value = value
        return super().get_prep_value(prep_value)
    
    def contribute_to_class(self, cls, name, *args, **kwargs):
        super().contribute_to_class(cls, name, *args, **kwargs)
        setattr(cls, self.name, self.descriptor_class(self))
    
    def formfield(self, **kwargs):
        defaults = {"form_class": forms.CharField}
        defaults.update(kwargs)
        return super().formfield(**defaults)


class JSONQuantityField(models.JSONField):
    """
    `QuantityField` that stores and accepts quantities as JSON.

    Example:
    ```
    class MyModel(models.Model):
        ...
        quantity = JSONQuantityField(unit='m', use_dict=True)
        ...
    ```
    """
    attr_class = Quantity
    default_validators = [validate_quantity]
    descriptor_class = QuantityDescriptor

    def __init__(self, unit: str, *args, **kwargs) -> None:
        """
        Initialize field.

        :param unit: The unit of the quantity. Other units may be used.
        :param use_dict: Whether to store the quantity as a dictionary instead of a list. Defaults to False.
        """
        kwargs.setdefault(
            "use_dict", False
        )  # Whether to store the quantity as a dictionary instead of a list
        try:
            validate_unit(unit)
        except ValidationError as exc:
            raise ValueError(exc)

        self.unit = unit
        self.use_dict = kwargs.pop("use_dict")
        super().__init__(*args, **kwargs)

    def get_prep_value(self, value: typing.Any):
        value = to_python(value)

        if isinstance(value, Quantity):
            value = value.rescale(self.unit)
            if self.use_dict:
                prep_value = _asdict(value)
            else:
                prep_value = _aslist(value)
        else:
            prep_value = value
        return super().get_prep_value(prep_value)

    def from_db_value(self, value, expression, connection):
        value = to_python(value)

        if isinstance(value, Quantity):
            value = value.rescale(self.unit)
        return value
    
    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs["unit"] = self.unit
        kwargs["use_dict"] = self.use_dict
        return name, path, args, kwargs
    
    def contribute_to_class(self, cls, name, *args, **kwargs):
        super().contribute_to_class(cls, name, *args, **kwargs)
        setattr(cls, self.name, self.descriptor_class(self))

