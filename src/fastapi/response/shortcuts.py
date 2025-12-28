from enum import Enum
import typing

import pydantic
from pydantic_core._pydantic_core import PydanticSerializationError  # type: ignore[import]
from starlette.responses import JSONResponse
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field

from src.logging import log_exception
from src.types import LoggerLike


class Status(Enum):
    """Response status."""

    SUCCESS = "success"
    """Indicates a successful response."""
    ERROR = "error"
    """Indicates an error response."""
    INFO = "info"
    """Indicates an informational response."""
    WARNING = "warning"
    """Indicates a warning response."""


DataT = typing.TypeVar(
    "DataT", typing.Mapping, typing.Sequence, BaseModel, pydantic.JsonValue, None
)
ErrorT = typing.TypeVar(
    "ErrorT", typing.Mapping, typing.Sequence, BaseModel, pydantic.JsonValue, None
)


@typing.final
class Schema(BaseModel, typing.Generic[DataT, ErrorT]):
    """Response schema."""

    status: Status = Field(
        ..., description="The status of the response, e.g., 'success' or 'error'."
    )
    message: str = Field(..., description="A short message describing the response.")
    detail: typing.Optional[str] = Field(
        default=None,
        description="typing.Optional detailed information about the response.",
    )
    data: typing.Optional[DataT] = Field(
        default=None, description="typing.Optional data payload for the response."
    )
    errors: typing.Optional[ErrorT] = Field(
        default=None, description="typing.Optional error details, if applicable."
    )


DataSchema: typing.TypeAlias = Schema[DataT, None]
"""Schema alias for a response with data only. Typically used for successful responses."""

ErrorSchema: typing.TypeAlias = Schema[None, ErrorT]
"""Schema alias for a response with errors only. Typically used for error responses."""

PydanticModel = typing.TypeVar(
    "PydanticModel",
    bound=pydantic.BaseModel,
)


def NewSchema(
    name: str,
    /,
    fields: typing.Dict[
        str, typing.Union[typing.Type[typing.Any], pydantic.fields.FieldInfo]
    ],
    base_model: typing.Type[PydanticModel] = pydantic.BaseModel,
    description: typing.Optional[str] = None,
) -> typing.Type[pydantic.BaseModel]:
    """
    Schema factory function to create a new Pydantic model dynamically.

    :param name: The name of the new model.
    :param fields: A dictionary of field names and their types or FieldInfo.
    :param base_model: The base model to inherit from. Defaults to pydantic.BaseModel.
    :param description: An optional description for the model.
    :return: A new Pydantic model class.

    Example:
    ```python
    from fastapi import FastAPI

    from src.fastapi.response.shortcuts import NewSchema, DataSchema, success

    app = FastAPI()

    @app.post(
        "/example",
        response_model=DataSchema[
            NewSchema("ExampleSchema", {"field1": str, "field2": int)
        ],
        description="Example endpoint",
    )
    async def example_endpoint():
        return success(data={"field1": "value", "field2": 42})
    ```

    This function allows you to create a new Pydantic model dynamically with the specified fields.
    The created model can be used as a response model in FastAPI endpoints.
    The fields can be defined using standard Python types or Pydantic's FieldInfo for more complex validation.
    """
    return type(
        name,
        (base_model,),
        {
            "__module__": __name__,
            "__doc__": description or f"{name} model",
            "__annotations__": fields,
        },
    )


def _clean_errors(errors: typing.Optional[ErrorT]) -> typing.Optional[ErrorT]:
    """
    Cleans the errors by removing any unserializable objects.
    This is a helper function to ensure that the errors can be serialized to JSON.
    """
    if errors is None:
        return None

    if isinstance(errors, (list, tuple, set)):
        for error in errors:
            if isinstance(error, dict):
                if "ctx" in error:
                    error["ctx"] = {  # type: ignore[assignment]
                        k: v
                        for k, v in error["ctx"].items()  # type: ignore[dict-item]
                        if isinstance(v, (str, int, float, bool))
                    }
    return errors  # type: ignore[return-value]


