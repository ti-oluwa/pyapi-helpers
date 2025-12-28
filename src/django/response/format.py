import functools
from django.http import HttpResponse
from typing import Callable, Optional, Dict, Any
import json
from asgiref.sync import sync_to_async
import asyncio

from . import HTTPResponseTco
from src.django.views import CBV, FBV
from src.django.response.shortcuts import Status as ResponseStatus

Formatter = Callable[[HTTPResponseTco], HTTPResponseTco]


def _transfer_response_props(original: HTTPResponseTco, new: HTTPResponseTco) -> HTTPResponseTco:
    """
    Updates the new response with attributes from the original response
    that are not already present.
    """
    for key, value in original.__dict__.items():
        if key not in new.__dict__:
            new.__dict__[key] = value
    return new


def enforce_format(formatter: Formatter):
    """
    Enforces a format for the response of a view function using the formatter provided.

    :param formatter: A function that restructures the response' data to a desired format.
    The function should expect the response as an argument and return the formatted response.
    In an asynchronous context, the formatter provided should be a coroutine function.
    """

    def decorator(view_func: FBV) -> FBV:
        if asyncio.iscoroutinefunction(view_func):

            @functools.wraps(view_func)
            async def wrapper(*args, **kwargs) -> HTTPResponseTco:
                response = await view_func(*args, **kwargs)
                formatted_response = formatter(response)
                async_transfer_props = sync_to_async(_transfer_response_props)
                return await async_transfer_props(response, formatted_response)
        else:

            @functools.wraps(view_func)
            def wrapper(*args, **kwargs) -> HTTPResponseTco:
                response = view_func(*args, **kwargs)
                formatted_response = formatter(response)
                return _transfer_response_props(response, formatted_response)

        return wrapper

    return decorator


DEFAULT_ERROR_MSG = "An error occurred while processing your request!"

DEFAULT_OK_MSG = "Request processed successfully!"

DEFAULT_NOT_FOUND_MSG = "Resource not found!"

compulsory_keys = {"status", "message"}
"""For generic response data formatting, these keys are compulsory."""
optional_keys = {"errors", "data", "detail"}
"""For generic response data formatting, these keys are optional."""
standard_keys = {*compulsory_keys, *optional_keys}
"""For generic response data formatting, these keys are all the keys that can be present in the formatted response."""


def is_formatted(data: Dict[str, Any]) -> bool:
    """Checks if the response data has already been formatted by the generic formatter."""
    non_standard_keys_found = set(data.keys()).difference(standard_keys)

    # If the compulsory keys are not present, the data is not formatted
    if not set(data.keys()).issuperset(compulsory_keys):
        return False

    # if any non-standard keys are found, they must be subset of optional keys
    # else, the data is not formatted
    if non_standard_keys_found and not non_standard_keys_found.issubset(optional_keys):
        return False

    # If 'status' is present, it must be either 'success' or 'error'
    if data["status"] not in {ResponseStatus.SUCCESS, ResponseStatus.ERROR}:
        return False

    # If 'message' is present, it must be a non-empty string
    if not isinstance(data["message"], str):
        return False

    # If 'errors' is present, it must be a non-empty dictionary or a list
    if (
        "errors" in data
        and data["errors"]
        and not isinstance(data["errors"], (dict, list))
    ):
        return False

    # If 'data' is present, it must be a dictionary, list or str
    if (
        "data" in data
        and data["data"]
        and not isinstance(data["data"], (dict, list, str))
    ):
        return False

    # If 'detail' is present, it must be a dictionary, list or str
    if (
        "detail" in data
        and data["detail"]
        and not isinstance(data["detail"], (dict, list, str))
    ):
        return False

    return True


def is_error_list(errors: Any) -> bool:
    if not isinstance(errors, (list, tuple)):
        return False
    for error in errors:
        if isinstance(error, str):
            continue
        return False
    return True


def is_error_dict(errors: Any) -> bool:
    if not isinstance(errors, dict):
        return False
    for value in errors.values():
        if is_error_list(value):
            continue
        return False
    return True


def is_error_dict_list(errors: Any) -> bool:
    if not isinstance(errors, (list, tuple)):
        return False
    for error in errors:
        if is_error_dict(error):
            continue
        return False
    return True


