class FastAPIException(Exception):
    """Base exception class for all exceptions in `helpers.fastapi` submodule"""

    pass


class ImproperlyConfigured(FastAPIException):
    """Raised when a configuration error is detected."""

    pass


__all__ = ["FastAPIException", "ImproperlyConfigured"]
