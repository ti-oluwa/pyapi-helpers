"""Response Shortcuts"""

from django.http import JsonResponse
from typing import Any, Dict, List, Optional, Union
import enum
from dataclasses import dataclass, asdict, KW_ONLY


class Status(enum.Enum):
    """Response status."""

    SUCCESS = "success"
    ERROR = "error"


@dataclass
class Schema:
    """Response schema."""

    _: KW_ONLY
    status: Status
    """The status of the response."""
    message: str
    """A short message describing the response."""
    detail: Optional[str] = None
    """Optional detailed information about the response."""
    data: Optional[Union[Dict[str, Any], List, str]] = None
    """Optional data payload for the response."""
    errors: Optional[Union[Dict, List]] = None
    """Optional error details, if applicable."""


def json_response(
    message: str = "Request successful!",
    *,
    data: Optional[Union[Dict[str, Any], List, str]] = None,
    status: Status = Status.SUCCESS,
    detail: Optional[str] = None,
    errors: Optional[Union[Dict, List]] = None,
    status_code: int = 200,
    **kwargs,
) -> JsonResponse:
    """Returns a JSON response with a structured payload."""
    status = Status(status)
    schema = Schema(
        status=status,
        message=message,
        detail=detail,
        data=data,
        errors=errors,
    )
    return JsonResponse(data=asdict(schema), status=status_code, **kwargs)


def success(
    message: str = "Request successful!",
    data: Optional[Union[Dict[str, Any], List, str]] = None,
    status_code: int = 200,
    **kwargs,
) -> JsonResponse:
    """Use for successful request."""
    return json_response(
        message=message,
        data=data,
        status_code=status_code,
        **kwargs,
    )


def error(
    message: str = "Oops! An error occurred",
    errors: Optional[Union[Dict, List]] = None,
    detail: Optional[str] = None,
    status_code: int = 500,
    **kwargs,
) -> JsonResponse:
    """Use for error responses."""
    return json_response(
        message=message,
        errors=errors,
        detail=detail,
        status_code=status_code,
        **kwargs,
    )


def not_modified(message: str = "Not modified", **kwargs) -> JsonResponse:
    """Use when a request is not modified."""
    return success(message, status_code=304, **kwargs)


def created(
    message: str = "Resource created",
    data: Optional[Union[Dict, List]] = None,
    **kwargs,
) -> JsonResponse:
    """Use when a resource is created."""
    return success(message, data=data, status_code=201, **kwargs)


def accepted(
    message: str = "Request accepted",
    data: Optional[Union[Dict, List]] = None,
    **kwargs,
) -> JsonResponse:
    """Use when a request is accepted."""
    return success(message, data=data, status_code=202, **kwargs)


def no_content(message: str = "No content", **kwargs) -> JsonResponse:
    """Use when there is no content to return."""
    return success(message, data=None, status_code=204, **kwargs)


def partial_content(
    message: str = "Partial content", data: Optional[Union[Dict, List]] = None, **kwargs
) -> JsonResponse:
    """Use when there is partial content to return."""
    return success(message, data=data, status_code=206, **kwargs)


def already_exists(message: str = "Resource already exists", **kwargs) -> JsonResponse:
    """Use when a resource already exists."""
    return error(message, status_code=409, **kwargs)


def validation_error(errors: Optional[Union[Dict, List]] = None, **kwargs) -> JsonResponse:
    """Use when a validation error occurs."""
    message = "Validation failed"
    return error(message, errors=errors, status_code=422, **kwargs)


def forbidden(
    message: str = "You don't have permission to access this resource", **kwargs
) -> JsonResponse:
    """Use when a user is forbidden from accessing a resource."""
    return error(message, errors=None, status_code=403, **kwargs)


def unprocessable_entity(
    message: str = "Unprocessable request", **kwargs
) -> JsonResponse:
    """Use when a request is unprocessable."""
    return error(message, status_code=422, **kwargs)