def json_response(
    message: str = "Request successful!",
    *,
    status: typing.Union[Status, str] = Status.SUCCESS,
    detail: typing.Optional[str] = None,
    data: typing.Optional[DataT] = None,
    errors: typing.Optional[ErrorT] = None,
    status_code: int = 200,
    logger: typing.Optional[LoggerLike] = None,
    **kwargs,
) -> JSONResponse:
    """Returns a JSON response with a structured payload."""
    schema = Schema[DataT, ErrorT](
        status=status if isinstance(status, Status) else Status(status),
        message=message,
        detail=detail,
        data=data,
        errors=_clean_errors(errors),
    )
    try:
        content = schema.model_dump(mode="json")
    except PydanticSerializationError as exc:
        log_exception(exc, logger=logger)
        return ORJSONResponse(
            content={
                "status": Status.ERROR.value,
                "message": "Response serialization failed",
                "detail": "Could not serialize response data",
                "errors": [{"type": "serialization_error"}],
            },
            status_code=500,
            **kwargs,
        )
    return ORJSONResponse(
        content=content,
        status_code=status_code,
        **kwargs,
    )


def success(
    message: str = "Request successful!",
    data: typing.Optional[DataT] = None,
    status_code: int = 200,
    **kwargs,
) -> JSONResponse:
    """Use for successful requests."""
    return json_response(
        message=message,
        status=Status.SUCCESS,
        data=data,
        status_code=status_code,
        **kwargs,
    )


ok = success


def info(
    message: str = "Information",
    data: typing.Optional[DataT] = None,
    status_code: int = 200,
    **kwargs,
) -> JSONResponse:
    """Use for informational responses."""
    return json_response(
        message=message,
        status=Status.INFO,
        data=data,
        status_code=status_code,
        **kwargs,
    )


def error(
    message: str = "Oops! An error occurred",
    errors: typing.Optional[ErrorT] = None,
    detail: typing.Optional[str] = None,
    status_code: int = 500,
    **kwargs,
) -> JSONResponse:
    """Use for error responses."""
    return json_response(
        message=message,
        status=Status.ERROR,
        errors=errors,
        detail=detail,
        status_code=status_code,
        **kwargs,
    )


def warning(
    message: str = "Warning! Something might be wrong",
    errors: typing.Optional[ErrorT] = None,
    detail: typing.Optional[str] = None,
    status_code: int = 400,
    **kwargs,
) -> JSONResponse:
    """Use for warning responses."""
    return json_response(
        message=message,
        status=Status.WARNING,
        errors=errors,
        detail=detail,
        status_code=status_code,
        **kwargs,
    )


def not_modified(message: str = "Not modified", **kwargs) -> JSONResponse:
    """Use when a request is not modified."""
    return success(message, status_code=304, **kwargs)


def created(
    message: str = "Resource created", data: typing.Optional[DataT] = None, **kwargs
) -> JSONResponse:
    """Use when a resource is created."""
    return success(message, data=data, status_code=201, **kwargs)


def accepted(
    message: str = "Request accepted", data: typing.Optional[DataT] = None, **kwargs
) -> JSONResponse:
    """Use when a request is accepted."""
    return success(message, data=data, status_code=202, **kwargs)


def no_content(message: str = "No content", **kwargs) -> JSONResponse:
    """Use when there is no content to return."""
    kwargs.pop("data", None)
    kwargs.pop("errors", None)
    kwargs.pop("detail", None)
    return JSONResponse(
        content=None,
        status_code=204,
        media_type="application/json",
        headers={"X-Message": message},
        **kwargs,
    )


def partial_content(
    message: str = "Partial content", data: typing.Optional[DataT] = None, **kwargs
) -> JSONResponse:
    """Use when there is partial content to return."""
    return success(message, data=data, status_code=206, **kwargs)


def already_exists(message: str = "Resource already exists", **kwargs) -> JSONResponse:
    """Use when a resource already exists."""
    return error(message, status_code=409, **kwargs)


def validation_error(errors: typing.Optional[ErrorT] = None, **kwargs) -> JSONResponse:
    """Use when a validation error occurs."""
    message = "Validation failed"
    return error(message, errors=errors, status_code=422, **kwargs)


def forbidden(
    message: str = "You don't have permission to access this resource", **kwargs
) -> JSONResponse:
    """Use when a user is forbidden from accessing a resource."""
    return error(message, errors=None, status_code=403, **kwargs)


def unprocessable_entity(
    message: str = "Unprocessable request", **kwargs
) -> JSONResponse:
    """Use when a request is unprocessable."""
    return error(message, status_code=422, **kwargs)


def bad_request(
    message: str = "Bad Request", status_code: int = 400, **kwargs
) -> JSONResponse:
    """Use when a request is bad."""
    return error(message, status_code=status_code, **kwargs)


def not_found(message: str = "Resource not found!", **kwargs) -> JSONResponse:
    """Use when a resource is not found."""
    return error(message, errors=None, status_code=404, **kwargs)


