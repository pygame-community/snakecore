"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This module implements utility job classes. 
"""
import asyncio
from collections import deque
import datetime
import inspect
import time
from typing import Any, Callable, Coroutine, Optional, Sequence, Union

import discord

from snakecore import events, jobs
from snakecore.constants import UNSET, _UnsetType, NoneType
from snakecore.constants.enums import (
    JobBoolFlags as JF,
    JobPermissionLevels,
    JobStopReasons,
)
from snakecore.exceptions import JobException
from snakecore.jobs import groupings, proxies
from snakecore.jobs.jobs import ManagedJobBase
from snakecore.utils import serializers
from snakecore.utils import DequeProxy

from . import messaging


class EventJobBase(jobs.ManagedJobBase, jobs.EventJobMixin):
    """An `ManagedJobBase` subclass that automatically inherits `EventJobMixin` and
    implements more helpful event-related behavior. It overloads `on_run()` to
    implement the `on_event(event)` method as a way to conveniently receive dispatched
    events as they come, with multiple options to customize its behavior, therefore
    making this behavior optional. By overloading `on_run()` manually while still calling
    `super().on_run()` within it, both methods can be used together.
    """

    DEFAULT_CLEAR_EVENTS_AT_STARTUP: bool = False
    """Whether to clear the event queue when a job starts.
    Defaults to False.
    """

    DEFAULT_OE_MAX_DISPATCHES: Optional[int] = None
    """Max. amount of events to pass to `on_event()`
    in one job loop iteration. Note that if the maximum
    is not reached and no more events are available, `on_event()`
    won't be called anymore (for that iteration). If set to
    `None`, the total amount passed will depend on other default variables
    as well as the amount of events initially present in the event queue.
    Defaults to None.
    """

    DEFAULT_OE_DISPATCH_ONLY_INITIAL: bool = False
    """Whether to only dispatch the events present in the event
    queue at the start of a job loop iteration to `on_event()`.
    Defaults to False.
    """

    DEFAULT_OE_AWAIT_DISPATCH: bool = True
    """Whether to await the arrival of an event before passing it to
    `on_event()`, if the event queue is empty. Awaiting like this will
    mark a job as idling. If there are one or more events in 
    the queue, awaiting will be skipped and those will be successively
    passed to `on_event()`. If set to `True`, awaiting will only occur if
    `DEFAULT_ONLY_INITIAL_EVENTS` is set to `False`. To prevent indefinite
    awaiting, `DEFAULT_MAX_OE_DISPATCHES` can be used to limit the total
    amounts to dispatch.
    Defaults to True.
    """

    DEFAULT_OE_DISPATCH_TIMEOUT: Union[float, datetime.timedelta, None] = None
    """The timeout period for awaiting another event, before ending the loop iteration.
    Defaults to None.
    """

    DEFAULT_OE_STOP_AFTER_DISPATCH_TIMEOUT: bool = False
    """Whether to stop if the timeout period for awaiting another event was reached.
    Defaults to False.
    """

    DEFAULT_OE_STOP_IF_NO_EVENTS: bool = False
    """Whether to stop if a loop iteration begins with an empty event queue.
    Defaults to False.
    """

    __slots__ = (
        "_oe_max_dispatches",
        "_oe_dispatch_timeout_secs",
    )

    def __init_subclass__(
        cls,
        class_uuid: Optional[str] = None,
    ):
        if not cls.EVENTS:
            raise TypeError("the 'EVENTS' class attribute must not be empty")

        elif not isinstance(cls.EVENTS, (list, tuple)):
            raise TypeError(
                "the 'EVENTS' class attribute must be of type 'tuple' and "
                "must contain one or more subclasses of `BaseEvent`"
            )
        elif not all(issubclass(et, events.BaseEvent) for et in cls.EVENTS):
            raise ValueError(
                "the 'EVENTS' class attribute "
                "must contain one or more subclasses of `BaseEvent`"
            )

        super().__init_subclass__(
            class_uuid=class_uuid,
        )

    def __init__(
        self,
        interval: Union[datetime.timedelta, _UnsetType] = UNSET,
        time: Union[datetime.time, Sequence[datetime.time], _UnsetType] = UNSET,
        count: Union[int, NoneType, _UnsetType] = UNSET,
        reconnect: Union[bool, _UnsetType] = UNSET,
        max_event_queue_size: Union[int, NoneType, _UnsetType] = UNSET,
        allow_event_queue_overflow: Union[bool, _UnsetType] = UNSET,
        block_events_on_stop: Union[bool, _UnsetType] = UNSET,
        block_events_while_stopped: Union[bool, _UnsetType] = UNSET,
        start_on_dispatch: Union[bool, _UnsetType] = UNSET,
        clear_events_at_startup: Union[bool, _UnsetType] = UNSET,
        oe_max_dispatches: Union[int, NoneType, _UnsetType] = UNSET,
        oe_dispatch_only_initial: Union[bool, _UnsetType] = UNSET,
        oe_await_dispatch: Union[bool, _UnsetType] = UNSET,
        oe_dispatch_timeout: Union[
            float, int, datetime.timedelta, NoneType, _UnsetType
        ] = UNSET,
        oe_stop_after_dispatch_timeout: Union[bool, _UnsetType] = UNSET,
        oe_stop_if_no_events: Union[bool, _UnsetType] = UNSET,
    ):
        ManagedJobBase.__init__(self, interval, time, count, reconnect)

        max_event_queue_size = (
            self.DEFAULT_MAX_EVENT_QUEUE_SIZE
            if max_event_queue_size is UNSET
            else max_event_queue_size
        )

        if isinstance(max_event_queue_size, (int, float)):
            self._max_event_queue_size = int(max_event_queue_size)
            if self._max_event_queue_size <= 0:
                self._max_event_queue_size = None
        else:
            self._max_event_queue_size = None

        self._bools |= JF.ALLOW_EVENT_QUEUE_OVERFLOW * int(
            not not (
                self.DEFAULT_ALLOW_EVENT_QUEUE_OVERFLOW
                if allow_event_queue_overflow is UNSET
                else allow_event_queue_overflow
            )
        )  # True/False

        self._bools |= JF.BLOCK_EVENTS_ON_STOP * int(
            not not (
                self.DEFAULT_BLOCK_EVENTS_ON_STOP
                if block_events_on_stop is UNSET
                else block_events_on_stop
            )
        )  # True/False

        self._bools |= JF.BLOCK_EVENTS_WHILE_STOPPED * int(
            not not (
                self.DEFAULT_BLOCK_EVENTS_WHILE_STOPPED
                if block_events_while_stopped is UNSET
                else block_events_while_stopped
            )
        )  # True/False

        self._bools |= JF.START_ON_DISPATCH * int(
            not not (
                self.DEFAULT_START_ON_DISPATCH
                if start_on_dispatch is UNSET
                else start_on_dispatch
            )
        )  # True/False

        self._bools |= JF.CLEAR_EVENTS_AT_STARTUP * int(
            not not (
                self.DEFAULT_CLEAR_EVENTS_AT_STARTUP
                if clear_events_at_startup is UNSET
                else clear_events_at_startup
            )
        )  # True/False

        oe_max_dispatches = (
            self.DEFAULT_OE_MAX_DISPATCHES
            if oe_max_dispatches is UNSET
            else oe_max_dispatches
        )

        if isinstance(oe_max_dispatches, (int, float)):
            self._oe_max_dispatches = int(oe_max_dispatches)
            if self._oe_max_dispatches < 0:
                self._oe_max_dispatches = None
        else:
            self._oe_max_dispatches = None

        self._bools |= JF.OE_DISPATCH_ONLY_INITIAL * int(
            not not (
                self.DEFAULT_OE_DISPATCH_ONLY_INITIAL
                if oe_dispatch_only_initial is UNSET
                else oe_dispatch_only_initial
            )
        )  # True/False

        self._bools |= JF.OE_AWAIT_DISPATCH * int(
            not not (
                self.DEFAULT_OE_AWAIT_DISPATCH
                if oe_await_dispatch is UNSET
                else oe_await_dispatch
            )
        )  # True/False

        oe_dispatch_timeout = (
            self.DEFAULT_OE_DISPATCH_TIMEOUT
            if oe_dispatch_timeout is UNSET
            else oe_dispatch_timeout
        )

        if isinstance(oe_dispatch_timeout, datetime.timedelta):
            self._oe_dispatch_timeout_secs = oe_dispatch_timeout.total_seconds()
        elif isinstance(oe_dispatch_timeout, (float, int)):
            self._oe_dispatch_timeout_secs = float(oe_dispatch_timeout)
        else:
            self._oe_dispatch_timeout_secs = None

        self._bools |= JF.OE_STOP_AFTER_DISPATCH_TIMEOUT * int(
            not not (
                self.DEFAULT_OE_STOP_AFTER_DISPATCH_TIMEOUT
                if oe_stop_after_dispatch_timeout is UNSET
                else oe_stop_after_dispatch_timeout
            )
        )  # True/False

        self._bools |= JF.OE_STOP_IF_NO_EVENTS * int(
            not not (
                self.DEFAULT_OE_STOP_IF_NO_EVENTS
                if oe_stop_if_no_events is UNSET
                else oe_stop_if_no_events
            )
        )  # True/False

        if self._bools & (
            JF.BLOCK_EVENTS_WHILE_STOPPED | JF.CLEAR_EVENTS_AT_STARTUP
        ):  # any
            self._bools &= ~JF.START_ON_DISPATCH  # False

        self._bools |= JF.ALLOW_DISPATCH  # True

        if (
            self._oe_max_dispatches is not None
            and self._oe_max_dispatches > 1
            or self._bools & JF.OE_DISPATCH_ONLY_INITIAL
        ):
            self._bools &= ~JF.OE_AWAIT_DISPATCH  # False

        self._event_queue = deque(maxlen=self._max_event_queue_size)

        self._bools &= ~(
            JF.STOPPING_BY_EMPTY_QUEUE | JF.STOPPING_BY_EVENT_TIMEOUT
        )  # False

    @property
    def event_queue(self) -> DequeProxy:
        """A read-only proxy to this job's event queue.

        Returns:
            DequeProxy: The event queue proxy.
        """
        return DequeProxy(self._event_queue)

    async def _on_start(self):
        if self._bools & JF.CLEAR_EVENTS_AT_STARTUP:
            self._event_queue.clear()

        await super()._on_start()

    async def on_event(self, event: events.BaseEvent):
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        The code to run in reaction to an event popped from the event queue.
        """
        pass

    async def _await_next_event_with_timeout(self):
        event = None
        if self._event_queue:
            event = self._event_queue.pop()
        else:
            try:
                self._bools |= JF.IS_IDLING  # True
                self._idling_since_ts = time.time()
                event = await asyncio.wait_for(
                    self.next_event(), timeout=self._oe_dispatch_timeout_secs
                )
                self._bools &= ~JF.IS_IDLING  # False
                self._idling_since_ts = None
            except asyncio.TimeoutError:
                if self._bools & JF.OE_STOP_AFTER_DISPATCH_TIMEOUT:
                    self._bools |= JF.STOPPING_BY_EVENT_TIMEOUT  # True
                    self.STOP()

        return event

    async def on_run(self):
        if not self._event_queue and self._bools & JF.OE_STOP_IF_NO_EVENTS:
            self._bools |= JF.STOPPING_BY_EMPTY_QUEUE  # True
            self.STOP()
            return

        max_dispatches = self._oe_max_dispatches

        if max_dispatches is None:
            if self._bools & JF.OE_DISPATCH_ONLY_INITIAL:
                max_dispatches = len(self._event_queue)

            elif self._bools & JF.OE_AWAIT_DISPATCH:
                while True:
                    if (event := await self._await_next_event_with_timeout()) is None:
                        return
                    await self.on_event(event)
            else:
                while self._event_queue:
                    await self.on_event(self._event_queue.pop())
                return

        max_dispatches = min(len(self._event_queue), max_dispatches)

        if self._bools & JF.OE_AWAIT_DISPATCH:
            for _ in range(max_dispatches):
                if (event := await self._await_next_event_with_timeout()) is None:
                    return
                await self.on_event(event)
        else:
            for _ in range(max_dispatches):
                await self.on_event(self._event_queue.pop())
                if not self._event_queue:
                    break

    def _stop_cleanup(
        self,
        reason: Optional[
            Union[JobStopReasons.Internal, JobStopReasons.External]
        ] = None,
    ):
        super()._stop_cleanup(reason=reason)

        self._bools &= ~(
            JF.STOPPING_BY_EVENT_TIMEOUT | JF.STOPPING_BY_EMPTY_QUEUE
        )  # False

    def get_stopping_reason(
        self,
    ) -> Optional[Union[JobStopReasons.Internal, JobStopReasons.External]]:
        if not self._bools & JF.IS_STOPPING:
            return
        elif (
            self._on_start_exception
            or self._on_run_exception
            or self._on_stop_exception
        ):
            return JobStopReasons.Internal.ERROR
        elif self._bools & JF.STOPPING_BY_EMPTY_QUEUE:
            return JobStopReasons.Internal.EMPTY_EVENT_QUEUE

        elif self._bools & JF.STOPPING_BY_EVENT_TIMEOUT:
            return JobStopReasons.Internal.EVENT_TIMEOUT

        elif self._job_loop.current_loop == self._count:
            return JobStopReasons.Internal.EXECUTION_COUNT_LIMIT
        elif self._bools & JF.TOLD_TO_STOP_BY_SELF:
            if self._bools & JF.TOLD_TO_RESTART:
                return JobStopReasons.Internal.RESTART
            elif self._bools & JF.TOLD_TO_COMPLETE:
                return JobStopReasons.Internal.COMPLETION
            elif self._bools & JF.TOLD_TO_BE_KILLED:
                return JobStopReasons.Internal.KILLING
            else:
                return JobStopReasons.Internal.UNSPECIFIC
        else:
            if self._bools & JF.TOLD_TO_RESTART:
                return JobStopReasons.External.RESTART
            elif self._bools & JF.TOLD_TO_BE_KILLED:
                return JobStopReasons.External.KILLING
            else:
                return JobStopReasons.External.UNKNOWN