def bad_request(
    message: str = "Bad Request", status_code: int = 400, **kwargs
) -> JsonResponse:
    """Use when a request is bad."""
    return error(message, status_code=status_code, **kwargs)


def notfound(message: str = "Resource not found!", **kwargs) -> JsonResponse:
    """Use when a resource is not found."""
    return error(message, errors=None, status_code=404, **kwargs)


def unauthorized(
    message: str = "You don't have authorization to access this resource", **kwargs
) -> JsonResponse:
    """Use when a user is unauthorized to access a resource."""
    return error(message, errors=None, status_code=401, **kwargs)


def server_error(
    message: str = "Internal Server Error", status_code: int = 500, **kwargs
) -> JsonResponse:
    """Use when a server error occurs."""
    return error(message, errors=None, status_code=status_code, **kwargs)


def conflict(
    message: str = "Data conflict!", status_code: int = 409, **kwargs
) -> JsonResponse:
    """Use when a data conflict occurs."""
    return error(message, status_code=status_code, **kwargs)


def failed_dependency(message: str = "Failed dependency", **kwargs) -> JsonResponse:
    """Use when a request fails due to a dependency."""
    return error(message, status_code=424, **kwargs)


def method_not_allowed(
    message: str = "Method not allowed", status_code: int = 405, **kwargs
) -> JsonResponse:
    """Use when a method is not allowed."""
    return error(message, errors=None, status_code=status_code, **kwargs)


def not_implemented(
    message: str = "Not implemented", status_code: int = 501, **kwargs
) -> JsonResponse:
    """Use when a method is not implemented."""
    return error(message, errors=None, status_code=status_code, **kwargs)


def expectation_failed(message: str = "Expectation failed", **kwargs) -> JsonResponse:
    """Use when the server cannot meet the expectation of the client."""
    return error(message, status_code=417, **kwargs)


def not_acceptable(message: str = "Not acceptable", **kwargs) -> JsonResponse:
    """Use when the server cannot provide the requested content type."""
    return error(message, status_code=406, **kwargs)


def payment_required(message: str = "Payment required", **kwargs) -> JsonResponse:
    """Use when payment is required to access a resource."""
    return error(message, status_code=402, **kwargs)


def too_many_requests(message: str = "Too many requests", **kwargs) -> JsonResponse:
    """Use when the client has sent too many requests in a given amount of time."""
    return error(message, errors=None, status_code=429, **kwargs)


def gone(message: str = "Resource gone", **kwargs) -> JsonResponse:
    """Use when a resource is no longer available."""
    return error(message, errors=None, status_code=410, **kwargs)


def too_large(message: str = "Request too large", **kwargs) -> JsonResponse:
    """Use when a request is too large."""
    return error(message, status_code=413, **kwargs)


def unsupported_media_type(
    message: str = "Unsupported media type", **kwargs
) -> JsonResponse:
    """Use when the server cannot process the media type of the request."""
    return error(message, status_code=415, **kwargs)


def precondition_failed(message: str = "Precondition failed", **kwargs) -> JsonResponse:
    """Use when a precondition in the request headers is not met."""
    return error(message, status_code=412, **kwargs)


def too_early(message: str = "Too early", **kwargs) -> JsonResponse:
    """Use when the client sends a request too early."""
    return error(message, status_code=425, **kwargs)


def service_unavailable(message: str = "Service unavailable", **kwargs) -> JsonResponse:
    """Use when the server is temporarily unavailable."""
    return error(message, errors=None, status_code=503, **kwargs)


def under_maintenance(
    message: str = "Service under maintenance", **kwargs
) -> JsonResponse:
    """Use when the server is under maintenance."""
    return service_unavailable(message, **kwargs)


def unavailable_for_legal_reasons(
    message: str = "Unavailable for legal reasons", **kwargs
) -> JsonResponse:
    """Use when a resource is unavailable for legal reasons."""
    return error(message, errors=None, status_code=451, **kwargs)


__all__ = [
    "json_response",
    "success",
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
