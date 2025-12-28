import collections
import collections.abc
import datetime
import typing
import sqlalchemy as sa
from sqlalchemy import orm
import sqlalchemy_utils as sa_utils

from src.fastapi.sqlalchemy import models
from src.fastapi.config import settings
from src.fastapi.apps import discover_apps, discover_models
from src.fastapi.utils import timezone
from src.fastapi.utils.password_validation import validate_password
from src.generics.utils.misc import is_iterable


class AbstractBaseUser(models.Model):
    """Abstract base class for user models in FastAPI applications using SQLAlchemy."""

    __abstract__ = True

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return not self.is_authenticated


class AbstractUserMeta(models.ModelBaseMeta):
    def __new__(cls, *args, **kwargs):
        new_cls = super().__new__(cls, *args, **kwargs)
        # Only check the username field and required fields if the class is not abstract
        if not getattr(new_cls, "__abstract__", False):
            cls.check_username_field(new_cls)
            cls.check_required_fields(new_cls)
        return new_cls

    @staticmethod
    def check_username_field(new_cls):
        field = new_cls.get_fields().get(new_cls.USERNAME_FIELD, None)
        if not field:
            raise ValueError(
                f"USERNAME_FIELD '{new_cls.USERNAME_FIELD}' not found in model {new_cls.__name__}"
            )
        if field.column.nullable:
            raise ValueError(
                f"USERNAME_FIELD '{new_cls.USERNAME_FIELD}' must not be nullable"
            )
        if not field.column.unique:
            raise ValueError(
                f"USERNAME_FIELD '{new_cls.USERNAME_FIELD}' must be unique"
            )
        return None

    @staticmethod
    def check_required_fields(new_cls) -> None:
        cls_fields = new_cls.get_fields()
        for field in new_cls.REQUIRED_FIELDS:
            if field not in cls_fields:
                raise ValueError(
                    f"REQUIRED_FIELDS '{field}' not found in model {new_cls.__name__}"
                )

        if isinstance(new_cls.REQUIRED_FIELDS, collections.abc.Mapping):
            for field_name, value in new_cls.REQUIRED_FIELDS.items():
                if not is_iterable(value):
                    raise ValueError(
                        f"REQUIRED_FIELDS mapping value for '{field_name}' must be an iterable"
                    )
                for validator in value:
                    if not callable(validator):
                        raise ValueError(
                            f"Items in REQUIRED_FIELDS mapping value for '{field_name}' must be a callable validator"
                        )
        return None


class AbstractUser(AbstractBaseUser, metaclass=AbstractUserMeta):
    """
    Abstract user model for FastAPI applications using SQLAlchemy.


    This class provides the basic fields and methods required for user authentication
    and management. It should be subclassed to create specific user models.

    Example usage:

    ```python
    from sqlalchemy import orm
    import sqlalchemy as sa
    from src.fastapi.models.users import AbstractUser

    class User(AbstractUser):
        __tablename__ = "users"

        email: orm.Mapped[str] = orm.mapped_column(sa.String, unique=True, nullable=False)
        first_name: orm.Mapped[str] = orm.mapped_column(sa.String, nullable=False)
        last_name: orm.Mapped[str] = orm.mapped_column(sa.String, nullable=False)
        # Additional fields and methods can be defined here

        USERNAME_FIELD = "email"
        REQUIRED_FIELDS = ["first_name", "last_name"]

    ```
    """

    __abstract__ = True

    password = orm.mapped_column(
        sa_utils.PasswordType(
            onload=lambda **kwargs: {
                "schemes": list(settings.get("PASSWORD_SCHEMES", ["md5_crypt"])),
                **kwargs,
            }
        ),
        nullable=False,
        doc="User's password",
    )
    is_active: orm.Mapped[bool] = orm.mapped_column(
        default=True, insert_default=True, doc="Is the user active?"
    )
    is_staff: orm.Mapped[bool] = orm.mapped_column(
        default=False, insert_default=False, doc="Is the user staff?"
    )
    is_admin: orm.Mapped[bool] = orm.mapped_column(
        default=False, insert_default=False, doc="Is the user admin?"
    )

    date_joined: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sa.DateTime(timezone=True),
        default=timezone.now,
        nullable=False,
        doc="Date the user joined the system",
    )
    updated_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sa.DateTime(timezone=True),
        default=timezone.now,
        onupdate=timezone.now,
        nullable=False,
        doc="Date the user was last updated",
    )

    USERNAME_FIELD: str = ""  # Leave empty to be set in subclasses
    REQUIRED_FIELDS: typing.Union[
        typing.Mapping[str, typing.List[typing.Callable]], typing.Iterable[str]
    ] = {}

    def get_username(self):
        """Return the username for the user."""
        return getattr(self, type(self).USERNAME_FIELD)

    @classmethod
    def _get_required_fields(cls):
        required_fields = {}
        # This is done to ensure that the username field is always the first field
        # in the required fields dictionary
        if isinstance(cls.REQUIRED_FIELDS, collections.abc.Mapping):
            required_fields[cls.USERNAME_FIELD] = cls.REQUIRED_FIELDS.get(
                cls.USERNAME_FIELD, []
            )
            required_fields.update(cls.REQUIRED_FIELDS)
            return required_fields

        required_fields[cls.USERNAME_FIELD] = []
        for field_name in cls.REQUIRED_FIELDS:
            required_fields[field_name] = []
        return required_fields

    # Override this method to customize how passwords are set
    def set_password(self, raw_password: str):
        """Set the password for the user."""
        self.password = validate_password(raw_password)

    # Override this method to customize how passwords are checked
    def check_password(self, raw_password: str) -> bool:
        """Check the password for the user."""
        return self.password == raw_password


class AnonymousUser(AbstractBaseUser):
    """Abstract user model for anonymous users in FastAPI applications using SQLAlchemy."""

    __abstract__ = True

    id: None = None  # type: ignore

    @property
    def is_authenticated(self):
        return False

    def __init_subclass__(cls):
        raise TypeError("Cannot subclass AnonymousUser")


def get_user_model() -> typing.Type[AbstractUser]:
    """
    Get the user model defined in settings.AUTH_USER_MODEL.

    This function searches through the installed apps and their models to find
    the user model specified in the `AUTH_USER_MODEL` setting.

    :return: The user model class.
    """
    auth_user_model: typing.Optional[str] = settings.AUTH_USER_MODEL
    if not auth_user_model:
        raise ValueError("AUTH_USER_MODEL is not set")

    app_name, model_name = auth_user_model.rsplit(".", maxsplit=1)

    for app in discover_apps():
        if app.name.endswith(app_name):
            for model in discover_models(app.name):
                if model.__name__ == model_name:
                    return model

    raise ValueError(f"User model '{auth_user_model}' not found")
