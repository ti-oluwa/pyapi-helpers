import asyncio
import importlib
import functools
import inspect
import types
import typing

from .config import settings
from .exceptions import AppError, AppConfigurationError
from .utils.sync import sync_to_async


class SubmoduleNotFoundError(AppError):
    """Raised when a submodule is not found in an app"""


class App:
    """A proxy object for an installed app"""

    def __init__(self, path: str) -> types.NoneType:
        self._path = path
        try:
            self._module = importlib.import_module(path, package=settings.BASE_DIR.name)
        except ImportError as exc:
            raise AppError(f"App not found: '{path}'") from exc

    @functools.cached_property
    def name(self) -> str:
        """Name of the app"""
        apps = self.apps
        if apps:
            return getattr(apps, "app_name", self._path)
        return self._path

    @functools.cached_property
    def apps(self) -> typing.Optional[types.ModuleType]:
        """Shortcut to the app's `apps` submodule"""
        try:
            return self.submodule("apps")
        except SubmoduleNotFoundError:
            return None

    @functools.cached_property
    def models(self) -> typing.Optional[types.ModuleType]:
        """Shortcut to the app's `models` submodule"""
        try:
            return self.submodule("models")
        except SubmoduleNotFoundError:
            return None

    @functools.cached_property
    def commands(self) -> typing.Optional[types.ModuleType]:
        """Shortcut to the app's `commands` submodule"""
        try:
            return self.submodule("commands")
        except SubmoduleNotFoundError:
            return None

    @functools.cached_property
    def services(self) -> typing.Optional[types.ModuleType]:
        """Shortcut to the app's `services` submodule"""
        try:
            return self.submodule("services")
        except SubmoduleNotFoundError:
            return None

    @functools.cached_property
    def routes(self) -> typing.Optional[types.ModuleType]:
        """Shortcut to the app's `routes` submodule"""
        try:
            return self.submodule("routes")
        except SubmoduleNotFoundError:
            return None

    def submodule(self, submodule_path: str) -> types.ModuleType:
        """
        Get a submodule from the app

        :param submodule_path: path to submodule in app
        :return: submodule object
        :raises SubmoduleNotFoundError: if submodule is not found in app
        """
        return get_submodule(self, submodule_path)

    def __repr__(self) -> str:
        return f"<App name={self.name} path={self._path}>"

    def __str__(self) -> str:
        return self.name


def get_submodule(app: App, submodule_path: str) -> types.ModuleType:
    """
    Get a submodule from the app

    :param app: app object
    :param submodule_path: path to submodule in app
    :return: submodule object
    :raises SubmoduleNotFoundError: if submodule is not found in app
    """
    if not submodule_path:
        return app._module

    try:
        submodule = importlib.import_module(
            f"{app._path}.{submodule_path}", package=settings.BASE_DIR.name
        )
    except ImportError as exc:
        # This means the ImportError was not caused by the submodule not being found
        # but by some other import issue (such as a missing dependency)
        if app._path not in str(exc):
            raise
        raise SubmoduleNotFoundError(
            f"Submodule '{submodule_path}' not found in app '{app._path}'"
        ) from exc

    return submodule


def discover_apps():
    """
    Searches for all installed apps and returns a proxy object for each

    The proxy object is a wrapper around the app's `apps` module
    and allows read-only access the module's attributes
    """
    for app_path in settings.INSTALLED_APPS:
        yield App(app_path)


def discover_models(*apps: str):
    """
    Searches for and yields all models in the specified app

    :param apps: name of apps to search for models in
    """
    import sqlalchemy as sa

    for app in discover_apps():
        if apps and app.name not in apps:
            continue
        models = app.models
        if not models:
            break
        for attr in dir(models):
            model = getattr(models, attr)
            if not inspect.isclass(model):
                continue

            mapper = sa.inspect(model, raiseerr=False)
            if mapper is not None and mapper.is_mapper:
                yield model


async def configure(app: App) -> None:
    """
    Run app's configuration logic

    If the function is not found, this is a no-op
    """
    try:
        apps = app.apps
        if not apps:
            return

        configure = getattr(apps, "configure", None)
        if not configure:
            return
        if asyncio.iscoroutinefunction(configure):
            await configure()
        elif callable(configure):
            await sync_to_async(configure)()
    except Exception as exc:
        raise AppConfigurationError(f"Error configuring app '{app.name}'") from exc
    return


async def configure_apps():
    """
    Run configuration logic for all apps in the project
    """
    for app in discover_apps():
        await configure(app)
