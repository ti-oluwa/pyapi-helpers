"""Simple dataclass implementation with field validation."""

import functools
import typing
from collections import OrderedDict
from types import MappingProxyType

from .fields import Field, Value
from .exceptions import FrozenInstanceError


def get_fields(cls: typing.Type) -> typing.Dict[str, Field]:
    """
    Inspect and retrieve all data fields from a class.

    :param cls: The class to inspect.
    :return: A dictionary of field names and their corresponding Field instances.
    """
    if issubclass(cls, DataClass) or hasattr(cls, "__fields__"):
        return dict(cls.__fields__)

    fields = {}
    for key, value in cls.__dict__.items():
        if isinstance(value, Field):
            fields[key] = value
    return fields


def _sort_by_name(item: typing.Tuple[str, Field]) -> str:
    return item[1].name or item[0]


def _dataclass_repr(
    instance: "DataClass",
) -> str:
    """Build a string representation of the dataclass instance."""
    fields = instance.__fields__
    field_strs = []
    instance_type = type(instance)
    for key, field in fields.items():
        value = field.__get__(instance, owner=instance_type)
        field_strs.append(f"{key}={value}")
    return f"{instance_type.__name__}({', '.join(field_strs)})"


def _dataclass_str(
    instance: "DataClass",
) -> str:
    """Build a string representation of the dataclass instance."""
    fields = instance.__fields__
    field_values = {}
    instance_type = type(instance)
    for key, field in fields.items():
        value = field.__get__(instance, owner=instance_type)
        field_values[key] = value
    return field_values.__repr__()


def _dataclass_getitem(instance: "DataClass", key: str) -> typing.Any:
    field = instance.__fields__[key]
    return field.__get__(instance, owner=type(instance))


def _dataclass_setitem(instance: "DataClass", key: str, value: typing.Any) -> None:
    field = instance.__fields__[key]
    field.__set__(instance, value)


def build_frozen_dataclass_setattr(
    original_setattr: typing.Callable[["DataClass", str, Value], None],
) -> typing.Callable[["DataClass", str, Value], None]:
    """Build a frozen dataclass setattr function."""

    def frozen_setattr(instance: "DataClass", key: str, value: Value) -> None:
        """Set an attribute on a frozen dataclass instance."""
        if key in instance._set_attributes:
            raise FrozenInstanceError(
                f"Cannot modify '{instance.__class__.__name__}.{key}'. "
                f"Instance is frozen and field '{key}' has already been set."
            ) from None

        return original_setattr(instance, key, value)

    return frozen_setattr


def build_frozen_dataclass_delattr(
    original_delattr: typing.Callable[["DataClass", str], None],
) -> typing.Callable[["DataClass", str], None]:
    """Build a frozen dataclass delattr function."""

    def frozen_delattr(instance: "DataClass", key: str) -> None:
        """Delete an attribute from a frozen dataclass instance."""
        if key in instance.base_to_effective_name_map:
            raise FrozenInstanceError(
                f"Cannot delete '{instance.__class__.__name__}.{key}'. "
                "Instance is frozen"
            ) from None

        return original_delattr(instance, key)

    return frozen_delattr


def _get_slotted_instance_state(
    slotted_instance: "DataClass",
) -> typing.Tuple[typing.Dict[str, typing.Any], typing.Dict[str, typing.Any]]:
    """Get the state of the slotted dataclass instance."""
    fields = slotted_instance.__fields__
    field_values = {}
    instance_type = type(slotted_instance)
    for key, field in fields.items():
        value = field.__get__(slotted_instance, owner=instance_type)
        field_values[key] = value

    attributes = {}
    pickleable_attributes = set(
        getattr(slotted_instance, "__slots__", [])
        + getattr(slotted_instance, "__state_attributes__", [])
    )
    for attr_name in pickleable_attributes:
        if attr_name in fields:
            continue
        if not hasattr(slotted_instance, attr_name):
            continue
        value = getattr(slotted_instance, attr_name)
        attributes[attr_name] = value
    return field_values, attributes


