import typing
from typing_extensions import Doc
from starlette.requests import HTTPConnection
from starlette import status
from fastapi.security.http import HTTPBase, HTTPAuthorizationCredentials
from fastapi.security.utils import get_authorization_scheme_param

from src.fastapi.openapi.models import HTTPToken as HTTPTokenModel
from src.fastapi.exceptions.utils import raise_http_exception


class HTTPToken(HTTPBase):
    """
    HTTP Token token authentication.

    ## Usage

    Create an instance object and use that object as the dependency in `Depends()`.

    The dependency result will be an `HTTPAuthorizationCredentials` object containing
    the `scheme` and the `credentials`.

    ## Example

    ```python
    from typing import Annotated

    from fastapi import Depends, FastAPI
    from fastapi.security import HTTPAuthorizationCredentials

    app = FastAPI()

    security = HTTPToken()


    @app.get("/users/me")
    def read_current_user(
        credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
    ):
        return {"scheme": credentials.scheme, "credentials": credentials.credentials}
    ```
    """

    def __init__(
        self,
        *,
        name: typing.Annotated[str, Doc("Authorization token name")] = "token",
        tokenFormat: typing.Annotated[
            typing.Optional[str], Doc("Token format.")
        ] = None,
        scheme_name: typing.Annotated[
            typing.Optional[str],
            Doc(
                """
                Security scheme name.

                It will be included in the generated OpenAPI (e.g. visible at `/docs`).
                """
            ),
        ] = None,
        description: typing.Annotated[
            typing.Optional[str],
            Doc(
                """
                Security scheme description.

                It will be included in the generated OpenAPI (e.g. visible at `/docs`).
                """
            ),
        ] = None,
        auto_error: typing.Annotated[
            bool,
            Doc(
                """
                By default, if the HTTP Token token is not provided (in an
                `Authorization` header), `HTTPToken` will automatically cancel the
                request and send the client an error.

                If `auto_error` is set to `False`, when the HTTP Token token
                is not available, instead of erroring out, the dependency result will
                be `None`.

                This is useful when you want to have optional authentication.

                It is also useful when you want to have authentication that can be
                provided in one of multiple optional ways (for example, in an HTTP
                Token token or in a cookie).
                """
            ),
        ] = True,
    ):
        self.model: HTTPTokenModel = HTTPTokenModel(
            tokenFormat=tokenFormat,
            description=description,
            scheme=name,
        )
        self.scheme_name = scheme_name or self.__class__.__name__
        self.auto_error = auto_error

    async def __call__(
        self, connection: HTTPConnection
    ) -> typing.Optional[HTTPAuthorizationCredentials]:
        authorization = connection.headers.get("Authorization")
        scheme, credentials = get_authorization_scheme_param(authorization)
        if not (authorization and scheme and credentials):
            if self.auto_error:
                return await raise_http_exception(
                    connection,
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authenticated",
                    headers={
                        "WWW-Authenticate": f"{self.model.scheme} {self.model.tokenFormat or ''}"
                    },
                )
            else:
                return None
        if scheme.lower() != self.model.scheme:
            if self.auto_error:
                return await raise_http_exception(
                    connection,
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid authentication credentials",
                    headers={
                        "WWW-Authenticate": f"{self.model.scheme} {self.model.tokenFormat or ''}"
                    },
                )
            else:
                return None
        return HTTPAuthorizationCredentials(scheme=scheme, credentials=credentials)
