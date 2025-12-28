import collections.abc
import functools
from typing import Dict, Mapping, Union, Any

from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import Response
from starlette import status
from starlette.websockets import WebSocketClose

from src.fastapi.exceptions import ImproperlyConfigured
from src.fastapi.config import settings
from src.logging import log_exception
from src import RESOURCES_PATH
from src.dependencies import depends_on
from src.generics.utils.caching import ttl_cache


class MaintenanceMiddleware:
    """
    Middleware to handle application maintenance mode.
    The middleware will return a 503 Service Unavailable response with the maintenance message.

    #### Ensure to place this middleware at the top of `MIDDLEWARE` settings.

    Middleware settings:

    - `MAINTENANCE_MODE.status`: Set as "ON" or "OFF", True or False, to enable or disable maintenance mode.
    - `MAINTENANCE_MODE.message`: The message to display in maintenance mode. Can be a path to a template file or a string.

    There are default maintenance message templates available:

    - `default:minimal`: Minimal and clean. Light-themed
    - `default:minimal_dark`: Dark-themed minimal
    - `default:techno`: Techno-themed
    - `default:jazz`: Playful jazz-themed

    In settings.py:

    ```python
    MAINTENANCE_MODE = {
        "status": True,
        "message": "default:techno"
    }
    ```
    """

    templates_dir = RESOURCES_PATH / "templates/maintenance"
    defaults_prefix = "default:"
    setting_name = "MAINTENANCE_MODE"

    @depends_on({"aiofiles": "aiofiles"})
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @functools.cached_property
    def settings(cls) -> Mapping[str, Any]:
        middleware_settings = settings.get(cls.setting_name, {})
        if not isinstance(middleware_settings, collections.abc.Mapping):
            raise TypeError(
                f"settings.{cls.setting_name} should be a mapping not {type(middleware_settings).__name__}"
            )
        return middleware_settings

    @functools.cached_property
    def maintenance_mode_on(self) -> bool:
        """Check if the application is in maintenance mode."""
        status = str(self.settings.get("status", "off"))
        return status.lower() in ["on", "true"]

    @ttl_cache(ttl=3600)
    async def get_message(self) -> Union[str, bytes]:
        """Return the maintenance message."""
        msg = self.settings.get("message", "default:minimal")

        if not isinstance(msg, str):
            raise ImproperlyConfigured(f"{self.setting_name}.message must be a string")

        if msg.lower().startswith(self.defaults_prefix.lower()):
            slice_start = len(self.defaults_prefix)
            template_name = msg[slice_start:]
            msg = await self.get_default_template(template_name)

        return msg or "Service Unavailable"

    async def get_default_template(self, name: str) -> Union[bytes, None]:
        """Get the default maintenance template content."""
        import aiofiles

        template_path = self.templates_dir / f"{name.lower()}.html"
        try:
            if template_path.exists():
                async with aiofiles.open(template_path, "rb") as file:
                    return await file.read()
        except Exception as exc:
            log_exception(exc)
        return None

    async def get_response_content(self) -> Union[str, bytes]:
        """Returns the response content."""
        return await self.get_message()

    async def get_response_headers(self) -> Dict[str, Any]:
        """Returns the response headers."""
        return {
            "Content-Type": "text/html",
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process the request."""
        if self.maintenance_mode_on:
            if scope["type"] == "http":
                content = await self.get_response_content()
                headers = await self.get_response_headers()
                response = Response(
                    content,
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    headers=headers,
                )
                await response(scope, receive, send)
                return

            elif scope["type"] == "websocket":
                websocket_close = WebSocketClose(
                    code=status.WS_1001_GOING_AWAY,
                    reason="Service Unavailable",
                )
                await websocket_close(scope, receive, send)
                return

        await self.app(scope, receive, send)
