import typing

from fastapi.openapi.models import HTTPBase


class HTTPToken(HTTPBase):
    scheme: str = "token"
    tokenFormat: typing.Optional[str] = None
