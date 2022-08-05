"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file implements base classes used to capture or emit events.
"""

import datetime
import time
from typing import Any, Optional, Type, Union

from snakecore.constants import UNSET

_EVENT_CLASS_MAP = {}


def get_event_class_from_runtime_id(
    class_runtime_id: str, default: Any = UNSET, /, closest_match: bool = False
) -> "BaseEvent":

    name, timestamp_str = class_runtime_id.split("-")

    if name in _EVENT_CLASS_MAP:
        if timestamp_str in _EVENT_CLASS_MAP[name]:
            return _EVENT_CLASS_MAP[name][timestamp_str]["class"]
        elif closest_match:
            for ts_str in _EVENT_CLASS_MAP[name]:
                return _EVENT_CLASS_MAP[name][ts_str]["class"]

    if default is UNSET:
        raise LookupError(
            "cannot find event class with an identifier of "
            f"'{class_runtime_id}' in the event class registry"
        )
    return default


def get_event_class_runtime_id(
    cls: Type["BaseEvent"],
    default: Any = UNSET,
    /,
) -> Union[str, Any]:
    """Get a event class by its runtime id string. This is the safe way
    of looking up event class runtime ids.

    Args:
        cls (Type[BaseEvent]): The event class whose identifier should be fetched.
        default (Any): A default value which will be returned if this function
          fails to produce the desired output. If omitted, exceptions will be
          raised.

    Raises:
        TypeError: 'cls' does not inherit from a event base class.
        LookupError: The given event class does not exist in the event class registry.
          This exception should not occur if event classes inherit their base classes
          correctly.

    Returns:
        str: The string identifier.
    """

    if not issubclass(cls, BaseEvent):
        if default is UNSET:
            raise TypeError("argument 'cls' must be a subclass of a event base class")
        return default

    try:
        class_runtime_id = cls._RUNTIME_ID
    except AttributeError:
        if default is UNSET:
            raise TypeError(
                "argument 'cls' must be a subclass of a event base class"
            ) from None
        return default

    try:
        name, timestamp_str = class_runtime_id.split("-")
    except (ValueError, AttributeError):
        if default is UNSET:
            raise ValueError(
                "invalid identifier found in the given event class"
            ) from None
        return default

    if name in _EVENT_CLASS_MAP:
        if timestamp_str in _EVENT_CLASS_MAP[name]:
            if _EVENT_CLASS_MAP[name][timestamp_str]["class"] is cls:
                return class_runtime_id
            else:
                if default is UNSET:
                    raise ValueError(
                        "The given event class has the incorrect identifier"
                    )
        else:
            if default is UNSET:
                ValueError(
                    "The given event class is registered under "
                    "a different identifier in the event class registry"
                )

    if default is UNSET:
        raise LookupError(
            "The given event class does not exist in the event class registry"
        )

    return default


def get_all_slot_names(cls):
    slots_list = []
    cls_slot_values = getattr(cls, "__slots__", None)
    if cls_slot_values:
        slots_list.extend(cls_slot_values)
    for base_cls in cls.__mro__[1:]:
        slots_list.extend(get_all_slot_names(base_cls))
    return slots_list


class BaseEvent:
    """The base class for all events."""

    _CREATED_AT = datetime.datetime.now(datetime.timezone.utc)
    _RUNTIME_ID = f"BaseEvent-{int(_CREATED_AT.timestamp()*1_000_000_000)}"

    __slots__ = (
        "_dispatcher",
        "_event_created_at_ts",
        "_real_event_created_at_ts",
        "_runtime_id",
    )

    __base_slots__ = __slots__
    # helper class attribute for faster copying by skipping initialization when
    # shallow-copying events

    def __init_subclass__(cls):

        cls._CREATED_AT = datetime.datetime.now(datetime.timezone.utc)

        name = cls.__name__
        timestamp = f"{int(cls._CREATED_AT.timestamp()*1_000_000_000)}"

        cls._RUNTIME_ID = f"{name}-{timestamp}"

        if name not in _EVENT_CLASS_MAP:
            _EVENT_CLASS_MAP[name] = {}

        _EVENT_CLASS_MAP[name][timestamp] = cls

        cls.__base_slots__ = tuple(get_all_slot_names(cls))

    def __init__(
        self, event_created_at: Optional[datetime.datetime] = None, dispatcher=None
    ):
        self._real_event_created_at_ts = time.time()
        if event_created_at is None:
            self._event_created_at_ts = self._real_event_created_at_ts
        else:
            self._event_created_at_ts = event_created_at.timestamp()

        self._runtime_id = (
            f"{self.__class__._RUNTIME_ID}:"
            f"{int(self._real_event_created_at_ts*1_000_000_000)}"
        )
        self._dispatcher = dispatcher

    @classmethod
    def get_class_runtime_id(cls) -> str:
        """Get the runtime id of this event class.

        Returns:
            str: The runtime id.
        """
        return cls._RUNTIME_ID

    @property
    def runtime_id(self) -> str:
        """The runtime id of this event object.

        Returns:
            str: The runtime id.
        """

        return self._runtime_id

    @property
    def real_event_created_at(self) -> datetime.datetime:
        """The time at which this event object was
        created at.

        Returns:
            datetime.datetime: The time.
        """
        return datetime.datetime.fromtimestamp(
            self._real_event_created_at_ts,
            tz=datetime.timezone.utc,
        )

    @property
    def event_created_at(self) -> datetime.datetime:
        """The time at which this event occured,
        which can be optionally set during instantiation.
        Defaults to the time of instantiation of the event object.

        Returns:
            datetime.datetime: The time.
        """
        return datetime.datetime.fromtimestamp(
            self._event_created_at_ts,
            tz=datetime.timezone.utc,
        )

    @property
    def dispatcher(self):
        """The object that dispatched this event, if available."""
        return self._dispatcher

    def copy(self) -> "BaseEvent":
        """Create a shallow copy of this event object.
        All shallow copies of this event retain the exact
        same attributes and properties.

        Returns:
            BaseEvent: The new copy.
        """
        new_obj = self.__class__.__new__(self.__class__)

        for attr in self.__base_slots__:
            setattr(new_obj, attr, getattr(self, attr))
        return new_obj

    __copy__ = copy

    def copy_unique(self) -> "BaseEvent":
        """Create a shallow copy of this event object,
        but treat that event as a newly dispatched object,
        by giving it a new runtime id and creation time.
        This event object will also become the dispatcher
        of the new unique copy.

        Returns:
            BaseEvent: The new unique copy.
        """
        unique_copy = self.copy()
        old_real_event_created_at_ts = unique_copy._real_event_created_at_ts
        unique_copy._real_event_created_at_ts = time.time()
        if old_real_event_created_at_ts is unique_copy._event_created_at_ts:
            # overwrite custom event creation time if none was initially provided
            unique_copy._event_created_at_ts = unique_copy._real_event_created_at_ts

        unique_copy._runtime_id = f"{self.__class__._RUNTIME_ID}:{int(self._real_event_created_at_ts*1_000_000_000)}"
        unique_copy._dispatcher = self

        return unique_copy

    def __repr__(self):
        attrs = " ".join(
            f"{attr}={val}"
            for attr, val in (
                (k, getattr(self, k)) for k in self.__slots__ if not k.startswith("_")
            )
        )
        return f"<{self.__class__.__name__}({attrs})>"


class CustomEvent(BaseEvent):
    """A base class for custom events."""

    __slots__ = ()
