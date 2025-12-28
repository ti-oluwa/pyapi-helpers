import typing
from dataclasses import dataclass
from typing_extensions import ParamSpec
from types import MappingProxyType
import copy
import collections.abc


class SupportsRichComparison(typing.Protocol):
    def __lt__(self, other: typing.Any, /) -> bool: ...
    def __le__(self, other: typing.Any, /) -> bool: ...
    def __gt__(self, other: typing.Any, /) -> bool: ...
    def __ge__(self, other: typing.Any, /) -> bool: ...
    def __eq__(self, other: typing.Any, /) -> bool: ...
    def __ne__(self, other: typing.Any, /) -> bool: ...


class SupportsKeysAndGetItem(typing.Protocol):
    def __getitem__(self, name: typing.Any, /) -> typing.Any: ...

    def keys(self) -> typing.Iterable[typing.Any]: ...


P = ParamSpec("P")
R = typing.TypeVar("R")
T = typing.TypeVar("T")

Function = typing.Callable[P, R]
CoroutineFunction = typing.Callable[P, typing.Awaitable[R]]
NoneType = type(None)


@dataclass
class _Dataclass:
    pass


DataclassType = type(_Dataclass)


class LoggerLike(typing.Protocol):
    """A protocol for logging objects that support various logging methods."""

    def log(self, *args: typing.Any, **kwargs: typing.Any) -> None: ...
    def debug(self, *args: typing.Any, **kwargs: typing.Any) -> None: ...
    def info(self, *args: typing.Any, **kwargs: typing.Any) -> None: ...
    def warning(self, *args: typing.Any, **kwargs: typing.Any) -> None: ...
    def error(self, *args: typing.Any, **kwargs: typing.Any) -> None: ...
    def critical(self, *args: typing.Any, **kwargs: typing.Any) -> None: ...
    def exception(
        self, *args: typing.Any, exc_info: bool = True, **kwargs: typing.Any
    ) -> None: ...


class MappingProxy(collections.abc.Mapping):
    """
    Read-only mapping proxy for accessing key-value pairs as attributes.

    Example:
    ```python
    mapping = {"key_outer": {"key_inner": "value"}}

    # Simple attribute access
    proxy = MappingProxy(mapping)
    assert proxy.key_outer["key_inner"] == "value"

    # Recursive attribute access
    proxy = MappingProxy(mapping, recursive=True)
    assert proxy.key_outer.key_inner == "value"

    # Non-existent key
    proxy.non_existent_key  # Raises AttributeError

    # Setting a value
    proxy.key = "value"  # Raises RuntimeError
    ```
    """

    def __init__(
        self,
        mapping: SupportsKeysAndGetItem,
        *,
        recursive: bool = False,
        copier: typing.Optional[
            typing.Callable[[SupportsKeysAndGetItem], SupportsKeysAndGetItem]
        ] = copy.deepcopy,
    ) -> None:
        """
        Initialize the mapping proxy.

        :param mapping: The mapping to wrap
        :param recursive: Whether to recursively wrap nested mappings
        :param copier: A function to copy the mapping before
            wrapping. If None, the mapping is wrapped directly.
            However, this is not recommended as it allows
            modifications of the original mapping to affect
            the proxy since a reference is stored instead of a new copy.
        """
        if callable(copier):
            mapping_ = copier(mapping)
        else:
            mapping_ = mapping

        if recursive:
            self.__dict__["_wrapped"] = self._wrap_mapping_recursively(mapping_)
        else:
            self.__dict__["_wrapped"] = self._wrap_mapping(mapping_)
        return

    @classmethod
    def _wrap_mapping(
        cls,
        mapping: SupportsKeysAndGetItem,
    ):
        if isinstance(mapping, MappingProxyType):
            wrapped = mapping
        else:
            # Wrapped in `MappingProxyType` to prevent modification of the original mapping
            wrapped = MappingProxyType(mapping)
        return wrapped

    @classmethod
    def _wrap_mapping_recursively(
        cls,
        mapping: SupportsKeysAndGetItem,
    ):
        new_mapping = {}
        for key in mapping.keys():
            value = mapping[key]

            if isinstance(value, collections.abc.Mapping):
                new_mapping[key] = cls(
                    cls._wrap_mapping_recursively(value),
                    recursive=False,
                    copier=None,
                )
            else:
                new_mapping[key] = value
        return MappingProxyType(new_mapping)

    def __setattr__(self, attr, value):
        raise RuntimeError(f"{self.__name__} instance cannot be modified")

    def __getattr__(self, attr: typing.Any) -> typing.Union["MappingProxy", typing.Any]:
        try:
            return self._wrapped[attr]
        except KeyError as exc:
            raise AttributeError(exc) from exc

    def __getitem__(self, key: typing.Any) -> typing.Union["MappingProxy", typing.Any]:
        # The default collections.abc.Mapping behavior is to raise a TypeError
        # If the key is not a string. In such cases, we need to use this class'
        # __getattr__ method directly.
        try:
            return getattr(self, key)
        except TypeError:
            return self.__getattr__(key)

    def __repr__(self) -> str:
        return f"{self.__name__}{repr(self._wrapped).removeprefix('mappingproxy')}"

    def __iter__(self):
        return iter(self._wrapped)

    def __len__(self) -> int:
        return len(self._wrapped)

    def __contains__(self, key: typing.Any) -> bool:
        try:
            self._wrapped[key]
        except KeyError:
            return False
        return True
