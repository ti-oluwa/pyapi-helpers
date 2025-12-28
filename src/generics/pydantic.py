from src.dependencies import deps_required

deps_required(
    {
        "pydantic": "https://pydantic-docs.helpmanual.io/",
    }
)

import copy
import typing
import pydantic
from pydantic.dataclasses import dataclass
from pydantic_core import PydanticUndefined, PydanticCustomError
import functools
import weakref

ModelT = typing.TypeVar("ModelT", bound=pydantic.BaseModel)
DepthT: typing.TypeAlias = typing.Union[bool, int]
PrefixT: typing.TypeAlias = str

DEFAULT_PREFIX = "Partial"
TOP_LEVEL = 0

# Cache for created models
_model_cache = weakref.WeakValueDictionary()


@typing.overload
def partial(
    model_cls: typing.Type[ModelT],  # noqa :ARG006
) -> typing.Type[ModelT]: ...


@typing.overload
def partial(
    *,
    include: typing.Optional[typing.List[str]] = None,
    depth: DepthT = TOP_LEVEL,
    prefix: typing.Optional[PrefixT] = None,
) -> typing.Callable[[typing.Type[ModelT]], typing.Type[ModelT]]: ...


@typing.overload
def partial(
    *,
    exclude: typing.Optional[typing.List[str]] = None,
    depth: DepthT = TOP_LEVEL,
    prefix: typing.Optional[PrefixT] = None,
) -> typing.Callable[[typing.Type[ModelT]], typing.Type[ModelT]]: ...


def _make_optional(
    field: pydantic.fields.FieldInfo,
    default: typing.Any,
    depth: DepthT,
    prefix: typing.Optional[PrefixT],
) -> tuple[object, pydantic.fields.FieldInfo]:
    """Helper function to make a field optional.

    :param field: The field to make optional
    :param default: Default value for the optional field
    :param depth: How deep to make nested models optional
    :param prefix: String to prepend to nested model names
    :returns: Tuple of (annotation, field_info)
    :raises ValueError: If depth is negative
    """
    tmp_field = copy.deepcopy(field)
    annotation = field.annotation or typing.Any

    if isinstance(depth, int) and depth < 0:
        raise ValueError("Depth cannot be negative")

    if (
        isinstance(annotation, type)
        and issubclass(annotation, pydantic.BaseModel)  # type: ignore[unreachable]
        and depth
    ):
        model_key = (annotation, depth, prefix)
        if model_key not in _model_cache:
            _model_cache[model_key] = partial(
                depth=depth - 1 if isinstance(depth, int) else depth,
                prefix=prefix,
            )(annotation)
        annotation = _model_cache[model_key]

    tmp_field.annotation = typing.Optional[annotation]  # type: ignore[assignment]
    tmp_field.default = default
    return tmp_field.annotation, tmp_field


def partial(  # type: ignore[no-redef]
    model_cls: typing.Optional[typing.Type[ModelT]] = None,  # noqa :ARG006
    *,
    include: typing.Optional[typing.List[str]] = None,
    exclude: typing.Optional[typing.List[str]] = None,
    depth: DepthT = TOP_LEVEL,
    prefix: typing.Optional[PrefixT] = None,
) -> typing.Callable[[typing.Type[ModelT]], typing.Type[ModelT]]:
    """
    Create a partial Pydantic model with optional fields.

    This decorator allows you to create a new model based on an existing one,
    where specified fields become optional. It's particularly useful for update
    operations where only some fields may be provided.

    :param model_cls: The Pydantic model to make partial
    :param include: List of field names to make optional. If None, all fields are included
    :param exclude: List of field names to keep required. If None, no fields are excluded
    :param depth: How deep to make nested models optional:
        - 0: Only top-level fields
        - n: n levels deep
        - True: All levels
    :param prefix: String to prepend to the new model's name
    :returns: A decorator function that creates a new model with optional fields
    :raises ValueError: If both include and exclude are provided
    :raises ValueError: If depth is negative

    Example:
        ```python
        @partial
        class UserUpdateSchema(UserSchema):
            pass

        # Make specific fields optional
        @partial(include=['name', 'email'])
        class UserPartialSchema(UserSchema):
            pass

        # Keep certain fields required
        @partial(exclude=['id'])
        class UserUpdateSchema(UserSchema):
            pass
        ```

    - Uses model caching to avoid recreating identical partial models
    """
    if include is not None and exclude is not None:
        raise ValueError("Cannot specify both include and exclude")

    if exclude is None:
        exclude = []

    @functools.lru_cache(maxsize=32)
    def create_partial_model(model_cls: typing.Type[ModelT]) -> typing.Type[ModelT]:
        """
        Create a new Pydantic model with optional fields.

        Cached model creation to avoid regenerating same models.
        """
        fields = model_cls.model_fields
        if include is None:
            fields = fields.items()
        else:
            fields = ((k, v) for k, v in fields.items() if k in include)

        return pydantic.create_model(
            f"{prefix or ''}{model_cls.__name__}",
            __base__=model_cls,
            __module__=model_cls.__module__,
            **{
                field_name: _make_optional(
                    field_info,
                    default=field_info.default
                    if field_info.default is not PydanticUndefined
                    else None,
                    depth=depth,
                    prefix=prefix,
                )
                for field_name, field_info in fields
                if exclude is None or field_name not in exclude
            },  # type: ignore[no-any-return]
        )  # type: ignore[no-any-return]

    if model_cls is None:
        return create_partial_model
    return create_partial_model(model_cls)  # type: ignore[no-any-return]


