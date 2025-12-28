from .base import FastAPIException, ImproperlyConfigured


class AppError(FastAPIException):
    """Raised when an application error is detected."""

    pass


class AppConfigurationError(AppError, ImproperlyConfigured):
    """Raised when an application configuration error is detected."""

    pass


__all__ = ["AppError", "AppConfigurationError"]