def _set_slotted_instance_state(
    slotted_instance: "DataClass",
    state: typing.Tuple[typing.Dict[str, typing.Any], typing.Dict[str, typing.Any]],
) -> "DataClass":
    """Set the state of the slotted dataclass."""
    field_values, attributes = state
    load(slotted_instance, field_values)
    for key, value in attributes.items():
        if key in slotted_instance.__fields__:
            continue
        setattr(slotted_instance, key, value)
    return slotted_instance


def _get_slot_attribute_name(
    unique_prefix: str,
    field_name: str,
) -> str:
    return f"_{unique_prefix}_{field_name}"


def _build_slotted_namespace(
    namespace: typing.Dict[str, typing.Any],
    own_fields: typing.Iterable[str],
    additional_slots: typing.Optional[typing.Union[typing.Tuple[str], str]] = None,
    parent_slotted_attributes: typing.Optional[typing.Dict[str, str]] = None,
) -> typing.Dict[str, typing.Any]:
    """
    Build a namespace for a slotted dataclass.

    :param namespace: The original namespace of the dataclass.
    :param own_fields: The fields directly defined in the dataclass.
    :param additional_slots: Additional slots to include in the __slots__ attribute.
    :param parent_slotted_attributes: Slotted attributes from parent classes, if any.
    :return: The modified namespace with __slots__ and other attributes.
    """
    # Only add slots for fields defined in the class, i.e those that are not
    # inherited from a base class.
    unique_prefix = f"slotted_{id(namespace)}"
    slotted_attributes_names = {
        key: _get_slot_attribute_name(unique_prefix, key) for key in own_fields
    }

    slots = set(slotted_attributes_names.values())
    if additional_slots:
        if isinstance(additional_slots, str):
            slots.add(additional_slots)
        else:
            slots.update(additional_slots)

    defined_slots = namespace.get("__slots__", None)
    if defined_slots:
        if isinstance(defined_slots, str):
            slots.add(defined_slots)
        else:
            slots.update(defined_slots)

    # Add __getstate__ and __setstate__ methods for pickling support
    if "__getstate__" not in namespace:
        namespace["__getstate__"] = _get_slotted_instance_state
    if "__setstate__" not in namespace:
        namespace["__setstate__"] = _set_slotted_instance_state

    namespace["__slots__"] = tuple(slots)
    if parent_slotted_attributes:
        slotted_attributes_names |= parent_slotted_attributes
    namespace["__slotted_names__"] = slotted_attributes_names
    namespace.pop("__dict__", None)
    namespace.pop("__weakref__", None)
    return namespace


def _dataclass_hash(instance: "DataClass") -> int:
    """Compute the hash of the dataclass instance based on descriptor fields."""
    fields = instance.__fields__
    instance_type = type(instance)
    try:
        return hash(
            tuple(
                hash(field.__get__(instance, instance_type))
                for field in fields.values()
            )
        )
    except TypeError as e:
        raise TypeError(f"Unhashable field value in {instance}: {e}")


def _dataclass_eq(
    instance: "DataClass",
    other: typing.Any,
) -> bool:
    """Compare two dataclass instances for equality."""
    if not isinstance(other, instance.__class__):
        return NotImplemented
    if instance is other:
        return True
    if not isinstance(other, DataClass):
        return False
    if len(instance.__fields__) != len(other.__fields__):
        return False

    for field in instance.__fields__.values():
        instance_value = field.__get__(instance, type(instance))
        other_value = field.__get__(other, type(instance))
        if instance_value != other_value:
            return False
    return True


u = str


