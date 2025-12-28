import typing
import sqlalchemy as sa
from sqlalchemy import orm


mapper_registry = orm.registry()


@mapper_registry.as_declarative_base()
class ModelBase:
    """
    Declarative base for SQLAlchemy model.
    """

    def __unicode__(self) -> str:
        return "[%s(%s)]" % (
            self.__class__.__name__,
            ", ".join(
                "%s=%s" % (k, self.__dict__[k])
                for k in sorted(self.__dict__)
                if not k.startswith("_sa_")
            ),
        )


ModelTco = typing.TypeVar("ModelTco", bound=ModelBase, covariant=True)


def get_app_name(model: typing.Type[ModelTco]) -> typing.Optional[str]:
    """
    Get the name of the app in which the model is defined.

    Uses the `app_name` attribute if defined in the parent module.
    If not defined, uses the last part of the parent module name.

    Specifying `app=False` in the parent module will exclude the model from the app.

    :param model: Model class
    """
    try:
        module_name: str = model.__module__
    except AttributeError:
        # Not a class or module
        return

    parent_name = module_name.rsplit(".", maxsplit=1)[0]
    if not parent_name:
        return None

    try:
        apps_module = __import__(parent_name + ".apps", fromlist=["app_name"], level=0)
    except ModuleNotFoundError:
        return None

    return getattr(apps_module, "app_name", parent_name).rsplit(".", maxsplit=1)[-1]


def _auto_tablename(model: typing.Type[ModelTco]) -> typing.Type[ModelTco]:
    """Add a declarative attribute to auto-generate the table name for the model"""
    # Check if the class is mapped or already has a __tablename__
    # This is to avoid the warning thrown when hasattr(model, "__tablename__")
    # is done on a model with the __tablename__ as an already `declared_attr`
    if sa.inspect(model, raiseerr=False) is not None:
        return model

    @orm.declared_attr  # type: ignore
    def _tablename(model: typing.Type[ModelTco]) -> str:
        import inflection  # type: ignore[import]

        app_name = get_app_name(model)
        model_name = inflection.tableize(model.__name__)

        if not app_name:
            return model_name
        return f"{app_name}__{model_name}"

    setattr(model, "__tablename__", _tablename)
    return model


class ModelBaseMeta(orm.DeclarativeMeta):
    """Metaclass for SQLAlchemy ModelBase"""

    def __new__(cls, *args, **kwargs) -> typing.Type[ModelBase]:
        attrs = kwargs or args[2]
        new_cls = super().__new__(cls, *args, **kwargs)
        auto_tablename = getattr(new_cls, "__auto_tablename__", False)
        tablename = getattr(new_cls, "__tablename__", None)
        # Since `__abstract__` is True by default, we need to set it explicitly
        # to False, in classes where it is not defined, especially subclasses
        setattr(new_cls, "__abstract__", attrs.get("__abstract__", False))

        new_cls = typing.cast(typing.Type[ModelBase], new_cls)
        if auto_tablename:
            if tablename is not None:
                raise RuntimeError(
                    f"Cannot set both `__auto_tablename__` and `__tablename__` on {new_cls}.\n "
                    "Set __auto_tablename__ to False to use a custom table name."
                )

            return _auto_tablename(new_cls)
        return new_cls

    def __iter__(cls):
        if hasattr(cls, "__mapper__"):
            values = cls.__mapper__.columns  # type: ignore
        else:
            values = vars(cls)

        for key, value in values.items():
            if isinstance(value, sa.Column):
                yield key, value


class Model(ModelBase, metaclass=ModelBaseMeta):
    """
    Abstract base SQLAlchemy model.

    Intended to be used as a base class for all models in the application.

    Subclasses can be used as dataclasses by also inheriting from `orm.MappedAsDataclass`.

    Note: Subclasses should define the `__tablename__` attribute to specify the table name.
    or set `__auto_tablename__` to True to auto-generate the table name based on the model and app name.

    By default;
    ```python

    class <ModelName>(Model):
        __tablename__ = "<app_name>__<model_name_plural>"
    ```
    """

    __tablename__: str  # Just a placeholder for the type checker
    """The name of the table in the database"""
    __abstract__: bool = True
    __auto_tablename__: bool = False
    """
    If True, the table name will be auto-generated based on the model and app name.
    Defaults to False.
    """
    __short_name__: typing.Optional[str] = None
    """A unique but short name or alias for the model."""
    __verbose_name__: typing.Optional[str] = None
    """A human-readable name for the model."""
    __verbose_name_plural__: typing.Optional[str] = None
    """A human-readable plural name for the model."""

    id = orm.mapped_column(
        sa.Integer,
        primary_key=True,
        index=True,
        doc="The primary key of the model",
        autoincrement=True,
    )

    @classmethod
    def get_fields(cls):
        """
        Returns a mapping of field/column name to `orm.MappedColumn`, of the model.
        """
        field_mappings: typing.Dict[str, orm.MappedColumn] = {}
        for key, value in cls.__dict__.items():
            if isinstance(value, orm.MappedColumn):
                field_mappings[key] = value
            elif isinstance(value, sa.Column):
                mapped_column = orm.mapped_column()
                mapped_column.column = value
                field_mappings[key] = mapped_column
        return field_mappings
