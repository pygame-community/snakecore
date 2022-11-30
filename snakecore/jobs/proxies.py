"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file implements proxy objects used by job and job managers
for extra features and encapsulation. 
"""

from asyncio import AbstractEventLoop
from collections import deque
import datetime
import itertools
from types import FunctionType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
    Optional,
    Type,
    TypedDict,
    Union,
    no_type_check,
    overload,
)

from snakecore import events
from snakecore.constants import UNSET, _UnsetType, JobPermissionLevels
from snakecore.constants.enums import JobBoolFlags as JF, JobOps
from snakecore.exceptions import JobIsDone

from . import jobs, manager


class JobProxy:
    __slots__ = (
        "__j",
        "__job_class",
        "__runtime_id",
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
        "_job_bools",
    )

    def __init__(self, job: "jobs.JobBase") -> None:
        self.__j: Optional["jobs.JobBase"] = job
        self._cache_current_job_state()

    def _cache_current_job_state(self):
        job = self.__j
        if job is None:
            return
        self.__job_class = job.__class__
        self.__runtime_id = job._runtime_id
        self.__permission_level = job.permission_level if job.alive() else None
        self.__creator = job.creator
        self._created_at = job.created_at
        self._registered_at = job.registered_at
        self._killed_at = job.killed_at
        self._done = job.done()
        self._initialized_since = job.initialized_since()
        self._alive_since = job.alive_since()
        self._last_stopping_reason = job._last_stopping_reason
        self._done_since = job.done_since()
        self._job_bools = job._bools

        if job.done():
            self.__j = None

    def _eject_from_source(self):
        if self.__j and self.__j.done():
            self._cache_current_job_state()
            self.__j = None

    def _check_if_ejected(self) -> bool:
        if self.__j is None:
            raise JobIsDone("this job object is already done.")

        return False

    @property
    def job_class(self) -> type[jobs.JobBase]:
        return self.__job_class

    @property
    def permission_level(self) -> Optional[JobPermissionLevels]:
        return (
            self.__j.permission_level
            if self.__j is not None
            else self.__permission_level
        )

    @property
    def runtime_id(self) -> str:
        return self.__runtime_id

    @property
    def creator(self) -> Optional["JobProxy"]:
        """`Optional[JobProxy]`: The `JobProxy` of the creator of this job."""
        return self.__creator

    @property
    def guardian(self) -> Optional["JobProxy"]:
        """`Optional[JobProxy]`: The `JobProxy` of the current guardian of this job."""
        return self.__j._guardian if self.__j is not None else None

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def registered_at(self) -> Optional[datetime.datetime]:
        return self._registered_at

    @property
    def killed_at(self) -> Optional[datetime.datetime]:
        return self._killed_at

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

    def is_being_killed(self):
        return self.__j.is_being_killed() if self.__j is not None else False

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
        return self._done_since

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
        return self.__j.await_done(timeout=timeout, cancel_if_killed=cancel_if_killed)  # type: ignore

    def await_unguard(self, timeout: Optional[float] = None):
        self._check_if_ejected()
        return self.__j.await_unguard(timeout=timeout)  # type: ignore

    def get_output_queue_proxy(self):
        self._check_if_ejected()
        return self.__j.get_output_queue_proxy()  # type: ignore

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
        return self.__j.get_output_field(field_name, default=default)  # type: ignore

    def get_output_queue_contents(self, queue_name: str, default=UNSET, /):
        self._check_if_ejected()
        return self.__j.get_output_queue_contents(queue_name, default=default)  # type: ignore

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
        return self.__j.output_field_is_set(field_name)  # type: ignore

    def output_queue_is_empty(self, queue_name: str):
        self._check_if_ejected()
        return self.__j.output_queue_is_empty(queue_name)  # type: ignore

    def await_output_field(self, field_name: str, timeout: Optional[float] = None):
        self._check_if_ejected()
        return self.__j.await_output_field(field_name, timeout=timeout)  # type: ignore

    def await_output_queue_add(
        self,
        queue_name: str,
        timeout: Optional[float] = None,
        cancel_if_cleared: bool = True,
    ):
        self._check_if_ejected()
        return self.__j.await_output_queue_add(  # type: ignore
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
        return self.__j.run_public_method(method_name, *args, **kwargs)  # type: ignore

    def __str__(self):
        return f"<JobProxy ({self.__j!s})>"

    def __repr__(self):
        return f"<JobProxy ({self.__j!r})>"


class _JobOutputQueueProxyDict(TypedDict):
    index: int
    rescue_buffer: Optional[deque[Any]]
    job_output_queue: list[Any]


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

    def __init__(self, job: jobs.JobBase) -> None:
        self.__j = job
        self.__job_class = job.__class__
        self.__job_proxy = job._proxy
        self.__output_queue_names = job.OutputQueues
        job_output_queues = self.__j._output_queues
        self._output_queue_proxy_dict: dict[str, _JobOutputQueueProxyDict] = {
            queue_name: {"index": 0, "rescue_buffer": None, "job_output_queue": job_output_queues[queue_name]}  # type: ignore
            for queue_name in self.__j.OutputQueues.get_all_names()  # type: ignore
        }

        self._default_queue_config = {"use_rescue_buffer": False}

    @property
    def job_proxy(self) -> "JobProxy":
        """`JobProxy`: The job this output queue proxy is pointing to."""
        return self.__job_proxy

    def verify_output_queue_support(
        self, queue_name: str, raise_exceptions=False
    ) -> bool:
        """Verify if a specified output queue name is supported by this
        output queue proxy's job. Disabled output queue names are seen
        as unsupported.

        Parameters
        ----------
        queue_name : str
            The name of the output queue to set.
        raise_exceptions : Optional[bool], optional
            Whether exceptions should be raised. Defaults to False.

        Raises
        ------
        TypeError
            `queue_name` is not a string.
        ValueError
            The specified queue name was marked as disabled.
        LookupError
            The specified queue name is not defined by this
            output queue proxy's job.

        Returns
        -------
        bool
            ``True`` if condition is met, ``False`` otherwise.
        """
        return self.__job_class.verify_output_queue_support(
            queue_name, raise_exceptions=raise_exceptions
        )

    def config_output_queue(
        self, queue_name: str, use_rescue_buffer: Optional[bool] = None
    ) -> None:
        """Configure settings for a specified output queue.

        Parameters
        ----------
        queue_name : str
            The name of the output queue to set.
        use_rescue_buffer : Optional[bool], optional
            Set up a rescue buffer for the specified output queue, which
            automatically collects queue values when a job cleares a
            queue. Defaults to None.
        """
        self.verify_output_queue_support(queue_name, raise_exceptions=True)

        if queue_name not in self._output_queue_proxy_dict:
            self._output_queue_proxy_dict[queue_name] = {
                "index": 0,
                "rescue_buffer": None,
                "job_output_queue": [],
            }

        if use_rescue_buffer:
            self._output_queue_proxy_dict[queue_name]["rescue_buffer"] = deque()
        elif use_rescue_buffer is False:
            self._output_queue_proxy_dict[queue_name]["rescue_buffer"] = None

    def config_output_queue_defaults(
        self, use_rescue_buffer: Optional[bool] = None
    ) -> None:
        """Configure default settings for output queues.

        Parameters
        ----------
        use_rescue_buffer : Optional[bool], optional
            Set up a rescue buffer for an output queue, which automatically collects
            queue values when a job cleares a queue. Defaults to None.
        """

        if use_rescue_buffer is not None:
            self._default_queue_config["use_rescue_buffer"] = bool(use_rescue_buffer)

    def _output_queue_clear_alert(self, queue_name: str) -> None:
        # Alerts OutputQueueProxy objects that their job
        # object is about to clear its output queues.
        queue_dict = self._output_queue_proxy_dict[queue_name]

        if queue_dict["rescue_buffer"] is not None:
            queue_dict["rescue_buffer"].extend(queue_dict["job_output_queue"])

        queue_dict["index"] = 0

    def _new_output_queue_alert(self, queue_name: str, queue_dict: list) -> None:
        if queue_name not in self._output_queue_proxy_dict:
            self._output_queue_proxy_dict[queue_name] = {
                "index": 0,
                "rescue_buffer": None,
                "job_output_queue": queue_dict,
            }
        else:
            self._output_queue_proxy_dict[queue_name]["job_output_queue"] = queue_dict

        if self._default_queue_config["use_rescue_buffer"]:
            self._output_queue_proxy_dict[queue_name]["rescue_buffer"] = deque()

    @overload
    def pop_output_queue(self, queue_name: str, amount: Optional[int] = None) -> Any:
        ...

    @overload
    def pop_output_queue(
        self, queue_name: str, amount: Optional[int] = None, all_values: bool = False
    ) -> list[Any]:
        ...

    def pop_output_queue(
        self, queue_name: str, amount: Optional[int] = None, all_values: bool = False
    ) -> Union[list[Any], Any]:
        """Get the oldest or a list of the specified amount of oldest entries in the
        specified output queue.

        Parameters
        ----------
        queue_name : str
            The name of the target output queue.
        amount : Optional[int], optional
            The maximum amount of entries to return.
            If there are less entries available than this amount, only
            Defaults to None.
        all_entries : bool, optional
            Whether all entries should be released at once. Defaults to False.

        Returns
        -------
        Union[list[Any], Any]
            The oldest value, or a list of the specified amount of them, if possible.

        Raises
        ------
        LookupError
            The target queue is exhausted, or empty.
        """

        self.verify_output_queue_support(queue_name, raise_exceptions=True)

        queue_dict = self._output_queue_proxy_dict[queue_name]

        if not all_values and amount is None:

            if queue_dict["rescue_buffer"]:
                return queue_dict["rescue_buffer"].popleft()
            elif queue_dict["job_output_queue"]:
                if queue_dict["index"] < len(queue_dict["job_output_queue"]):
                    output = queue_dict["job_output_queue"][queue_dict["index"]]
                    queue_dict["index"] += 1
                    return output

                raise LookupError(
                    f"the target queue with name '{queue_name}' is exhausted"
                )

            else:
                raise LookupError(f"the target queue with name '{queue_name}' is empty")

        elif all_values or isinstance(amount, int) and amount > 0:
            entries = []

            for _ in itertools.count() if all_values else range(amount):  # type: ignore
                if queue_dict["rescue_buffer"]:
                    entries.append(queue_dict["rescue_buffer"].popleft())  # type: ignore
                elif queue_dict["job_output_queue"]:
                    if queue_dict["index"] < len(queue_dict["job_output_queue"]):
                        entries.append(
                            queue_dict["job_output_queue"][queue_dict["index"]]
                        )
                        queue_dict["index"] += 1
                    else:
                        break
                else:
                    break

            return entries

        raise TypeError(f"argument 'amount' must be None or a positive integer")

    def output_queue_is_empty(
        self, queue_name: str, ignore_rescue_buffer: bool = False
    ) -> bool:
        """Whether the specified output queue is empty.

        Parameters
        ----------
        queue_name : str
            The name of the target output queue.
        ignore_rescue_buffer : bool
            Whether the contents of the rescue buffer
            should be considered as well. Defaults to False.

        Returns
        -------
        bool
            ``True`` if condition is met, ``False`` otherwise.

        Raises
        ------
        TypeError
            `queue_name` is not a string.
        LookupError
            The specified queue name is not defined by this output
            queue proxy's job.
        """

        self.verify_output_queue_support(queue_name, raise_exceptions=True)

        if ignore_rescue_buffer:
            return not self._output_queue_proxy_dict[queue_name]["job_output_queue"]

        queue_dict = self._output_queue_proxy_dict[queue_name]
        return not queue_dict["rescue_buffer"] and not queue_dict["job_output_queue"]

    def output_queue_is_exhausted(self, queue_name: str) -> bool:
        """Whether the specified output queue is exhausted,
        meaning that no new values are available.

        Parameters
        ----------
        queue_name : str
            The name of the target output queue.
        ignore_rescue_buffer : bool
            Whether the contents of the rescue buffer should be considered as well.
            Defaults to False.

        Returns
        -------
        bool
            ``True`` if condition is met, ``False`` otherwise.

        Raises
        ------
            TypeError
            `queue_name` is not a string.
            LookupError
            The specified queue name is not defined by
              this output queue proxy's job.
        """

        self.verify_output_queue_support(queue_name, raise_exceptions=True)
        queue_dict = self._output_queue_proxy_dict.get(queue_name, UNSET)

        if queue_dict is UNSET:
            return False

        if queue_dict["job_output_queue"] and queue_dict["index"] >= len(
            queue_dict["job_output_queue"]
        ):
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

        Parameters
        ----------
        timeout : float, optional
            The maximum amount of time to wait in seconds. Defaults to None.
        cancel_if_cleared : bool
            Whether `asyncio.CancelledError` should be raised if the output queue is
            cleared. If set to `False`, `UNSET` will be the result of the coroutine.
            Defaults to False.

        Raises
        ------
        TypeError
            Output fields aren't supported for this job, or `field_name` is not a string.
        LookupError
            The specified field name is not defined by this job
        JobIsDone
            This job object is already done.
        asyncio.TimeoutError
            The timeout was exceeded.
        asyncio.CancelledError:
            The job was killed, or the output queue was cleared.

        Returns
        -------
            Coroutine: A coroutine that evaluates to the most recent output queue
              value, or `UNSET` if the queue is cleared.
        """

        return self.__j.await_output_queue_add(
            queue_name, timeout=timeout, cancel_if_cleared=cancel_if_cleared
        )


