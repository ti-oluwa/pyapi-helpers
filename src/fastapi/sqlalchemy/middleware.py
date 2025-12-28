from starlette.types import ASGIApp, Receive, Scope, Send

from src.fastapi.sqlalchemy.setup import get_session, get_async_session


class AsyncSessionMiddleware:
    """
    ASGI Middleware to attach an async DB session to the request object.

    Automatically commits the session to the database and closes it after the request is processed.
    Uncommitted changes are rolled back if an exception occurs while processing the request.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        async def app_with_session(scope: Scope, receive: Receive, send: Send) -> None:
            async with get_async_session() as session:
                scope["state"] = getattr(scope, "state", {})
                scope["state"]["db_session"] = session
                await self.app(scope, receive, send)

        await app_with_session(scope, receive, send)


class SessionMiddleware:
    """
    ASGI Middleware to attach a DB session to the request object.

    Automatically commits the session to the database and closes it after the request is processed.
    Uncommitted changes are rolled back if an exception occurs while processing the request.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        async def app_with_session(scope: Scope, receive: Receive, send: Send) -> None:
            with get_session() as session:
                scope["state"] = getattr(scope, "state", {})
                scope["state"]["db_session"] = session
                await self.app(scope, receive, send)

        await app_with_session(scope, receive, send)
