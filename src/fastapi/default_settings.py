import typing
import fastapi
import pydantic
import starlette.exceptions


INSTALLED_APPS: typing.Sequence[str] = []

APP: typing.Dict[str, typing.Any] = {
    "debug": True,
}

DEFAULT_DEPENDENCIES: typing.Sequence[str] = []

SQLALCHEMY = {
    "engine": {
        "sync": {
            "future": True,
            "connect_args": {},
            "echo": True,
        },
        "async": {
            "future": True,
            "connect_args": {},
            "echo": True,
        },
    },
    "sessionmaker": {
        "sync": {
            "autocommit": False,
            "autoflush": False,
            "future": True,
            "expire_on_commit": False,
        },
        "async": {
            "autocommit": False,
            "autoflush": False,
            "future": True,
            "expire_on_commit": False,
        },
    },
}


TIMEZONE: str = "UTC"

AUTH_USER_MODEL: typing.Optional[str] = None

MIDDLEWARE: typing.Sequence[
    typing.Union[str, typing.Tuple[str, typing.Dict[str, typing.Any]]]
] = [
    "helpers.fastapi.middleware.core.AllowedHostsMiddleware",
    "helpers.fastapi.middleware.core.AllowedIPsMiddleware",
    "helpers.fastapi.middleware.core.HostBlacklistMiddleware",
    "helpers.fastapi.middleware.core.IPBlacklistMiddleware",
    "helpers.fastapi.middleware.users.ConnectedUserMiddleware",
]

PASSWORD_SCHEMES: typing.Sequence[str] = ["md5_crypt"]

PASSWORD_VALIDATORS: typing.Sequence[str] = [
    "helpers.fastapi.utils.password_validation.common_password_validator",
    "helpers.fastapi.utils.password_validation.mixed_case_validator",
    "helpers.fastapi.utils.password_validation.special_characters_validator",
    "helpers.fastapi.utils.password_validation.digit_validator",
]

ALLOWED_HOSTS: typing.Sequence[str] = ["*"]

ALLOWED_IPS: typing.Sequence[str] = ["*"]

BLACKLISTED_HOSTS: typing.Sequence[str] = []

BLACKLISTED_IPS: typing.Sequence[str] = []

MAILING: typing.Dict[str, typing.Any] = {}

MAINTENANCE_MODE: typing.Dict[str, typing.Any] = {
    "status": "off",
    "message": "default:minimal_dark",
}


EXCEPTION_HANDLERS: typing.Mapping[
    typing.Union[int, typing.Type[BaseException]], str
] = {
    fastapi.exceptions.ValidationException: "helpers.fastapi.response.exception_handling.validation_exception_handler",
    starlette.exceptions.HTTPException: "helpers.fastapi.response.exception_handling.http_exception_handler",
    Exception: "helpers.fastapi.response.exception_handling.generic_exception_handler",
    pydantic.ValidationError: "helpers.fastapi.response.exception_handling.pydantic_validation_error_handler",
    fastapi.exceptions.RequestValidationError: "helpers.fastapi.response.exception_handling.request_validation_error_handler",
}

SENSITIVE_HEADERS: typing.Iterable[str] = {
    "x-access-token",
    "x-refresh-token",
    "x-otp",
    "x-otp-token",
    "x-auth-token",
    "authorization",
    "x-api-key",
    "x-client-id",
    "x-client-secret",
    "x-client-token",
    "x-api-token",
    "x-api-secret",
}

LOG_CONNECTION_EVENTS: bool = False  # Enable/disable request event logging

REDIS_URL: str = "redis://localhost:6379/0"
