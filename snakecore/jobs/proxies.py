"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file implements proxy objects used by job and job managers
for extra features and encapsulation. 
"""

from collections import deque
import datetime
import functools
import itertools
from types import FunctionType
import types
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional, Type, Union

from snakecore import events
from snakecore.constants import UNSET, _UnsetType, JobPermissionLevels, JobOps
from snakecore.constants.enums import JobBoolFlags as JF
from snakecore.exceptions import JobIsDone, JobStateError

from . import jobs, manager


class JobProxy:  # will be overridden at runtime
    """A proxy class that provides an interface for safe access to job objects at
    runtime.
    """

    __slots__ = (
        "__j",
        "__job_class",
        "__runtime_identifier",
        "_created_at",
        "_registered_at",
    )

    def __init__(self, job: "jobs.JobBase"):
        ...

    def _cache_current_job_state(self):
        ...

    def _eject_from_source(self):
        ...

    def _check_if_ejected(self):
        ...

    @property
    def job_class(self) -> jobs.JobBase:
        ...

    @property
    def permission_level(self) -> JobPermissionLevels:
        ...

    @property
    def runtime_identifier(self) -> str:
        ...

    @property
    def creator(self) -> Optional["JobProxy"]:
        """The `JobProxy` of the creator of this job."""
        ...

    @property
    def guardian(self) -> Optional[jobs.JobBase]:
        """The `JobProxy` of the current guardian of this job."""
        ...

    @property
    def created_at(self) -> datetime.datetime:
        ...

    @property
    def registered_at(self) -> Optional[datetime.datetime]:
        ...

    @property
    def killed_at(self) -> Optional[datetime.datetime]:
        ...

    @property
    def completed_at(self) -> Optional[datetime.datetime]:
        ...

    initialized = (
        jobs.JobBase.initialized
    )  # fool autocompetion tools in order to reuse docstrings

    is_initializing = jobs.JobBase.is_initializing

    initialized_since = jobs.JobBase.initialized_since

    alive = jobs.JobBase.alive

    alive_since = jobs.JobBase.alive_since

    is_starting = jobs.JobBase.is_starting

    is_running = jobs.JobBase.is_running

    running_since = jobs.JobBase.running_since

    is_stopping = jobs.JobBase.is_stopping

    get_stopping_reason = jobs.JobBase.get_stopping_reason

    stopped = jobs.JobBase.stopped

    get_last_stopping_reason = jobs.JobBase.get_last_stopping_reason

    stopped_since = jobs.JobBase.stopped_since

    is_idling = jobs.JobBase.is_idling

    idling_since = jobs.JobBase.idling_since

    run_failed = jobs.JobBase.run_failed

    killed = jobs.JobBase.killed

    is_being_killed = jobs.JobBase.is_being_killed

    is_being_startup_killed = jobs.JobBase.is_being_startup_killed

    completed = jobs.JobBase.completed

    is_completing = jobs.JobBase.is_completing

    done = jobs.JobBase.done

    done_since = jobs.JobBase.done_since

    is_restarting = jobs.JobBase.is_restarting

    was_restarted = jobs.JobBase.was_restarted

    is_being_guarded = jobs.JobBase.is_being_guarded

    await_done = jobs.JobBase.await_done

    await_unguard = jobs.JobBase.await_unguard

    get_output_queue_proxy = jobs.JobBase.get_output_queue_proxy

    verify_output_field_support = jobs.JobBase.verify_output_field_support

    verify_output_queue_support = jobs.JobBase.verify_output_queue_support

    get_output_field = jobs.JobBase.get_output_field

    get_output_queue_contents = jobs.JobBase.get_output_queue_contents

    get_output_field_names = jobs.JobBase.get_output_field_names

    get_output_queue_names = jobs.JobBase.get_output_queue_names

    has_output_field_name = jobs.JobBase.has_output_field_name

    has_output_queue_name = jobs.JobBase.has_output_queue_name

    output_field_is_set = jobs.JobBase.output_field_is_set

    output_queue_is_empty = jobs.JobBase.output_queue_is_empty

    await_output_field = jobs.JobBase.await_output_field

    await_output_queue_add = jobs.JobBase.await_output_queue_add

    verify_public_method_suppport = jobs.JobBase.verify_public_method_suppport

    get_public_method_names = jobs.JobBase.get_public_method_names

    has_public_method_name = jobs.JobBase.has_public_method_name

    public_method_is_async = jobs.JobBase.public_method_is_async

    run_public_method = jobs.JobBase.run_public_method


class _JobProxy:
    __slots__ = (
        "__j",
        "__job_class",
        "__runtime_identifier",
        "__permission_level",
        "__creator",
        "_created_at",
        "_registered_at",
        "_done_since",
        "_initialized_since",
        "_alive_since",
        "_last_stopping_reason",
        "_killed_at",
        "_completed_at",
        "_done",
        "_bools",
    )

    def __init__(self, job: "jobs.JobBase"):
        self.__j = job
        self._cache_current_job_state()

    def _cache_current_job_state(self):
        job = self.__j
        if job is None:
            return
        self.__job_class = job.__class__
        self.__runtime_identifier = job._runtime_identifier
        self.__permission_level = job.permission_level if job.alive() else None
        self.__creator = job.creator
        self._created_at = job.created_at
        self._registered_at = job.registered_at
        self._done = job.done()
        self._initialized_since = job.initialized_since()
        self._alive_since = job.alive_since()
        self._last_stopping_reason = job._last_stopping_reason
        self._done_since = job.done_since()
        self._job_bools = job._bools

        if job.done():
            self.__j = None

    def _eject_from_source(self):
        if self.__j.done():
            self._cache_current_job_state()
            self.__j = None

    def _check_if_ejected(self):
        if self.__j is None:
            raise JobIsDone("this job object is already done.")

    @property
    def job_class(self) -> jobs.JobBase:
        return self.__job_class

    @property
    def permission_level(self) -> Optional[JobPermissionLevels]:
        return (
            self.__j.permission_level
            if self.__j is not None
            else self.__permission_level
        )

    @property
    def runtime_identifier(self) -> str:
        return self.__runtime_identifier

    @property
    def creator(self) -> Optional["JobProxy"]:
        """The `JobProxy` of the creator of this job."""
        return self.__creator

    @property
    def guardian(self) -> Optional["JobProxy"]:
        """The `JobProxy` of the current guardian of this job."""
        return self.__j._guardian if self.__j is not None else None

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def registered_at(self) -> Optional[datetime.datetime]:
        return self.__j.registered_at

    @property
    def killed_at(self) -> Optional[datetime.datetime]:
        return self.__j.killed_at

    @property
    def completed_at(self) -> Optional[datetime.datetime]:
        return self.__job_class.completed_at

    def initialized(self):
        return self.__j.initialized() if self.__j is not None else True

    def is_initializing(self):
        return self.__j.is_initializing() if self.__j is not None else False

    def initialized_since(self):
        return (
            self.__j.initialized_since()
            if self.__j is not None
            else self._initialized_since
        )

    def alive(self):
        return self.__j.alive() if self.__j is not None else False

    def alive_since(self):
        return self.__j.alive_since() if self.__j is not None else self._alive_since

    def is_starting(self):
        return self.__j.is_starting() if self.__j is not None else False

    def is_running(self):
        return self.__j.is_running() if self.__j is not None else False

    def running_since(self):
        return self.__j.running_since() if self.__j is not None else None

    def is_stopping(self):
        return self.__j.is_stopping() if self.__j is not None else False

    def get_stopping_reason(self):
        return self.__j.get_stopping_reason() if self.__j is not None else None

    def stopped(self):
        return self.__j.stopped() if self.__j is not None else False

    def get_last_stopping_reason(self):
        return (
            self.__j.get_last_stopping_reason()
            if self.__j is not None
            else self._last_stopping_reason
        )

    def stopped_since(self):
        return self.__j.stopped_since() if self.__j is not None else None

    def is_idling(self):
        return self.__j.is_idling() if self.__j is not None else False

    def idling_since(self):
        return self.__j.idling_since() if self.__j is not None else None

    def run_failed(self):
        return self.__j.run_failed() if self.__j is not None else False

    def killed(self):
        return (
            self.__j.killed()
            if self.__j is not None
            else bool(self._job_bools & JF.KILLED)
        )

    def is_being_killed(self, get_reason=False):
        return (
            self.__j.is_being_killed(get_reason=get_reason)
            if self.__j is not None
            else False
        )

    def is_being_startup_killed(self):
        return self.__j.is_being_startup_killed() if self.__j is not None else False

    def completed(self):
        return (
            self.__j.completed()
            if self.__j is not None
            else bool(self._job_bools & JF.COMPLETED)
        )

    def is_completing(self):
        return self.__j.is_completing() if self.__j is not None else False

    def done(self):
        return self._done

    def done_since(self):
        return self.__j.done_since() if self._done else self._done_since

    completed_at = killed_at = property(fget=done_since)

    def is_restarting(self):
        return (
            self.__j.is_restarting()
            if self.__j is not None
            else self._last_stopping_reason
        )

    def was_restarted(self):
        return self.__j.was_restarted() if self.__j is not None else False

    def is_being_guarded(self):
        return self.__j.is_being_guarded() if self.__j is not None else False

    def await_done(
        self, timeout: Optional[float] = None, cancel_if_killed: bool = False
    ):
        self._check_if_ejected()
        return self.__j.await_done(timeout=timeout, cancel_if_killed=cancel_if_killed)

    def await_unguard(self, timeout: Optional[float] = None):
        self._check_if_ejected()
        return self.__j.await_unguard(timeout=timeout)

    def get_output_queue_proxy(self):
        self._check_if_ejected()
        return self.__j.get_output_queue_proxy()

    def verify_output_field_support(self, field_name: str, raise_exceptions=False):
        return self.__job_class.verify_output_field_support(
            field_name, raise_exceptions=raise_exceptions
        )

    def verify_output_queue_support(self, queue_name: str, raise_exceptions=False):
        return self.__job_class.verify_output_queue_support(
            queue_name, raise_exceptions=raise_exceptions
        )

    def get_output_field(self, field_name: str, default=UNSET, /):
        self._check_if_ejected()
        return self.__j.get_output_field(field_name, default=default)

    def get_output_queue_contents(self, queue_name: str, default=UNSET, /):
        self._check_if_ejected()
        return self.__j.get_output_queue_contents(queue_name, default=default)

    def get_output_field_names(self):
        return self.__job_class.get_output_field_names()

    def get_output_queue_names(self):
        return self.__job_class.get_output_queue_names()

    def has_output_field_name(self, field_name: str):
        return self.__job_class.has_output_field_name(field_name)

    def has_output_queue_name(self, queue_name: str):
        return self.__job_class.has_output_queue_name(queue_name)

    def output_field_is_set(self, field_name: str):
        self._check_if_ejected()
        return self.__j.output_field_is_set(field_name)

    def output_queue_is_empty(self, queue_name: str):
        self._check_if_ejected()
        return self.__j.output_queue_is_empty(queue_name)

    def await_output_field(self, field_name: str, timeout: Optional[float] = None):
        self._check_if_ejected()
        return self.__j.await_output_field(field_name, timeout=timeout)

    def await_output_queue_add(
        self,
        queue_name: str,
        timeout: Optional[float] = None,
        cancel_if_cleared: bool = True,
    ):
        self._check_if_ejected()
        return self.__j.await_output_queue_add(
            queue_name, timeout=timeout, cancel_if_cleared=cancel_if_cleared
        )

    def verify_public_method_suppport(self, method_name: str, raise_exceptions=False):
        return self.__job_class.verify_public_method_suppport(
            method_name, raise_exceptions=raise_exceptions
        )

    def get_public_method_names(self):
        return self.__job_class.get_public_method_names()

    def has_public_method_name(self, method_name: str):
        return self.__job_class.has_public_method_name(method_name)

    def public_method_is_async(self, method_name: str):
        return self.__job_class.public_method_is_async(method_name)

    def run_public_method(self, method_name: str, *args, **kwargs):
        self._check_if_ejected()
        return self.__j.run_public_method(method_name, *args, **kwargs)

    def __str__(self):
        return f"<JobProxy ({self.__j!s})>"

    def __repr__(self):
        return f"<JobProxy ({self.__j!r})>"


class JobOutputQueueProxy:
    """A helper class for managed job objects to share
    data with other jobs in a continuous manner.
    This class should not be instantiated directly,
    but instances can be requested from job obects that support it.
    """

    __slots__ = (
        "__j",
        "__job_class",
        "__job_proxy",
        "_default_queue_config",
        "__output_queue_names",
        "_output_queue_proxy_dict",
    )

    def __init__(self, job: jobs.JobBase):
        self.__j = job
        self.__job_class = job.__class__
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

    def verify_output_queue_support(
        self, queue_name: str, raise_exceptions=False
    ) -> bool:
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
        return self.__job_class.verify_output_queue_support(
            queue_name, raise_exceptions=raise_exceptions
        )

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
            JobIsDone: This job object is already done.
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

    def __init__(
        self,
        mgr: manager.JobManager,
        job: jobs.ManagedJobBase,
    ):
        ...

    is_running = manager.JobManager.is_running

    @property
    def _loop(self):
        ...

    def get_job_stop_timeout(
        self,
    ) -> Optional[float]:  # placeholder method with docstring
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
        target_cls: Optional[Type[jobs.ManagedJobBase]] = None,
    ):
        """Check if the permissions of the job of this `JobManagerProxy` object
        are sufficient for carrying out the specified operation on the given input.

        Args:
            op (str): The operation. Must be one of the operations defined in the
              `JobOps` class namespace.
            target (Optional[JobProxy], optional): The target job's proxy for an
              operation.
              Defaults to None.
            target_cls (Optional[Type[jobs.ManagedJobBase]],
              optional):
              The target job class for an operation. Defaults to None.

        Returns:
            bool: The result of the permission check.
        """
        ...

    def _eject(self):
        """
        Irreversible job death. Do not call this method without ensuring that
        a job is killed.
        """
        ...

    def _self_ungard(self):
        ...

    get_job_class_permission_level = manager.JobManager.get_job_class_permission_level

    register_job_class = manager.JobManager.register_job_class

    unregister_job_class = manager.JobManager.unregister_job_class

    job_class_is_registered = manager.JobManager.job_class_is_registered

    create_job = manager.JobManager.create_job

    initialize_job = manager.JobManager.initialize_job

    register_job = manager.JobManager.register_job

    create_and_register_job = manager.JobManager.create_and_register_job

    restart_job = manager.JobManager.restart_job

    start_job = manager.JobManager.start_job

    stop_job = manager.JobManager.stop_job

    kill_job = manager.JobManager.kill_job

    guard_job = manager.JobManager.guard_job

    unguard_job = manager.JobManager.unguard_job

    guard_on_job = manager.JobManager.guard_on_job

    find_job = manager.JobManager.find_job

    find_jobs = manager.JobManager.find_jobs

    wait_for_event = manager.JobManager.wait_for_event

    dispatch_event = manager.JobManager.dispatch_event

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

    def __init__(self, mgr: manager.JobManager, job: jobs.JobBase):
        self.__mgr = mgr
        self.__j = job
        self._job_stop_timeout = None

    def is_running(self):
        return self.__mgr.is_running()

    @property
    def _loop(self):
        return self.__mgr._loop

    def get_job_stop_timeout(self):
        return (
            self._job_stop_timeout
            if self._job_stop_timeout
            else self.__mgr.get_global_job_stop_timeout()
        )

    def get_job_class_permission_level(
        self, cls: Type[jobs.ManagedJobBase], default: Any = UNSET, /
    ) -> Union[JobPermissionLevels, Any]:
        return self.__mgr.get_job_class_permission_level(cls, default)

    def verify_permissions(
        self,
        op: JobPermissionLevels,
        target: Optional[JobProxy] = None,
        target_cls: Optional[Type[jobs.ManagedJobBase]] = None,
        register_permission_level: Optional[JobPermissionLevels] = None,
    ) -> bool:
        return self.__mgr._verify_permissions(
            self.__j,
            op,
            target=target if target is not None else target,
            target_cls=target_cls,
            register_permission_level=register_permission_level,
            raise_exceptions=False,
        )

    def register_job_class(
        self, cls: Type[jobs.ManagedJobBase], permission_level: JobPermissionLevels
    ):
        return self.__mgr.register_job_class(
            cls, permission_level=permission_level, _iv=self.__j
        )

    def unregister_job_class(self, cls: Type[jobs.ManagedJobBase]):
        return self.__mgr.unregister_job_class(cls, _iv=self.__j)

    def job_class_is_registered(self, cls: Type[jobs.ManagedJobBase]) -> bool:
        return self.__mgr.job_class_is_registered(cls)

    def create_job(
        self,
        cls: Type[jobs.ManagedJobBase],
        *args,
        **kwargs,
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
        self,
        cls: Type[jobs.ManagedJobBase],
        *args,
        **kwargs,
    ) -> JobProxy:
        return await self.__mgr.create_and_register_job(
            cls,
            *args,
            _return_proxy=True,
            _iv=self.__j,
            **kwargs,
        )

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

    def guard_on_job(
        self,
        job_proxy: JobProxy,
    ):
        return self.__mgr.guard_on_job(job_proxy, _iv=self.__j)

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

    def _self_ungard(self):
        if self.__j._guardian is not None:
            guardian = self.__mgr._get_job_from_proxy(self.__j._guardian)
            self.__mgr.unguard_job(self.__j, _iv=guardian)

    def find_job(
        self,
        *,
        identifier: Union[str, _UnsetType] = None,
        created_at: Union[datetime.datetime, _UnsetType] = None,
    ) -> Optional[JobProxy]:

        return self.__mgr.find_job(
            identifier=identifier,
            created_at=created_at,
            _return_proxy=True,
            _iv=self.__j,
        )

    def find_jobs(
        self,
        *,
        classes: Optional[
            Union[
                Type[jobs.ManagedJobBase],
                tuple[
                    Type[jobs.ManagedJobBase],
                    ...,
                ],
            ]
        ] = tuple(),
        exact_class_match: bool = False,
        creator: Union[JobProxy, _UnsetType] = UNSET,
        created_before: Union[datetime.datetime, _UnsetType] = UNSET,
        created_after: Union[datetime.datetime, _UnsetType] = UNSET,
        permission_level: Union[JobPermissionLevels, _UnsetType] = UNSET,
        above_permission_level: Union[JobPermissionLevels, _UnsetType] = UNSET,
        below_permission_level: Union[
            JobPermissionLevels, _UnsetType
        ] = JobPermissionLevels.SYSTEM,
        alive: Union[bool, _UnsetType] = UNSET,
        is_starting: Union[bool, _UnsetType] = UNSET,
        is_running: Union[bool, _UnsetType] = UNSET,
        is_idling: Union[bool, _UnsetType] = UNSET,
        is_being_guarded: Union[bool, _UnsetType] = UNSET,
        guardian: Union[JobProxy, _UnsetType] = UNSET,
        is_stopping: Union[bool, _UnsetType] = UNSET,
        is_restarting: Union[bool, _UnsetType] = UNSET,
        is_being_killed: Union[bool, _UnsetType] = UNSET,
        is_completing: Union[bool, _UnsetType] = UNSET,
        stopped: Union[bool, _UnsetType] = UNSET,
        query_match_mode: Literal["ANY", "ALL"] = "ALL",
    ) -> tuple[JobProxy]:

        return self.__mgr.find_jobs(
            classes=classes,
            exact_class_match=exact_class_match,
            creator=creator,
            created_before=created_before,
            created_after=created_after,
            permission_level=permission_level,
            above_permission_level=above_permission_level,
            below_permission_level=below_permission_level,
            alive=alive,
            is_starting=is_starting,
            is_running=is_running,
            is_idling=is_idling,
            is_being_guarded=is_being_guarded,
            guardian=guardian,
            is_stopping=is_stopping,
            is_restarting=is_restarting,
            is_being_killed=is_being_killed,
            is_completing=is_completing,
            stopped=stopped,
            query_match_mode=query_match_mode,
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

    def __str__(self):
        return (
            f"<{self.__class__.__name__}>\n{self.__mgr!s}\n"
            f"<{self.__class__.__name__}>"
        )

    def __repr__(self):
        return f"<{self.__class__.__name__} ({self.__mgr!r})>"


for key, obj in _JobProxy.__dict__.items():  # replace placeholder functions
    if isinstance(obj, (FunctionType, type)):
        obj.__qualname__ = f"JobProxy.{obj.__name__}"
        obj.__doc__ = getattr(JobProxy, key).__doc__


for key, obj in _JobManagerProxy.__dict__.items():
    if isinstance(obj, (FunctionType, type)):
        obj.__qualname__ = f"JobManagerProxy.{obj.__name__}"
        obj.__doc__ = getattr(JobManagerProxy, key).__doc__


if not TYPE_CHECKING:
    _JobProxy.__doc__ = JobProxy.__doc__
    _JobProxy.__qualname__ = _JobProxy.__name__ = "JobProxy"
    JobProxy = _JobProxy

    _JobManagerProxy.__doc__ = JobManagerProxy.__doc__
    _JobManagerProxy.__qualname__ = _JobManagerProxy.__name__ = "JobManagerProxy"
    JobManagerProxy = _JobManagerProxy
