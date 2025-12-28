from typing import Union, Dict, List, Optional
from django.utils.module_loading import import_string
from urllib.parse import parse_qs
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser, AbstractBaseUser

from src.django.channels import channels_settings


token_settings = channels_settings.AUTH.TOKEN
"""Proxy for accessing the token settings defined in the helpers settings"""


@database_sync_to_async
def get_token_user(key: str) -> Union[AbstractBaseUser, AnonymousUser]:
    """
    Retrieve the token from the database by key and return the token user

    :param key: The key of the token
    :return: The token user if it exists, or an AnonymousUser otherwise
    """
    model_path = token_settings.model
    model = import_string(model_path)
    try:
        token = model.objects.select_related("user").get(key=key)
    except model.DoesNotExist:
        return AnonymousUser()
    return token.user


async def get_token_header() -> str:
    """Get the token header from settings"""
    header: str = token_settings.header
    header = header.lower().replace("_", "-").removeprefix("ws-")
    return header


async def get_token_from_headers(keyword: str, headers: List) -> Optional[str]:
    """
    Get the token from the headers

    :param keyword: The keyword to search for in the headers
    :param headers: Scope headers
    :return: The token if found else, None.
    """
    name = await get_token_header()
    for header in headers:
        key = header[0].decode("utf-8")
        value = header[1].decode("utf-8")

        if key == name and value.startswith(f"{keyword} "):
            return value.split(" ")[1]
    return None


async def get_token_from_scope(keyword: str, scope: Dict) -> Optional[str]:
    """
    Checks the websocket consumer scope headers and query string for a token.

    :param scope: scope from websocket consumer
    :return: Token if found else, None.
    """
    query_string = scope["query_string"].decode("utf-8")
    header = await get_token_header()
    param_name = header.replace("-", "_")

    if query_string:
        # Check query params for token
        query_params = parse_qs(query_string)
        token = query_params.get(param_name, None)
        if token:
            return token[0].split(" ")[1]

    # Check headers for t
    headers = scope.get("headers", [])
    return await get_token_from_headers(keyword, headers)


class TokenMiddleware(BaseMiddleware):
    """
    Middleware that authenticates the user based on the token

    This middleware checks the scope headers for a token and authenticates the user based on the token.

    In scope headers, the auth token should be in the format: "Token <_token_>"

    Example Usage:
    ```JSON
    HELPERS_SETTINGS = {
        "WEBSOCKETS": {
            "CHANNELS": {
                "AUTH": {
                    "TOKEN": {
                        "header": "WS_X_AUTH_TOKEN",
                        "model": "rest_framework.authtoken.models.Token",
                    },
                    ...
                },
                "MIDDLEWARE": [
                    ...
                    "helpers.websockets.channels.auth.token.TokenMiddleware",
                    ...
                ]
            }
        },
    }

    ```
    """

    keyword = "Token"

    async def __call__(self, scope, receive, send):
        token_string = await get_token_from_scope(self.keyword, scope)
        scope[channels_settings.AUTH.SCOPE_USER_KEY] = await get_token_user(
            token_string
        )
        return await super().__call__(scope, receive, send)