@dataclass(frozen=True)
class _ModelConfig(typing.Generic[ModelT]):
    """Configuration for partial model creation."""

    model: typing.Type[ModelT]
    depth: DepthT
    prefix: PrefixT


def _create_model_config(*args: typing.Any) -> _ModelConfig:
    """
    Factory function to create and validate model configuration.

    :raises TypeError: If arguments are invalid
    """
    if not args:
        raise TypeError("ModelT type argument is required")

    if len(args) > 3:
        raise TypeError(f"Expected at most 3 arguments, got {len(args)}")

    model, *rest = args  # type: ignore[assignment]
    if not (isinstance(model, type) and issubclass(model, pydantic.BaseModel)):
        raise TypeError(f"Expected BaseModel subclass, got {type(model)}")

    if not rest:
        return _ModelConfig(model, TOP_LEVEL, DEFAULT_PREFIX)

    depth = rest[0]
    if not isinstance(depth, (int, bool)):
        if not isinstance(depth, str):
            raise TypeError(
                f"Expected int, bool or str for depth/prefix, got {type(depth)}"
            )
        # Case where first arg is prefix
        return _ModelConfig(model, TOP_LEVEL, depth)

    prefix = rest[1] if len(rest) > 1 else DEFAULT_PREFIX
    if not isinstance(prefix, str):
        raise TypeError(f"Expected str for prefix, got {type(prefix)}")

    return _ModelConfig(model, depth, prefix)


class Partial(typing.Generic[ModelT]):
    """
    Generic Type for creating partial Pydantic models.

    Supports three forms of instantiation:
    1. Partial[ModelT]  # Uses default depth and prefix
    2. Partial[ModelT, depth]  # Uses default prefix
    3. Partial[ModelT, depth, prefix]
    4. Partial[ModelT, prefix]  # Uses default depth

    :param ModelT: The Pydantic model to make partial
    :param depth: How deep to make fields optional (int, bool)
    :param prefix: Prefix for the generated model name (str)

    Example:
        ```python
        class User(BaseModel):
            name: str
            age: int

        # These are all valid:
        PartialUser = Partial[User]  # depth=0, prefix="Partial"
        UpdateUser = Partial[User, "Update"]  # depth=0, prefix="Update"
        DeepUpdateUser = Partial[User, True, "Update"]  # All nested fields optional
        ```
    """

    def __class_getitem__(  # type: ignore[override]
        cls,
        wrapped: typing.Union[typing.Type[ModelT], typing.Tuple[typing.Any, ...]],
    ) -> typing.Type[ModelT]:
        """Converts model to a partial model with optional fields."""
        args = wrapped if isinstance(wrapped, tuple) else (wrapped,)
        config = _create_model_config(*args)

        return partial(
            depth=config.depth,
            prefix=config.prefix,
        )(config.model)  # type: ignore[no-any-return, return-value]

    def __new__(
        cls,
        *args: object,  # noqa :ARG003
        **kwargs: object,  # noqa :ARG003
    ) -> "Partial[ModelT]":
        """Cannot instantiate.

        :raises TypeError: Direct instantiation not allowed.
        """
        raise TypeError("Cannot instantiate abstract Partial class.")

    def __init_subclass__(
        cls,
        *args: object,
        **kwargs: object,
    ) -> typing.NoReturn:
        """Cannot subclass.

        :raises TypeError: Subclassing not allowed.
        """
        raise TypeError("Cannot subclass {}.Partial".format(cls.__module__))


def parse_bool_like(v: typing.Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, str):
        v = v.strip().lower()
        if v in {
            "true",
            "1",
            "yes",
            "y",
            "on",
            "enabled",
        }:
            return True
        elif v in {
            "false",
            "0",
            "no",
            "n",
            "none",
            "null",
            "nil",
            "n/a",
            "off",
            "disabled",
        }:
            return False
    if isinstance(v, int):
        return bool(v)
    raise PydanticCustomError(
        "bool_like",
        "Invalid value for boolean-like field: '{value}'. Expected 'true', 'false', '1', '0', 'yes', 'no', 'y', 'n' or an integer",
        {"value": v, "type": type(v).__name__},  # type: ignore[arg-type] # noqa: F821
    )


BoolLike = typing.Annotated[
    bool,
    pydantic.PlainValidator(
        parse_bool_like,
        json_schema_input_type=typing.Union[str, int, bool],
    ),
]