class GenericManagedJob(jobs.ManagedJobBase):

    __slots__ = (
        "_on_init_func",
        "_on_start_func",
        "_on_run_func",
        "_on_stop_func",
        "_on_start_error_func",
        "_on_run_error_func",
        "_on_stop_error_func",
    )

    def __init__(
        self,
        on_init: Optional[
            Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        ] = None,
        on_start: Optional[
            Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        ] = None,
        on_start_error: Optional[
            Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        ] = None,
        on_run: Optional[
            Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        ] = None,
        on_run_error: Optional[
            Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        ] = None,
        on_stop: Optional[
            Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        ] = None,
        on_stop_error: Optional[
            Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        ] = None,
        interval: Union[datetime.timedelta, _UnsetType] = UNSET,
        time: Union[datetime.time, Sequence[datetime.time], _UnsetType] = UNSET,
        count: Union[int, NoneType, _UnsetType] = UNSET,
        reconnect: Union[bool, _UnsetType] = UNSET,
    ):
        supercls = ManagedJobBase
        supercls.__init__(interval, time, count, reconnect)
        self._on_init_func = on_init or supercls.on_init
        self._on_start_func = on_start or supercls.on_start
        self._on_start_error_func = on_start_error or supercls.on_start_error
        self._on_run_func = on_run or supercls.on_run
        self._on_run_error_func = on_run_error or supercls.on_run_error
        self._on_stop_func = on_stop or supercls.on_stop
        self._on_stop_error_func = on_stop_error or supercls.on_stop_error

    async def on_init(self):
        return await self._on_init_func(self)

    async def on_start(self):
        return await self._on_start_func(self)

    async def on_start_error(self):
        return await self._on_start_error_func(self)

    async def on_run(self):
        return await self._on_run_func(self)

    async def on_run_error(self):
        return await self._on_run_error_func(self)

    async def on_stop(self):
        return await self._on_stop_func(self)

    async def on_stop_error(self):
        return await self._on_stop_error_func(self)


class SingleRunJob(jobs.ManagedJobBase):
    """A subclass of `ManagedJobBase` whose subclasses's
    job objects will only run once and then complete themselves
    if they fail automatically. For more control, use `ManagedJobBase` directly.
    """

    DEFAULT_COUNT = 1

    async def on_stop(self):
        self.COMPLETE()
