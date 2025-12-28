"""Data fields"""

import functools
from types import NoneType
import uuid
import decimal
import datetime
import typing
import json
import base64
import io
import copy
import ipaddress
from urllib3.util import Url, parse_url
from typing_extensions import Unpack, Self, ParamSpec
from collections import defaultdict

try:
    import orjson as json
except ImportError:
    import json

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo  # type: ignore[import]

from src.types import SupportsRichComparison
from src.generics.utils.misc import is_iterable_type, is_iterable
from src.dependencies import depends_on
from src.generics.utils.datetime import iso_parse, parse_duration
from . import validators as field_validators
from .exceptions import (
    FieldError,
    SerializationError,
    DeserializationError,
    FieldValidationError,
)
from ._utils import iexact, is_valid_type, SerializerRegistry


_T = typing.TypeVar("_T")
_V = typing.TypeVar("_V")
P = ParamSpec("P")
R = typing.TypeVar("R")


FieldValidator: typing.TypeAlias = typing.Callable[
    [
        _T,
        typing.Optional["Field[_T]"],
        typing.Optional[typing.Any],
    ],
    None,
]
"""Field validator type alias. 
Takes 3 arguments - value, field_instance, instance
"""
DefaultFactory = typing.Callable[[], typing.Union[_T, typing.Any]]
"""Type alias for default value factories."""
FieldSerializer: typing.TypeAlias = typing.Callable[
    [
        _T,
        typing.Union["_Field_co", typing.Any],
        typing.Optional[typing.Dict[str, typing.Any]],
    ],
    typing.Any,
]
"""
Type alias for serializers.

Takes three arguments - the value, the field instance, and optional context, and returns the serialized value.
Should raise a SerializationError if serialization fails.
"""
FieldDeserializer: typing.TypeAlias = typing.Callable[
    [
        typing.Union["_Field_co", typing.Any],
        typing.Any,
    ],
    _T,
]
"""
Type alias for deserializers.

Takes a three arguments - the field type, the value to deserialize, and the field instance.
Returns the deserialized value.
Should raise a DeserializationError if deserialization fails.
"""


class empty:
    """Class to represent missing/empty values."""

    def __bool__(self):
        return False

    def __init_subclass__(cls):
        raise TypeError("empty cannot be subclassed.")

    def __new__(cls):
        raise TypeError("empty cannot be instantiated.")


class UndefinedType:
    """Class to represent an UndefinedType type."""

    def __init_subclass__(cls):
        raise TypeError("UndefinedType cannot be subclassed.")

    def __new__(cls):
        raise TypeError("UndefinedType cannot be instantiated.")


