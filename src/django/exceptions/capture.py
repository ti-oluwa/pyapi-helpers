"""
Exception Capturing API.

Use `capture.drf_exception_handler` to enable exception capture globally when using DRF.

Use the `capture.enable` decorator to enable for specific views only, especially, non-drf views.
"""

from django.http import HttpResponse, Http404
from django.core.exceptions import PermissionDenied, BadRequest, ValidationError

from src.dependencies import depends_on
from src.generics.exceptions.capture import ExceptionCaptor as BaseExceptionCaptor


class ExceptionCaptor(BaseExceptionCaptor[BaseException, HttpResponse]):
    DEFAULT_RESPONSE_TYPE = HttpResponse
    EXCEPTION_CODES = {
        ValidationError: 422,
        Http404: 404,
        PermissionDenied: 403,
        BadRequest: 400,
    }
    CONTENT_TYPE_KWARG = "content_type"
    DEFAULT_CONTENT_TYPE = "application/json"
    STATUS_CODE_KWARG = "status"


capture = ExceptionCaptor
enable = ExceptionCaptor.enable


@depends_on({"rest_framework": "djangorestframework"})
def drf_exception_handler(exc, context):
    """
    Exception handler for Django Rest Framework.

    Processes `ExceptionCaptured` exceptions and leaves the rest
    to `rest_framework.views.drf_exception_handler`

    Example:
    ```python
    REST_FRAMEWORK = {
        "EXCEPTION_HANDLER": "helpers.django.exceptions.capture.drf_exception_handler"
    }
    ```
    """
    from rest_framework import views, exceptions

    if isinstance(exc, ExceptionCaptor.ExceptionCaptured):
        response = exc.response
        captured_exception = exc.captive

        if isinstance(captured_exception, exceptions.APIException):
            if getattr(captured_exception, "auth_header", None):
                response.headers["WWW-Authenticate"] = captured_exception.auth_header
            if getattr(captured_exception, "wait", None):
                response.headers["Retry-After"] = "%d" % captured_exception.wait
            views.set_rollback()
        return response

    return views.exception_handler(exc, context)


__all__ = [
    "ExceptionCaptor",
    "capture",
    "enable",
    "drf_exception_handler",
]
