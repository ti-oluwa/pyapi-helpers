import typing
from django.utils.module_loading import import_string

from src.django.channels import channels_settings


def get_middlewares() -> typing.List[str]:
    """Returns the list of middlewares defined in the helpers settings"""
    middlewares: typing.List[str] = channels_settings.MIDDLEWARE
    return middlewares


def apply_middleware(router, middleware: typing.List[str]):
    """
    Applies the middleware to the router
    """
    for path in middleware:
        middleware_cls = import_string(path)
        router = middleware_cls(router)
    return router


async def async_reject_connection(send, message: str, code: int) -> None:
    """Rejects the connection with the given message and code"""
    await send({"type": "websocket.close", "code": code, "reason": message})
    return None


def reject_connection(send, message: str, code: int) -> None:
    """Rejects the connection with the given message and code"""
    send({"type": "websocket.close", "code": code, "reason": message})
    return None


def get_user_from_scope(
    scope: typing.Dict,
    *,
    user_key: str = channels_settings.AUTH.SCOPE_USER_KEY,
) -> typing.Optional[typing.Any]:
    """
    Returns the user objects from the connection scope based
    on the given key or settings, if found. Else, returns None.

    :param scope: websocket connection scope
    :param user_key: Key to be used to retrieve the user object from the scope
    """
    return scope.get(user_key, None)
