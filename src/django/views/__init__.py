from inspect import isclass
from django.views import View
from django.http import HttpResponse
from typing import TypeVar, Callable, Coroutine, Any, Union


CBV = TypeVar("CBV", bound=View)
FBV = TypeVar(
    "FBV",
    bound=Callable[
        ..., Union[HttpResponse, Any] | Coroutine[Any, Any, Union[HttpResponse, Any]]
    ],
)


def is_view_class(view) -> bool:
    """Returns whether a view is a class-based view."""
    return isclass(view) and issubclass(view, View)
