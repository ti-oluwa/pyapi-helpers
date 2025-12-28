import re
from typing import Callable, Any, Union, Dict, Optional
import functools
from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect
import asyncio
from asgiref.sync import sync_to_async

from src.logging import log_exception
from . import HTTPResponseTco
from src.django.views import is_view_class, CBV, FBV


def notify_user(
    view_func: Optional[FBV] = None,
    *,
    status_code: int = 200,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    notify_func: Optional[Callable[..., Any]] = None,
    contact_attr: str = "email",
) -> Callable[[FBV], FBV]:
    """
    Attempts to send a notification to the request user on the specified status code.

    Errors while sending are silently ignored but logged.

    :param view_func: The view function to decorate.
    :param notify_func: Function that sends the notification. Should take 3 arguments: subject, body, and recipient, in that order.
    If this is not provided, the decorator assumes the user object has a `send_mail` method, and it will be used.
    :param status_code: The trigger response status code. Default is 200 OK.
    :param subject: Notification subject. A generic subject will be used if not provided.
    :param body: Notification content. A generic body will be used if not provided.
    :param contact_attr: Attribute of the user that holds the contact information like "email" or "phonenumber".
    """
    if notify_func and not callable(notify_func):
        raise ValueError("A notification function must be callable")

    def decorator(view_func: FBV) -> FBV:
        def handle_notification(request: HttpRequest, response: HTTPResponseTco) -> None:
            nonlocal subject
            nonlocal body
            subject = subject or f"Request to {request.path}"
            body = (
                body
                or f"Your request to {request.path} got response {response.status_code} - {response.reason_phrase}"
            )

            if response.status_code == status_code:
                user = request.user
                try:
                    contact = getattr(user, contact_attr)
                    if notify_func:
                        notify_func(subject, body, contact)
                    else:
                        user.send_mail(subject, body)
                except Exception as exc:
                    log_exception(exc)

        if asyncio.iscoroutinefunction(view_func):

            async def wrapper(
                view, request: HttpRequest, *args: str, **kwargs: Any
            ) -> HTTPResponseTco:
                response = await view_func(view, request, *args, **kwargs)
                await sync_to_async(handle_notification)(request, response)
                return response
        else:

            def wrapper(
                view, request: HttpRequest, *args: str, **kwargs: Any
            ) -> HTTPResponseTco:
                response = view_func(view, request, *args, **kwargs)
                handle_notification(request, response)
                return response

        return functools.wraps(view_func)(wrapper)  # type: ignore

    if view_func:
        return decorator(view_func)  # type: ignore
    return decorator


CodeMap = Dict[Union[int, str], Union[int, str]]


def _get_replacement_code(code_map: CodeMap, code: int) -> int:
    """
    Get the new status code based on the mapping.

    :param code_map: A dictionary mapping old status codes to new status codes.
    :param code: The status code to be replaced.
    """
    replacement = code
    try:
        # use the status code as is
        key = code
        replacement = code_map[key]
    except KeyError:
        # try using the status code as a string
        key = str(code)
        try:
            replacement = code_map[key]
        except KeyError:
            # try using the status code as a regex pattern
            for old_code, new_code in code_map.items():
                if not isinstance(old_code, str):
                    continue
                # replace 'x' with '\d' to match any digit
                code_pattern = old_code.lower().replace("x", r"\d")
                re_pattern = re.compile(code_pattern)
                if re_pattern.match(key):
                    replacement = new_code
                    break
    try:
        return int(replacement)
    except ValueError as exc:
        raise ValueError(f"Invalid status code mapping: {replacement}") from exc


def map_code(code_map: CodeMap, *, method: str = "dispatch"):
    """
    Replaces response status code based on a mapping.

    Leaves the status code as is if no map is found.

    :param view_func: The view function to be decorated.
    :param code_map: A dictionary mapping old status codes to new status codes.
    :param method: For specificity, the method to be decorated in a class-based view.
    By default, it is set to "dispatch" which is sufficient for capturing all responses.

    Example usage:
    ```python

    @map_code({404: 400})
    def my_view(request):
        return HttpResponse(status=404)
    ```

    Or for class-based views:
    ```python

    @map_code({"2xx": 200}) # replace all 2xx status codes with 200
    class MyView(View):
        def put(self, request):
            return HttpResponse(status=202)

        def post(self, request):
            return HttpResponse(status=201)
    ```
    """
    if not code_map:
        raise ValueError("A status code mapping must be provided to use this decorator")

    def view_decorator(view: Union[CBV, FBV]) -> Union[CBV, FBV]:
        if is_view_class(view):
            nonlocal method
            method = method.lower()
            view_method = getattr(view, method)
            setattr(view, method, view_decorator(view_method))
            return view

        if not callable(view):
            raise ValueError("A view function must be provided to use this decorator")

        if asyncio.iscoroutinefunction(view):

            async def method_wrapper(*args, **kwargs) -> HTTPResponseTco:
                response = await view(*args, **kwargs)
                response.status_code = await sync_to_async(_get_replacement_code)(
                    code_map, response.status_code
                )
                return response
        else:

            def method_wrapper(*args, **kwargs) -> HTTPResponseTco:
                response = view(*args, **kwargs)
                response.status_code = _get_replacement_code(
                    code_map, response.status_code
                )
                return response

        return functools.wraps(view)(method_wrapper)

    return view_decorator


def redirect_authenticated(
    redirect_to: Union[Callable, str], *, method: str = "dispatch"
):
    """
    Redirects authenticated users to designated view.

    :param redirect_to: The view to redirect to. Could be a view, view name or url.
    :param method: For specificity, the method to be decorated in a class-based view.
    """

    def decorator(view: Union[CBV, FBV]) -> Union[CBV, FBV]:
        if is_view_class(view):
            nonlocal method
            method = method.lower()
            view_method = getattr(view, method)
            setattr(view, method, decorator(view_method))
            return view

        if asyncio.iscoroutinefunction(view):

            async def wrapper(self, request: HttpRequest, *args: str, **kwargs: Any):
                if request.user.is_authenticated:
                    return redirect(redirect_to)

                return await view(self, request, *args, **kwargs)
        else:

            def wrapper(self, request: HttpRequest, *args: str, **kwargs: Any):
                if request.user.is_authenticated:
                    return redirect(redirect_to)

                return view(self, request, *args, **kwargs)

        return functools.wraps(view)(wrapper)

    return decorator


def to_JsonResponse(view_func: FBV) -> FBV:
    """
    Function based view decorator.

    Ensures that the decorated view returns a JsonResponse.
    """
    if asyncio.iscoroutinefunction(view_func):

        async def wrapper(request: HttpRequest, *args, **kwargs) -> JsonResponse:
            response: HTTPResponseTco = await view_func(request, *args, **kwargs)

            if (
                isinstance(response, JsonResponse)
                or response.headers.get("content-type") == "application/json"
            ):
                return response

            return JsonResponse(
                data={
                    "status": "error" if response.status_code >= 400 else "success",
                    "detail": response.content.decode(),
                },
                status=response.status_code,
            )
    else:

        def wrapper(request: HttpRequest, *args, **kwargs) -> JsonResponse:
            response = view_func(request, *args, **kwargs)

            if (
                isinstance(response, JsonResponse)
                or response.headers.get("content-type") == "application/json"
            ):
                return response

            return JsonResponse(
                data={
                    "status": "error" if response.status_code >= 400 else "success",
                    "detail": response.content.decode(),
                },
                status=response.status_code,
            )

    return functools.wraps(view_func)(wrapper)
