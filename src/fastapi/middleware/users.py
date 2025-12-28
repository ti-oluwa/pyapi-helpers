from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import HTTPConnection

from src.fastapi.models.users import AbstractBaseUser, AnonymousUser


class ConnectedUserMiddleware:
    """
    Middleware that adds the connected user to the connection state.
    `connection.state.user` will be an ``AbstractBaseUser`` instance.

    If no user is connected, `connection.state.user` will be an ``AnonymousUser`` instance.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope, receive)
        connected_user = getattr(connection.state, "user", None)
        if not isinstance(connected_user, AbstractBaseUser):
            connection.state.user = AnonymousUser()

        await self.app(scope, receive, send)
