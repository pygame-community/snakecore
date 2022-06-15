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
from snakecore.constants.enums import JobPermissionLevels, JobStopReasons
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
        "_clear_events_at_startup",
        "_oe_max_dispatches",
        "_oe_dispatch_only_initial",
        "_oe_await_dispatch",
        "_oe_dispatch_timeout_secs",
        "_oe_stop_after_dispatch_timeout",
        "_oe_stop_if_no_events",
        "_stopping_by_event_timeout",
        "_stopping_by_empty_queue",
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

        self._allow_event_queue_overflow = not not (
            self.DEFAULT_ALLOW_EVENT_QUEUE_OVERFLOW
            if allow_event_queue_overflow is UNSET
            else allow_event_queue_overflow
        )

        self._block_events_on_stop = not not (
            self.DEFAULT_BLOCK_EVENTS_ON_STOP
            if block_events_on_stop is UNSET
            else block_events_on_stop
        )

        self._block_events_while_stopped = not not (
            self.DEFAULT_BLOCK_EVENTS_WHILE_STOPPED
            if block_events_while_stopped is UNSET
            else block_events_while_stopped
        )

        self._start_on_dispatch = not not (
            self.DEFAULT_START_ON_DISPATCH
            if start_on_dispatch is UNSET
            else start_on_dispatch
        )

        self._clear_events_at_startup = not not (
            self.DEFAULT_CLEAR_EVENTS_AT_STARTUP
            if clear_events_at_startup is UNSET
            else clear_events_at_startup
        )

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

        self._oe_dispatch_only_initial = not not (
            self.DEFAULT_OE_DISPATCH_ONLY_INITIAL
            if oe_dispatch_only_initial is UNSET
            else oe_dispatch_only_initial
        )

        self._oe_await_dispatch = not not (
            self.DEFAULT_OE_AWAIT_DISPATCH
            if oe_await_dispatch is UNSET
            else oe_await_dispatch
        )

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

        self._oe_stop_after_dispatch_timeout = not not (
            self.DEFAULT_OE_STOP_AFTER_DISPATCH_TIMEOUT
            if oe_stop_after_dispatch_timeout is UNSET
            else oe_stop_after_dispatch_timeout
        )

        self._oe_stop_if_no_events = not not (
            self.DEFAULT_OE_STOP_IF_NO_EVENTS
            if oe_stop_if_no_events is UNSET
            else oe_stop_if_no_events
        )

        if self._block_events_while_stopped or self._clear_events_at_startup:
            self._start_on_dispatch = False

        self._allow_dispatch = True

        if (
            self._oe_max_dispatches is not None
            and self._oe_max_dispatches > 1
            or self._oe_dispatch_only_initial
        ):
            self._oe_await_dispatch = False

        self._event_queue = deque(maxlen=self._max_event_queue_size)

        self._stopping_by_empty_queue = False
        self._stopping_by_event_timeout = False

    @property
    def event_queue(self) -> DequeProxy:
        return DequeProxy(self._event_queue)

    async def _on_start(self):
        if self._clear_events_at_startup:
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
                self._is_idling = True
                self._idling_since_ts = time.time()
                event = await asyncio.wait_for(
                    self.next_event(), timeout=self._oe_dispatch_timeout_secs
                )
                self._is_idling = False
                self._idling_since_ts = None
            except asyncio.TimeoutError:
                if self._oe_stop_after_dispatch_timeout:
                    self._stopping_by_event_timeout = True
                    self.STOP()

        return event

    async def on_run(self):
        if not self._event_queue and self._oe_stop_if_no_events:
            self._stopping_by_empty_queue = True
            self.STOP()
            return

        max_dispatches = self._oe_max_dispatches

        if max_dispatches is None:
            if self._oe_dispatch_only_initial:
                max_dispatches = len(self._event_queue)

            elif self._oe_await_dispatch:
                while True:
                    if (event := await self._await_next_event_with_timeout()) is None:
                        return
                    await self.on_event(event)
            else:
                while self._event_queue:
                    await self.on_event(self._event_queue.pop())
                return

        max_dispatches = min(len(self._event_queue), max_dispatches)

        if self._oe_await_dispatch:
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

        self._stopping_by_event_timeout = False
        self._stopping_by_empty_queue = False

    def get_stopping_reason(
        self,
    ) -> Optional[Union[JobStopReasons.Internal, JobStopReasons.External]]:
        if not self._is_stopping:
            return
        elif (
            self._on_start_exception
            or self._on_run_exception
            or self._on_stop_exception
        ):
            return JobStopReasons.Internal.ERROR
        elif self._stopping_by_empty_queue:
            return JobStopReasons.Internal.EMPTY_EVENT_QUEUE

        elif self._stopping_by_event_timeout:
            return JobStopReasons.Internal.EVENT_TIMEOUT

        elif self._job_loop.current_loop == self._count:
            return JobStopReasons.Internal.EXECUTION_COUNT_LIMIT
        elif self._stop_by_self:
            if self._told_to_restart:
                return JobStopReasons.Internal.RESTART
            elif self._told_to_complete:
                return JobStopReasons.Internal.COMPLETION
            elif self._told_to_be_killed:
                return JobStopReasons.Internal.KILLING
            else:
                return JobStopReasons.Internal.UNSPECIFIC
        else:
            if self._told_to_restart:
                return JobStopReasons.External.RESTART
            elif self._told_to_be_killed:
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
        on_init: Optional[Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]] = None,
        on_start: Optional[Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]] = None,
        on_start_error: Optional[Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]] = None,
        on_run: Optional[Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]] = None,
        on_run_error: Optional[Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]] = None,
        on_stop: Optional[Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]] = None,
        on_stop_error: Optional[Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]] = None,
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
    job objects will only run once and then complete themselves.
    If they fail
    automatically. For more control, use `ManagedJobBase` directly.
    """

    DEFAULT_COUNT = 1

    async def on_stop(self):
        self.COMPLETE()


class RegisterDelayedJob(jobs.ManagedJobBase):
    """A group of jobs that add a given set of job proxies
    to their `JobManager` after a given period
    of time in seconds.

    Output Fields:
        'success_failure_tuple': A tuple containing two tuples,
        with the successfully registered job proxies in the
        first one and the failed proxies in the second.
    """

    class OutputFields(groupings.OutputNameRecord):
        success_failure_tuple: str
        """A tuple containing two tuples,
        with the successfully registered job proxies in the
        first one and the failed proxies in the second.
        """

    class OutputQueues(groupings.OutputNameRecord):
        successes: str
        failures: str

    class PublicMethods(groupings.NameRecord):
        get_successes_async: Optional[Callable[[], Coroutine]]
        """get successfuly scheduled jobs"""

    DEFAULT_COUNT = 1

    def __init__(self, delay: float, *job_proxies: proxies.JobProxy, **kwargs):
        """Create a new instance.

        Args:
            delay (float): The delay for the input jobs in seconds.
            *job_proxies Union[ClientEventJob, ManagedJobBase]: The jobs to be delayed.
        """
        super().__init__(**kwargs)
        self.data.delay = delay
        self.data.jobs = deque(job_proxies)
        self.data.success_jobs = []
        self.data.success_futures = []
        self.data.failure_jobs = []

    async def on_run(self):
        await asyncio.sleep(self.data.delay)
        while self.data.jobs:
            job_proxy = self.data.jobs.popleft()
            try:
                await self.manager.register_job(job_proxy)
            except (
                ValueError,
                TypeError,
                LookupError,
                JobException,
                AssertionError,
                discord.DiscordException,
            ):
                self.data.failure_jobs.append(job_proxy)
                self.push_output_queue("failures", job_proxy)
            else:
                self.data.success_jobs.append(job_proxy)
                self.push_output_queue("successes", job_proxy)

        success_jobs_tuple = tuple(self.data.success_jobs)

        self.set_output_field(
            "success_failure_tuple",
            (success_jobs_tuple, tuple(self.data.failure_jobs)),
        )

        for fut in self.data.success_futures:
            if not fut.cancelled():
                fut.set_result(success_jobs_tuple)

    @jobs.publicjobmethod(is_async=True)
    def get_successes_async(self):
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self.data.success_futures.append(fut)
        return asyncio.wait_for(fut, None)

    async def on_stop(self):
        self.COMPLETE()

class MethodCallJob(
    jobs.ManagedJobBase,
    class_uuid="7d2fee26-d8b9-4e93-b761-4d152d355bae",
):
    """A job class for calling the method of a specified name on an object given as
    argument.

    Recommended Permission Level:
        JobPermissionLevels.LOWEST

    Output Fields:
        'output': The returned output of the method call.
    """

    class OutputFields(groupings.OutputNameRecord):
        output: str
        "The returned output of the method call."

    DEFAULT_COUNT = 1
    DEFAULT_RECONNECT = False

    def __init__(
        self,
        instance: object,
        method_name: str,
        is_async: bool = False,
        instance_args: tuple[Any, ...] = (),
        instance_kwargs: Optional[dict] = None,
    ):

        super().__init__()

        self.data.instance = instance
        self.data.method_name = method_name + ""
        self.data.is_async = is_async

        if not isinstance(instance, serializers.BaseSerializer):
            getattr(instance, method_name)

        self.data.instance_args = list(instance_args)
        self.data.instance_kwargs = instance_kwargs or {}

    async def on_init(self):
        if isinstance(self.data.instance, serializers.BaseSerializer):
            self.data.instance = await self.data.instance.deserialized_async()
            getattr(self.data.instance, self.data.method_name)

        for i in range(len(self.data.instance_args)):
            arg = self.data.instance_args[i]
            if isinstance(arg, serializers.BaseSerializer):
                self.data.instance_args[i] = await arg.deserialized_async()

        for key in self.data.instance_kwargs:
            kwarg = self.data.instance_kwargs[key]
            if isinstance(kwarg, serializers.BaseSerializer):
                self.data.instance_kwargs[key] = await kwarg.deserialized_async()

    async def on_run(self):
        output = getattr(self.data.instance, self.data.method_name)(
            *self.data.instance_args, **self.data.instance_kwargs
        )
        if self.data.is_async:
            output = await output

        self.set_output_field("output", output)

    async def on_stop(self):
        if self.run_failed():
            self.KILL()
        else:
            self.COMPLETE()
