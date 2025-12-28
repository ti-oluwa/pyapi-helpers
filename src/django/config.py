import functools
import collections.abc

from typing import Any, Dict, Union
from types import MappingProxyType
from django.conf import settings as django_settings

from src.generics.utils.misc import merge_mappings


def _make_proxy_getter(module, settings: Any):
    def proxy_getter(name: str) -> Any:
        try:
            value = getattr(settings, name)
        except AttributeError:
            value = getattr(settings, name.upper())
        return value

    if hasattr(module, "__getattr__"):
        return functools.wraps(module.__getattr__)(proxy_getter)
    return proxy_getter


def make_proxy(module, settings):
    """
    Makes settings accessible through the module
    """
    module.__getattr__ = _make_proxy_getter(module, settings)
    return module


DEFAULT_SETTINGS = {
    "CHANNELS": {
        "AUTH": {
            "API_KEY": {
                "header": "WS_X_API_KEY",
                "model": "rest_framework_api_key.models.APIKey",
            },
            "TOKEN": {
                "header": "WS_X_AUTH_TOKEN",
                "model": "rest_framework.authtoken.models.Token",
            },
            "SCOPE_USER_KEY": "user",
        },
        "MIDDLEWARE": [
            "channels.security.websocket.AllowedHostsOriginValidator",
        ],
    },
    "MAINTENANCE_MODE": {"status": "off", "message": "default:minimal_dark"},
    "RESPONSE_FORMATTER": {
        "formatter": "default",
        "exclude": [r"/admin*"],
        "enforce_format": True,
    },
}


class ValueStoreProxy(collections.abc.Mapping):
    """
    Proxy for accessing the values in a value store or dictionary as attributes
    """

    def __init__(self, valuestore: Dict[str, Any], *, recursive: bool = False) -> None:
        if recursive:
            self.valuestore = self.nested_valuestores_to_proxies(valuestore)
        else:
            # Wrapped in MappingProxyType to prevent modification of the original dictionary
            self.valuestore = MappingProxyType(valuestore)

    @classmethod
    def nested_valuestores_to_proxies(
        cls,
        valuestore: Dict[str, Any],
    ) -> Dict[str, Union["ValueStoreProxy", Any]]:
        new_valuestore = {}
        for key, value in valuestore.items():
            if not isinstance(value, collections.abc.Mapping):
                new_valuestore[key] = value
            elif isinstance(value, ValueStoreProxy):
                new_valuestore[key] = value
            else:
                new_valuestore[key] = ValueStoreProxy(value, recursive=True)
        return new_valuestore

    def __getattr__(self, name: str) -> Union["ValueStoreProxy", Any]:
        try:
            return self.valuestore[name]
        except KeyError as exc:
            raise AttributeError(exc) from exc

    def __getitem__(self, name: str) -> Union["ValueStoreProxy", Any]:
        return getattr(self, name)

    def __repr__(self):
        return f"{self.__name__}({repr(self.valuestore)})"

    def __iter__(self):
        return iter(self.valuestore)

    def __len__(self):
        return len(self.valuestore)

    def get(self, name: str, default: Any = None) -> Any:
        try:
            return getattr(self, name)
        except AttributeError:
            return default


class _Settings(ValueStoreProxy):
    """Settings loader"""

    __instance = None

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        if cls.__instance:
            raise RuntimeError("Settings already loaded")

        cls.__instance = instance
        return instance

    def __init__(self, setting_name: str) -> None:
        settings: Dict[str, Any] = merge_mappings(
            DEFAULT_SETTINGS, getattr(django_settings, setting_name, {})
        )
        return super().__init__(settings, recursive=True)


settings = _Settings("HELPERS_SETTINGS")
"""`helpers` module's settings"""
