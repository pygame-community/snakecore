"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file implements the base classes for job mixins,
which are feature sets for jobs that can be incorporated
in subclasses using multiple inheritance.
"""

import asyncio
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
import datetime
import time
from typing import Optional, Union

from snakecore.constants import (
    JobBoolFlags as JF,
    JobStopReasons,
)

from snakecore.utils.utils import DequeProxy
from . import jobs
from .jobs import JobMixin
from snakecore import events


class BaseEventJobMixin(JobMixin):
    """A mixin class that enables jobs to receive events from their job manager.

    Attributes:
        EVENTS: A tuple denoting the set of `BaseEvent` classes whose
          instances should be received after their corresponding event is
          registered by the job manager of an instance of this class. By
          default, all instances of `BaseEvent` will be propagated.
    """

    EVENTS: tuple[type[events.BaseEvent], ...] = (events.BaseEvent,)

    DEFAULT_MAX_EVENT_QUEUE_SIZE: Optional[int] = None

    DEFAULT_ALLOW_EVENT_QUEUE_OVERFLOW: bool = False

    DEFAULT_BLOCK_EVENTS_ON_STOP: bool = True
    DEFAULT_START_ON_EVENT_DISPATCH: bool = False
    DEFAULT_BLOCK_EVENTS_WHILE_STOPPED: bool = True
    DEFAULT_CLEAR_EVENTS_AT_STARTUP: bool = True
    """Whether to clear the event queue when a job starts.
    Defaults to False.
    """

    DEFAULT_ALLOW_DOUBLE_EVENT_DISPATCH: bool = False

    DEFAULT_STOP_ON_EMPTY_EVENT_QUEUE: bool = False
    """Whether to stop if a job loop iteration begins with an empty event queue.
    Defaults to False.
    """

    # __slots__ = (
    #     "_event_queue",
    #     "_max_event_queue_size",
    #     "_event_queue_futures",
    # )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        max_event_queue_size = self.DEFAULT_MAX_EVENT_QUEUE_SIZE

        if isinstance(max_event_queue_size, (int, float)):
            self._max_event_queue_size = int(max_event_queue_size)
            if self._max_event_queue_size <= 0:
                self._max_event_queue_size = None
        else:
            self._max_event_queue_size = None

        self._bools |= JF.ALLOW_EVENT_QUEUE_OVERFLOW * int(
            self.DEFAULT_ALLOW_EVENT_QUEUE_OVERFLOW
        )  # True/False

        self._bools |= JF.BLOCK_EVENTS_ON_STOP * int(
            self.DEFAULT_BLOCK_EVENTS_ON_STOP
        )  # True/False

        self._bools |= JF.START_ON_EVENT_DISPATCH * int(
            self.DEFAULT_START_ON_EVENT_DISPATCH
        )  # True/False
        self._bools |= JF.BLOCK_EVENTS_WHILE_STOPPED * int(
            self.DEFAULT_BLOCK_EVENTS_WHILE_STOPPED
        )  # True/False
        self._bools |= JF.CLEAR_EVENTS_AT_STARTUP * int(
            self.DEFAULT_CLEAR_EVENTS_AT_STARTUP
        )  # True/False

        self._bools |= JF.ALLOW_DOUBLE_EVENT_DISPATCH * int(
            self.DEFAULT_ALLOW_DOUBLE_EVENT_DISPATCH
        )  # True/False

        self._bools |= JF.STOP_ON_EMPTY_EVENT_QUEUE * int(
            self.DEFAULT_STOP_ON_EMPTY_EVENT_QUEUE
        )  # True/False

        if self._bools & (
            JF.BLOCK_EVENTS_WHILE_STOPPED | JF.CLEAR_EVENTS_AT_STARTUP
        ):  # any
            self._bools &= ~JF.START_ON_EVENT_DISPATCH  # False

        self._bools |= JF.EVENT_DISPATCH_ENABLED  # True

        self._event_queue_futures: list[asyncio.Future[bool]] = []
        # used for idlling while no events are available
        self._event_queue = deque(maxlen=self._max_event_queue_size)

        self._bools &= ~JF.STOPPING_BY_EMPTY_EVENT_QUEUE  # False

    async def _on_start(self):
        if self._bools & JF.CLEAR_EVENTS_AT_STARTUP:
            self._event_queue.clear()

        await super()._on_start()

    @property
    def event_queue(self) -> DequeProxy:
        """A read-only proxy to this job's event queue.
        Returns:
            DequeProxy: The event queue proxy.
        """
        return DequeProxy(self._event_queue)

    def _add_event(self, event: events.BaseEvent):
        is_running = self.is_running() and not self._bools & JF.STOPPED
        if (
            not self._bools & JF.EVENT_DISPATCH_ENABLED
            or (
                self._bools & (TRUE := JF.BLOCK_EVENTS_ON_STOP | JF.IS_STOPPING) == TRUE
            )  # all
            or (self._bools & JF.BLOCK_EVENTS_WHILE_STOPPED and not is_running)
        ):
            return

        elif (
            len(self._event_queue) == self._max_event_queue_size
            and not self._bools & JF.ALLOW_EVENT_QUEUE_OVERFLOW
        ):
            return

        self._event_queue.append(event)

        if not is_running and self._bools & JF.START_ON_EVENT_DISPATCH:
            self._START()

        elif self._event_queue_futures:
            for fut in self._event_queue_futures:
                if not fut.done():
                    fut.set_result(True)
            self._event_queue_futures.clear()

    def event_check(self, event: events.BaseEvent) -> bool:
        """A method for subclasses that can be overloaded to perform validations on a `BaseEvent`
        instance that was dispatched to them. Must return a boolean value indicating the
        validaiton result. If not overloaded, this method will always return `True`.
        Args:
            event (events.BaseEvent): The event object to run checks upon.
        """
        return True

    async def next_event(self) -> events.BaseEvent:
        if not self._event_queue:
            fut = self._manager._loop.create_future()
            self._event_queue_futures.append(fut)
            await fut  # wait till an event is dispatched

        return self._event_queue.popleft()

    async def wait_for_event_dispatch(self) -> bool:
        if not self._event_queue:
            fut = self._manager._loop.create_future()
            self._event_queue_futures.append(fut)
            return await fut  # wait till an event is dispatched

        return True

    async def mixin_routine(self):
        if not self._event_queue and self._bools & JF.STOP_ON_EMPTY_EVENT_QUEUE:
            self._bools |= JF.STOPPING_BY_EMPTY_EVENT_QUEUE  # True
            self.STOP()
            return

    @contextmanager
    def blocked_event_queue(self):
        """A method to be used as a context manager for
        temporarily blocking the event queue of this event job
        while running an operation, thereby disabling event dispatch to it.
        """
        try:
            self._bools &= ~JF.EVENT_DISPATCH_ENABLED  # False
            yield
        finally:
            self._bools |= JF.EVENT_DISPATCH_ENABLED  # True

    def event_queue_is_blocked(self) -> bool:
        """Whether event dispatching to this event job's event queue
        is disabled and its event queue is blocked.
        Returns:
            bool: True/False
        """
        return not self._bools & JF.EVENT_DISPATCH_ENABLED

    def block_queue(self):
        """Block the event queue of this event job, thereby disabling
        event dispatch to it.
        """
        self._bools &= ~JF.EVENT_DISPATCH_ENABLED  # False

    def unblock_queue(self):
        """Unblock the event queue of this event job, thereby enabling
        event dispatch to it.
        """
        self._bools |= JF.EVENT_DISPATCH_ENABLED  # True

    def _stop_cleanup(
        self,
        reason: Optional[
            Union[JobStopReasons.Internal, JobStopReasons.External]
        ] = None,
    ):
        for fut in self._event_queue_futures:
            if not fut.done():
                fut.cancel("Job has stopped running.")

        self._event_queue_futures.clear()

        super()._stop_cleanup(reason=reason)


class EventJobMixin(BaseEventJobMixin):
    """A subclass of `BaseEventJobMixin` that implements a `on_event(event)`
    listener as the primary way to receive dispatched events as they come,
    with multiple options to customize its behavior. `next_event()` is used
    to implement this behavior and should not be used on its own anymore.
    """

    DEFAULT_OE_MAX_EVENT_HANDLINGS: Optional[int] = None
    """Max. amount of events to handle with `on_event()`
    in one job loop iteration. Note that if the maximum
    is not reached and no more events are available, `on_event()`
    still won't be called anymore (for that iteration). If set to
    `None`, the total amount handled will depend on other default variables
    as well as the amount of events initially present in the event queue.
    Defaults to None.
    """

    DEFAULT_OE_HANDLE_ONLY_INITIAL_EVENTS: bool = False
    """Whether to only handle the events present in the event
    queue at the start of a job loop iteration with `on_event()`.
    Defaults to False.
    """

    DEFAULT_AWAIT_EVENT_DISPATCH: bool = True
    """Whether to await the arrival of events before handling them with
    `on_event()`, if the event queue is empty. Awaiting like this will
    mark a job as idling. If there are one or more events in 
    the queue, awaiting will be skipped and those will be successively
    handled with `on_event()`. If set to `True`, awaiting will only occur if
    `DEFAULT_OE_DISPATCH_ONLY_INITIAL_EVENTS` is set to `False`. To prevent
    indefinite awaiting, `DEFAULT_OE_DISPATCH_TIMEOUT` can be used to limit
    the waiting time. Defaults to True.
    """

    DEFAULT_EVENT_DISPATCH_TIMEOUT: Union[float, datetime.timedelta, None] = None
    """The timeout period for awaiting another event, before ending the loop iteration.
    Defaults to None.
    """

    DEFAULT_STOP_ON_EVENT_DISPATCH_TIMEOUT: bool = False
    """Whether to stop a job if the timeout period for awaiting another event was reached.
    Defaults to False.
    """

    # __slots__ = (
    #     "_event_queue",
    #     "_max_event_queue_size",
    #     "_event_queue_futures",
    #     "_oe_max_event_handlings",
    #     "_event_dispatch_timeout_secs",
    # )

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
        **kwargs,
    ):
        super().__init__(**kwargs)

        oe_max_event_handlings = self.DEFAULT_OE_MAX_EVENT_HANDLINGS

        if isinstance(oe_max_event_handlings, (int, float)):
            self._oe_max_event_handlings = int(oe_max_event_handlings)
            if self._oe_max_event_handlings < 0:
                self._oe_max_event_handlings = None
        else:
            self._oe_max_event_handlings = None

        self._bools |= JF.OE_HANDLE_ONLY_INITIAL_EVENTS * int(
            not not (self.DEFAULT_OE_HANDLE_ONLY_INITIAL_EVENTS)
        )  # True/False

        self._bools |= JF.AWAIT_EVENT_DISPATCH * int(
            self.DEFAULT_AWAIT_EVENT_DISPATCH
        )  # True/False

        event_dispatch_timeout = self.DEFAULT_EVENT_DISPATCH_TIMEOUT

        if isinstance(event_dispatch_timeout, datetime.timedelta):
            self._event_dispatch_timeout_secs = event_dispatch_timeout.total_seconds()
        elif isinstance(event_dispatch_timeout, (float, int)):
            self._event_dispatch_timeout_secs = float(event_dispatch_timeout)
        else:
            self._event_dispatch_timeout_secs = None

        self._bools |= JF.STOP_ON_EVENT_DISPATCH_TIMEOUT * int(
            not not (self.DEFAULT_STOP_ON_EVENT_DISPATCH_TIMEOUT)
        )  # True/False

        self._event_queue_futures: list[asyncio.Future[bool]] = []
        # used for idlling while no events are available
        self._event_queue = deque(maxlen=self._max_event_queue_size)

        self._bools &= ~(
            JF.STOPPING_BY_EMPTY_EVENT_QUEUE | JF.STOPPING_BY_EVENT_DISPATCH_TIMEOUT
        )  # False

    async def on_event(self, event: events.BaseEvent):
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        The code to run in reaction to an event popped from the event queue.
        """
        pass

    async def on_event_error(self, exc: Exception, event: events.BaseEvent):
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        The code to use to react to failed attempts to handle events.
        """
        pass

    async def _await_next_event_with_timeout(self):
        event = None
        if self._event_queue:
            event = self._event_queue.popleft()
        else:
            try:
                self._bools |= JF.IS_IDLING  # True
                self._idling_since_ts = time.time()
                event = await asyncio.wait_for(
                    self.next_event(), timeout=self._event_dispatch_timeout_secs
                )
                self._bools &= ~JF.IS_IDLING  # False
                self._idling_since_ts = None
            except asyncio.TimeoutError:
                if self._bools & JF.STOP_ON_EVENT_DISPATCH_TIMEOUT:
                    self._bools |= JF.STOPPING_BY_EVENT_DISPATCH_TIMEOUT  # True
                    self.STOP()

        return event

    async def mixin_routine(self):
        if not self._event_queue and self._bools & JF.STOP_ON_EMPTY_EVENT_QUEUE:
            self._bools |= JF.STOPPING_BY_EMPTY_EVENT_QUEUE  # True
            self.STOP()
            return

        max_event_handlings = self._oe_max_event_handlings

        if max_event_handlings is None:
            if self._bools & JF.OE_HANDLE_ONLY_INITIAL_EVENTS:
                max_event_handlings = len(self._event_queue)

            elif self._bools & JF.AWAIT_EVENT_DISPATCH:
                while True:
                    if (event := await self._await_next_event_with_timeout()) is None:
                        return
                    try:
                        await self.on_event(event)
                    except Exception as e:
                        try:
                            await self.on_event_error(e, event)
                        except Exception as e:
                            pass
            else:
                while self._event_queue:
                    event = self._event_queue.popleft()
                    try:
                        await self.on_event(event)
                    except Exception as e:
                        try:
                            await self.on_event_error(e, event)
                        except Exception as e:
                            pass
                return

        max_event_handlings = min(len(self._event_queue), max_event_handlings)

        if self._bools & JF.AWAIT_EVENT_DISPATCH:
            for _ in range(max_event_handlings):
                if (event := await self._await_next_event_with_timeout()) is None:
                    return

                try:
                    await self.on_event(event)
                except Exception as e:
                    try:
                        await self.on_event_error(e, event)
                    except Exception as e:
                        pass
        else:
            for _ in range(max_event_handlings):
                event = self._event_queue.popleft()
                try:
                    await self.on_event(event)
                except Exception as e:
                    try:
                        await self.on_event_error(e, event)
                    except Exception as e:
                        pass

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
            JF.STOPPING_BY_EVENT_DISPATCH_TIMEOUT | JF.STOPPING_BY_EMPTY_EVENT_QUEUE
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
        elif self._bools & JF.STOPPING_BY_EMPTY_EVENT_QUEUE:
            return JobStopReasons.Internal.EMPTY_EVENT_QUEUE

        elif self._bools & JF.STOPPING_BY_EVENT_DISPATCH_TIMEOUT:
            return JobStopReasons.Internal.EVENT_DISPATCH_TIMEOUT

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


class EventSession:
    """A class that represents an asynchronous event handling session
    of a `MultiEventJobMixin` class.

    Returns:
        _type_: _description_
    """

    __slots__ = (
        "_event",
        "_task",
        "_data",
        "_timestamp",
    )

    def __init__(
        self,
        event: events.BaseEvent,
        task: asyncio.Task,
        data: jobs.JobNamespace,
        timestamp: Optional[datetime.datetime] = None,
    ):
        self._event: events.BaseEvent = event
        self._task: asyncio.Task = task
        self._data: jobs.JobNamespace = data
        self._timestamp = timestamp or datetime.datetime.now(datetime.timezone.utc)

    @property
    def event(self) -> events.BaseEvent:
        return self._event

    @property
    def task(self) -> asyncio.Task:
        return self._task

    @property
    def data(self) -> jobs.JobNamespace:
        return self._data

    @property
    def timestamp(self) -> datetime.datetime:
        return self._timestamp


class MultiEventJobMixin(EventJobMixin):
    """A subclass of `EventJobMixin` which allows for handling dispatched events
    via `on_event()` concurrently.
    """

    DEFAULT_MAX_EVENT_SESSION_QUEUE_SIZE: Optional[int] = None
    """The maximum amount of finished event sessions that
    can be held in the event session queue. If this
    maximum is reached or surpassed, handling events with
    `on_event()` sessions will stop until the queue
    size falls below the maximum. 
    """

    DEFAULT_ALLOW_EVENT_SESSION_QUEUE_OVERFLOW: bool = False

    DEFAULT_OE_MAX_CONCURRENCY: int = 2
    """Max. amount of `on_event()`
    sessions that are allowed to run concurrently.
    If this maximum is reached, the creation of new
    `on_event()` sessions will stop until space is
    available.
    Defaults to 2.
    """

    OENamespace = jobs.JobNamespace

    # __slots__ = (
    #     "_active_event_sessions",
    #     "_event_session_queue",
    #     "_max_event_queue_size",
    #     "_event_queue_futures",
    #     "_max_event_session_queue_size",
    #     "_oe_max_concurrency",
    #     "_oe_data",
    # )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        max_event_queue_size = self.DEFAULT_MAX_EVENT_QUEUE_SIZE

        if isinstance(max_event_queue_size, (int, float)):
            self._max_event_queue_size = int(max_event_queue_size)
            if self._max_event_queue_size <= 0:
                self._max_event_queue_size = None
        else:
            self._max_event_queue_size = None

        max_event_session_queue_size = self.DEFAULT_MAX_EVENT_SESSION_QUEUE_SIZE

        if isinstance(max_event_session_queue_size, (int, float)):
            self._max_event_session_queue_size = int(max_event_session_queue_size)
            if self._max_event_session_queue_size <= 0:
                self._max_event_session_queue_size = None
        else:
            self._max_event_session_queue_size = None

        self._active_event_sessions: dict[events.BaseEvent, EventSession] = {}
        self._oe_max_concurrency = max(int(self.DEFAULT_OE_MAX_CONCURRENCY), 1)

        self._event_session_queue: deque[EventSession] = deque(
            maxlen=self._max_event_session_queue_size
        )

        self._oe_concurrency_space_futures: list[asyncio.Future] = []
        # used for idlling while no events are available

        self._oe_data: ContextVar[jobs.JobNamespace] = ContextVar("oe_data")

    @property
    def oe_data(self) -> jobs.JobNamespace:
        if (ns := self._oe_data.get(None)) is not None:
            return ns

        raise AttributeError(
            "this attribute is only available during the execution of an `on_event()` "
            "session"
        )

    @property
    def event_session_queue(self) -> deque[EventSession]:
        return self._event_session_queue

    def event_session_queue_is_full(self) -> bool:
        return len(self._event_session_queue) == self._max_event_session_queue_size

    def _max_on_event_concurrency_reached(self) -> bool:
        return len(self._active_event_sessions) >= self._oe_max_concurrency

    async def _on_event(self, event: events.BaseEvent, oe_data: OENamespace):
        token = self._oe_data.set(oe_data)
        try:
            await self.on_event(event)
        except Exception as e:
            await self.on_event_error(e, event)
            raise
        finally:
            self._oe_data.reset(token)

    def _create_event_session(self, event: events.BaseEvent):

        oe_data = self.OENamespace()

        event_session = EventSession(
            event,
            (oe_task := asyncio.create_task(self._on_event(event, oe_data))),
            oe_data,
            datetime.datetime.now(datetime.timezone.utc),
        )

        self._active_event_sessions[event] = event_session

        def _finish_event_session(tsk: asyncio.Task):
            del self._active_event_sessions[event]
            self._event_session_queue.append(event_session)

            if (
                self._oe_concurrency_space_futures
                and len(self._active_event_sessions) < self._oe_max_concurrency
            ):
                for fut in self._oe_concurrency_space_futures:
                    if not fut.done():
                        fut.set_result(True)

                self._oe_concurrency_space_futures.clear()

        oe_task.add_done_callback(_finish_event_session)

        return True

    def _wait_for_on_event_concurrency_space(self):
        fut = self._manager._loop.create_future()
        self._oe_concurrency_space_futures.append(fut)
        return fut

    async def mixin_routine(self):
        if not self._event_queue and self._bools & JF.STOP_ON_EMPTY_EVENT_QUEUE:
            self._bools |= JF.STOPPING_BY_EMPTY_EVENT_QUEUE  # True
            self.STOP()
            return

        max_event_handlings = self._oe_max_event_handlings

        if max_event_handlings is None:
            if self._bools & JF.OE_HANDLE_ONLY_INITIAL_EVENTS:
                max_event_handlings = len(self._event_queue)

            elif self._bools & JF.AWAIT_EVENT_DISPATCH:
                while True:
                    if (event := await self._await_next_event_with_timeout()) is None:
                        return

                    if (
                        self.event_session_queue_is_full()
                        and not self._bools & JF.ALLOW_EVENT_QUEUE_OVERFLOW
                    ):
                        self._event_queue.appendleft(
                            event
                        )  # reinsert event for the next event session creation attempt
                        return

                    elif self._max_on_event_concurrency_reached():
                        await self._wait_for_on_event_concurrency_space()

                    self._create_event_session(event)

            else:
                while self._event_queue:
                    event = self._event_queue.popleft()
                    if (
                        self.event_session_queue_is_full()
                        and not self._bools & JF.ALLOW_EVENT_QUEUE_OVERFLOW
                    ):
                        self._event_queue.appendleft(event)
                        return

                    elif self._max_on_event_concurrency_reached():
                        await self._wait_for_on_event_concurrency_space()

                    self._create_event_session(event)

                return

        max_event_handlings = min(len(self._event_queue), max_event_handlings)

        if self._bools & JF.AWAIT_EVENT_DISPATCH:
            for _ in range(max_event_handlings):
                event = self._event_queue.popleft()
                if (event := await self._await_next_event_with_timeout()) is None:
                    return

                if (
                    self.event_session_queue_is_full()
                    and not self._bools & JF.ALLOW_EVENT_QUEUE_OVERFLOW
                ):
                    self._event_queue.appendleft(event)
                    return

                elif self._max_on_event_concurrency_reached():
                    await self._wait_for_on_event_concurrency_space()

                self._create_event_session(event)

        else:
            for _ in range(max_event_handlings):
                event = self._event_queue.popleft()

                if (
                    self.event_session_queue_is_full()
                    and not self._bools & JF.ALLOW_EVENT_QUEUE_OVERFLOW
                ):
                    self._event_queue.appendleft(event)
                    return

                elif self._max_on_event_concurrency_reached():
                    await self._wait_for_on_event_concurrency_space()

                self._create_event_session(event)

                if not self._event_queue:
                    break

    async def _on_stop(self):
        for event_sessions in self._active_event_sessions.values():
            if not event_sessions._task.done():
                event_sessions._task.cancel(f"Job {self!r} is stopping.")

        await super()._on_stop()
