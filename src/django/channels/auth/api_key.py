from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs
from django.utils.module_loading import import_string
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async

from src.django.channels import channels_settings
from src.django.channels.utils import async_reject_connection


apikey_settings = channels_settings.AUTH.API_KEY
"""Proxy for accessing the API key settings defined in the helpers settings"""


@database_sync_to_async
def check_api_key_is_valid(api_key: str) -> bool:
    """
    Check if an API key is valid.

    :param api_key: The API key to check
    :return: True if the API key exists, False otherwise
    """

    model_path = apikey_settings.model
    model = import_string(model_path)
    try:
        return model.objects.is_valid(api_key)
    except model.DoesNotExist:
        return False


async def get_api_key_header() -> str:
    """Get the API key header from settings"""
    header: str = apikey_settings.header
    header = header.lower().replace("_", "-").removeprefix("ws-")
    return header


async def get_api_key_from_headers(headers: List) -> Optional[Any]:
    """
    Get the API key from the headers

    :param headers: Scope headers
    """
    name = await get_api_key_header()
    for header in headers:
        key = header[0].decode("utf-8")
        value = header[1].decode("utf-8")

        if key == name:
            return value
    return None


async def get_api_key_from_scope(scope: Dict) -> Optional[str]:
    """
    Checks the websocket consumer scope headers and query string for an API key.

    This function checks the headers and query string for an api key.

    :param scope: scope from websocket consumer
    :return: API key if found else, None.
    """
    query_string = scope["query_string"].decode("utf-8")
    header = await get_api_key_header()
    param_name = header.replace("-", "_")

    if query_string:
        # Check query params for API key
        query_params = parse_qs(query_string)
        api_key = query_params.get(param_name, None)
        if api_key:
            return api_key[0]

    # Check headers for API key
    headers = scope.get("headers", [])
    return await get_api_key_from_headers(headers)


UNAUTHORIZED_MSG = "Unauthorized! Ensure a valid API key is included in your connection request's header or url query params."
UNAUTHORIZED_CODE = 4001  # Unauthorized error code


class APIKeyAuthMiddleware(BaseMiddleware):
    """
    Ensures that a valid API key is provided before accepting a connection

    The headers and query string are checked for an api key.

    The default header is "X-API-KEY" and the query string parameter is
    "x_api_key". These can be changed in the settings.

    By default, `rest_framework_api_key.models.APIKey` is used to
    validate the API key.

    Example Usage:

    ```JSON
    HELPERS_SETTINGS = {
        ...,
        "WEBSOCKETS": {
            "CHANNELS": {
                "AUTHORIZATION": {
                    "API_KEY": {
                        "header": "WS_X_API_KEY",
                        "model": "rest_framework_api_key.models.APIKey",
                    }
                },
                "MIDDLEWARE": [
                    "helpers.websockets.channels.auth.api_key.APIKeyAuthMiddleware"
                ]
                ...
            },
            ...
        },
        ...
    }
    ```
    """

    async def __call__(self, scope, receive, send):
        api_key = await get_api_key_from_scope(scope)
        if not api_key:
            return await async_reject_connection(
                send, UNAUTHORIZED_MSG, UNAUTHORIZED_CODE
            )

        authorized = await check_api_key_is_valid(api_key)
        if not authorized:
            return await async_reject_connection(
                send, UNAUTHORIZED_MSG, UNAUTHORIZED_CODE
            )
        return await super().__call__(scope, receive, send)
