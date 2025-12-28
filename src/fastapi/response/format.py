import typing
import copy
import orjson
from starlette.responses import Response, StreamingResponse

from . import ResponseTco
from .shortcuts import Status as ResponseStatus, Schema as ResponseSchema

Formatter = typing.Callable[
    [Response], typing.Union[Response, typing.Awaitable[Response]]
]


DEFAULT_ERROR_MSG = "An error occurred while processing your request!"

DEFAULT_OK_MSG = "Request processed successfully!"

DEFAULT_NOT_FOUND_MSG = "Resource not found!"


def is_error_list(errors: typing.Any) -> typing.TypeGuard[typing.List[str]]:
    if not isinstance(errors, (list, tuple)):
        return False
    for error in errors:
        if isinstance(error, str):
            continue
        return False
    return True


def is_error_dict(errors: typing.Any) -> typing.TypeGuard[typing.Dict[str, typing.Any]]:
    if not isinstance(errors, dict):
        return False
    for value in errors.values():
        if is_error_list(value):
            continue
        return False
    return True


def is_error_dict_list(
    errors: typing.Any,
) -> typing.TypeGuard[typing.List[typing.Dict[str, typing.Any]]]:
    if not isinstance(errors, (list, tuple)):
        return False
    for error in errors:
        if is_error_dict(error):
            continue
        return False
    return True


DEFAULT_ERROR_MSG = "An error occurred while processing your request!"

DEFAULT_OK_MSG = "Request processed successfully!"

DEFAULT_NOT_FOUND_MSG = "Resource not found!"

COMPULSORY_RESPONSE_DATA_KEYS = {"status", "message"}
"""For generic response data formatting, these keys are compulsory."""
OPTIONAL_RESPONSE_DATA_KEYS = {"errors", "data", "detail"}
"""For generic response data formatting, these keys are optional."""
STANDARD_RESPONSE_DATA_KEYS = {
    *COMPULSORY_RESPONSE_DATA_KEYS,
    *OPTIONAL_RESPONSE_DATA_KEYS,
}
"""For generic response data formatting, these keys are all the keys that can be present in the formatted response."""


def is_formatted(data: typing.Dict[str, typing.Any]) -> bool:
    """Checks if the response data has already been formatted by the generic formatter."""
    keys_found = set(data.keys())
    non_standard_keys_found = set(keys_found).difference(STANDARD_RESPONSE_DATA_KEYS)

    # If the compulsory keys are not present, the data is not formatted
    if not set(keys_found).issuperset(COMPULSORY_RESPONSE_DATA_KEYS):
        return False

    # if typing.any non-standard keys are found, they must be subset of optional keys
    # else, the data is not formatted
    if non_standard_keys_found and not non_standard_keys_found.issubset(
        OPTIONAL_RESPONSE_DATA_KEYS
    ):
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


def generic_response_data_formatter(
    response_data: typing.Any, response_ok: bool
) -> typing.Dict[str, typing.Any]:
    """
    Generic response data formatter

    Formatted response data structure:
    ```JSON
    {
        "status": "success" | "error",
        "message": ...,
        "errors": ...,
        "data": ...,
        "detail": ...,
    }
    ```
    """
    status = ResponseStatus.SUCCESS if response_ok else ResponseStatus.ERROR

    if not isinstance(response_data, dict):
        formatted = ResponseSchema(
            status=status,
            message=DEFAULT_OK_MSG if response_ok else DEFAULT_ERROR_MSG,
        )
        if not response_data:
            return formatted.model_dump(mode="json")

        if response_ok:
            formatted.data = response_data
        else:
            if is_formatted(response_data):
                formatted.detail = response_data
            else:
                formatted.errors = response_data
        return formatted.model_dump(mode="json")

    if is_formatted(response_data):
        return ResponseSchema(**response_data).model_dump(mode="json")

    message = response_data.get("message", None)
    detail = response_data.get("detail", None)
    response_data_keys = list(response_data.keys())

    if not (message and isinstance(message, str)):
        # If the detail is provided, use it as the message
        # Else, use the default success or error message
        if response_ok:
            message = DEFAULT_OK_MSG
        else:
            message = DEFAULT_ERROR_MSG

    formatted = ResponseSchema(
        status=status,
        message=message,
    )
    if detail and isinstance(detail, str):
        formatted.detail = detail

    if response_ok:
        # If the response was successful, include the data
        data = response_data.get("data", None)
        if data is not None and STANDARD_RESPONSE_DATA_KEYS.issuperset(
            response_data_keys
        ):
            # If the data is provided, and the rest of the
            # keys in the response data are standard
            formatted.data = data
        else:
            # Else, assume the data is the response data
            formatted.data = response_data

    else:
        # If the response was not successful, include the errors
        errors = response_data.get("errors", None)
        if errors is not None and STANDARD_RESPONSE_DATA_KEYS.issuperset(
            response_data_keys
        ):
            # If the errors are provided, use them
            formatted.errors = errors
        else:
            if (
                is_error_dict(response_data)
                or is_error_list(response_data)
                or is_error_dict_list(response_data)
            ):
                formatted.errors = response_data
            elif (
                is_error_dict(detail)
                or is_error_list(detail)
                or is_error_dict_list(detail)
            ):
                formatted.errors = detail
    return formatted.model_dump(mode="json")


def is_streaming_response(response: Response) -> bool:
    """
    Checks if the response is a streaming response.
    """
    return isinstance(response, StreamingResponse)


async def json_httpresponse_formatter(response: ResponseTco) -> ResponseTco:
    """
    Formats JSON serializable response data into a structured format.

    Only works for HTTP responses with JSON serializable data.

    Uses generic formmater to format the response' data.
    """
    response_type = type(response)
    status_code = response.status_code
    if status_code in {204, 304} or is_streaming_response(response):
        return response

    data = orjson.loads(response.body) if response.body else ""
    response_ok = status_code >= 200 and status_code < 300
    formatted_data = generic_response_data_formatter(data, response_ok)

    # Ensure that the status message is not misleading
    if status_code == 404 and formatted_data["message"] == DEFAULT_ERROR_MSG:
        formatted_data["message"] = DEFAULT_NOT_FOUND_MSG

    content = orjson.dumps(
        formatted_data,
        option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY,
    )
    headers = copy.copy(response.headers)
    headers["Content-Length"] = str(len(content))
    formatted_response = response_type(
        content,
        status_code=status_code,
        media_type="application/json",
        headers=headers,
    )
    return formatted_response
