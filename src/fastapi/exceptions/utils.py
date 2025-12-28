import typing
from starlette.exceptions import HTTPException
from starlette.requests import HTTPConnection


async def raise_http_exception(
    connection: HTTPConnection,
    status_code: int,
    detail: str = "Oops! An error occurred.",
    headers: typing.Optional[typing.Dict[str, str]] = None,
):
    """
    Raises an HTTP exception with the provided status code and detail.

    :param connection: The HTTP connection.
    :param status_code: The status code to return.
    :param detail: The detail to return. Default is "Oops! An error occurred.".
    """
    raise HTTPException(
        status_code=status_code,
        detail=detail,
        headers=headers,
    )
