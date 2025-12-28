import fastapi
import importlib

from src.fastapi.application import app_setup


def path(module: str, router_name: str = "router") -> fastapi.APIRouter:
    """
    Returns the router instance from the given module path

    :param module: module path e.g. apps.users.endpoints
    :param router_name: router name. Default is `router`

    Example Usage:
    ```python
    import fastapi

    router = fastapi.APIRouter()

    # Includes the router defined at apps.users.endpoints in this router
    router.include_router(path("apps.users.endpoints", router_name="router"))
    ```
    """
    try:
        return importlib.import_module(module).__dict__[router_name]
    except KeyError:
        raise ImportError(f"Router not found in module: {module}")


def install_router(router: fastapi.APIRouter, router_name: str, **kwargs) -> None:
    """
    Installs a setup that includes the FastAPI APIRouter in the application.

    :param router: FastAPI router instance
    :param router_name: router name
    :param kwargs: additional router setup arguments
    """
    import inflection  # type: ignore[import]

    def _router_setup(app: fastapi.FastAPI) -> fastapi.FastAPI:
        app.include_router(router, **kwargs)
        return app

    setup_name = inflection.underscore(f"include_{router_name}")
    app_setup(_router_setup, name=setup_name)
    return