def to_json_serializer(
    value: typing.Any,
    field: "Field",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> typing.Any:
    """Serialize a value to JSON."""
    return json.loads(json.dumps(value))


def to_string_serializer(
    value: typing.Any,
    field: "Field",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> str:
    """Serialize a value to a string."""
    return str(value)


def unsupported_serializer(
    value: typing.Any,
    field: "Field",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> None:
    """Raise an error for unsupported serialization."""
    raise SerializationError(
        f"'{type(field).__name__}' does not support serialization format. "
        f"Supported formats are: {', '.join(field.serializer.serializer_map.keys())}.",
        field.effective_name,
    )


def _unsupported_serializer_factory():
    """
    Return a function that raises an error for unsupported serialization.

    To be used in defaultdict for field serializer instantiation
    """
    return unsupported_serializer


def unsupported_deserializer(field: "Field", value: typing.Any) -> None:
    """Raise an error for unsupported deserialization."""
    raise DeserializationError(
        f"'{type(field).__name__}' does not support deserialization '{value}'.",
        field.effective_name,
    )


def to_python_serializer(
    value: _T,
    field: "Field",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> _T:
    """Serialize a value to Python object."""
    return value


DEFAULT_FIELD_SERIALIZERS: typing.Dict[str, FieldSerializer] = {
    "json": to_json_serializer,
    "python": to_python_serializer,
}


def default_deserializer(
    field: "Field[_T]",
    value: typing.Any,
) -> _T:
    """
    Deserialize a value to the specified field type.

    :param field_type: The type to which the value should be deserialized.
    :param value: The value to deserialize.
    :param field: The field instance to which the value belongs.
    :return: The deserialized value.
    """
    field_type = field.field_type
    if is_iterable(field_type):
        for arg in field_type:
            arg = typing.cast(typing.Type[_T], arg)
            try:
                return default_deserializer(field, value)
            except DeserializationError:
                continue

    deserialized = field_type(value)  # type: ignore[call-arg]
    deserialized = typing.cast(_T, deserialized)
    return deserialized


@typing.final
class Value(typing.Generic[_T], typing.NamedTuple):
    """
    Wrapper for field values.
    """

    value: typing.Union[_T, typing.Any]
    is_valid: bool = False

    def __bool__(self) -> bool:
        return bool(self.value)

    def __hash__(self) -> int:
        return hash(self.value)


def _get_cache_key(value: typing.Any) -> typing.Any:
    return value if isinstance(value, (int, str, tuple, frozenset)) else id(value)


@typing.overload
def Factory(
    factory: typing.Callable[P, R],
    /,
    needs_field: bool = False,
    *args: P.args,
    **kwargs: P.kwargs,
) -> typing.Callable[[], R]: ...


@typing.overload
def Factory(
    factory: typing.Callable[..., R],
    /,
    needs_field: bool = True,
    *args: typing.Any,
    **kwargs: typing.Any,
) -> typing.Callable[["Field"], R]: ...


def Factory(
    factory: typing.Callable[..., R],
    /,
    needs_field: bool = False,
    *args: typing.Any,
    **kwargs: typing.Any,
) -> typing.Union[typing.Callable[[], R], typing.Callable[["Field"], R]]:
    """
    Factory function to create a callable that invokes the provided factory with the given arguments.

    :param factory: The factory function to invoke.
    :param needs_field: If True, the factory function will be called with a field instance as the first argument.
    :param args: Additional arguments to pass to the factory function.
    :param kwargs: Additional keyword arguments to pass to the factory function.
    :return: A callable that, when invoked, calls the factory with the provided arguments.
    """
    if needs_field:

        def context_factory_func(field: "Field") -> R:
            return factory(field, *args, **kwargs)  # type: ignore[call-arg]

        return context_factory_func

    def factory_func() -> R:
        return factory(*args, **kwargs)

    return factory_func


class FieldMeta(type):
    def __init__(cls, name, bases, attrs):
        default_validators = getattr(cls, "default_validators", [])
        default_serializers = getattr(cls, "default_serializers", {})
        cls.default_validators = frozenset(
            field_validators.load_validators(*default_validators)
        )
        cls.default_serializers = {
            **DEFAULT_FIELD_SERIALIZERS,
            **default_serializers,
        }


class Field(typing.Generic[_T], metaclass=FieldMeta):
    """Attribute descriptor for enforcing type validation and constraints."""

    default_serializers: typing.Mapping[str, FieldSerializer] = {}
    default_deserializer: FieldDeserializer = default_deserializer
    default_validators: typing.Iterable[FieldValidator[_T]] = []

    def __init__(
        self,
        field_type: typing.Union[
            typing.Type[_T],
            typing.Type[UndefinedType],
            typing.Tuple[typing.Type[_T], ...],
        ],
        default: typing.Union[
            _T, DefaultFactory[_T], typing.Type[empty], NoneType
        ] = empty,
        lazy: bool = False,
        alias: typing.Optional[str] = None,
        allow_null: bool = False,
        required: bool = False,
        validators: typing.Optional[typing.Iterable[FieldValidator[_T]]] = None,
        serializers: typing.Optional[
            typing.Mapping[str, "FieldSerializer[_T, Self]"]
        ] = None,
        deserializer: typing.Optional["FieldDeserializer[Self, _T]"] = None,
    ):
        """
        Initialize the field.

        :param field_type: The expected type for field values.
        :param lazy: If True, the field will not be validated until it is accessed.
        :param alias: Optional string for alternative field naming, defaults to None.
        :param allow_null: If True, permits the field to be set to None, defaults to False.
        :param required: If True, field values must be explicitly provided, defaults to False.
        :param validators: A list of validation functions to apply to the field's value, defaults to None.
            Validators should be callables that accept the field value and the optional field instance as arguments.
            NOTE: Values returned from the validators are not used, but they should raise a FieldError if the value is invalid.
        :param serializers: A mapping of serialization formats to their respective serializer functions, defaults to None.
        :param default: A default value for the field to be used if no value is set, defaults to empty.
        :param deserializer: A deserializer function to convert the field's value to the expected type, defaults to None.
        :param on_setvalue: Callable to run on the value just before setting it, defaults to None.
            This is useful for transforming the value before it is set on the instance.
        """
        self.field_type = field_type
        self.lazy = lazy
        self.name = None
        self.alias = alias
        self.allow_null = allow_null
        self.required = required
        all_validators = [*self.default_validators, *(validators or [])]
        validator = field_validators.pipe(*all_validators) if all_validators else None
        self.validator = validator
        all_serializers = {
            **self.default_serializers,
            **(serializers or {}),
        }
        self.serializer = SerializerRegistry(
            defaultdict(
                _unsupported_serializer_factory,
                all_serializers,
            )
        )
        self.deserializer = deserializer or type(self).default_deserializer
        self.default = default
        self._init_args = ()
        self._init_kwargs = {}
        self._serialized_cache = defaultdict(None)
        self._validated_cache = defaultdict(None)

    def post_init_validate(self):
        """
        Validate the field after initialization.

        This method is called after the field is initialized to perform additional validation
        to ensure that the field is correctly configured.
        """
        if not is_valid_type(self.field_type):
            raise TypeError(f"Specified type '{self.field_type}' is not a valid type.")

        no_default = self.default is empty
        if self.required and not no_default:
            raise FieldError("A default value is not necessary when required=True")

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        instance._init_args = args
        instance._init_kwargs = kwargs
        return instance

    @functools.cached_property
    def effective_name(self) -> typing.Optional[str]:
        """
        Return the effective name of the field.

        This is either the alias (if provided) or the name of the field.
        """
        return self.alias or self.name

    def get_default(self) -> typing.Union[_T, typing.Type[empty], NoneType]:
        """Return the default value for the field."""
        default_value = self.default
        if default_value is empty:
            return empty

        if callable(default_value):
            try:
                return default_value()  # type: ignore[call-arg]
            except Exception as exc:
                raise FieldError(
                    f"An error occurred while calling the default factory for '{self.effective_name}'."
                ) from exc
        return default_value

    def bind(self, parent: typing.Type[typing.Any], name: str) -> None:
        """
        Called when the field is bound to a parent class.

        Things like assigning the field name, and performing any necessary validation
        on the class (parent) it is bound to.
        :param parent: The parent class to which the field is bound.
        :param name: The name of the field.
        """
        self.name = name

    def __set_name__(self, owner: typing.Type[typing.Any], name: str):
        """Assign the field name when the descriptor is initialized on the class."""
        self.bind(owner, name)

    def __delete__(self, instance: typing.Any):
        self.delete_value(instance)

    @typing.overload
    def __get__(
        self,
        instance: typing.Any,
        owner: typing.Optional[typing.Type[typing.Any]],
    ) -> typing.Union[_T, typing.Any]: ...

    @typing.overload
    def __get__(
        self,
        instance: typing.Optional[typing.Any],
        owner: typing.Type[typing.Any],
    ) -> Self: ...

    def __get__(
        self,
        instance: typing.Optional[typing.Any],
        owner: typing.Optional[typing.Type[typing.Any]],
    ) -> typing.Optional[typing.Union[_T, Self]]:
        """Retrieve the field value from an instance or return the default if unset."""
        if instance is None:
            return self

        field_value = self.get_value(instance)
        if not field_value.is_valid:
            # with self._lock:
            return self.set_value(instance, field_value.value, True).value
        return field_value.value

    def __set__(self, instance: typing.Any, value: typing.Any):
        """Set and validate the field value on an instance."""
        if value is empty:
            if self.required:
                raise FieldError(
                    f"'{type(instance).__name__}.{self.effective_name}' is a required field."
                )
            return

        # with self._lock:
        cache_key = _get_cache_key(value)
        if cache_key in self._serialized_cache:
            del self._serialized_cache[cache_key]
        self.set_value(instance, value, not self.lazy)

    def get_value(self, instance: typing.Any) -> Value[_T]:
        """
        Get the field value from an instance.

        :param instance: The instance to which the field belongs.
        :param name: The name of the field.
        :return: The field value gotten from the instance.
        """
        field_name = self.name
        if not field_name:
            raise FieldError(
                f"'{type(self).__name__}' on '{type(instance).__name__}' has no name. Ensure it is bound to a class."
            )

        if hasattr(instance, "__dict__"):
            return instance.__dict__[field_name]
        # For slotted classes
        slotted_name = instance.__slotted_names__[field_name]
        return object.__getattribute__(instance, slotted_name)

    def set_value(
        self,
        instance: typing.Any,
        value: _T,
        validate: bool = True,
    ) -> Value[_T]:
        """
        Set the field's value on an instance, performing validation if required.

        :param instance: The instance to which the field belongs.
        :param value: The field value to set.
        :param validate: If True, validate the value before setting it.
        :return: The set field value.
        """
        field_name = self.name
        if not field_name:
            raise FieldError(
                f"'{type(self).__name__}' on '{type(instance).__name__}' has no name. Ensure it is bound to a class."
            )

        if validate:
            field_value = Value(
                self.validate(value, instance),
                is_valid=True,
            )
        else:
            field_value = Value(value)

        # Store directly in __dict__ to avoid recursion
        if hasattr(instance, "__dict__"):
            instance.__dict__[field_name] = field_value
        else:  # For slotted classes
            slotted_name = instance.__slotted_names__[field_name]
            object.__setattr__(instance, slotted_name, field_value)
        return field_value

    def delete_value(self, instance: typing.Any) -> None:
        """
        Delete the field's value from an instance.

        :param instance: The instance to which the field belongs.
        """
        field_name = self.name
        if not field_name:
            raise FieldError(
                f"'{type(self).__name__}' on '{type(instance).__name__}' has no name. Ensure it is bound to a class."
            )

        if hasattr(instance, "__dict__"):
            del instance.__dict__[field_name]
        else:  # For slotted classes
            slotted_name = instance.__slotted_names__[field_name]
            object.__delattr__(instance, slotted_name)

    def check_type(self, value: typing.Any) -> typing.TypeGuard[_T]:
        """Check if the value is of the expected type."""
        if self.field_type is UndefinedType:
            return True
        return isinstance(value, self.field_type)

    def validate(
        self,
        value: typing.Any,
        instance: typing.Optional[typing.Any],
    ) -> typing.Union[_T, typing.Any]:
        """
        Casts the value to the field's type, validates it, and runs any field validators.

        Override/extend this method to add custom validation logic.

        :param value: The value to validate.
        :param instance: The instance to which the field belongs.
        """
        if value is None and self.allow_null:
            return None

        cache_key = _get_cache_key(value)
        if self._validated_cache.get(cache_key) is not None:
            return self._validated_cache[cache_key]

        if self.check_type(value):
            deserialized = value
        else:
            deserialized = self.deserialize(value)
            if not self.check_type(deserialized):
                raise FieldValidationError(
                    f"'{self.__name__}' expected type '{self.field_type}', but got '{type(deserialized)}'.",
                    self.effective_name,
                )

        if self.validator:
            self.validator(deserialized, self, instance)

        # with self._lock:
        self._validated_cache[cache_key] = deserialized
        return deserialized

    def serialize(
        self,
        value: typing.Any,
        fmt: str,
        context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    ) -> typing.Optional[typing.Any]:
        """
        Serialize the given value to the specified format using the field's serializer.

        :param value: The value to serialize.
        :param fmt: The serialization format.
        :param context: Additional context for serialization.
        """
        if value is None:
            return None

        cache_key = _get_cache_key(value)
        if self._serialized_cache.get(cache_key) is not None:
            return self._serialized_cache[cache_key]

        try:
            serialiazed = self.serializer(fmt, value, self, context)
        except (ValueError, TypeError) as exc:
            raise SerializationError(
                f"Failed to serialize '{type(self).__name__}' value {value!r} to '{fmt}'.",
                self.effective_name,
            ) from exc

        if serialiazed is not None:
            # with self._lock:
            self._serialized_cache[cache_key] = serialiazed
        return serialiazed

    def deserialize(self, value: typing.Any) -> _T:
        """
        Cast the value to the field's specified type, if necessary.

        Converts the field's value to the specified type before it is set on the instance.
        """
        field_type = typing.cast(
            typing.Union[typing.Type[_T], typing.Tuple[typing.Type[_T]]],
            self.field_type,
        )
        try:
            return self.deserializer(self, value)
        except (ValueError, TypeError) as exc:
            raise DeserializationError(
                f"Failed to deserialize value '{value}' to type '{field_type}'.",
                self.effective_name,
            ) from exc

    NO_DEEPCOPY_ARGS: typing.Set[str] = {
        "field_type",
    }
    """
    Indices of arguments that should not be deepcopied when copying the field.

    This is useful for arguments that are immutable or should not be copied to avoid shared state.
    """
    NO_DEEPCOPY_KWARGS: typing.Set[str] = {
        "validators",
        "regex",
        "serializers",
        "deserializer",
        "default",
        "field_type",
    }
    """
    Names of keyword arguments that should not be deepcopied when copying the field.

    This is useful for arguments that are immutable or should not be copied to avoid shared state.
    """

    def __deepcopy__(self, memo):
        args = [
            (copy.deepcopy(arg, memo) if index not in self.NO_DEEPCOPY_ARGS else arg)
            for index, arg in enumerate(self._init_args)
        ]
        kwargs = {
            key: (
                copy.deepcopy(value, memo)
                if value not in self.NO_DEEPCOPY_KWARGS
                else value
            )
            for key, value in self._init_kwargs.items()
        }
        field_copy = self.__class__(*args, **kwargs)
        field_copy.name = self.name
        return field_copy


_Field_co = typing.TypeVar("_Field_co", bound=Field, covariant=True)


class FieldInitKwargs(typing.Generic[_T], typing.TypedDict, total=False):
    """Possible keyword arguments for initializing a field."""

    alias: typing.Optional[str]
    """Optional string for alternative field naming."""
    lazy: bool
    """If True, the field will not be validated until it is accessed."""
    allow_null: bool
    """If True, permits the field to be set to None."""
    required: bool
    """If True, the field must be explicitly provided."""
    validators: typing.Optional[typing.Iterable[FieldValidator[_T]]]
    """A list of validation functions to apply to the field's value."""
    serializers: typing.Optional[typing.Dict[str, FieldSerializer]]
    """A mapping of serialization formats to their respective serializer functions."""
    deserializer: typing.Optional[FieldDeserializer]
    """A deserializer function to convert the field's value to the expected type."""
    default: typing.Union[_T, DefaultFactory, typing.Type[empty], NoneType]
    """A default value for the field to be used if no value is set."""


class AnyField(Field[typing.Any]):
    """Field for handling values of any type."""

    def __init__(self, **kwargs: Unpack[FieldInitKwargs[typing.Any]]):
        kwargs.setdefault("allow_null", True)
        super().__init__(field_type=UndefinedType, **kwargs)


def boolean_deserializer(field: "BooleanField", value: typing.Any) -> bool:
    if value in field.TRUTHY_VALUES:
        return True
    if value in field.FALSY_VALUES:
        return False
    return bool(value)


def boolean_json_serializer(
    value: bool,
    field: "BooleanField",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> bool:
    """Serialize a boolean value to JSON."""
    return value


class BooleanField(Field[bool]):
    """Field for handling boolean values."""

    TRUTHY_VALUES = {
        True,
        1,
        "1",
        iexact("true"),
        iexact("yes"),
    }
    FALSY_VALUES = {  # Use sets for faster lookups
        False,
        0,
        "0",
        iexact("false"),
        iexact("no"),
        iexact("nil"),
        iexact("null"),
        iexact("none"),
    }
    default_deserializer = boolean_deserializer
    default_serializers = {
        "json": boolean_json_serializer,
    }

    def __init__(self, **kwargs: Unpack[FieldInitKwargs[bool]]):
        kwargs.setdefault("allow_null", True)
        super().__init__(field_type=bool, **kwargs)


def build_min_max_value_validators(
    min_value: typing.Optional[SupportsRichComparison],
    max_value: typing.Optional[SupportsRichComparison],
) -> typing.List[FieldValidator[typing.Any]]:
    """Construct min and max value validators."""
    if min_value is None and max_value is None:
        return []
    if min_value is not None and max_value is not None and min_value >= max_value:
        raise ValueError("min_value must be less than max_value")

    validators = []
    if min_value is not None:
        validators.append(field_validators.gte(min_value))
    if max_value is not None:
        validators.append(field_validators.lte(max_value))
    return validators


class FloatField(Field[float]):
    """Field for handling float values."""

    def __init__(
        self,
        *,
        min_value: typing.Optional[float] = None,
        max_value: typing.Optional[float] = None,
        **kwargs: Unpack[FieldInitKwargs[float]],
    ):
        validators = kwargs.get("validators", [])
        validators = typing.cast(typing.Iterable[FieldValidator[float]], validators)
        validators = [
            *validators,
            *build_min_max_value_validators(min_value, max_value),
        ]
        kwargs["validators"] = validators
        super().__init__(
            field_type=float,
            **kwargs,
        )


class IntegerField(Field[int]):
    """Field for handling integer values."""

    def __init__(
        self,
        *,
        min_value: typing.Optional[int] = None,
        max_value: typing.Optional[int] = None,
        **kwargs: Unpack[FieldInitKwargs[int]],
    ):
        validators = kwargs.get("validators", [])
        validators = typing.cast(typing.Iterable[FieldValidator[int]], validators)
        validators = [
            *validators,
            *build_min_max_value_validators(min_value, max_value),
        ]
        kwargs["validators"] = validators
        super().__init__(
            field_type=int,
            **kwargs,
        )


def build_min_max_length_validators(
    min_length: typing.Optional[int],
    max_length: typing.Optional[int],
) -> typing.List[FieldValidator[typing.Any]]:
    """Construct min and max length validators."""
    if min_length is None and max_length is None:
        return []
    if min_length is not None and max_length is not None and min_length <= max_length:
        raise ValueError("min_length cannot be greater than max_length")

    validators = []
    if min_length is not None:
        validators.append(field_validators.min_len(min_length))
    if max_length is not None:
        validators.append(field_validators.max_len(max_length))
    return validators


class StringField(Field[str]):
    """Field for handling string values."""

    DEFAULT_MIN_LENGTH: typing.Optional[int] = None
    """Default minimum length of values."""
    DEFAULT_MAX_LENGTH: typing.Optional[int] = None
    """Default maximum length of values."""

    default_serializers = {
        "json": to_string_serializer,
    }

    def __init__(
        self,
        *,
        min_length: typing.Optional[int] = None,
        max_length: typing.Optional[int] = None,
        trim_whitespaces: bool = True,
        to_lowercase: bool = False,
        to_uppercase: bool = False,
        **kwargs: Unpack[FieldInitKwargs[str]],
    ):
        """
        Initialize the field.

        :param min_length: The minimum length allowed for the field's value.
        :param max_length: The maximum length allowed for the field's value.
        :param trim_whitespaces: If True, leading and trailing whitespaces will be removed.
        :param kwargs: Additional keyword arguments for the field.
        """
        validators = kwargs.get("validators", [])
        validators = typing.cast(typing.Iterable[FieldValidator[str]], validators)
        validators = [
            *validators,
            *build_min_max_length_validators(min_length, max_length),
        ]
        kwargs["validators"] = validators
        super().__init__(field_type=str, **kwargs)
        self.trim_whitespaces = trim_whitespaces
        self.to_lowercase = to_lowercase
        self.to_uppercase = to_uppercase

    def post_init_validate(self):
        super().post_init_validate()
        if self.to_lowercase and self.to_uppercase:
            raise FieldError("`to_lowercase` and `to_uppercase` cannot both be set.")

    def deserialize(self, value: typing.Any) -> str:
        deserialized = super().deserialize(value)
        if self.trim_whitespaces:
            deserialized = deserialized.strip()
        if self.to_lowercase:
            return deserialized.lower()
        if self.to_uppercase:
            return deserialized.upper()
        return deserialized


class DictField(Field[typing.Dict]):
    """Field for handling dictionary values."""

    def __init__(self, **kwargs: Unpack[FieldInitKwargs[typing.Dict]]):
        super().__init__(dict, **kwargs)


class UUIDField(Field[uuid.UUID]):
    """Field for handling UUID values."""

    default_serializers = {
        "json": to_string_serializer,
    }

    def __init__(self, **kwargs: Unpack[FieldInitKwargs[uuid.UUID]]):
        super().__init__(field_type=uuid.UUID, **kwargs)


IterT = typing.TypeVar("IterT", bound=typing.Iterable[typing.Any])


def _get_adder(field_type: typing.Type[IterT]) -> typing.Callable:
    """
    Get the appropriate adder function for the specified iterable type.
    This function returns the method used to add elements to the iterable type.

    Example:
    ```python
    adder = _get_adder(list)
    adder([], 1)  # Adds 1 to the list
    ```
    """
    if issubclass(field_type, list):
        return list.append
    if issubclass(field_type, set):
        return set.add
    if issubclass(field_type, tuple):
        return tuple.__add__
    if issubclass(field_type, frozenset):
        # frozenset is immutable, so we need to create a new frozenset
        # with the new value added
        return lambda frozenset_, value: frozenset(
            frozenset(list(frozenset_) + [value])
        )
    raise TypeError(f"Unsupported iterable type: {field_type}")


def iterable_python_serializer(
    value: IterT,
    field: "IterableField[IterT, _V]",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> IterT:
    """
    Serialize an iterable to a list of serialized values.

    :param value: The iterable to serialize.
    :param field: The field instance to which the iterable belongs.
    :param context: Additional context for serialization.
    :return: The serialized iterable.
    """
    field_type = field.field_type
    serialized = field_type.__new__(field_type)  # type: ignore

    for item in value:
        serialized_item = field.child.serialize(item, fmt="python", context=context)
        field.adder(serialized, serialized_item)
    return serialized


def iterable_json_serializer(
    value: IterT,
    field: "IterableField[IterT, _V]",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> typing.List[typing.Any]:
    """
    Serialize an iterable to JSON compatible format.

    :param value: The iterable to serialize.
    :param field: The field instance to which the iterable belongs.
    :param context: Additional context for serialization.
    :return: The serialized iterable.
    """
    return [field.child.serialize(item, fmt="json", context=context) for item in value]


def iterable_deserializer(
    field: "IterableField[IterT, _V]",
    value: typing.Any,
) -> IterT:
    """
    Deserialize an iterable value to the specified field type.

    :param field_type: The type to which the value should be deserialized.
    :param value: The value to deserialize.
    :param field: The field instance to which the value belongs.
    :return: The deserialized value.
    """
    field_type = field.field_type
    field_type = typing.cast(typing.Type[IterT], field_type)
    deserialized = field_type.__new__(field_type)  # type: ignore

    for item in value:
        deserialized_item = field.child.deserialize(item)
        field.adder(deserialized, deserialized_item)
    return deserialized


def validate_iterable(
    value: IterT,
    field: "IterableField[IterT, _V]",
    instance: typing.Optional[typing.Any],
) -> None:
    """
    Validate the elements of an iterable field.
    This function checks if the elements of the iterable are valid according to the child field's validation rules.
    :param value: The iterable value to validate.
    :param field: The field instance to which the iterable belongs.
    :param instance: The instance to which the field belongs.
    """
    for item in value:
        field.child.validate(item, instance)


class IterableField(typing.Generic[IterT, _V], Field[IterT]):
    """Base class for iterable fields."""

    default_serializers = {
        "python": iterable_python_serializer,
        "json": iterable_json_serializer,
    }
    default_deserializer = iterable_deserializer  # type: ignore
    default_validators = (validate_iterable,)  # type: ignore

    def __init__(
        self,
        field_type: typing.Type[IterT],
        child: typing.Optional[Field[_V]] = None,
        *,
        size: typing.Optional[int] = None,
        **kwargs: Unpack[FieldInitKwargs[IterT]],
    ):
        """
        Initialize the field.

        :param field_type: The expected iterable type for the field.
        :param child: Optional field for validating elements in the field's value.
        :param size: Optional size constraint for the iterable.
        """
        if not is_iterable_type(field_type, exclude=(str, bytes)):
            raise TypeError(
                "Specified type must be an iterable type; excluding str or bytes."
            )

        validators = kwargs.get("validators", [])
        if size is not None:
            validators = typing.cast(typing.Iterable[FieldValidator[IterT]], validators)
            validators = [
                *validators,
                field_validators.max_len(size),
            ]
            kwargs["validators"] = validators
        super().__init__(field_type=field_type, **kwargs)  # type: ignore
        self.child = child or AnyField()
        self.adder = _get_adder(field_type)  # type: ignore

    def post_init_validate(self):
        super().post_init_validate()
        if not isinstance(self.child, Field):
            raise TypeError(
                f"'child' must be a field instance , not {type(self.child).__name__}."
            )

    def check_type(self, value: typing.Any) -> typing.TypeGuard[IterT]:
        if not super().check_type(value):
            return False

        if value and self.child.field_type is not UndefinedType:
            for item in value:
                if not self.child.check_type(item):
                    return False
        return True


class ListField(IterableField[typing.List[_V], _V]):
    """Field for lists, with optional validation of list elements through the `child` field."""

    def __init__(
        self,
        child: typing.Optional[Field[_V]] = None,
        *,
        size: typing.Optional[int] = None,
        **kwargs: Unpack[FieldInitKwargs[typing.List[_V]]],
    ):
        super().__init__(
            field_type=list,
            child=child,
            size=size,
            **kwargs,
        )


class SetField(IterableField[typing.Set[_V], _V]):
    """Field for sets, with optional validation of set elements through the `child` field."""

    def __init__(
        self,
        child: typing.Optional[Field[_V]] = None,
        *,
        size: typing.Optional[int] = None,
        **kwargs: Unpack[FieldInitKwargs[typing.Set[_V]]],
    ):
        super().__init__(
            field_type=set,
            child=child,
            size=size,
            **kwargs,
        )


class TupleField(IterableField[typing.Tuple[_V], _V]):
    """Field for tuples, with optional validation of tuple elements through the `child` field."""

    def __init__(
        self,
        child: typing.Optional[Field[_V]] = None,
        *,
        size: typing.Optional[int] = None,
        **kwargs: Unpack[FieldInitKwargs[typing.Tuple[_V]]],
    ):
        super().__init__(
            field_type=tuple,
            child=child,
            size=size,
            **kwargs,
        )


def get_quantizer(dp: int) -> decimal.Decimal:
    """Get the quantizer for the specified number of decimal places."""
    if dp < 0:
        raise ValueError("Decimal places (dp) must be a non-negative integer.")
    return decimal.Decimal(f"0.{'0' * (dp - 1)}1") if dp > 0 else decimal.Decimal("1")


class DecimalField(Field[decimal.Decimal]):
    """Field for handling decimal values."""

    default_serializers = {
        "json": to_string_serializer,
    }

    def __init__(
        self,
        dp: typing.Optional[int] = None,
        **kwargs: Unpack[FieldInitKwargs[decimal.Decimal]],
    ):
        """
        Initialize the field.

        :param dp: The number of decimal places to round the field's value to.
        :param kwargs: Additional keyword arguments for the field.
        """
        super().__init__(field_type=decimal.Decimal, **kwargs)
        if dp is not None and dp < 0:
            raise ValueError("Decimal places (dp) must be a non-negative integer.")
        self.dp = int(dp) if dp is not None else None
        self._quantizer = get_quantizer(self.dp) if self.dp is not None else None

    def deserialize(self, value) -> decimal.Decimal:
        deserialized = super().deserialize(value)
        if self.dp is not None:
            self._quantizer = typing.cast(decimal.Decimal, self._quantizer)
            return deserialized.quantize(self._quantizer)
        return deserialized


email_validator = field_validators.pattern(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    message="'{name}' must be a valid email address.",
)


class EmailField(StringField):
    """Field for handling email addresses."""

    default_validators = (email_validator,)

    def __init__(
        self,
        *,
        min_length=None,
        max_length=None,
        trim_whitespaces=True,
        to_lowercase=True,  # Field prefers to store email values in lowercase
        to_uppercase=False,
        **kwargs,
    ):
        super().__init__(
            min_length=min_length,
            max_length=max_length,
            trim_whitespaces=trim_whitespaces,
            to_lowercase=to_lowercase,
            to_uppercase=to_uppercase,
            **kwargs,
        )


def url_deserializer(
    field: Field,
    value: typing.Any,
) -> typing.Any:
    """Deserialize URL data to the specified type."""
    return parse_url(str(value))


class URLField(Field[Url]):
    """Field for handling URL values."""

    default_serializers = {
        "json": to_string_serializer,
    }
    default_deserializer = url_deserializer

    def __init__(self, **kwargs: Unpack[FieldInitKwargs[Url]]):
        super().__init__(field_type=Url, **kwargs)


class ChoiceField(Field[_T]):
    """Field for with predefined choices for values."""

    def __init__(
        self,
        field_type: typing.Type[_T],
        *,
        choices: typing.Iterable[_T],
        **kwargs: Unpack[FieldInitKwargs[_T]],
    ) -> NoneType:
        if len(set(choices)) < 2:
            raise ValueError("At least two unique choices are required.")
        validators = kwargs.get("validators", [])
        validators = typing.cast(typing.Iterable[FieldValidator[_T]], validators)
        validators = [
            *validators,
            field_validators.in_(choices),
        ]
        kwargs["validators"] = validators
        super().__init__(field_type=field_type, **kwargs)


class StringChoiceField(StringField, ChoiceField[str]):
    """String field with predefined choices for values."""

    pass


class IntegerChoiceField(IntegerField, ChoiceField[int]):
    """Integer field with predefined choices for values."""

    pass


class FloatChoiceField(FloatField, ChoiceField[float]):
    """Float field with predefined choices for values."""

    pass


def json_deserializer(field: Field, value: typing.Any) -> typing.Any:
    """Deserialize JSON data to the specified type."""
    return json.loads(json.dumps(value))


class JSONField(AnyField):
    """Field for handling JSON data."""

    default_deserializer = json_deserializer


hex_color_validator = field_validators.pattern(
    r"^#(?:[0-9a-fA-F]{3,4}){1,2}$",
    message="'{name}' must be a valid hex color code.",
)


class HexColorField(StringField):
    """Field for handling hex color values."""

    # DEFAULT_MIN_LENGTH = 4
    # DEFAULT_MAX_LENGTH = 9
    default_validators = (hex_color_validator,)


rgb_color_validator = field_validators.pattern(
    r"^rgb[a]?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*(\d{1,3})\s*)?\)$",
    message="'{name}' must be a valid RGB color code.",
)


class RGBColorField(StringField):
    """Field for handling RGB color values."""

    # DEFAULT_MAX_LENGTH = 38
    default_validators = (rgb_color_validator,)

    def __init__(
        self,
        *,
        min_length=None,
        max_length=None,
        trim_whitespaces=True,
        **kwargs,
    ):
        # Field enforces lowercase for RGB color values
        kwargs["to_lowercase"] = True
        kwargs["to_uppercase"] = False
        super().__init__(
            min_length=min_length,
            max_length=max_length,
            trim_whitespaces=trim_whitespaces,
            **kwargs,
        )


hsl_color_validator = field_validators.pattern(
    r"^hsl[a]?\(\s*(\d{1,3})\s*,\s*(\d{1,3})%?\s*,\s*(\d{1,3})%?\s*(?:,\s*(\d{1,3})\s*)?\)$",
    message="'{name}' must be a valid HSL color code.",
)


class HSLColorField(StringField):
    """Field for handling HSL color values."""

    # DEFAULT_MAX_LENGTH = 40
    default_validators = (hsl_color_validator,)

    def __init__(
        self,
        *,
        min_length=None,
        max_length=None,
        trim_whitespaces=True,
        **kwargs,
    ):
        # Field enforces lowercase for HSL color values
        kwargs["to_lowercase"] = True
        kwargs["to_uppercase"] = False
        super().__init__(
            min_length=min_length,
            max_length=max_length,
            trim_whitespaces=trim_whitespaces,
            **kwargs,
        )


slug_validator = field_validators.pattern(
    r"^[a-zA-Z0-9_-]+$",
    message="'{name}' must be a valid slug.",
)


class SlugField(StringField):
    """Field for URL-friendly strings."""

    default_validators = (slug_validator,)


def ip_address_deserializer(field: Field, value: typing.Any) -> typing.Any:
    """Deserialize IP address data to an IP address object."""
    return ipaddress.ip_address(value)


class IPAddressField(
    Field[typing.Union[ipaddress.IPv4Address, ipaddress.IPv6Address]],
):
    """Field for handling IP addresses."""

    default_serializers = {
        "json": to_string_serializer,
    }
    default_deserializer = ip_address_deserializer

    def __init__(
        self,
        **kwargs: Unpack[
            FieldInitKwargs[typing.Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]
        ],
    ):
        super().__init__(
            field_type=(
                ipaddress.IPv4Address,
                ipaddress.IPv6Address,
            ),
            **kwargs,
        )


def timedelta_deserializer(field: Field, value: typing.Any) -> datetime.timedelta:
    """Deserialize duration data to time delta."""
    duration = parse_duration(value)
    if duration is None:
        raise DeserializationError(f"Invalid duration value - {value}")
    return duration


class DurationField(Field[datetime.timedelta]):
    """Field for handling duration values."""

    default_serializers = {
        "json": to_string_serializer,
    }
    default_deserializer = timedelta_deserializer

    def __init__(self, **kwargs: Unpack[FieldInitKwargs[datetime.timedelta]]):
        super().__init__(field_type=datetime.timedelta, **kwargs)


TimeDeltaField = DurationField


def timezone_deserializer(field: Field, value: typing.Any) -> zoneinfo.ZoneInfo:
    """Deserialize timezone data to `zoneinfo.ZoneInfo` object."""
    return zoneinfo.ZoneInfo(value)


class TimeZoneField(Field[datetime.tzinfo]):
    """Field for handling timezone values."""

    default_serializers = {
        "json": to_string_serializer,
    }
    default_deserializer = timezone_deserializer

    def __init__(self, **kwargs: Unpack[FieldInitKwargs[datetime.tzinfo]]):
        super().__init__(field_type=datetime.tzinfo, **kwargs)


DatetimeType = typing.TypeVar(
    "DatetimeType",
    bound=typing.Union[datetime.date, datetime.datetime, datetime.time],
)


def datetime_serializer(
    value: DatetimeType,
    field: "BaseDateTimeField[DatetimeType]",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> str:
    """Serialize a datetime object to a string."""
    return value.strftime(field.output_format)


class BaseDateTimeField(Field[DatetimeType]):
    """Mixin base for datetime fields."""

    DEFAULT_OUTPUT_FORMAT: str = "%Y-%m-%d %H:%M:%S%z"
    default_serializers = {
        "json": datetime_serializer,
    }

    def __init__(
        self,
        field_type: typing.Type[DatetimeType],
        *,
        input_formats: typing.Optional[typing.Iterable[str]] = None,
        output_format: typing.Optional[str] = None,
        **kwargs: Unpack[FieldInitKwargs[DatetimeType]],
    ):
        """
        Initialize the field.

        :param input_formats: Possible expected input format (ISO or RFC) for the date value.
            If not provided, the field will attempt to parse the date value
            itself, which may be slower.

        :param output_format: The preferred output format for the date value.
        :param kwargs: Additional keyword arguments for the field.
        """
        super().__init__(field_type=field_type, **kwargs)  # type: ignore
        self.input_formats = input_formats
        self.output_format = output_format or self.DEFAULT_OUTPUT_FORMAT


def iso_date_deserializer(
    field: BaseDateTimeField[datetime.date],
    value: str,
) -> datetime.date:
    """Parse a date string in ISO format."""
    return iso_parse(value, fmt=field.input_formats).date()


def iso_time_deserializer(
    field: BaseDateTimeField[datetime.time],
    value: str,
) -> datetime.time:
    """Parse a time string in ISO format."""
    return iso_parse(value, fmt=field.input_formats).time()


class DateField(BaseDateTimeField[datetime.date]):
    """Field for handling date values."""

    DEFAULT_OUTPUT_FORMAT = "%Y-%m-%d"
    default_deserializer = iso_date_deserializer

    def __init__(
        self,
        *,
        input_formats: typing.Optional[typing.Iterable[str]] = None,
        output_format: typing.Optional[str] = None,
        **kwargs: Unpack[FieldInitKwargs[datetime.date]],
    ):
        super().__init__(
            field_type=datetime.date,
            input_formats=input_formats,
            output_format=output_format,
            **kwargs,
        )


class TimeField(BaseDateTimeField[datetime.time]):
    """Field for handling time values."""

    DEFAULT_OUTPUT_FORMAT = "%H:%M:%S.%s"
    default_deserializer = iso_time_deserializer

    def __init__(
        self,
        *,
        input_formats: typing.Optional[typing.Iterable[str]] = None,
        output_format: typing.Optional[str] = None,
        **kwargs: Unpack[FieldInitKwargs[datetime.time]],
    ):
        super().__init__(
            field_type=datetime.time,
            input_formats=input_formats,
            output_format=output_format,
            **kwargs,
        )


def datetime_deserializer(
    field: BaseDateTimeField[datetime.datetime],
    value: str,
) -> datetime.datetime:
    """Parse a datetime string in ISO format."""
    return iso_parse(value, fmt=field.input_formats)


class DateTimeField(BaseDateTimeField[datetime.datetime]):
    """Field for handling datetime values."""

    DEFAULT_OUTPUT_FORMAT = "%Y-%m-%d %H:%M:%S%z"
    default_deserializer = datetime_deserializer

    def __init__(
        self,
        *,
        tz: typing.Optional[typing.Union[datetime.tzinfo, str]] = None,
        input_formats: typing.Optional[typing.Iterable[str]] = None,
        output_format: typing.Optional[str] = None,
        **kwargs: Unpack[FieldInitKwargs[datetime.datetime]],
    ):
        """
        Initialize the field.

        :param tz: The timezone to use for the datetime value. If this set,
            the datetime value will be represented in this timezone.

        :param input_format: Possible expected input format (ISO or RFC) for the datetime value.
            If not provided, the field will attempt to parse the datetime value
            itself, which may be slower.

        :param output_format: The preferred output format for the datetime value.
        :param kwargs: Additional keyword arguments for the field.
        """
        super().__init__(
            field_type=datetime.datetime,
            input_formats=input_formats,
            output_format=output_format,
            **kwargs,
        )
        self.tz = timezone_deserializer(self, tz) if tz else None

    def deserialize(self, value: typing.Any) -> datetime.datetime:
        deserialized = super().deserialize(value)
        if self.tz:
            if deserialized.tzinfo:
                deserialized = deserialized.astimezone(self.tz)
            else:
                deserialized = deserialized.replace(tzinfo=self.tz)
        return deserialized


def bytes_serializer(
    value: bytes,
    field: "BytesField",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> str:
    """Serialize bytes to a string."""
    return base64.b64encode(value).decode(encoding=field.encoding)


def bytes_deserializer(
    field: "BytesField",
    value: typing.Any,
) -> bytes:
    """Deserialize an object or base64-encoded string to bytes."""
    if isinstance(value, str):
        try:
            return base64.b64decode(value.encode(encoding=field.encoding))
        except (ValueError, TypeError) as exc:
            raise DeserializationError(
                f"Invalid base64 string for bytes: {value!r}"
            ) from exc
    return bytes(value)


class BytesField(Field[bytes]):
    """Field for handling byte values."""

    default_serializers = {
        "json": bytes_serializer,
    }
    default_deserializer = bytes_deserializer

    def __init__(
        self, encoding: str = "utf-8", **kwargs: Unpack[FieldInitKwargs[bytes]]
    ):
        """
        Initialize the field.

        :param encoding: The encoding to use when encoding/decoding byte strings.
        :param kwargs: Additional keyword arguments for the field.
        """
        super().__init__(field_type=bytes, **kwargs)
        self.encoding = encoding


IOType = typing.TypeVar("IOType", bound=io.IOBase)


class BaseIOField(Field[IOType]):
    """Base field for handling I/O objects."""

    default_serializers = {
        "json": unsupported_serializer,
    }
    default_deserializer = unsupported_deserializer  # type: ignore


def get_file_name(file_obj: io.BufferedIOBase) -> str:
    """Get the name of the file object."""
    if hasattr(file_obj, "name"):
        return file_obj.name.split(".")[-1].lower()  # type: ignore
    return ""


def get_file_size(file_obj: io.BufferedIOBase) -> int:
    """Get the size of the file object in bytes."""
    if hasattr(file_obj, "seek") and hasattr(file_obj, "tell"):
        file_obj.seek(0, 2)  # Move to end of file to check size
        size = file_obj.tell()
        file_obj.seek(0)  # Reset file pointer to the beginning
        return size
    return 0


def file_serializer(
    file_obj: io.BufferedIOBase,
    field: "Field",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> typing.Dict[str, typing.Any]:
    """Serialize the file object to a dictionary."""
    return {
        "name": get_file_name(file_obj),
        "size": get_file_size(file_obj),
    }


class FileField(BaseIOField[io.BufferedIOBase]):
    """Field for handling files"""

    default_serializers = {
        "json": file_serializer,
    }

    def __init__(
        self,
        max_size: typing.Optional[int] = None,
        allowed_types: typing.Optional[typing.Iterable[str]] = None,
        **kwargs: Unpack[FieldInitKwargs],
    ):
        """
        Initialize the field.

        :param max_size: The maximum size of the file in bytes.
        :param allowed_types: A list of allowed file types or extensions.
        :param kwargs: Additional keyword arguments for the field.
        """
        validators = kwargs.get("validators", [])
        validators = typing.cast(
            typing.Iterable[FieldValidator[io.BufferedIOBase]], validators
        )
        if max_size is not None:
            validators = [
                *validators,
                field_validators.lte(max_size, pre_validation_hook=get_file_size),
            ]
        if allowed_types:
            validators = [
                *validators,
                field_validators.pattern(
                    r"^.*\.(?:" + "|".join(allowed_types) + r")$",
                    pre_validation_hook=get_file_name,
                ),
            ]
        kwargs["validators"] = validators
        super().__init__(field_type=io.BufferedIOBase, **kwargs)

    def __delete__(self, instance: typing.Any):
        value = self.__get__(instance, type(instance))
        if value and not value.closed:
            value.close()
        super().__delete__(instance)


# These phone number fields are implemented with dependencies on the `phonenumbers` library.
# Hence, the fields are only available when the `phonenumbers` library is installed.
# Here we use a ghost field approach to make the fields available even when the dependencies.
# Although, a DependencyRequired is raised when the fields are initialized without the required
# dependencies installed. This allows other fields in this module to be useable even without
# the dependencies for these fields being installed.
@depends_on({"phonenumbers": "phonenumbers"})
def _PhoneNumberField(**kwargs): ...


@depends_on({"phonenumbers": "phonenumbers"})
def _PhoneNumberStringField(**kwargs): ...


PhoneNumberField = _PhoneNumberField  # type: ignore
PhoneNumberField.__name__ = "PhoneNumberField"
PhoneNumberStringField = _PhoneNumberStringField  # type: ignore
PhoneNumberStringField.__name__ = "PhoneNumberStringField"

# Makes sure the ghost phonenumber fields are unavailable for import using these names
del _PhoneNumberField, _PhoneNumberStringField


try:
    # This will override the ghost fields above if the `phonenumbers` library is installed
    # and the library is successfully imported. If the `phonenumbers` library is not installed,
    # the fields below will not be available and the ghost phonenumber fields above will be used instead.
    # and a proper warning/error will be displayed when the fields are initialized without the required
    # dependencies installed.
    # This also tricks the typing system into thinking the phonenumber fields are classes even when
    # the ghost phonenumber fields are function-based versions, thereby improving typing for the field.

    # This approach is verbose but this is the best balance I could find as regards proper typing for
    # the field, and field dependency management
    from phonenumbers import (  # type: ignore[import]
        PhoneNumber,
        parse as parse_number,
        format_number,
        PhoneNumberFormat,
    )

    def phone_number_serializer(
        value: PhoneNumber,
        field: "PhoneNumberField",
        context: typing.Optional[typing.Dict[str, typing.Any]],
    ) -> str:
        """Serialize a phone number object to a string format."""
        output_format = typing.cast(int, field.output_format)
        return format_number(value, output_format)

    def phone_number_deserializer(
        field: "PhoneNumberField",
        value: typing.Any,
    ) -> PhoneNumber:
        """Deserialize a string to a phone number object."""
        return parse_number(value)

    class PhoneNumberField(Field[PhoneNumber]):
        """Phone number object field."""

        DEFAULT_OUTPUT_FORMAT = PhoneNumberFormat.E164
        default_serializers = {
            "json": phone_number_serializer,
        }
        default_deserializer = phone_number_deserializer

        def __init__(
            self,
            output_format: typing.Optional[int] = None,
            **kwargs: Unpack[FieldInitKwargs[PhoneNumber]],
        ):
            """
            Initialize the field.

            :param output_format: The preferred output format for the phone number value.
                E.g. PhoneNumberFormat.E164, PhoneNumberFormat.INTERNATIONAL, etc.
                See the `phonenumbers` library for more details.
            :param kwargs: Additional keyword arguments for the field.
            """
            super().__init__(field_type=PhoneNumber, **kwargs)
            self.output_format = output_format or self.DEFAULT_OUTPUT_FORMAT

    def phone_number_string_serializer(
        value: PhoneNumber,
        field: "PhoneNumberStringField",
        context: typing.Optional[typing.Dict[str, typing.Any]],
    ) -> str:
        """Serialize a phone number object to a string format."""
        return format_number(value, field.output_format)

    def phone_number_string_deserializer(
        field: "PhoneNumberStringField",
        value: typing.Any,
    ) -> str:
        """Deserialize a string to a phone number object."""
        return format_number(parse_number(value), field.output_format)

    class PhoneNumberStringField(StringField):
        """Phone number string field"""

        DEFAULT_OUTPUT_FORMAT = PhoneNumberFormat.E164
        default_serializers = {
            "json": phone_number_string_serializer,
        }
        default_deserializer = phone_number_string_deserializer

        def __init__(
            self,
            output_format: typing.Optional[int] = None,
            **kwargs: Unpack[FieldInitKwargs],
        ):
            """
            Initialize the field.

            :param output_format: The preferred output format for the phone number value.
                E.g. PhoneNumberFormat.E164, PhoneNumberFormat.INTERNATIONAL, etc.
                See the `phonenumbers` library for more details.
            :param kwargs: Additional keyword arguments for the field.
            """
            super().__init__(max_length=20, **kwargs)
            self.output_format = output_format or self.DEFAULT_OUTPUT_FORMAT

except ImportError:
    pass


__all__ = [
    "empty",
    "UndefinedType",
    "FieldError",
    "Field",
    "Factory",
    "FieldInitKwargs",
    "AnyField",
    "BooleanField",
    "StringField",
    "FloatField",
    "IntegerField",
    "DictField",
    "ListField",
    "SetField",
    "TupleField",
    "DecimalField",
    "EmailField",
    "URLField",
    "ChoiceField",
    "StringChoiceField",
    "IntegerChoiceField",
    "FloatChoiceField",
    "JSONField",
    "HexColorField",
    "RGBColorField",
    "HSLColorField",
    "IPAddressField",
    "SlugField",
    "DateField",
    "TimeField",
    "DurationField",
    "TimeDeltaField",
    "DateTimeField",
    "BytesField",
    "BaseIOField",
    "FileField",
    "PhoneNumberField",
    "PhoneNumberStringField",
]
