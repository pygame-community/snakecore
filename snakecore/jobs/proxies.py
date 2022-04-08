"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

This file implements proxy objects used by job and job managers
for extra features and encapsulation. 
"""

from collections import deque
import datetime
import itertools
from types import FunctionType
from typing import Any, Callable, Optional, Sequence, Type, Union

from snakecore import events
from snakecore.constants import UNSET, _UnsetType
from .jobs import (
    JobPermissionLevels,
    EventJobBase,
    IntervalJobBase,
    JobBase,
)

from . import manager


class JobProxy:
    """A proxy class that provides an interface for safe access to job objects at
    runtime.
    """

    __slots__ = (
        "__j",
        "__job_class",
        "__identifier",
        "__created_at",
        "__registered_at",
    )

    def __init__(self, job):
        self.__j = job
        self.__job_class = job.__class__
        self.__identifier = job._runtime_identifier
        self.__created_at = job.created_at

    @property
    def job_class(self) -> JobBase:
        return self.__job_class

    @property
    def runtime_identifier(self) -> str:
        return self.__identifier

    @property
    def creator(self) -> Optional[JobBase]:
        """The `JobProxy` of the creator of this job."""
        return self.__j._creator

    @property
    def guardian(self) -> Optional[JobBase]:
        """The `JobProxy` of the current guardian of this job."""
        return self.__j._guardian

    @property
    def created_at(self) -> datetime.datetime:
        return self.__created_at

    @property
    def registered_at(self) -> Optional[datetime.datetime]:
        return self.__j._registered_at

    @property
    def killed_at(self) -> Optional[datetime.datetime]:
        return self.__job_class.killed_at.fget(self.__j)

    @property
    def completed_at(self) -> Optional[datetime.datetime]:
        return self.__job_class.completed_at.fget(self.__j)

    @property
    def schedule_identifier(self) -> Optional[str]:
        """The identfier of the scheduling operation that instantiated
        this job, if available.
        """
        return self.__j._schedule_identifier

    loop_count = (
        JobBase.loop_count
    )  # fool autocompetion tools by overriding at runtime to prevent duplicate docstrings

    initialized = JobBase.initialized

    is_initializing = JobBase.is_initializing

    initialized_since = JobBase.initialized_since

    alive = JobBase.alive

    alive_since = JobBase.alive_since

    is_starting = JobBase.is_starting

    is_running = JobBase.is_running

    is_stopping = JobBase.is_stopping

    get_stopping_reason = JobBase.get_stopping_reason

    stopped = JobBase.stopped

    get_last_stopping_reason = JobBase.get_last_stopping_reason

    stopped_since = JobBase.stopped_since

    is_idling = JobBase.is_idling

    idling_since = JobBase.idling_since

    run_failed = JobBase.run_failed

    killed = JobBase.killed

    is_being_killed = JobBase.is_being_killed

    is_being_startup_killed = JobBase.is_being_startup_killed

    completed = JobBase.completed

    is_completing = JobBase.is_completing

    done = JobBase.done

    done_since = JobBase.done_since

    is_restarting = JobBase.is_restarting

    was_restarted = JobBase.was_restarted

    is_being_guarded = JobBase.is_being_guarded

    await_done = JobBase.await_done

    await_unguard = JobBase.await_unguard

    get_output_queue_proxy = JobBase.get_output_queue_proxy

    verify_output_field_support = JobBase.verify_output_field_support

    verify_output_queue_support = JobBase.verify_output_queue_support

    get_output_field = JobBase.get_output_field

    get_output_queue_contents = JobBase.get_output_queue_contents

    get_output_field_names = JobBase.get_output_field_names

    get_output_queue_names = JobBase.get_output_queue_names

    has_output_field_name = JobBase.has_output_field_name

    has_output_field_name = JobBase.has_output_field_name

    output_field_is_set = JobBase.output_field_is_set

    output_queue_is_empty = JobBase.output_queue_is_empty

    await_output_field = JobBase.await_output_field

    await_output_queue_add = JobBase.await_output_queue_add

    verify_public_method_suppport = JobBase.verify_public_method_suppport

    get_public_method_names = JobBase.get_public_method_names

    has_public_method_name = JobBase.has_public_method_name

    public_method_is_async = JobBase.public_method_is_async

    run_public_method = JobBase.run_public_method

    def interval_job_next_iteration(self) -> Optional[datetime.datetime]:
        """
        THIS METHOD WILL ONLY WORK ON PROXIES TO JOB OBJECTS
        THAT ARE INSTANCES OF `IntervalJobBase`.

        When the next iteration of `.on_run()` will occur.
        If not known, this method will return `None`.

        Returns:
            datetime.datetime: The time at which the next iteration will occur,
            if available.

        Raises:
            TypeError: The class of this job proxy's job is not an 'IntervalJobBase' subclass.
        """
        try:
            return self.__j.next_iteration()
        except AttributeError:
            raise TypeError(
                f"The '{self.__job_class.__name__}' job class of this job object's"
                " proxy is not an 'IntervalJobBase' subclass"
            ) from None

    def interval_job_get_interval(self) -> tuple[int, int, int]:
        """
        THIS METHOD WILL ONLY WORK ON PROXIES TO JOB OBJECTS
        THAT ARE `IntervalJobBase` SUBCLASSES.

        Returns a tuple of the seconds, minutes and hours at which this job
        object is executing its `.on_run()` method.

        Returns:
            tuple: `(seconds, minutes, hours)`

        Raises:
            TypeError: The class of this job proxy's job is not an 'IntervalJobBase' subclass.
        """
        try:
            return self.__j.get_interval()
        except AttributeError:
            raise TypeError(
                f"The '{self.__job_class.__name__}' job class of this job object's"
                " proxy is not an 'IntervalJobBase' subclass"
            ) from None

    def __str__(self):
        return f"<JobProxy ({self.__j!s})>"

    def __repr__(self):
        return f"<JobProxy ({self.__j!r})>"


class _JobProxy:
    __slots__ = (
        "__j",
        "__job_class",
        "__identifier",
        "__created_at",
        "__registered_at",
    )

    def __init__(self, job):
        self.__j = job
        self.__job_class = job.__class__
        self.__identifier = job._runtime_identifier
        self.__created_at = job.created_at
        self.__registered_at = job.registered_at

    def loop_count(self):
        return self.__j.loop_count()

    def initialized(self):
        return self.__j.initialized()

    def is_initializing(self):
        return self.__j.is_initializing()

    def initialized_since(self):
        return self.__j.initialized_since()

    def is_awaiting(self):
        return self.__j.is_awaiting()

    def awaiting_since(self):
        return self.__j.awaiting_since()

    def alive(self):
        return self.__j.alive()

    def alive_since(self):
        return self.__j.alive_since()

    def is_starting(self):
        return self.__j.is_starting()

    def is_running(self):
        return self.__j.is_running()

    def running_since(self):
        return self.__j.running_since()

    def is_stopping(self):
        return self.__j.is_stopping()

    def get_stopping_reason(self):
        return self.__j.get_stopping_reason()

    def stopped(self):
        return self.__j.stopped()

    def get_last_stopping_reason(self):
        return self.__j.get_last_stopping_reason()

    def stopped_since(self):
        return self.__j.stopped_since()

    def is_idling(self):
        return self.__j.is_idling()

    def idling_since(self):
        return self.__j.idling_since()

    def run_failed(self):
        return self.__j.run_failed()

    def killed(self):
        return self.__j.killed()

    def killed_at(self):
        return self.__j.killed_at()

    def is_being_killed(self, get_reason=False):
        return self.__j.is_being_killed(get_reason=get_reason)

    def is_being_startup_killed(self):
        return self.__j.is_being_startup_killed()

    def completed(self):
        return self.__j.completed()

    def completed_at(self):
        return self.__j.completed_at()

    def is_completing(self):
        return self.__j.is_completing()

    def done(self):
        return self.__j.done()

    def done_since(self):
        return self.__j.done_since()

    def is_restarting(self):
        return self.__j.is_restarting()

    def was_restarted(self):
        return self.__j.was_restarted()

    def is_being_guarded(self):
        return self.__j.is_being_guarded()

    def await_done(
        self, timeout: Optional[float] = None, cancel_if_killed: bool = False
    ):
        return self.__j.await_done(timeout=timeout, cancel_if_killed=cancel_if_killed)

    def await_unguard(self, timeout: Optional[float] = None):
        return self.__j.await_unguard(timeout=timeout)

    def get_output_queue_proxy(self):
        return self.__j.get_output_queue_proxy()

    def verify_output_field_support(self, field_name: str, raise_exceptions=False):
        return self.__j.verify_output_field_support(
            field_name, raise_exceptions=raise_exceptions
        )

    def verify_output_queue_support(self, queue_name: str, raise_exceptions=False):
        return self.__j.verify_output_queue_support(
            queue_name, raise_exceptions=raise_exceptions
        )

    def get_output_field(self, field_name: str, default=UNSET, /):
        return self.__j.get_output_field(field_name, default=default)

    def get_output_queue_contents(self, queue_name: str, default=UNSET, /):
        return self.__j.get_output_queue_contents(queue_name, default=default)

    def get_output_field_names(self):
        return self.__j.get_output_field_names()

    def get_output_queue_names(self):
        return self.__j.get_output_queue_names()

    def has_output_field_name(self, field_name: str):
        return self.__j.has_output_field_name(field_name)

    def has_output_queue_name(self, queue_name: str):
        return self.__j.has_output_queue_name(queue_name)

    def output_field_is_set(self, field_name: str):
        return self.__j.output_field_is_set(field_name)

    def output_queue_is_empty(self, queue_name: str):
        return self.__j.output_queue_is_empty(queue_name)

    def await_output_field(self, field_name: str, timeout: Optional[float] = None):
        return self.__j.await_output_field(field_name, timeout=timeout)

    def await_output_queue_add(
        self,
        queue_name: str,
        timeout: Optional[float] = None,
        cancel_if_cleared: bool = True,
    ):
        return self.__j.await_output_queue_add(
            queue_name, timeout=timeout, cancel_if_cleared=cancel_if_cleared
        )

    def verify_public_method_suppport(self, method_name: str, raise_exceptions=False):
        return self.__j.verify_public_method_suppport(
            method_name, raise_exceptions=raise_exceptions
        )

    def get_public_method_names(self):
        return self.__j.get_public_method_names()

    def has_public_method_name(self, method_name: str):
        return self.__j.has_public_method_name(method_name)

    def public_method_is_async(self, method_name: str):
        return self.__j.public_method_is_async(method_name)

    def run_public_method(self, method_name: str, *args, **kwargs):
        return self.__j.run_public_method(method_name, *args, **kwargs)


class JobOutputQueueProxy:
    """A helper class for job objects to share
    data with other jobs in a continuous manner.
    This class should not be instantiated directly,
    but instances can be requested from job obects that support it.
    """

    __slots__ = (
        "__j",
        "__job_proxy",
        "_default_queue_config",
        "__output_queue_names",
        "_output_queue_proxy_dict",
    )

    def __init__(self, job: JobBase):
        self.__j = job
        self.__job_proxy = job._proxy
        self.__output_queue_names = job.OutputQueues
        job_output_queues = self.__j._output_queues
        self._output_queue_proxy_dict: dict[
            str, list[Union[int, Optional[deque[Any]], list[Any]]]
        ] = {
            queue_name: [0, None, job_output_queues[queue_name]]
            for queue_name in self.__j.OutputQueues.get_all_names()
        }

        self._default_queue_config = {"use_rescue_buffer": False}

    @property
    def job_proxy(self):
        """The job this output queue proxy is pointing to.

        Returns:
            JobProxy: The job proxy.
        """
        return self.__job_proxy

    def verify_output_queue_support(self, queue_name: str, raise_exceptions=False):
        """Verify if a specified output queue name is supported by this
        output queue proxy's job. Disabled output queue names are seen
        as unsupported.

        Args:
            queue_name (str): The name of the output queue to set.
            raise_exceptions (Optional[bool], optional): Whether exceptions should
              be raised. Defaults to False.

        Raises:
            TypeError: `queue_name` is not a string.
            ValueError: The specified queue name was marked as disabled.
            LookupError: The specified queue name is not defined by this
              output queue proxy's job.

        Returns:
            bool: True/False
        """

        value = getattr(self.__output_queue_names, queue_name, None)

        if value is None:
            if raise_exceptions:
                raise (
                    LookupError(
                        f"queue name '{queue_name}' is not defined in "
                        f"'OutputQueues' class namespace of class "
                        f"'{self.__j.__class__.__name__}' that this proxy "
                        "references"
                    )
                    if isinstance(queue_name, str)
                    else TypeError(
                        f"'queue_name' argument must be of type str,"
                        f" not {queue_name.__class__.__name__}"
                    )
                )
            return False

        elif value == "DISABLED":
            if raise_exceptions:
                raise ValueError(
                    f"the output queue name '{queue_name}' has been marked as disabled"
                )
            return False

        return True

    def config_output_queue(
        self, queue_name: str, use_rescue_buffer: Optional[bool] = None
    ):
        """Configure settings for a speficied output queue.

        Args:
            queue_name (str): The name of the output queue to set.
            use_rescue_buffer (Optional[bool], optional): Set up a rescue buffer for
              the specified output queue, which automatically collects queue values
              when a job cleares a queue. Defaults to None.
        """
        self.verify_output_queue_support(queue_name, raise_exceptions=True)

        if queue_name not in self._output_queue_proxy_dict:
            self._output_queue_proxy_dict[queue_name] = [0, None, []]

        if use_rescue_buffer:
            self._output_queue_proxy_dict[queue_name][1] = deque()
        elif use_rescue_buffer is False:
            self._output_queue_proxy_dict[queue_name][1] = None

    def config_output_queue_defaults(self, use_rescue_buffer: Optional[bool] = None):
        """Configure default settings for output queues.

        Args:
            use_rescue_buffer (Optional[bool], optional): Set up a rescue buffer for
              an output queue, which automatically collects queue values
              when a job cleares a queue. Defaults to None.
        """

        if use_rescue_buffer is not None:
            self._default_queue_config["use_rescue_buffer"] = bool(use_rescue_buffer)

    def _output_queue_clear_alert(self, queue_name: str):
        # Alerts OutputQueueProxy objects that their job
        # object is about to clear its output queues.
        queue_list = self._output_queue_proxy_dict[queue_name]

        if queue_list[1] is not None:
            queue_list[1].extend(queue_list[2])

        queue_list[0] = 0

    def _new_output_queue_alert(self, queue_name: str, queue_list: list):
        if queue_name not in self._output_queue_proxy_dict:
            self._output_queue_proxy_dict[queue_name] = [0, None, queue_list]
        else:
            self._output_queue_proxy_dict[queue_name][2] = queue_list

        if self._default_queue_config["use_rescue_buffer"]:
            self._output_queue_proxy_dict[queue_name][1] = deque()

    def pop_output_queue(
        self, queue_name: str, amount: Optional[int] = None, all_values: bool = False
    ):
        """Get the oldest or a list of the specified amount of oldest entries in the
        speficied output queue.

        Args:
            queue_name (str): The name of the target output queue.
            amount (Optional[int], optional): The maximum amount of entries to return.
              If there are less entries available than this amount, only
              Defaults to None.
            all_entries (bool, optional): Whether all entries should be released at once.
              Defaults to False.

        Raises:
            LookupError: The target queue is exhausted, or empty.

        Returns:
            object: The oldest value, or a list of the specified amount of them, if
              possible.
        """
        self.verify_output_queue_support(queue_name, raise_exceptions=True)

        queue_list = self._output_queue_proxy_dict[queue_name]

        if not all_values and amount is None:

            if queue_list[1]:
                return queue_list[1].popleft()
            elif queue_list[2]:
                if queue_list[0] < len(queue_list[2]):
                    output = queue_list[2][queue_list[0]]
                    queue_list[0] += 1
                    return output

                raise LookupError(
                    f"the target queue with name '{queue_name}' is exhausted"
                )

            else:
                raise LookupError(f"the target queue with name '{queue_name}' is empty")

        elif all_values or isinstance(amount, int) and amount > 0:
            entries = []

            for _ in itertools.count() if all_values else range(amount):
                if queue_list[1]:
                    entries.append(queue_list[1].popleft())
                elif queue_list[2]:
                    if queue_list[0] < len(queue_list[2]):
                        entries.append(queue_list[2][queue_list[0]])
                        queue_list[0] += 1
                    else:
                        break
                else:
                    break

            return entries

        raise TypeError(f"argument 'amount' must be None or a positive integer")

    def output_queue_is_empty(self, queue_name: str, ignore_rescue_buffer=False):
        """Whether the specified output queue is empty.

        Args:
            queue_name (str): The name of the target output queue.
            ignore_rescue_buffer (bool): Whether the contents of the rescue buffer
              should be considered as well. Defaults to False.

        Raises:
            TypeError: `queue_name` is not a string.
            LookupError: The specified queue name is not defined by this output
            queue proxy's job.

        Returns:
            bool: True/False
        """

        self.verify_output_queue_support(queue_name, raise_exceptions=True)

        if ignore_rescue_buffer:
            return not self._output_queue_proxy_dict[queue_name][2]

        queue_list = self._output_queue_proxy_dict[queue_name]
        return not queue_list[1] and not queue_list[2]

    def output_queue_is_exhausted(self, queue_name: str):
        """Whether the specified output queue is exhausted,
        meaning that no new values are available.

        Args:
            queue_name (str): The name of the target output queue.
            ignore_rescue_buffer (bool): Whether the contents of
            the rescue buffer should be considered as well.
            Defaults to False.

        Raises:
            TypeError: `queue_name` is not a string.
            LookupError: The specified queue name is not defined by
              this output queue proxy's job.

        Returns:
            bool: True/False
        """

        self.verify_output_queue_support(queue_name, raise_exceptions=True)
        queue_list = self._output_queue_proxy_dict.get(queue_name, UNSET)

        if queue_list is UNSET:
            return False

        if queue_list[2] and queue_list[0] >= len(queue_list[2]):
            return True
        return False

    def await_output_queue_add(
        self,
        queue_name: str,
        timeout: Optional[float] = None,
        cancel_if_cleared: bool = True,
    ):
        """Wait for the job object of this output queue proxy to add to the specified
        output queue while it is running, using the coroutine output of this method.

        Args:
            timeout (float, optional): The maximum amount of time to wait in seconds.
              Defaults to None.
            cancel_if_cleared (bool): Whether `asyncio.CancelledError` should be
              raised if the output queue is cleared. If set to `False`, `UNSET`
              will be the result of the coroutine. Defaults to False.

        Raises:
            TypeError: Output fields aren't supported for this job, or `field_name`
              is not a string.
            LookupError: The specified field name is not defined by this job
            JobStateError: This job object is already done.
            asyncio.TimeoutError: The timeout was exceeded.
            asyncio.CancelledError:
                The job was killed, or the output queue was cleared.

        Returns:
            Coroutine: A coroutine that evaluates to the most recent output queue
              value, or `UNSET` if the queue is cleared.
        """

        return self.__j.await_output_queue_add(
            queue_name, timeout=timeout, cancel_if_cleared=cancel_if_cleared
        )


class JobManagerProxy:

    __slots__ = ("__mgr", "__j", "_job_stop_timeout")

    def __init__(self, mgr, job: Union[EventJobBase, IntervalJobBase]):
        self.__mgr = mgr
        self.__j = job
        self._job_stop_timeout = None

    is_running = manager.JobManager.is_running

    def get_job_stop_timeout(self):  # placeholder method with docstring
        """Get the maximum time period in seconds for the job object managed
        by this `JobManagerProxy` to stop when halted from the
        job manager, either due to stopping, restarted or killed.
        By default, this method returns the global job timeout set for the
        current job manager, but that can be overridden with a custom
        timeout when trying to stop the job object.

        Returns:
            float: The timeout in seconds.
            None: No timeout was set for the job object or globally for the
              current job manager.
        """
        ...

    def verify_permissions(
        self,
        op: JobPermissionLevels,
        target: Optional[JobProxy] = None,
        target_cls: Optional[Union[Type[EventJobBase], Type[IntervalJobBase]]] = None,
        schedule_identifier: Optional[str] = None,
        invoker_identifier: Optional[str] = None,
    ):
        """Check if the permissions of the job of this `JobManagerProxy` object
        are sufficient for carrying out the specified operation on the given input.

        Args:
            op (str): The operation. Must be one of the operations defined in the
              `JobVerbs` class namespace.
            target (Optional[JobProxy], optional): The target job's proxy for an
              operation.
              Defaults to None.
            target_cls (Optional[Union[Type[EventJobBase], Type[IntervalJobBase]]],
              optional):
              The target job class for an operation. Defaults to None.
            schedule_identifier (Optional[str], optional):
              A target schedule identifier. Defaults to None.
            invoker_identifier (Optional[str], optional):
              A target job with this specific identifier if existent, but can also be
              an enpty string. Defaults to None.

        Returns:
            bool: The result of the permission check.
        """
        ...

    create_job = manager.JobManager.create_job

    initialize_job = manager.JobManager.initialize_job

    register_job = manager.JobManager.register_job

    create_and_register_job = manager.JobManager.create_and_register_job

    job_scheduling_is_initialized = manager.JobManager.job_scheduling_is_initialized

    wait_for_job_scheduling_initialization = (
        manager.JobManager.wait_for_job_scheduling_initialization
    )

    wait_for_job_scheduling_uninitialization = (
        manager.JobManager.wait_for_job_scheduling_uninitialization
    )

    create_job_schedule = manager.JobManager.create_job_schedule

    get_job_schedule_identifiers = manager.JobManager.get_job_schedule_identifiers

    job_schedule_has_failed = manager.JobManager.job_schedule_has_failed

    has_job_schedule = manager.JobManager.has_job_schedule

    remove_job_schedule = manager.JobManager.remove_job_schedule

    restart_job = manager.JobManager.restart_job

    start_job = manager.JobManager.start_job

    stop_job = manager.JobManager.stop_job

    kill_job = manager.JobManager.kill_job

    def get_guarded_jobs(self) -> tuple:
        """Get the jobs currently being guarded by the manager,
        for the job object of this job manager proxy.

        Returns:
            tuple: A tuple of guarded jobs
        """
        ...

    guard_job = manager.JobManager.guard_job

    unguard_job = manager.JobManager.unguard_job

    guarding_job = manager.JobManager.guarding_job

    def has_job(self, job_proxy: JobProxy) -> bool:
        """Whether a specific job object is currently in this
        job manager.

        Args:
            job_proxy (JobProxy): The target job's proxy.

        Returns:
            bool: True/False
        """
        ...

    __contains__ = has_job

    has_job_identifier = manager.JobManager.has_job_identifier


class _JobManagerProxy:  # hidden implementation to trick type-checker engines
    __slots__ = ("__mgr", "__j", "_job_stop_timeout")

    def __init__(self, mgr: manager.JobManager, job):
        self.__mgr = mgr
        self.__j = job
        self._job_stop_timeout = None

    def is_running(self):
        return self.__mgr.is_running()

    def get_job_stop_timeout(self):
        return (
            self._job_stop_timeout
            if self._job_stop_timeout
            else self.__mgr.get_global_job_stop_timeout()
        )

    def verify_permissions(
        self,
        op: JobPermissionLevels,
        target: Optional[JobProxy] = None,
        target_cls: Optional[Union[Type[EventJobBase], Type[IntervalJobBase]]] = None,
        schedule_identifier: Optional[str] = None,
        invoker_identifier: Optional[str] = None,
    ) -> bool:
        return self.__mgr._verify_permissions(
            self.__j,
            op,
            target=target if target is not None else target,
            target_cls=target_cls,
            schedule_identifier=schedule_identifier,
            invoker_identifier=invoker_identifier,
            raise_exceptions=False,
        )

    def create_job(
        self, cls: Union[Type[EventJobBase], Type[IntervalJobBase]], *args, **kwargs
    ):
        return self.__mgr.create_job(
            cls, *args, _return_proxy=True, _iv=self.__j, **kwargs
        )

    async def initialize_job(self, job_proxy: JobProxy, raise_exceptions: bool = True):
        return await self.__mgr.initialize_job(
            job_proxy, raise_exceptions=raise_exceptions
        )

    async def register_job(self, job_proxy: JobProxy):
        return await self.__mgr.register_job(job_proxy, _iv=self.__j)

    async def create_and_register_job(
        self, cls: Union[Type[EventJobBase], Type[IntervalJobBase]], *args, **kwargs
    ) -> JobProxy:
        return await self.__mgr.create_and_register_job(
            cls,
            *args,
            _return_proxy=True,
            _iv=self.__j,
            **kwargs,
        )

    def job_scheduling_is_initialized(self):
        return self.__mgr.job_scheduling_is_initialized()

    def wait_for_job_scheduling_initialization(self):
        return self.__mgr.wait_for_job_scheduling_initialization()

    def wait_for_job_scheduling_uninitialization(self):
        return self.__mgr.wait_for_job_scheduling_uninitialization()

    async def create_job_schedule(
        self,
        cls: Union[Type[EventJobBase], Type[IntervalJobBase]],
        timestamp: Union[datetime.datetime, datetime.timedelta],
        recur_interval: Union[int, datetime.timedelta] = 0,
        max_recurrences: int = 1,
        job_args: tuple = (),
        job_kwargs: Optional[dict] = None,
    ) -> str:
        return await self.__mgr.create_job_schedule(
            cls=cls,
            timestamp=timestamp,
            recur_interval=recur_interval,
            max_recurrences=max_recurrences,
            job_args=job_args,
            job_kwargs=job_kwargs,
            _iv=self.__j,
        )

    def get_job_schedule_identifiers(self):
        return self.__mgr.get_job_schedule_identifiers()

    def job_schedule_has_failed(self, schedule_identifier: str):
        return self.__mgr.job_schedule_has_failed(schedule_identifier)

    def has_job_schedule(self, schedule_identifier: str):
        return self.__mgr.has_job_schedule(schedule_identifier)

    async def remove_job_schedule(
        self,
        schedule_identifier: str,
    ):
        return await self.__mgr.remove_job_schedule(schedule_identifier, _iv=self.__j)

    def restart_job(
        self, job_proxy: JobProxy, stopping_timeout: Optional[float] = None
    ):
        job = self.__mgr._get_job_from_proxy(job_proxy)

        if job is self.__j:
            job.RESTART()

        return self.__mgr.restart_job(
            job_proxy, stopping_timeout=stopping_timeout, _iv=self.__j
        )

    def start_job(
        self,
        job_proxy: JobProxy,
    ):
        return self.__mgr.start_job(job_proxy, _iv=self.__j)

    def stop_job(
        self,
        job_proxy: JobProxy,
        stopping_timeout: Optional[float] = None,
        force=False,
    ):
        job = self.__mgr._get_job_from_proxy(job_proxy)

        if job is self.__j:
            job.STOP(force=force)

        return self.__mgr.stop_job(
            job_proxy, stopping_timeout=stopping_timeout, force=force, _iv=self.__j
        )

    def kill_job(self, job_proxy: JobProxy, stopping_timeout: Optional[float] = None):
        job = self.__mgr._get_job_from_proxy(job_proxy)

        if job is self.__j:
            job.KILL()

        return self.__mgr.kill_job(
            job_proxy, stopping_timeout=stopping_timeout, _iv=self.__j
        )

    def get_guarded_jobs(self) -> tuple:
        return tuple(self.__j._guarded_job_proxies_set)

    def guard_job(
        self,
        job_proxy: JobProxy,
    ):
        return self.__mgr.guard_job(job_proxy, _iv=self.__j)

    def unguard_job(
        self,
        job_proxy: JobProxy,
    ):
        return self.__mgr.unguard_job(job_proxy, _iv=self.__j)

    def guarding_job(
        self,
        job_proxy: JobProxy,
    ):
        return self.__mgr.guarding_job(job_proxy, _iv=self.__j)

    def _eject(self):
        """
        Irreversible job death. Do not call this method without ensuring that
        a job is killed.
        """
        if not self.__j.alive():
            self.__mgr._remove_job(self.__j)
            self.__j._manager = None
            self.__j = None
            self.__mgr = None

    def _unguard(self):
        if self.__j._is_being_guarded:
            guardian = self.__mgr._get_job_from_proxy(self.__j._guardian)
            self.__mgr.unguard_job(self.__j, _iv=guardian)

    def find_job(
        self,
        *,
        identifier: Union[str, _UnsetType] = None,
        created_at: Union[datetime.datetime, _UnsetType] = None,
    ) -> Optional["JobProxy"]:

        return self.__mgr.find_job(
            identifier=identifier,
            created_at=created_at,
            _return_proxy=True,
            _iv=self.__j,
        )

    def find_jobs(
        self,
        *,
        classes: tuple[
            Union[
                Type[EventJobBase],
                Type[IntervalJobBase],
            ]
        ] = tuple(),
        exact_class_match: bool = False,
        created_before: Union[datetime.datetime, _UnsetType] = UNSET,
        created_after: Union[datetime.datetime, _UnsetType] = UNSET,
        permission_level: Union[JobPermissionLevels, _UnsetType] = UNSET,
        above_permission_level: Union[JobPermissionLevels, _UnsetType] = UNSET,
        below_permission_level: JobPermissionLevels = JobPermissionLevels.SYSTEM,
        alive: Union[bool, _UnsetType] = UNSET,
        is_starting: Union[bool, _UnsetType] = UNSET,
        is_running: Union[bool, _UnsetType] = UNSET,
        is_idling: Union[bool, _UnsetType] = UNSET,
        is_awaiting: Union[bool, _UnsetType] = UNSET,
        is_stopping: Union[bool, _UnsetType] = UNSET,
        is_restarting: Union[bool, _UnsetType] = UNSET,
        is_being_killed: Union[bool, _UnsetType] = UNSET,
        is_being_completed: Union[bool, _UnsetType] = UNSET,
        stopped: Union[bool, _UnsetType] = UNSET,
    ) -> tuple["JobProxy"]:

        return self.__mgr.find_jobs(
            classes=classes,
            exact_class_match=exact_class_match,
            created_before=created_before,
            created_after=created_after,
            permission_level=permission_level,
            above_permission_level=above_permission_level,
            below_permission_level=below_permission_level,
            alive=alive,
            is_starting=is_starting,
            is_running=is_running,
            is_idling=is_idling,
            is_awaiting=is_awaiting,
            is_stopping=is_stopping,
            is_restarting=is_restarting,
            is_being_killed=is_being_killed,
            is_being_completed=is_being_completed,
            stopped=stopped,
            _return_proxy=True,
            _iv=self.__j,
        )

    def wait_for_event(
        self,
        *event_types: Type[events.BaseEvent],
        check: Optional[Callable[[events.BaseEvent], bool]] = None,
        timeout: Optional[float] = None,
    ):
        return self.__mgr.wait_for_event(
            *event_types,
            check=check,
            timeout=timeout,
        )

    def dispatch_event(self, event: events.BaseEvent):
        event._dispatcher = self.__j._proxy
        return self.__mgr.dispatch_event(event, _iv=self.__j)

    def has_job(self, job_proxy: JobProxy):
        return self.__mgr.has_job(job_proxy)

    __contains__ = has_job

    def has_job_identifier(self, identifier: str):
        return self.__mgr.has_job_identifier(identifier)


for key, obj in _JobProxy.__dict__.items():
    if isinstance(obj, FunctionType):
        setattr(JobProxy, key, obj)


for key, obj in _JobManagerProxy.__dict__.items():
    if isinstance(obj, FunctionType):
        setattr(JobManagerProxy, key, obj)
