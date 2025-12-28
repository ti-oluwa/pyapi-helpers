import enum
import typing
import json
from dataclasses import dataclass, KW_ONLY
from django.utils.translation import gettext as _

from src.generics.utils.choice import ExtendedEnum
from src.dependencies.channels.exceptions import InvalidData


class BaseEventType(ExtendedEnum):
    """Enumeration of various types of an event."""

    pass


class EventType(BaseEventType):
    """Default event types"""

    Ping = _("ping")
    Pong = _("pong")
    ErrorOccurred = _("error_occurred")


@dataclass(slots=True)
class Event:
    """Base class for events."""

    type: typing.Union[enum.Enum, BaseEventType]
    """The type of the event."""
    message: str = "An event occurred."
    """A message describing the event."""
    data: typing.Optional[typing.Any] = None
    """Additional data associated with the event."""

    def as_dict(self) -> typing.Dict[str, typing.Any]:
        """Return the event as a dictionary."""
        return {
            "type": self.type.value,
            "message": self.message,
            "data": self.data,
        }

    def as_json(self) -> str:
        """Return the event as a JSON encoded string."""
        return json.dumps(self.as_dict())

    @classmethod
    def load(
        cls,
        __data: typing.Union[str, typing.Mapping[str, typing.Any]],
        /,
        event_type_enum: typing.Union[
            typing.Type[enum.Enum], typing.Type[BaseEventType]
        ],
    ):
        """
        Load an event from a JSON string or a dictionary.

        :param __data: Event data as a JSON string or mapping.
        :param event_type_enum: The enumeration of possible/allowed event types.
        :return: The loaded event.
        """
        if isinstance(__data, str):
            return cls.from_json(__data, event_type_enum)
        return cls.from_dict(dict(__data), event_type_enum)

    @classmethod
    def from_json(
        cls,
        __json: str,
        /,
        event_type_enum: typing.Union[
            typing.Type[enum.Enum], typing.Type[BaseEventType]
        ],
    ):
        """
        Load an event from a JSON string.

        :param __json: The JSON encoded event data.
        :param event_type_enum: The enumeration of possible/allowed event types.
        :return: The loaded event.
        """
        data: typing.Dict = json.loads(__json)
        return cls.from_dict(data, event_type_enum)

    @classmethod
    def from_dict(
        cls,
        __dict: typing.MutableMapping[str, typing.Any],
        /,
        event_type_enum: typing.Union[
            typing.Type[enum.Enum], typing.Type[BaseEventType]
        ],
    ):
        """
        Load an event from a dictionary.

        :param __dict: Event data as a dictionary/mapping.
        :param event_type_enum: The enumeration of possible/allowed event types.
        :return: The loaded event.
        """
        type_str = __dict.pop("type", None)
        if not type_str:
            raise InvalidData(
                {
                    "type": [_("Missing 'type' key in event data.")],
                }
            )

        event_type = event_type_enum(type_str)
        return cls(type=event_type, **__dict)

    def ensure_data(self, *keys: str) -> bool:
        """
        Validate that the data contains the specified keys.

        :param keys: The keys that should be present in the event data.
        :return: True if the data contains all the required keys.
        :raises InvalidData: If any of the required keys are missing.
        """
        data = self.data or {}
        errors = []
        for key in keys:
            if key == "":
                continue

            if key not in data:
                errors.append(_(f"Missing key '{key}' in event data."))

        if errors:
            raise InvalidData(
                {
                    "data": errors,
                }
            )
        return True


@dataclass(slots=True)
class IncomingEvent(Event):
    """Event sent from a client, received by a websocket consumer."""

    pass


class EventStatus(ExtendedEnum):
    OK = "ok"
    ERROR = "error"


@dataclass(slots=True)
class OutgoingEvent(Event):
    """Event from websocket consumer, to be sent to clients."""

    _: KW_ONLY
    status: EventStatus = EventStatus.OK
    """The status the event conveys. Whether it is error or success event."""
    errors: typing.Optional[
        typing.Union[typing.Dict[str, typing.Any], typing.List[str], str]
    ] = None
    """Errors associated with the event in case of an error status."""

    def as_dict(self) -> typing.Dict[str, typing.Any]:
        return {
            "status": self.status.value,
            **super(OutgoingEvent, self).as_dict(),
            "errors": self.errors,
        }