class JobManagerProxy:
    __slots__ = (
        "__mgr",
        "__j",
        "__job_class",
        "__runtime_id",
        "__permission_level",
        "__creator",
        "_created_at",
        "_job_stop_timeout",
        "_registered_at",
        "_done_since",
        "_initialized_since",
        "_alive_since",
        "_last_stopping_reason",
        "_killed_at",
        "_completed_at",
        "_done",
        "_job_bools",
    )

    def __init__(self, mgr: manager.JobManager, job: jobs.JobBase) -> None:
        self.__mgr: manager.JobManager = mgr
        self.__j: jobs.JobBase = job
        self._job_stop_timeout = None

    def is_running(self):
        return self.__mgr.is_running()

    def _check_if_ejected(self) -> bool:
        if not (self.__j and self.__mgr):
            raise RuntimeError("This job manager proxy has been invalidated.")
        return False

    @property
    def manager_job(self) -> JobProxy:
        """The job manager's representative job."""
        self._check_if_ejected()
        return self.__mgr._manager_job._proxy  # type: ignore

    @property
    def _loop(self) -> AbstractEventLoop:
        self._check_if_ejected()
        return self.__mgr._loop

    def get_job_stop_timeout(self) -> Optional[float]:
        """`Optional[float]`: Get the maximum time period in seconds for the job object managed
        by this `JobManagerProxy` to stop when halted from the
        job manager, either due to stopping, restarted or killed.
        By default, this method returns the global job timeout set for the
        current job manager, but that can be overridden with a custom
        timeout when trying to stop the job object.
        """
        self._check_if_ejected()
        return (
            self._job_stop_timeout
            if self._job_stop_timeout
            else self.__mgr.get_global_job_stop_timeout()
        )

    def verify_permissions(
        self,
        op: JobOps,
        target: Optional[JobProxy] = None,
        target_cls: Optional[type[jobs.ManagedJobBase]] = None,
        register_permission_level: Optional[JobPermissionLevels] = None,
    ) -> bool:
        """Check if the permissions of the job of this `JobManagerProxy` object
        are sufficient for carrying out the specified operation on the given input.

        Parameters
        ----------
        op : JobOps
            The operation. Must be one of the operations defined in the `JobOps`
            class namespace.
        target : Optional[JobProxy], optional
            The target job's proxy for an operation. Defaults to None.
        target_cls : Optional[type[ManagedJobBase]], optional
            The target job class for an operation. Defaults to None.

        Returns
        -------
        bool
            The result of the permission check.
        """
        self._check_if_ejected()
        return self.__mgr._verify_permissions(
            self.__j,  # type: ignore
            op,
            target=target if target is not None else target,
            target_cls=target_cls,
            register_permission_level=register_permission_level,
            raise_exceptions=False,
        )

    def get_job_permission_level(self, job_proxy: JobProxy) -> JobPermissionLevels:
        self._check_if_ejected()
        return self.__mgr.get_job_permission_level(job_proxy)

    def create_job(
        self,
        cls: type[jobs.ManagedJobBase],
        *args,
        **kwargs,
    ):
        self._check_if_ejected()
        return self.__mgr.create_job(
            cls, *args, _return_proxy=True, _iv=self.__j, **kwargs
        )

    async def initialize_job(self, job_proxy: JobProxy, raise_exceptions: bool = True):
        self._check_if_ejected()
        return await self.__mgr.initialize_job(
            job_proxy, raise_exceptions=raise_exceptions
        )

    async def register_job(self, job_proxy: JobProxy):
        self._check_if_ejected()
        return await self.__mgr.register_job(job_proxy, _iv=self.__j)  # type: ignore

    async def create_and_register_job(
        self,
        cls: type[jobs.ManagedJobBase],
        *args,
        **kwargs,
    ) -> JobProxy:
        self._check_if_ejected()
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
        self._check_if_ejected()
        job = self.__mgr._get_job_from_proxy(job_proxy)

        if job is self.__j:
            job.restart()

        return self.__mgr.restart_job(
            job_proxy, stopping_timeout=stopping_timeout, _iv=self.__j  # type: ignore
        )

    def start_job(
        self,
        job_proxy: JobProxy,
    ):
        self._check_if_ejected()
        return self.__mgr.start_job(job_proxy, _iv=self.__j)  # type: ignore

    def stop_job(
        self,
        job_proxy: JobProxy,
        stopping_timeout: Optional[float] = None,
        force=False,
    ):
        self._check_if_ejected()
        job = self.__mgr._get_job_from_proxy(job_proxy)

        if job is self.__j:
            job.stop(force=force)

        return self.__mgr.stop_job(
            job_proxy, stopping_timeout=stopping_timeout, force=force, _iv=self.__j
        )  # type: ignore

    def kill_job(self, job_proxy: JobProxy, stopping_timeout: Optional[float] = None):
        self._check_if_ejected()
        job = self.__mgr._get_job_from_proxy(job_proxy)

        if job is self.__j:
            job.kill()

        return self.__mgr.kill_job(
            job_proxy, stopping_timeout=stopping_timeout, _iv=self.__j  # type: ignore
        )

    def guard_job(
        self,
        job_proxy: JobProxy,
    ):
        self._check_if_ejected()
        return self.__mgr.guard_job(job_proxy, _iv=self.__j)  # type: ignore

    def unguard_job(
        self,
        job_proxy: JobProxy,
    ):
        self._check_if_ejected()
        return self.__mgr.unguard_job(job_proxy, _iv=self.__j)  # type: ignore

    def guard_on_job(
        self,
        job_proxy: JobProxy,
    ):
        return self.__mgr.guard_on_job(job_proxy, _iv=self.__j)  # type: ignore

    def _eject(self):
        """Irreversible job death. Do not call this method without ensuring that
        a job is killed.
        """
        self._check_if_ejected()
        if not self.__j.alive():
            self.__mgr._remove_job(self.__j)  # type: ignore
            self.__j._manager = None
            self.__j = None  # type: ignore
            self.__mgr = None  # type: ignore

    def _self_ungard(self):
        self._check_if_ejected()
        if self.__j._guardian is not None:
            guardian = self.__mgr._get_job_from_proxy(self.__j._guardian)
            self.__mgr.unguard_job(self.__j, _iv=guardian)  # type: ignore

    def find_job(
        self,
        *,
        identifier: Optional[str] = None,
        created_at: Optional[datetime.datetime] = None,
    ) -> Optional[JobProxy]:
        self._check_if_ejected()
        return self.__mgr.find_job(
            identifier=identifier,
            created_at=created_at,
            _return_proxy=True,
        )  # type: ignore

    def find_jobs(  # type: ignore
        self,
        *,
        classes: Optional[
            Union[
                type[jobs.ManagedJobBase],
                tuple[
                    type[jobs.ManagedJobBase],
                    ...,
                ],
            ]
        ] = tuple(),
        exact_class_match: bool = False,
        creator: JobProxy = UNSET,
        created_before: datetime.datetime = UNSET,
        created_after: datetime.datetime = UNSET,
        permission_level: JobPermissionLevels = UNSET,
        above_permission_level: JobPermissionLevels = UNSET,
        below_permission_level: JobPermissionLevels = UNSET,
        alive: bool = UNSET,
        is_starting: bool = UNSET,
        is_running: bool = UNSET,
        is_idling: bool = UNSET,
        is_being_guarded: bool = UNSET,
        guardian: JobProxy = UNSET,
        is_stopping: bool = UNSET,
        is_restarting: bool = UNSET,
        is_being_killed: bool = UNSET,
        is_completing: bool = UNSET,
        stopped: bool = UNSET,
        query_match_mode: Literal["ANY", "ALL"] = "ALL",
    ) -> tuple[JobProxy, ...]:
        self._check_if_ejected()
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
        )  # type: ignore

    def wait_for_event(
        self,
        *event_types: type[events.BaseEvent],
        check: Optional[Callable[[events.BaseEvent], bool]] = None,
        timeout: Optional[float] = None,
    ):
        self._check_if_ejected()
        return self.__mgr.wait_for_event(
            *event_types,
            check=check,
            timeout=timeout,
            _iv=self.__j,  # type: ignore
        )

    def dispatch_event(self, event: events.BaseEvent):
        event._dispatcher = self.__j._proxy
        return self.__mgr.dispatch_event(event, _iv=self.__j)  # type: ignore

    def has_job(self, job_proxy: JobProxy):
        """Whether a specific job object is currently in this
        job manager.

        Parameters
        ----------
            job_proxy (JobProxy): The target job's proxy.

        Returns
        -------
            bool: True/False
        """
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