notfound = not_found  # For backward compatibility


def unauthorized(
    message: str = "You don't have authorization to access this resource", **kwargs
) -> JSONResponse:
    """Use when a user is unauthorized to access a resource."""
    return error(message, errors=None, status_code=401, **kwargs)


def server_error(
    message: str = "Internal Server Error", status_code: int = 500, **kwargs
) -> JSONResponse:
    """Use when a server error occurs."""
    return error(message, errors=None, status_code=status_code, **kwargs)


def conflict(
    message: str = "Data conflict!", status_code: int = 409, **kwargs
) -> JSONResponse:
    """Use when a data conflict occurs."""
    return error(message, status_code=status_code, **kwargs)


def failed_dependency(message: str = "Failed dependency", **kwargs) -> JSONResponse:
    """Use when a request fails due to a dependency."""
    return error(message, status_code=424, **kwargs)


def method_not_allowed(
    message: str = "Method not allowed", status_code: int = 405, **kwargs
) -> JSONResponse:
    """Use when a method is not allowed."""
    return error(message, errors=None, status_code=status_code, **kwargs)


def not_implemented(
    message: str = "Not implemented", status_code: int = 501, **kwargs
) -> JSONResponse:
    """Use when a method is not implemented."""
    return error(message, errors=None, status_code=status_code, **kwargs)


def expectation_failed(message: str = "Expectation failed", **kwargs) -> JSONResponse:
    """Use when the server cannot meet the expectation of the client."""
    return error(message, status_code=417, **kwargs)


def not_acceptable(message: str = "Not acceptable", **kwargs) -> JSONResponse:
    """Use when the server cannot provide the requested content type."""
    return error(message, status_code=406, **kwargs)


def payment_required(message: str = "Payment required", **kwargs) -> JSONResponse:
    """Use when payment is required to access a resource."""
    return error(message, status_code=402, **kwargs)


def too_many_requests(message: str = "Too many requests", **kwargs) -> JSONResponse:
    """Use when the client has sent too many requests in a given amount of time."""
    return error(message, errors=None, status_code=429, **kwargs)


def gone(message: str = "Resource gone", **kwargs) -> JSONResponse:
    """Use when a resource is no longer available."""
    return error(message, errors=None, status_code=410, **kwargs)


def too_large(message: str = "Request too large", **kwargs) -> JSONResponse:
    """Use when a request is too large."""
    return error(message, status_code=413, **kwargs)


def unsupported_media_type(
    message: str = "Unsupported media type", **kwargs
) -> JSONResponse:
    """Use when the server cannot process the media type of the request."""
    return error(message, status_code=415, **kwargs)


def precondition_failed(message: str = "Precondition failed", **kwargs) -> JSONResponse:
    """Use when a precondition in the request headers is not met."""
    return error(message, status_code=412, **kwargs)


def too_early(message: str = "Too early", **kwargs) -> JSONResponse:
    """Use when the client sends a request too early."""
    return error(message, status_code=425, **kwargs)


def service_unavailable(message: str = "Service unavailable", **kwargs) -> JSONResponse:
    """Use when the server is temporarily unavailable."""
    return error(message, errors=None, status_code=503, **kwargs)


def under_maintenance(
    message: str = "Service under maintenance", **kwargs
) -> JSONResponse:
    """Use when the server is under maintenance."""
    return service_unavailable(message, **kwargs)


def unavailable_for_legal_reasons(
    message: str = "Unavailable for legal reasons", **kwargs
) -> JSONResponse:
    """Use when a resource is unavailable for legal reasons."""
    return error(message, errors=None, status_code=451, **kwargs)


__all__ = [
    "Status",
    "Schema",
    "DataSchema",
    "ErrorSchema",
    "NewSchema",
    "json_response",
    "success",
    "ok",
    "info",
    "error",
    "not_modified",
    "created",
    "accepted",
    "no_content",
    "partial_content",
    "already_exists",
    "validation_error",
    "forbidden",
    "unprocessable_entity",
    "bad_request",
    "notfound",
    "unauthorized",
    "server_error",
    "conflict",
    "failed_dependency",
    "method_not_allowed",
    "not_implemented",
    "expectation_failed",
    "not_acceptable",
    "payment_required",
    "too_many_requests",
    "gone",
    "too_large",
    "unsupported_media_type",
    "precondition_failed",
    "too_early",
    "service_unavailable",
    "under_maintenance",
    "unavailable_for_legal_reasons",
]
