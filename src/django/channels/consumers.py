from enum import Enum
import typing
from contextlib import asynccontextmanager
from channels.generic.websocket import AsyncConsumer
from channels.generic.websocket import AsyncJsonWebsocketConsumer
import functools
import inspect

from .events import (
    IncomingEvent,
    OutgoingEvent,
    EventStatus,
    EventType,
    BaseEventType,
)
from src.django.channels.exceptions import UnsupportedEvent
from src.logging import log_exception
from src.generics.utils.misc import merge_enums


ERROR_ATTRIBUTES = ("detail", "message_dict", "error_dict", "error_list")


def _clean_errors(errors: typing.Any):
    if not errors:
        return errors

    if isinstance(errors, dict):
        cleaned_errors = {}
        for key, error in errors.items():
            cleaned_errors[key] = _clean_errors(error)
        return cleaned_errors

    elif isinstance(errors, (list, set, tuple)):
        cleaned_errors = []
        for error in errors:
            cleaned_errors.append(_clean_errors(error))
        return cleaned_errors

    elif isinstance(errors, BaseException):
        if errors.args:
            if not inspect.isroutine(errors.args[0]):
                return _clean_errors(errors.args[0])

    return str(errors)


@asynccontextmanager
async def capture_exception(
    consumer: AsyncConsumer,
    exc_class: typing.Optional[typing.Type[BaseException]] = None,
):
    """
    Captures any exceptions that occurs within the context.

    Sends an outgoing error event constructed from the exception back to
    the connected client.

    :param consumer: the async consumer in/for which this context manager is being used.
    :param exc_class: The base exception class to target
    """
    exc_class = exc_class or BaseException
    try:
        yield
    except exc_class as exc:
        log_exception(exc)
        message = exc.args[0] if exc.args else str(exc)
        if not isinstance(message, str):
            message = "An error occurred"

        errors = None
        for attr_name in ERROR_ATTRIBUTES:
            errors = getattr(exc, attr_name, None)
            if errors is not None:
                break

        outgoing_event = OutgoingEvent(
            type=EventType.ErrorOccurred,
            status=EventStatus.ERROR,
            message=message,
            errors=_clean_errors(errors),
        )
        await consumer.send(outgoing_event.as_json())
    finally:
        pass


_AsyncJSONConsumer = typing.TypeVar(
    "_AsyncJSONConsumer", bound=AsyncJsonWebsocketConsumer
)


class AsyncJsonWebsocketEventConsumerMeta(type):
    """Async JSON websocket event consumer meta class"""

    @staticmethod
    def add_event_send_handler(
        consumer_cls: typing.Type[_AsyncJSONConsumer], event: str
    ):
        async def send_handler(self: _AsyncJSONConsumer, event):
            await self.send_json(event)

        send_handler.__name__ = event
        setattr(consumer_cls, event, send_handler)
        return consumer_cls

    def __new__(cls, name, bases, attrs, **kwargs):
        consumer_cls: AsyncJsonWebsocketConsumer = super().__new__(
            cls, name, bases, attrs, **kwargs
        )
        # Auto add sending handler for event defined by `consumer_cls.event_type_enum`
        for event_type in consumer_cls.get_event_type_enum():
            send_handler = getattr(consumer_cls, event_type.value, None)
            if send_handler and inspect.isroutine(send_handler):
                continue
            cls.add_event_send_handler(consumer_cls, event_type.value)

        return consumer_cls


class AsyncJsonWebsocketEventConsumer(
    AsyncJsonWebsocketConsumer, metaclass=AsyncJsonWebsocketEventConsumerMeta
):
    """
    Custom Async JSON websocket consumer with boiler-plate mechanisms
    for handling events.

    Check `websockets/channels/events.py` for more details
    on events
    """

    event_type_enum: typing.Type[BaseEventType] = EventType
    """Enumeration of expected/acceptable event types accepted or sent by the consumer"""
    ignore_unsupported_events: bool = False
    """
    Whether to ignore unsupported events type. 
    `UnsupportedEvent` is raised for unsupported event types if set to True.
    
    Defaults to False.
    """
    base_exception_captured: typing.Type[BaseException] = Exception
    """The base exception class to be captured when auto-handling exceptions"""

    async def on_connect(self):
        """Called after a connection is established/accepted."""
        pass

    async def on_disconnect(self, close_code):
        """Called after a connection is closed."""
        pass

    async def on_receive(self, content, **kwargs):
        """
        Called immediately after an event is received before it is handled/processed.

        Perform any necessary pre-processing on the event in this method
        """
        return content

    async def connect(self):
        await super().connect()
        await self.on_connect()

    async def disconnect(self, close_code):
        await self.on_disconnect(close_code)

    @classmethod
    @functools.cache
    def get_event_type_enum(cls) -> typing.Type[Enum]:
        # Merge the specific event type class and the default one
        # so default events can also be accepted
        return merge_enums(
            cls.event_type_enum.__name__, *set((cls.event_type_enum, EventType))
        )

    async def receive_json(self, content, **kwargs):
        content = await self.on_receive(content, **kwargs)

        async with capture_exception(
            consumer=self, exc_class=self.base_exception_captured
        ):
            incoming_event = IncomingEvent.load(
                content, self.get_event_type_enum()
            )
            return await self.handle_incoming_event(incoming_event)

    async def handle_incoming_event(self, incoming_event: IncomingEvent):
        """Calls the appropriate handler for the incoming event type."""
        handler = getattr(self, f"handle_{incoming_event.type.value}", None)
        if handler:
            return await handler(incoming_event)

        if self.ignore_unsupported_events:
            return
        raise UnsupportedEvent(f"Unsupported event '{incoming_event.type.value}'.")

    ###################################
    # INCOMING EVENT HANDLERS GO HERE #
    ###################################

    async def handle_ping(self, incoming_event: IncomingEvent):
        outgoing_event = OutgoingEvent(
            type=EventType.Pong,
            message="Pong!",
            data=incoming_event.data,
        )
        await self.send_json(outgoing_event.as_dict())
