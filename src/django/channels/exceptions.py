from django.core.exceptions import ValidationError


class WebsocketException(Exception):
    """Base websocket exception"""

    pass


class UnsupportedEvent(WebsocketException):
    """Raised for invalid or unsupported websocket event types"""

    pass


class InvalidData(WebsocketException, ValidationError):
    """Validation error for invalid data in an event."""

    pass
