from typing import TypeVar
from starlette.responses import Response, JSONResponse

from .shortcuts import *  # noqa

ResponseTco = TypeVar("ResponseTco", bound=Response, covariant=True)
JSONResponseTco = TypeVar("JSONResponseTco", bound=JSONResponse, covariant=True)