class DataClassMeta(type):
    """Metaclass for DataClass types"""

    def __new__(
        cls,
        name: str,
        bases: typing.Tuple[typing.Type],
        attrs: typing.Dict[str, typing.Any],
        frozen: bool = False,
        slots: typing.Union[typing.Tuple[str], bool] = False,
        repr: bool = False,
        str: bool = False,
        sort: typing.Union[
            bool, typing.Callable[[typing.Tuple[str, Field]], typing.Any]
        ] = False,
        hash: bool = False,
        eq: bool = False,
        getitem: bool = False,
        setitem: bool = False,
    ):
        """
        Create a new DataClass type.

        :param name: Name of the new class.
        :param bases: Base classes for the new class.
        :param attrs: Attributes and namespace for the new class.
        :param slots: If True, use __slots__ for instance attribute storage.
            If a tuple, use as additional slots.
            If False, use __dict__ for instance attribute storage.
        :param dict_repr: Whether to use dict representation for __repr__ or to use the default.
        :param sort: If True, sort fields by name. If a callable, use as the sort key.
            If False, do not sort fields.
        :param frozen: If True, the dataclass is immutable after creation.
        :param hash: If True, add __hash__ method to the class.
        :param eq: If True, add __eq__ method to the class.
        :param getitem: If True, add __getitem__ method to the class.
        :param setitem: If True, add __setitem__ method to the class.
        :return: New DataClass type
        """
        own_fields = {}
        fields = {}
        base_to_effective_name_map = {}
        effective_to_base_name_map = {}
        parent_slotted_attributes = {}
        for key, value in attrs.items():
            if isinstance(value, Field):
                value.post_init_validate()
                own_fields[key] = value
                fields[key] = value
                effective_name = value.alias or key
                base_to_effective_name_map[key] = effective_name
                effective_to_base_name_map[effective_name] = key

        # Inspect the base classes for fields and borrow them
        inspected = set()
        for base_ in bases:
            for cls_ in base_.mro()[:-1]:
                if cls_ in inspected:
                    continue

                inspected.add(cls_)
                if not hasattr(cls_, "__fields__"):
                    continue

                if slots and hasattr(cls_, "__slotted_names__"):
                    parent_slotted_attributes.update(cls_.__slotted_names__)

                cls_ = typing.cast(typing.Type["DataClass"], cls_)
                # Borrow fields from the base class
                fields.update(cls_.__fields__)
                base_to_effective_name_map.update(cls_.base_to_effective_name_map)
                effective_to_base_name_map.update(cls_.effective_to_base_name_map)

        if slots:
            # Replace the original namespace with a slotted one.
            slotted_namespace = _build_slotted_namespace(
                namespace=attrs.copy(),
                own_fields=own_fields.keys(),
                additional_slots=slots
                if isinstance(slots, (u, tuple, list, set))
                else None,
                parent_slotted_attributes=parent_slotted_attributes,
            )
            attrs = slotted_namespace

        if frozen:
            attrs["__setattr__"] = build_frozen_dataclass_setattr(attrs["__setattr__"])
            attrs["__delattr__"] = build_frozen_dataclass_delattr(attrs["__delattr__"])
        if repr:
            attrs["__repr__"] = _dataclass_repr
        if str:
            attrs["__str__"] = _dataclass_str
        if getitem:
            attrs["__getitem__"] = _dataclass_getitem
        if setitem:
            attrs["__setitem__"] = _dataclass_setitem
        if hash:
            attrs["__hash__"] = _dataclass_hash
        if eq:
            attrs["__eq__"] = _dataclass_eq

        sort = attrs.get("sort", sort)
        if sort:
            if callable(sort):
                sort_key = sort
            else:
                sort_key = _sort_by_name

            sort_key = typing.cast(
                typing.Callable[[typing.Tuple[u, Field]], u], sort_key
            )
            fields_data = list(fields.items())
            fields_data.sort(key=sort_key)
            fields = OrderedDict(fields_data)

        # Make read-only to prevent accidental modification
        attrs["__fields__"] = MappingProxyType(fields)
        attrs["base_to_effective_name_map"] = MappingProxyType(
            base_to_effective_name_map
        )
        attrs["effective_to_base_name_map"] = MappingProxyType(
            effective_to_base_name_map
        )
        new_cls = super().__new__(cls, name, bases, attrs)
        return new_cls


