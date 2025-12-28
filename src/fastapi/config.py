import os
import typing
import collections.abc
import importlib
from types import ModuleType

from src.generics.utils.misc import merge_mappings
from src.types import MappingProxy
from src.fastapi import default_settings


SETTINGS_ENV_VARIABLE = "FASTAPI_SETTINGS_MODULE"


def _settings_from_module(module: ModuleType) -> typing.Dict[str, typing.Any]:
    settings = {}
    for attr in dir(module):
        if not attr.isupper():
            continue
        settings[attr] = getattr(module, attr)
    return settings


def load_settings(settings_module: str) -> typing.Dict[str, typing.Any]:
    """Load settings from a module"""
    module = importlib.import_module(settings_module)
    return _settings_from_module(module)


class Settings:
    """
    Application Settings.

    Loads settings from a module and provide a read-only interface to access them.

    By default, settings are loaded from the module specified in the `FAST_API_SETTINGS_MODULE` environment variable,
    and is merged with the default settings provided in the `default_settings` module.

    Example:
    ```python
    import fastapi
    from src.fastapi.config import settings

    async def lifespan(app: fastapi.FastAPI) -> None:
        try:
            settings.configure(DEBUG=True)
            # do other pre-startup setup
            yield
        finally:
            pass

    app = fastapi.FastAPI(lifespan=lifespan, ...)

    print(settings.DEBUG) # True
    ```
    """

    def __init__(self, settings_module: typing.Optional[str] = None, /) -> None:
        self.__dict__["_store"] = None
        self.__dict__["_settings_module"] = settings_module

    @property
    def configured(self) -> bool:
        return self._store is not None and isinstance(
            self._store, collections.abc.Mapping
        )

    def __setattr__(self, name: typing.Any, value: typing.Any):
        raise RuntimeError(f"{type(self).__name__} cannot be modified")

    def __getattr__(self, name: str) -> typing.Any:
        if not self.configured:
            raise RuntimeError(
                f"{type(self).__name__} not configured. "
                f"Run `configure(...)` before attribute access"
            )
        try:
            return self._store[name]
        except KeyError as exc:
            raise AttributeError(exc) from exc

    def __getitem__(self, name: typing.Any) -> typing.Any:
        return getattr(self, name)

    def configure(self, **options: typing.Any) -> None:
        """
        Configure the settings by merging user-defined settings with default settings.

        This method loads settings from the module specified in the `FASTAPI_SETTINGS_MODULE` environment variable,
        merges them with the default settings from the `default_settings` module, and applies any additional options

        Ensure that is called before accessing any settings attributes. Else, a RuntimeError will be raised.
        """
        if self.configured:
            return

        user_defined_settings = load_settings(
            self.__dict__["_settings_module"] or os.environ[SETTINGS_ENV_VARIABLE]
        )
        defaults = _settings_from_module(default_settings)
        aggregate_settings = merge_mappings(
            defaults, user_defined_settings, merge_nested=True
        )

        for key, value in options.items():
            if not key.isupper():
                raise ValueError(
                    "Options for settings should be provided in upper case."
                )
            aggregate_settings[key] = value

        self.__dict__["_store"] = MappingProxy(aggregate_settings, recursive=True)


settings = Settings()
