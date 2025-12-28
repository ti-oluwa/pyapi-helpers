from django.http import HttpResponse, JsonResponse
from typing import TypeVar

from .shortcuts import * # noqa

HTTPResponseTco = TypeVar("HTTPResponseTco", bound=HttpResponse, covariant=True)
JSONResponseTco = TypeVar("JSONResponseTco", bound=JsonResponse, covariant=True)
