import pydantic
from fastapi.exceptions import RequestValidationError, ValidationException
from starlette.requests import HTTPConnection
from starlette.responses import Response
from starlette.exceptions import HTTPException

from . import shortcuts


async def generic_exception_handler(
    connection: HTTPConnection, exc: Exception
) -> Response:
    """Prepares and returns a properly formatted response for any exception."""
    return shortcuts.error(
        status_code=500,
        detail=str(exc),
    )


async def validation_exception_handler(
    connection: HTTPConnection, exc: ValidationException
) -> Response:
    """Prepares and returns a properly formatted response for a `fastapi.ValidationException`."""
    return shortcuts.validation_error(errors=list(exc.errors()))


async def http_exception_handler(
    connection: HTTPConnection, exc: HTTPException
) -> Response:
    """Prepares and returns a properly formatted response for a `starlette.HTTPException`."""
    return shortcuts.error(
        status_code=exc.status_code,
        detail=exc.detail,
        headers=exc.headers,
    )


async def pydantic_validation_error_handler(
    connection: HTTPConnection, exc: pydantic.ValidationError
) -> Response:
    """Prepares and returns a properly formatted response for a `pydantic.ValidationError`."""
    return shortcuts.unprocessable_entity(errors=exc.errors())


async def request_validation_error_handler(
    connection: HTTPConnection, exc: RequestValidationError
) -> Response:
    """Prepares and returns a properly formatted response for a `fastapi.RequestValidationError`."""
    return shortcuts.unprocessable_entity(
        errors=exc.errors(), detail=str(exc.body) if exc.body else None
    )
