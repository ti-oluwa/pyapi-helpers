import typing
from django.utils.module_loading import import_string
from django.urls import URLPattern

from src.django.channels.utils import apply_middleware, get_middlewares


def include(path: str, routes_name: str = "websocket_urlpatterns"):
    """
    Adapted from Django's `include` function to import websocket routes from a module.

    :param path: The path to the module containing the routes.
    :param routes_name: The name of the variable containing the routes in the module.
    :return: A URLRouter with the routes applied.
    """
    from channels.routing import URLRouter

    urlpatterns: typing.Optional[typing.List[URLPattern]] = import_string(
        f"{path}.{routes_name}"
    )
    if not isinstance(urlpatterns, list):
        raise ValueError(f"Could not find valid routes, '{routes_name}'")
    return URLRouter(urlpatterns)


def get_application(routes: typing.List[URLPattern]):
    """
    Returns the application/router with the routes and middleware applied.

    :param routes: The routes to be applied to the application.
    """
    from channels.routing import URLRouter

    router = URLRouter(routes)
    router = apply_middleware(router, get_middlewares())
    return router