def generic_response_data_formatter(
    response_data: Any, response_ok: bool
) -> Dict[str, Any]:
    """
    Generic response data formatter

    Formatted response data structure:
    ```JSON
    {
        "status": "success" | "error",
        "message": "Request processed successfully" | ...,
        "errors": ..., # If response has errors
        "data": ..., # If response is successful and has data
        "detail": ..., # Dependent on the response
    }
    ```
    """
    status = "success" if response_ok else "error"

    if not isinstance(response_data, dict):
        formatted = {
            "status": status,
            "message": DEFAULT_OK_MSG if response_ok else DEFAULT_ERROR_MSG,
        }
        if not response_data:
            return formatted
        if response_ok:
            formatted["data"] = response_data
        else:
            if isinstance(response_data, (list, dict)):
                formatted["errors"] = response_data
            else:
                formatted["detail"] = response_data
        return formatted

    if is_formatted(response_data):
        return response_data

    message = response_data.get("message", None)
    detail = response_data.get("detail", None)
    errors = response_data.get("errors", None)
    data = response_data.get("data", None)
    response_data_keys = list(response_data.keys())

    if message is None or not isinstance(message, str):
        # If the detail is provided, use it as the message
        # Else, use the default success or error message
        if detail and isinstance(detail, str):
            message = detail
        elif response_ok:
            message = DEFAULT_OK_MSG
        else:
            message = DEFAULT_ERROR_MSG

    formatted = {
        "status": status,
        "message": message,
    }

    if response_ok:
        # If the response is successful, include the data

        if data is not None and standard_keys.issuperset(response_data_keys):
            # If the data is provided, and the rest of the
            # keys in the response data are standard
            formatted["data"] = data
        else:
            # Else, assume the data is the response data
            formatted["data"] = response_data
    else:
        # If the response is an error, include the detail and errors

        if detail and detail != message and isinstance(detail, str):
            # If the detail is different from the message, include it in the response
            formatted["detail"] = detail

        # If the response is an error, include the errors
        if errors is not None and standard_keys.issuperset(response_data_keys):
            # If the errors are provided, use them
            formatted["errors"] = errors
        else:
            if (
                is_error_dict(response_data)
                or is_error_list(response_data)
                or is_error_dict_list(response_data)
            ):
                formatted["errors"] = response_data
            elif (
                is_error_dict(detail)
                or is_error_list(detail)
                or is_error_dict_list(detail)
            ):
                formatted["errors"] = detail
    return formatted


def json_httpresponse_formatter(response: HTTPResponseTco) -> HTTPResponseTco:
    """
    Formats JSON serializable response data into a structured format.

    Only works for HTTP responses with JSON serializable data.

    Uses generic formmater to format the response' data.
    """
    status_code = response.status_code
    if status_code == 204:
        # No content response
        return response

    data = json.loads(response.content) if response.content else ""
    response_ok = status_code >= 200 and status_code < 300
    formatted_data = generic_response_data_formatter(data, response_ok)

    # Ensure that the status message is not misleading
    if status_code == 404 and formatted_data["message"] == DEFAULT_ERROR_MSG:
        formatted_data["message"] = DEFAULT_NOT_FOUND_MSG

    content = json.dumps(formatted_data)
    return HttpResponse(content, status=status_code, content_type="application/json")


def drf_response_formatter(response: HTTPResponseTco) -> HTTPResponseTco:
    """
    Formats a Django Rest Framework response data into a structured format.

    Works for HTTP responses with JSON serializable data also.

    Formated response data structure:
    ```JSON
    {
        "status": "success" | "error",
        "message": "Request processed successfully" | ...,
        "errors": {
            "field_name": [
                "Error message 1",
                "Error message 2"
            ]
        }, # If response has errors
        "data": { ... }, # If response is successful and has data
        "detail": ..., # Dependent on the response
    }
    ```
    """
    try:
        # Try to render the response
        response = response.render()
    except AttributeError:
        pass
    return json_httpresponse_formatter(response)


def format_response(cbv: CBV = None, formatter: Optional[Formatter] = None) -> CBV:
    """
    Formats the response of a class-based view to a structured format.

    Ensure that the view returns a JSON serializable response.

    :param cbv: The CBV to be decorated.
    :param formatter: Preferred formatter for the view.
    If not provided, `drf_response_formatter` will be used as it is globally compatible.

    Example Usage:
    ```python
    from rest_framework import views

    @format_response
    class DRFFooView(views.APIView):
        ...
    ```

    Or;
    ```python
    from django.views import generic
    def foo_formatter(response: Response) -> Response:
        ...

    @format_response(formatter=foo_formatter)
    class FooView(generic.View):
        ...
    ```
    """
    formatter = formatter or drf_response_formatter
    if cbv is None:
        # Return this same decorator but with the formatter already set
        decorator = functools.partial(format_response, formatter=formatter)
        return decorator

    cbv.dispatch = enforce_format(formatter)(cbv.dispatch)
    return cbv