class DataClass(metaclass=DataClassMeta, slots=True):
    """
    Simple dataclass.

    Dataclasses are defined by subclassing `DataClass` and defining fields as class attributes.
    Dataclasses enforce type validation, field requirements, and custom validation functions.

    :param frozen: If True, the dataclass is immutable after creation.
    :param slots: If True, use __slots__ for instance attribute storage.
        If a tuple, use as additional slots.
        If False, use __dict__ for instance attribute storage.
    :param repr: If True, use dict representation for __repr__ or to use the default.
    :param str: If True, use dict representation for __str__ or to use the default.
    :param sort: If True, sort fields by name. If a callable, use as the sort key.
        If False, do not sort fields.
    :param getitem: If True, add __getitem__ method to the class.
    :param setitem: If True, add __setitem__ method to the class.
    """

    __slots__ = ("__weakref__", "_set_attributes")
    __state_attributes__ = ()
    """
    Attributes to be included in the state of the dataclass when __getstate__ is called,
    usually during pickling
    """
    __fields__: typing.Mapping[str, Field[typing.Any]] = {}
    base_to_effective_name_map: typing.Mapping[str, str] = {}
    effective_to_base_name_map: typing.Mapping[str, str] = {}

    def __init__(
        self,
        data: typing.Optional[typing.Mapping[str, typing.Any]] = None,
    ) -> None:
        """
        Initialize the dataclass with raw data or keyword arguments.

        :param data: Raw data to initialize the dataclass with.
        """
        self._set_attributes = (
            set()
        )  # Set of attributes that have been set on the instance
        if data is not None:
            load(self, data)

    def __init_subclass__(cls) -> None:
        """Ensure that subclasses define fields."""
        if len(cls.__fields__) == 0:
            raise TypeError("Subclasses must define fields")
        return


_DataClass_co = typing.TypeVar("_DataClass_co", bound=DataClass, covariant=True)


def load(
    instance: _DataClass_co, data: typing.Mapping[str, typing.Any]
) -> _DataClass_co:
    """
    Load raw data into the dataclass instance.

    :param data: Mapping of raw data to initialize the dataclass instance with.
    :return: This same instance with the raw data loaded.
    """
    for name, field in instance.__fields__.items():
        key = instance.base_to_effective_name_map[name]
        if key not in data:
            value = field.get_default()
        else:
            value = data[key]

        field.__set__(instance, value)
    return instance


def from_dict(
    dataclass_: typing.Type[_DataClass_co],
    data: typing.Mapping[str, typing.Any],
) -> _DataClass_co:
    """
    Convert a dictionary to a dataclass instance.

    :param data: The dictionary to convert.
    :param dataclass_: The dataclass type to convert to.
    :return: The dataclass instance.
    """
    return load(dataclass_(), data)


def from_attributes(
    dataclass_: typing.Type[_DataClass_co],
    obj: typing.Any,
) -> _DataClass_co:
    """
    Convert an object to a dataclass instance by loading fields using
    the objects attributes

    :param obj: The object to convert.
    :param dataclass_: The dataclass type to convert to.
    :return: The dataclass instance.
    """
    instance = dataclass_()
    for name, field in dataclass_.__fields__.items():
        key = dataclass_.base_to_effective_name_map[name]

        if not hasattr(obj, key):
            value = field.get_default()
        else:
            value = getattr(obj, key)
        field.__set__(instance, value)
    return instance


def deserialize(
    dataclass_: typing.Type[_DataClass_co],
    obj: typing.Any,
    *,
    attributes: bool = False,
) -> _DataClass_co:
    """
    Deserialize an object to a dataclass instance.

    :param obj: The object to deserialize.
    :param dataclass_: The dataclass type to convert to.
    :param attributes: If True, load fields using the object's attributes.
    :return: The dataclass instance.
    """
    if attributes:
        return from_attributes(dataclass_, obj)
    return from_dict(dataclass_, obj)


@functools.cache
def get_field(
    cls: typing.Type[DataClass],
    field_name: str,
) -> typing.Optional[Field]:
    """
    Get a field by its name.

    :param cls: The DataClass type to search in.
    :param field_name: The name of the field to retrieve.
    :return: The field instance or None if not found.
    """
    field = cls.__fields__.get(field_name, None)
    if field is None and field_name in cls.effective_to_base_name_map:
        field_name = cls.effective_to_base_name_map[field_name]
        field = cls.__fields__.get(field_name, None)
    return field
