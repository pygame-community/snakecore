"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file implements a job manager class for running and managing job objects
at runtime. 
"""

import asyncio
from collections import ChainMap
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from ctypes.wintypes import tagRECT
import datetime
import pickle
import random
import time
from typing import (
    Any,
    Callable,
    Coroutine,
    Literal,
    Optional,
    Type,
    Union,
)

import discord
from snakecore.constants import UNSET, _UnsetType, JobBoolFlags as JF

from snakecore.constants.enums import (
    _JOB_OPS_PRES_CONT,
    JobPermissionLevels,
    JobOps,
)
from snakecore.exceptions import (
    JobException,
    JobInitializationError,
    JobIsDone,
    JobIsGuarded,
    JobNotAlive,
    JobPermissionError,
    JobStateError,
)
from snakecore.utils import FastChainMap
from snakecore import events
from . import jobs, loops


class JobManager:
    """The job manager for all interval and event based jobs.
    It acts as a container for interval and event job objects,
    whilst also being responsible dispatching events to event job objects.
    Each of the jobs that a job manager contains can use a proxy to
    register new job objects that they instantiate at runtime.
    """

    def __init__(
        self,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        global_job_timeout: Optional[float] = None,
        default_job_permission_level: JobPermissionLevels = JobPermissionLevels.MEDIUM,
    ):
        """Create a new job manager instance.

        Args:
            loop (Optional[asyncio.AbstractEventLoop], optional): The event loop to use for this job
              manager and all of its jobs. Defaults to None.
            global_job_timeout (Optional[float], optional): The default global job timeout
              in seconds. Defaults to None.
            global_job_timeout (JobPermissionLevels, optional): The default job permission level
            for any job. Defaults to `MEDIUM`.
        """
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()

        self._created_at = datetime.datetime.now(datetime.timezone.utc)
        self._runtime_id = (
            f"{id(self)}-{int(self._created_at.timestamp()*1_000_000_000)}"
        )

        self._loop = loop
        self._event_job_ids = {}
        self._job_class_data: dict[str, dict[str, Any]] = {}
        self._default_job_permission_level: Optional[
            JobPermissionLevels
        ] = default_job_permission_level
        self._job_id_map: dict[
            str, tuple[jobs.ManagedJobBase, JobPermissionLevels]
        ] = {}
        self._manager_job = None
        self._event_waiting_queues = {}
        self._initialized = False
        self._is_running = False

        if global_job_timeout:
            global_job_timeout = float(global_job_timeout)

        self._global_job_stop_timeout = global_job_timeout

    def _check_init(self):
        if not self._initialized:
            raise RuntimeError("this job manager is not initialized")

    def _check_running(self):
        if not self._is_running:
            raise RuntimeError("this job manager is not running")

    def _check_init_and_running(self):
        if not self._initialized:
            raise RuntimeError("this job manager is not initialized")

        elif not self._is_running:
            raise RuntimeError("this job manager is not running")

    def _check_manager_misuse(self):
        current_job: Union[jobs.ManagedJobBase, int] = loops._current_job.get(
            (_rand := random.getrandbits(4))
        )

        if current_job is not _rand:
            if not isinstance(current_job, jobs.ManagedJobBase):
                raise RuntimeError(
                    "could not determine the current job of this execution context"
                )
            elif current_job._runtime_id in self._job_id_map:
                raise JobPermissionError(
                    "explicitly using job managers from within their jobs is not allowed"
                )

        return True

    @property
    def identifier(self) -> str:
        return self._runtime_id

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the event loop of this job manager. This is useful
        in situations where a former event loop was closed.

        Args:
            loop (asyncio.AbstractEventLoop): A new event loop this
              job manager is meant to use.

        Raises:
            TypeError: Invalid object given as input.
            RuntimeError: The currently used event loop is not closed.
        """
        if not isinstance(loop, asyncio.AbstractEventLoop):
            raise TypeError(
                "invalid event loop, must be a subclass of 'asyncio.AbstractEventLoop'"
            ) from None
        elif not self._loop.is_closed():
            raise RuntimeError("the currently used event loop is not yet closed")
        self._loop = loop

    def is_running(self) -> bool:
        """Whether this job manager is currently running, meaning that it has been
        initialized and has not yet quit.

        Returns:
            bool: True/False
        """
        return self._is_running

    def initialized(self) -> bool:
        """Whether this job manager was initialized.
        This can return True even if a job manager
        has quit. To check if a job manager is running,
        use the `is_running()` method.

        Returns:
            bool: True/False
        """
        return self._initialized

    def get_global_job_stop_timeout(self) -> Optional[float]:
        """Get the maximum time period in seconds for job objects to stop
        when halted from this manager, either due to stopping,
        restarted or killed.

        Returns:
            float: The timeout in seconds.
            None: No timeout is currently set.
        """
        return self._global_job_stop_timeout

    def set_global_job_stop_timeout(self, timeout: Optional[float]):
        """Set the maximum time period in seconds for job objects to stop
        when halted from this manager, either due to stopping,
        restarted or killed.

        Args:
            timeout (Optional[float]): The timeout in seconds,
            or None to clear any previous timeout.
        """

        if timeout:
            timeout = float(timeout)

        self._check_manager_misuse()
        self._global_job_stop_timeout = timeout

    def get_default_job_permission_level(self) -> Optional[JobPermissionLevels]:
        return self._default_job_permission_level

    def set_default_job_permission_level(self, permission_level: JobPermissionLevels):
        if not isinstance(permission_level, JobPermissionLevels):
            raise TypeError(
                "argument 'permission_level' must be a usable enum value from the 'JobPermissionLevels' enum"
            )
        elif permission_level >= JobPermissionLevels.SYSTEM:
            raise ValueError(
                "argument 'permission_level' must be a usable enum value from the 'JobPermissionLevels' enum"
            )

        self._default_job_permission_level = permission_level

    async def initialize(self) -> bool:
        """Initialize this job manager, if it hasn't yet been initialized.

        Returns:
            bool: Whether the call was successful.
        """

        if not self._initialized:
            self._initialized = True
            self._is_running = True
            self._job_class_data[jobs.JobManagerJob._RUNTIME_ID] = {
                "class": jobs.JobManagerJob,
                "instances": {},
            }

            self._manager_job = self._get_job_from_proxy(
                await self.create_and_register_job(
                    jobs.JobManagerJob, with_permission_level=JobPermissionLevels.SYSTEM
                )
            )
            self._manager_job._creator = self._manager_job._proxy
            return True

        return False

    def _verify_permissions(
        self,
        invoker: jobs.ManagedJobBase,
        op: JobOps,
        target: Optional[Union[jobs.ManagedJobBase, "proxies.JobProxy"]] = None,
        register_permission_level: Optional[JobPermissionLevels] = None,
        target_cls: Optional[Type[jobs.ManagedJobBase]] = None,
        raise_exceptions=True,
    ) -> bool:

        if (
            isinstance(invoker, jobs.JobManagerJob)
            and invoker._runtime_id in self._job_id_map
        ):
            return True

        if target is not None:
            target_cls = target.__class__
            if isinstance(target, proxies.JobProxy):
                target = self._get_job_from_proxy(target)

            elif not isinstance(target, jobs.ManagedJobBase):
                raise TypeError(
                    "argument 'target' must be a an instance of a job object or a job proxy"
                )

            elif isinstance(target, jobs.JobManagerJob):
                raise JobPermissionError(
                    "argument 'target' cannot be a JobManagerJob instance"
                )

        if target_cls is not None:
            if issubclass(target_cls, jobs.JobManagerJob):
                raise JobPermissionError(
                    "JobManagerJob cannot be manually instantiated"
                )

            elif register_permission_level is not None and (
                not isinstance(register_permission_level, JobPermissionLevels)
                or register_permission_level >= JobPermissionLevels.SYSTEM
            ):
                raise TypeError(
                    "argument 'with_permission_level' must be a usable enum value "
                    "defined in the 'JobPermissionLevels' enum"
                )

        invoker_permission_level = self._job_id_map[invoker._runtime_id][1]

        if not isinstance(op, JobOps):
            raise TypeError(
                "argument 'op' must be an enum value defined in the 'JobOps' enum"
            )

        elif (
            op is JobOps.CUSTOM_EVENT_DISPATCH
            and invoker_permission_level < JobPermissionLevels.MEDIUM
        ):
            if raise_exceptions:
                raise JobPermissionError(
                    f"insufficient permission level of {invoker._runtime_id} "
                    f"({invoker_permission_level.name}) "
                    "for dispatching custom events to job objects "
                )
            return False

        elif (
            op is JobOps.EVENT_DISPATCH
            and invoker_permission_level < JobPermissionLevels.HIGH
        ):
            if raise_exceptions:
                raise JobPermissionError(
                    f"insufficient permission level of {invoker._runtime_id} "
                    f"({invoker_permission_level.name}) "
                    "for dispatching non-custom events to job objects "
                )
            return False

        elif op in (
            JobOps.CREATE,
            JobOps.INITIALIZE,
        ):
            if invoker_permission_level < JobPermissionLevels.MEDIUM:
                if raise_exceptions:
                    raise JobPermissionError(
                        f"insufficient permission level of {invoker._runtime_id} "
                        f"({invoker_permission_level.name}) "
                        f"for {_JOB_OPS_PRES_CONT[op.name].lower()} job objects"
                    )
                return False

        elif op is JobOps.REGISTER:

            if register_permission_level is None:
                raise TypeError(
                    "argument 'with_permission_level'"
                    " cannot be None if enum 'op' is 'REGISTER'"
                )

            if invoker_permission_level < JobPermissionLevels.MEDIUM:
                if raise_exceptions:
                    raise JobPermissionError(
                        f"insufficient permission level of {invoker._runtime_id} "
                        f"({invoker_permission_level.name}) "
                        f"for {_JOB_OPS_PRES_CONT[op.name].lower()} job objects"
                    )
                return False

            elif (
                invoker_permission_level is JobPermissionLevels.MEDIUM
                and register_permission_level >= JobPermissionLevels.MEDIUM
            ):
                if raise_exceptions:
                    raise JobPermissionError(
                        f"insufficient permission level of {invoker._runtime_id} "
                        f"({invoker_permission_level.name}) "
                        f"for {_JOB_OPS_PRES_CONT[op.name].lower()} job objects"
                        f"with the permission level '{register_permission_level.name}'"
                    )
                return False

            elif (
                invoker_permission_level is JobPermissionLevels.HIGH
                and register_permission_level > JobPermissionLevels.HIGH
            ):
                if raise_exceptions:
                    raise JobPermissionError(
                        f"insufficient permission level of {invoker._runtime_id} "
                        f"({invoker_permission_level.name}) "
                        f"for {_JOB_OPS_PRES_CONT[op.name].lower()} job objects"
                        f"with the permission level '{register_permission_level.name}'"
                    )
                return False

        elif op in (JobOps.GUARD, JobOps.UNGUARD):
            if target is None:
                raise TypeError(
                    "argument 'target'"
                    "cannot be None if enum 'op' is 'START', "
                    "'RESTART', 'STOP' 'KILL', 'GUARD' or 'UNGUARD'"
                )

            if invoker_permission_level < JobPermissionLevels.MEDIUM:
                if raise_exceptions:
                    raise JobPermissionError(
                        f"insufficient permission level of {invoker._runtime_id} "
                        f"({invoker_permission_level.name}) "
                        f"for {_JOB_OPS_PRES_CONT[op.name].lower()} job objects"
                    )
                return False

            elif invoker_permission_level is JobPermissionLevels.MEDIUM:
                if target._creator is not invoker._proxy:
                    if raise_exceptions:
                        raise JobPermissionError(
                            f"insufficient permission level of '{invoker._runtime_id}' "
                            f"({invoker_permission_level.name}) "
                            f"for {_JOB_OPS_PRES_CONT[op.name].lower()} "
                            f"job objects of the specified class '{target_cls.__qualname__}' "
                            "its instance did not create."
                        )
                    return False

            elif invoker_permission_level is JobPermissionLevels.HIGH:
                if target_permission_level > JobPermissionLevels.HIGH:
                    if raise_exceptions:
                        raise JobPermissionError(
                            f"insufficient permission level of '{invoker._runtime_id}' "
                            f"({invoker_permission_level.name}) "
                            f"for {_JOB_OPS_PRES_CONT[op.name].lower()} "
                            f"job objects of the specified class '{target_cls.__qualname__}' "
                            f"with permission level '{target_permission_level.name}'"
                        )
                    return False

        elif op in (
            JobOps.START,
            JobOps.RESTART,
            JobOps.STOP,
            JobOps.KILL,
        ):
            if target is None:
                raise TypeError(
                    "argument 'target'"
                    " cannot be None if enum 'op' is 'START',"
                    " 'RESTART', 'STOP' 'KILL' or 'GUARD'"
                )

            target_permission_level = self._job_id_map[target._runtime_id][1]

            if invoker_permission_level < JobPermissionLevels.MEDIUM:
                raise JobPermissionError(
                    f"insufficient permission level of {invoker._runtime_id} "
                    f"({invoker_permission_level.name}) "
                    f"for {_JOB_OPS_PRES_CONT[op.name].lower()} job objects "
                )

            elif invoker_permission_level is JobPermissionLevels.MEDIUM:
                if (
                    target_permission_level < JobPermissionLevels.MEDIUM
                    and target._creator is not invoker._proxy
                ):
                    if raise_exceptions:
                        raise JobPermissionError(
                            f"insufficient permission level of '{invoker._runtime_id}' "
                            f"({invoker_permission_level.name}) "
                            f"for {_JOB_OPS_PRES_CONT[op.name].lower()} "
                            f"job objects of the specified class '{target_cls.__qualname__}' "
                            f"with permission level '{target_permission_level.name}' "
                            "that it did not create."
                        )
                    return False

                elif target_permission_level >= JobPermissionLevels.MEDIUM:
                    if raise_exceptions:
                        raise JobPermissionError(
                            f"insufficient permission level of '{invoker._runtime_id}' "
                            f"({invoker_permission_level.name}) "
                            f"for {_JOB_OPS_PRES_CONT[op.name].lower()} "
                            f"job objects of the specified class '{target_cls.__qualname__}' "
                            f"with permission level '{target_permission_level.name}'"
                        )
                    return False

            elif invoker_permission_level is JobPermissionLevels.HIGH:
                if target_permission_level >= JobPermissionLevels.HIGH:
                    if raise_exceptions:
                        raise JobPermissionError(
                            f"insufficient permission level of '{invoker._runtime_id}' "
                            f"({invoker_permission_level.name}) "
                            f"for {_JOB_OPS_PRES_CONT[op.name].lower()} "
                            f"job objects of the specified class '{target_cls.__qualname__}' "
                            f"with permission level '{target_permission_level.name}'"
                        )
                    return False
        return True

    def create_job(
        self,
        cls: Type[jobs.ManagedJobBase],
        *args,
        _return_proxy=True,
        _iv: Optional[jobs.ManagedJobBase] = None,
        **kwargs,
    ) -> Union[jobs.ManagedJobBase, "proxies.JobProxy"]:
        """Create an instance of a job class and return it.

        Args:
            cls (Type[jobs.ManagedJobBase]):
               The job class to instantiate a job object from.

        Returns:
            JobProxy: A job proxy object.

        Raises:
            RuntimeError: This job manager object is not initialized.
        """

        self._check_init_and_running()

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.CREATE, target_cls=cls)
        else:
            self._check_manager_misuse()
            _iv = self._manager_job

        job = cls(*args, **kwargs)
        job._manager = proxies.JobManagerProxy(self, job)
        job._creator = _iv._proxy if _iv is not None else None
        proxy = job._proxy

        if _return_proxy:
            return proxy
        return job

    def _get_job_from_proxy(self, job_proxy: "proxies.JobProxy") -> jobs.ManagedJobBase:
        try:
            job = job_proxy._JobProxy__j
        except AttributeError:
            raise TypeError("invalid job proxy") from None
        return job

    async def initialize_job(
        self,
        job_proxy: "proxies.JobProxy",
        raise_exceptions: bool = True,
        _iv: Optional[jobs.ManagedJobBase] = None,
    ) -> bool:
        """Initialize a job object.

        Args:
            job_proxy (JobProxy): The proxy to the job object.
            raise_exceptions (bool, optional): Whether exceptions should be raised.
              Defaults to True.

        Returns:
            bool: Whether the initialization attempt was successful.

        Raises:
            JobStateError: The job given was already initialized.
            JobIsGuarded: The job given is being guarded by another job.
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.INITIALIZE, target=job)
        else:
            self._check_manager_misuse()
            _iv = self._manager_job

        if job._guardian is not None and _iv._proxy is not job._guardian:
            raise JobIsGuarded(
                "the given target job object is being guarded by another job"
            ) from None

        if not job._bools & JF.INITIALIZED:
            try:
                await job._INITIALIZE_EXTERNAL()
                job._bools |= JF.INITIALIZED  # True

            except Exception as e:
                if raise_exceptions:
                    raise JobInitializationError(
                        "job initialization failed due to an error: "
                        f"{e.__class__.__name__}: {e}"
                    ) from e
        else:
            if raise_exceptions:
                raise JobStateError("this job object is already initialized") from None
            else:
                return False

        return bool(job._bools & JF.INITIALIZED)

    async def register_job(
        self,
        job_proxy: "proxies.JobProxy",
        with_permission_level: Optional[JobPermissionLevels] = None,
        start: bool = True,
        _iv: Optional[jobs.ManagedJobBase] = None,
    ):
        """Register a job object to this JobManager,
        while initializing it if necessary.

        Args:
            job (JobProxy): The job object to be registered.
            start (bool): Whether the given job object should start automatically
              upon registration.
            with_permission_level (Optional[JobPermissionLevels], optional)
              The permission level under which the job object should be registered.
              If set to `None`, the default job manager permission level will be
              chosen. Defaults to None.

        Raises:
            JobIsDone: The given job object is already done.
            JobStateError: Invalid job state for registration.
            JobIsGuarded: The job given is being guarded by another job.
            JobException: job-specific errors preventing registration.
            RuntimeError: This job manager object is not initialized.
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        if with_permission_level is None:
            with_permission_level = self._default_job_permission_level

        elif not isinstance(with_permission_level, JobPermissionLevels):
            raise TypeError(
                "argument 'with_permission_level' must be None or a usable enum value "
                "defined in the 'JobPermissionLevels' enum"
            )

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(
                _iv,
                op=JobOps.REGISTER,
                target=job,
                register_permission_level=with_permission_level,
            )
        else:
            self._check_manager_misuse()
            _iv = self._manager_job

        if job._guardian is not None and _iv._proxy is not job._guardian:
            raise JobIsGuarded(
                "the given target job object is being guarded by another job"
            ) from None

        if job._bools & (JF.KILLED | JF.COMPLETED):
            raise JobIsDone("The given job object is already done")

        if not job._bools & JF.INITIALIZED:
            await self.initialize_job(job._proxy, _iv=self._manager_job)

        if (
            job.__class__._SINGLE
            and job.__class__._RUNTIME_ID in self._job_class_data
            and len(self._job_class_data[job.__class__._RUNTIME_ID]["instances"]) > 0
        ):
            raise JobException(
                "cannot have more than one instance of a"
                f" '{job.__class__.__qualname__}' job registered at a time."
            )

        self._add_job(job, with_permission_level=with_permission_level, start=start)
        job._registered_at_ts = time.time()

    async def create_and_register_job(
        self,
        cls: Type[jobs.ManagedJobBase],
        *args,
        with_permission_level: Optional[JobPermissionLevels] = None,
        _return_proxy: bool = True,
        _iv: Optional[jobs.ManagedJobBase] = None,
        **kwargs,
    ) -> "proxies.JobProxy":
        """Create an instance of a job class, register it to this job manager,
        and start it.

        Args:
            cls (Type[jobs.ManagedJobBase]): The job class to instantiate.
            *args (Any): Positional arguments for the job constructor.
            with_permission_level (Optional[JobPermissionLevels], optional)
              The permission level under which the job object should be registered.
              If set to `None`, the default job manager permission level will be
              chosen. Defaults to None.
            **kwargs (Any): Keyword arguments for the job constructor
              (excluding `with_permission_level`).

        Returns:
            JobProxy: A job proxy object.
        """
        j = self.create_job(cls, *args, _return_proxy=False, _iv=_iv, **kwargs)
        await self.register_job(
            j._proxy, start=True, with_permission_level=with_permission_level, _iv=_iv
        )
        if _return_proxy:
            return j._proxy
        return j

    def __iter__(self):
        return iter(job._proxy for job, _ in self._job_id_map.values())

    def _add_job(
        self,
        job: jobs.ManagedJobBase,
        with_permission_level: JobPermissionLevels,
        start: bool = True,
    ):
        """THIS METHOD IS ONLY MEANT FOR INTERNAL USE BY THIS CLASS.

        Add the given job object to this job manager, and start it.

        Args:
            job: jobs.ManagedJobBase:
                The job to add.
            with_permission_level (JobPermissionLevels)
              The permission level under which the job object should be added.
            start (bool, optional):
                Whether a given interval job object should start immediately
                after being added. Defaults to True.
        Raises:
            TypeError: An invalid object was given as a job.
            RuntimeError:
                A job was given that was already present in the
                manager, or this job manager has not been initialized.
        """

        if job._runtime_id in self._job_id_map:
            raise RuntimeError(
                "the given job is already present in this manager"
            ) from None

        if isinstance(job, jobs.EventJobMixin):
            for ev_type in job.EVENTS:
                if ev_type._RUNTIME_ID not in self._event_job_ids:
                    self._event_job_ids[ev_type._RUNTIME_ID] = set()
                self._event_job_ids[ev_type._RUNTIME_ID].add(job._runtime_id)

        elif not isinstance(job, jobs.ManagedJobBase):
            raise TypeError(
                "expected an instance of a ManagedJobBase subclass, "
                f"not {job.__class__.__qualname__}"
            ) from None

        if job.__class__._RUNTIME_ID not in self._job_class_data:
            self._job_class_data[job.__class__._RUNTIME_ID] = {
                "class": job.__class__,
                "instances": {},
            }

        self._job_class_data[job.__class__._RUNTIME_ID]["instances"][
            job._runtime_id
        ] = (job, with_permission_level)

        self._job_id_map[job._runtime_id] = (job, with_permission_level)

        job._permission_level = with_permission_level

        if start:
            job._START_EXTERNAL()

    def _remove_job(self, job: jobs.ManagedJobBase):
        """THIS METHOD IS ONLY MEANT FOR INTERNAL USE BY THIS CLASS and job manager
        proxies.

        Remove the given job object from this job manager.

        Args:
            *jobs (jobs.ManagedJobBase):
                The job to be removed, if present.
        Raises:
            TypeError: An invalid object was given as a job.
        """
        if not isinstance(job, jobs.ManagedJobBase):
            raise TypeError(
                "expected an instance of class 'ManagedJobBase' "
                f", not {job.__class__.__qualname__}"
            ) from None

        if isinstance(job, jobs.EventJobMixin):
            for ev_type in job.EVENTS:
                if (
                    ev_type._RUNTIME_ID in self._event_job_ids
                    and job._runtime_id in self._event_job_ids[ev_type._RUNTIME_ID]
                ):
                    self._event_job_ids[ev_type._RUNTIME_ID].remove(job._runtime_id)
                if not self._event_job_ids[ev_type._RUNTIME_ID]:
                    del self._event_job_ids[ev_type._RUNTIME_ID]

        if job._runtime_id in self._job_id_map:
            del self._job_id_map[job._runtime_id]

        if (
            job._runtime_id
            in self._job_class_data[job.__class__._RUNTIME_ID]["instances"]
        ):
            del self._job_class_data[job.__class__._RUNTIME_ID]["instances"][
                job._runtime_id
            ]

        if not self._job_class_data[job.__class__._RUNTIME_ID]["instances"]:
            del self._job_class_data[job.__class__._RUNTIME_ID]

    def _remove_jobs(self, *jobs: jobs.ManagedJobBase):
        """THIS METHOD IS ONLY MEANT FOR INTERNAL USE BY THIS CLASS.

        Remove the given job objects from this job manager.

        Args:
            *jobs: jobs.ManagedJobBase: The jobs to be removed, if
              present.
        Raises:
            TypeError: An invalid object was given as a job.
        """
        for job in jobs:
            self._remove_job(job)

    def has_job(self, job_proxy: "proxies.JobProxy") -> bool:
        """Whether a job is contained in this job manager.

        Args:
            job_proxy (JobProxy): The proxy to the job object to look
              for.

        Returns:
            bool: True/False
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        return job._runtime_id in self._job_id_map

    def has_job_identifier(self, identifier: str) -> bool:
        """Whether a job with the given identifier is contained in this job manager.

        Args:
            identifier (str): The job identifier.

        Returns:
            bool: True/False
        """

        self._check_init_and_running()

        return identifier in self._job_id_map

    def get_job_permission_level(
        self, job_proxy: "proxies.JobProxy"
    ) -> JobPermissionLevels:

        job = self._get_job_from_proxy(job_proxy)

        if job._runtime_id in self._job_id_map:
            return self._job_id_map[job._runtime_id][1]

        raise LookupError("could not find the specified job in this job manager")

    def find_job(
        self,
        *,
        identifier: Union[str, _UnsetType] = None,
        created_at: Union[datetime.datetime, _UnsetType] = None,
        _return_proxy: bool = True,
    ) -> Optional["proxies.JobProxy"]:
        """Find the first job that matches the given criteria specified as arguments,
        and return a proxy to it, otherwise return `None`.

        Args:

            identifier (str, optional): The exact identifier of the job to find. This
              argument overrides any other parameter below. Defaults to None.
            created_at (datetime.datetime, optional): The exact creation date of the
              job to find. Defaults to None.

        Returns:
            JobProxy: The proxy of the job object, if present.
            None: No matching job object found.

        Raises:
            TypeError: One of the arguments must be specified.
        """

        self._check_init_and_running()

        if identifier is not None:
            if isinstance(identifier, str):
                if identifier in self._job_id_map:
                    if _return_proxy:
                        return self._job_id_map[identifier][0]._proxy
                    return self._job_id_map[identifier][0]
                return None

            raise TypeError(
                f"'identifier' must be of type 'str', not {type(identifier)}"
            ) from None

        elif created_at is not None:
            if isinstance(created_at, datetime.datetime):
                for job, _ in self._job_id_map.values():
                    if job.created_at == created_at:
                        return job._proxy if _return_proxy else job
                return None

            raise TypeError(
                f"'created_at' must be of type 'datetime.datetime', not {type(created_at)}"
            ) from None

        raise TypeError(
            "the arguments 'identifier' and 'created_at' cannot both be None"
        ) from None

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
        creator: Union["proxies.JobProxy", _UnsetType] = UNSET,
        created_before: Union[datetime.datetime, _UnsetType] = UNSET,
        created_after: Union[datetime.datetime, _UnsetType] = UNSET,
        permission_level: Union[JobPermissionLevels, _UnsetType] = UNSET,
        above_permission_level: Union[JobPermissionLevels, _UnsetType] = UNSET,
        below_permission_level: Union[JobPermissionLevels, _UnsetType] = UNSET,
        alive: Union[bool, _UnsetType] = UNSET,
        is_starting: Union[bool, _UnsetType] = UNSET,
        is_running: Union[bool, _UnsetType] = UNSET,
        is_idling: Union[bool, _UnsetType] = UNSET,
        is_being_guarded: Union[bool, _UnsetType] = UNSET,
        guardian: Union["proxies.JobProxy", _UnsetType] = UNSET,
        is_stopping: Union[bool, _UnsetType] = UNSET,
        is_restarting: Union[bool, _UnsetType] = UNSET,
        is_being_killed: Union[bool, _UnsetType] = UNSET,
        is_completing: Union[bool, _UnsetType] = UNSET,
        stopped: Union[bool, _UnsetType] = UNSET,
        query_match_mode: Literal["ANY", "ALL"] = "ALL",
        _return_proxy: bool = True,
    ) -> tuple["proxies.JobProxy"]:
        """Find jobs that match the given criteria specified as arguments,
        and return a tuple of proxy objects to them.

        Args:
            classes: (
                 Optional[
                    Union[
                        Type[jobs.ManagedJobBase],
                        tuple[Type[jobs.ManagedJobBase],
                            ...,
                        ]
                    ]
                ]
            , optional): The class(es) of the job objects to limit the job search to,
              excluding subclasses. Defaults to `()`.
            exact_class_match (bool, optional): Whether an exact match is required for
              the classes in the previous parameter, or subclasses are allowed too.
              Defaults to False.
            creator (JobProxy, optional): The object that the value of
              this attribute on a job should have.
            created_before (datetime.datetime, optional): The lower age limit
              of the jobs to find.
            created_after (datetime.datetime, optional): The upper age limit
              of the jobs to find.
            permission_level (JobPermissionLevels, optional): The permission
              level of the jobs to find.
            above_permission_level (JobPermissionLevels, optional): The lower
              permission level value of the jobs to find.
            below_permission_level (JobPermissionLevels, optional): The upper
              permission level value of the jobs to find.
            alive (bool, optional): A boolean that a job's state should
              match.
            is_running (bool, optional): A boolean that a job's state
              should match.
            is_idling (bool, optional): A boolean that a job's state
              should match.
            is_being_guarded (bool, optional): A boolean that a job's
              state should match.
            guardian (Optional[JobProxy], optional): A value that the value of
              this attribute on a job should match.
            is_stopping (bool, optional): A boolean that a job's state
              should match.
            is_restarting (bool, optional): A boolean that a job's
              state should match.
            is_being_killed (bool, optional): A boolean that a job's
              state should match.
            is_completing (bool, optional): A boolean that a job's state
              should match.
            stopped (bool, optional): A boolean that a job's state should
              match.
            query_match_mode (Literal["any", "all"], optional): A string to control
              if the query keyword arguments of this method must match all at
              once or only need one match. Defaults to "all".

        Returns:
            tuple: A tuple of the job object proxies that were found.
        """

        self._check_init_and_running()

        job_map = self._job_id_map

        filter_functions = []

        if classes:
            if isinstance(classes, type):
                if issubclass(classes, jobs.ManagedJobBase):
                    classes = (classes,)
                else:
                    raise TypeError(
                        "'classes' must be a tuple of 'ManagedJobBase' "
                        "subclasses or a single subclass"
                    ) from None

            elif isinstance(classes, tuple):
                if not all(issubclass(c, jobs.ManagedJobBase) for c in classes):
                    raise TypeError(
                        "'classes' must be a tuple of 'ManagedJobBase' "
                        "subclasses or a single subclass"
                    ) from None

            if exact_class_match:
                if query_match_mode == "all":
                    job_map = FastChainMap(
                        *(
                            self._job_class_data[job_class._RUNTIME_ID]["instances"]
                            for job_class in classes
                            if job_class._RUNTIME_ID in self._job_class_data
                        ),
                        ignore_defaultdicts=True,
                    )
                else:
                    filter_functions.append(lambda job: job.__class__ in classes)
            else:
                filter_functions.append(lambda job: isinstance(job, classes))

        if creator is not UNSET:
            if isinstance(creator, proxies.JobProxy):
                filter_functions.append(lambda job: job.creator is creator)
            else:
                raise TypeError(
                    "'creator' must be of type 'JobProxy', not "
                    f"{type(created_before)}"
                ) from None

        if created_before is not UNSET:
            if isinstance(created_before, datetime.datetime):
                filter_functions.append(lambda job: job.created_at < created_before)
            else:
                raise TypeError(
                    "'created_before' must be of type 'datetime.datetime', not "
                    f"{type(created_before)}"
                ) from None

        if created_after is not UNSET:
            if isinstance(created_after, datetime.datetime):
                filter_functions.append(lambda job: job.created_at > created_after)
            else:
                raise TypeError(
                    "'created_after' must be of type 'datetime.datetime', not "
                    f"{type(created_after)}"
                ) from None

        if permission_level is not UNSET:
            if not isinstance(permission_level, JobPermissionLevels):
                raise TypeError(
                    "argument 'permission_level' must be an enum value from the "
                    "JobPermissionLevels enum"
                )

            filter_functions.append(
                lambda job: job.permission_level is permission_level
            )

        if below_permission_level is not UNSET:
            if not isinstance(below_permission_level, JobPermissionLevels):
                raise TypeError(
                    "argument 'below_permission_level' must be an enum value from the "
                    "JobPermissionLevels enum"
                )

            filter_functions.append(
                lambda job: job.permission_level < below_permission_level
            )

        if above_permission_level is not UNSET:
            if not isinstance(above_permission_level, JobPermissionLevels):
                raise TypeError(
                    "argument 'above_permission_level' must be an enum value from the "
                    "JobPermissionLevels enum"
                )

            filter_functions.append(
                lambda job: job.permission_level > above_permission_level
            )

        if alive is not UNSET:
            alive = bool(alive)
            filter_functions.append(lambda job: job.alive() is alive)

        if is_starting is not UNSET:
            is_starting = bool(is_starting)
            filter_functions.append(lambda job: job.is_starting() is is_starting)

        if is_running is not UNSET:
            is_running = bool(is_running)
            filter_functions.append(lambda job: job.is_running() is is_running)

        if is_idling is not UNSET:
            is_idling = bool(is_idling)
            filter_functions.append(lambda job: job.is_idling() is is_idling)

        if is_being_guarded is not UNSET:
            is_being_guarded = bool(is_being_guarded)
            filter_functions.append(
                lambda job: job.is_being_guarded() is is_being_guarded
            )

        if guardian is not UNSET:
            if isinstance(creator, proxies.JobProxy):
                filter_functions.append(lambda job: job.guardian is guardian)
            else:
                raise TypeError(
                    "'guardian' must be of type 'JobProxy', not "
                    f"{type(created_before)}"
                ) from None

        if is_stopping is not UNSET:
            is_stopping = bool(is_stopping)
            filter_functions.append(lambda job: job.is_stopping() is is_stopping)

        if is_restarting is not UNSET:
            is_restarting = bool(is_restarting)
            filter_functions.append(lambda job: job.is_restarting() is is_restarting)

        if is_being_killed is not UNSET:
            is_being_killed = bool(is_being_killed)
            filter_functions.append(
                lambda job: job.is_being_killed() is is_being_killed
            )

        if is_completing is not UNSET:
            is_completing = bool(is_completing)
            filter_functions.append(lambda job: job.is_completing() is is_completing)

        if stopped is not UNSET:
            stopped = bool(stopped)
            filter_functions.append(lambda job: job.stopped() is stopped)

        bool_func = None

        if isinstance(query_match_mode, str):
            if query_match_mode.lower() == "all":
                bool_func = all
            elif query_match_mode.lower() == "any":
                bool_func = any
            else:
                raise ValueError(
                    "argument 'query_match_mode' must be either 'all' or 'any'"
                )
        else:
            raise TypeError(
                "argument 'query_match_mode' must be a string matching either "
                "'all' or 'any'"
            )

        if filter_functions:
            if _return_proxy:
                return tuple(
                    job._proxy
                    for job, _ in job_map.values()
                    if bool_func(filter_func(job) for filter_func in filter_functions)
                )

            return tuple(
                job
                for job, _ in job_map.values()
                if bool_func(filter_func(job) for filter_func in filter_functions)
            )

        if _return_proxy:
            return tuple(job._proxy for job, _ in job_map.values())

        return tuple(job for job, _ in job_map.values())

    def start_job(
        self,
        job_proxy: "proxies.JobProxy",
        _iv: Optional[jobs.ManagedJobBase] = None,
    ) -> bool:

        """Start the given job object, if is hasn't already started.

        Args:
            job_proxy (JobProxy): The proxy to the job object.

        Returns:
            bool: Whether the operation was successful.

        Raises:
            JobInitializationError: The given job object was not initialized.
            JobIsGuarded: The job given is being guarded by another job.
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        if not job._bools & JF.INITIALIZED:
            raise JobInitializationError(
                "The given job object was not initialized"
            ) from None

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.START, target=job)
        else:
            self._check_manager_misuse()
            _iv = self._manager_job

        if job._guardian is not None and _iv._proxy is not job._guardian:
            raise JobIsGuarded(
                "the given target job object is being guarded by another job"
            ) from None

        return job._START_EXTERNAL()

    def restart_job(
        self,
        job_proxy: Union[jobs.ManagedJobBase, "proxies.JobProxy"],
        stopping_timeout: Optional[float] = None,
        _iv: Optional[jobs.ManagedJobBase] = None,
    ) -> bool:
        """Restart the given job object. This provides a cleaner way
        to forcefully stop a job and restart it, or to wake it up from
        a stopped state.

        Args:
            job_proxy (JobProxy): The proxy to the job object.
            stopping_timeout (Optional[float], optional):
              An optional timeout in seconds for the maximum time period
              for stopping the job while it is restarting. This overrides
              the global timeout of this job manager if present.

        Returns:
            bool: Whether the operation was initiated by the job.

        Raises:
            JobInitializationError: The given job object was not initialized.
            JobIsGuarded: The job given is being guarded by another job.s
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        if not job._bools & JF.INITIALIZED:
            raise JobInitializationError(
                "The given job object was not initialized"
            ) from None

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.RESTART, target=job)
        else:
            self._check_manager_misuse()
            _iv = self._manager_job

        if job._guardian is not None and _iv._proxy is not job._guardian:
            raise JobIsGuarded(
                "the given target job object is being guarded by another job"
            ) from None

        if stopping_timeout:
            stopping_timeout = float(stopping_timeout)
            job._manager._job_stop_timeout = stopping_timeout

        return job._RESTART_EXTERNAL()

    def stop_job(
        self,
        job_proxy: "proxies.JobProxy",
        stopping_timeout: Optional[float] = None,
        force: bool = False,
        _iv: Optional[jobs.ManagedJobBase] = None,
    ) -> bool:
        """Stop the given job object.

        Args:
            job_proxy (JobProxy): The proxy to the job object.
            force (bool): Whether to suspend all operations of the job forcefully.
            stopping_timeout (Optional[float], optional): An optional timeout in
              seconds for the maximum time period for stopping the job. This
              overrides the global timeout of this job manager if present.

        Returns:
            bool: Whether the operation was successful.

        Raises:
            JobInitializationError: The given job object was not initialized.
            JobIsGuarded: The given job object is being guarded by another job.
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        if not job._bools & JF.INITIALIZED:
            raise JobInitializationError(
                "The given job object was not initialized"
            ) from None

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.STOP, target=job)
        else:
            self._check_manager_misuse()
            _iv = self._manager_job

        if job._guardian is not None and _iv._proxy is not job._guardian:
            raise JobIsGuarded(
                "the given target job object is being guarded by another job"
            ) from None

        if stopping_timeout:
            stopping_timeout = float(stopping_timeout)
            job._manager._job_stop_timeout = stopping_timeout

        return job._STOP_EXTERNAL(force=force)

    def kill_job(
        self,
        job_proxy: "proxies.JobProxy",
        stopping_timeout: Optional[float] = None,
        _iv: Optional[jobs.ManagedJobBase] = None,
    ) -> bool:
        """Stops a job's current execution unconditionally and remove it from its
        job manager.

        Args:
            job_proxy (JobProxy): The proxy to the job object.
            stopping_timeout (Optional[float], optional):
              An optional timeout in seconds for the maximum time period for
              stopping the job while it is being killed. This overrides the
              global timeout of this job manager if present.

        Returns:
            bool: Whether the operation was successful.

        Raises:
            JobInitializationError: The given job object was not initialized.
            JobIsGuarded: The job given is being guarded by another job.s
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        if not job._bools & JF.INITIALIZED:
            raise JobInitializationError(
                "The given job object was not initialized"
            ) from None

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.KILL, target=job)
        else:
            self._check_manager_misuse()
            _iv = self._manager_job

        if job._guardian is not None and _iv._proxy is not job._guardian:
            raise JobIsGuarded(
                "the given target job object is being guarded by another job"
            ) from None

        if stopping_timeout:
            stopping_timeout = float(stopping_timeout)
            job._manager._job_stop_timeout = stopping_timeout

        return job._KILL_EXTERNAL(awaken=True)

    def guard_job(
        self,
        job_proxy: "proxies.JobProxy",
        _iv: Optional[jobs.ManagedJobBase] = None,
    ):
        """Place a guard on the given job object, to prevent unintended state
        modifications by other jobs. This guard can only be broken by other
        jobs when they have a high enough permission level.

        Args:
            job_proxy (JobProxy): The proxy to the job object.

        Raises:
            JobIsGuarded: The given target job object is already being guarded.
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        if not job._bools & JF.INITIALIZED:
            raise JobInitializationError(
                "The given job object was not initialized"
            ) from None

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.GUARD, target=job)
        else:
            self._check_manager_misuse()
            _iv = self._manager_job

        if job._guardian is not None:
            raise JobIsGuarded(
                "the given target job object is already being guarded by another job"
            ) from None

        if _iv._guarded_job_proxies_dict is None:
            _iv._guarded_job_proxies_dict = {}

        if job._runtime_id not in _iv._guarded_job_proxies_dict:
            job._guardian = _iv._proxy
            _iv._guarded_job_proxies_dict[job._runtime_id] = job._proxy
        else:
            raise JobIsGuarded(
                "the given target job object is already"
                " being guarded by the invoker job object"
            ) from None

    def unguard_job(
        self,
        job_proxy: "proxies.JobProxy",
        _iv: Optional[jobs.ManagedJobBase] = None,
    ):
        """Remove the guard on the given job object, to prevent unintended state
        modifications by other jobs.

        Args:
            job_proxy (JobProxy): The proxy to the job object.

        Raises:
            JobStateError: The given target job object is not being guarded by a job.
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        if not job._bools & JF.INITIALIZED:
            raise JobInitializationError(
                "The given job object was not initialized"
            ) from None

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.UNGUARD, target=job)
        else:
            self._check_manager_misuse()
            _iv = self._manager_job

        if job._guardian is None:
            raise JobStateError("the given job object is not being guarded by a job")

        guardian = self._get_job_from_proxy(job._guardian)

        if (
            _iv._guarded_job_proxies_dict is not None
            and job._runtime_id in _iv._guarded_job_proxies_dict
        ):
            job._guardian = None
            del _iv._guarded_job_proxies_dict[job._runtime_id]

        elif _iv is self._manager_job:
            job._guardian = None

            del guardian._guarded_job_proxies_dict[job._runtime_id]

        else:
            raise JobStateError(
                "the given target job object is not "
                "being guarded by the invoker job object"
            )

        for fut in job._unguard_futures:
            if not fut.done():
                fut.set_result(True)

        job._unguard_futures.clear()

    @contextmanager
    def guard_on_job(
        self,
        job_proxy: "proxies.JobProxy",
        _iv: Optional[jobs.ManagedJobBase] = None,
    ):
        """A context manager for automatically guarding and unguarding a job object.
        If the given job object is already unguarded or guarded by another job when
        this context manager is ending, it will not atttempt to unguard.

        This method is meant to be used with the `with` statement:
        ```py
        with manager.guard_on_job(job):
            ... # interact with a job
        ```

        Args:
            job_proxy (JobProxy): The proxy to the job object.

        Yields:
            The job proxy given as input.

        Raises:
            JobStateError: The given target job object already being guarded by a job.
        """

        if not isinstance(_iv, jobs.ManagedJobBase):
            _iv = self._manager_job

        self.guard_job(job_proxy, _iv=_iv)
        try:
            yield job_proxy
        finally:
            job = self._get_job_from_proxy(job_proxy)
            if job._guardian is not None and job._guardian is _iv._proxy:
                self.unguard_job(job_proxy, _iv=_iv)

    def __contains__(self, job_proxy: "proxies.JobProxy"):
        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)
        return job._runtime_id in self._job_id_map

    def dispatch_event(
        self,
        event: events.BaseEvent,
        _iv: Optional[jobs.ManagedJobBase] = None,
    ):
        """Dispatch an instance of a `BaseEvent` subclass to all event job
        objects in this job manager that are listening for it.

        Args:
            event (BaseEvent): The event to be dispatched.
        """

        self._check_init_and_running()

        if isinstance(_iv, jobs.ManagedJobBase):
            if isinstance(event, events.BaseEvent):
                if isinstance(event, events.CustomEvent):
                    self._verify_permissions(_iv, op=JobOps.CUSTOM_EVENT_DISPATCH)
                else:
                    self._verify_permissions(_iv, op=JobOps.EVENT_DISPATCH)
            else:
                raise TypeError("argument 'event' must be an instance of BaseEvent")
        else:
            if not isinstance(event, events.BaseEvent):
                raise TypeError("argument 'event' must be an instance of BaseEvent")
            self._check_manager_misuse()
            _iv = self._manager_job

        if _iv is not None:
            # for cases where the default _iv might not yet be set
            event._dispatcher = _iv._proxy

        event_class_identifier = event.__class__._RUNTIME_ID

        if event_class_identifier in self._event_waiting_queues:
            target_event_waiting_queue = self._event_waiting_queues[
                event_class_identifier
            ]
            deletion_queue_indices = []

            for i, waiting_list in enumerate(target_event_waiting_queue):
                if (
                    isinstance(event, waiting_list[0])
                    and waiting_list[1] is not None
                    and waiting_list[1](event)
                ):
                    if not waiting_list[2].cancelled():
                        waiting_list[2].set_result(event.copy())
                    deletion_queue_indices.append(i)

            for idx in reversed(deletion_queue_indices):
                del target_event_waiting_queue[idx]

        if event_class_identifier in self._event_job_ids:
            jobs_identifiers = self._event_job_ids[event_class_identifier]

            for identifier in jobs_identifiers:
                event_job = self._job_id_map[identifier][0]
                event_copy = event.copy()
                if event_job.event_check(event_copy):
                    event_job._add_event(event_copy)

    def wait_for_event(
        self,
        *event_types: Type[events.BaseEvent],
        check: Optional[Callable[[events.BaseEvent], bool]] = None,
        timeout: Optional[float] = None,
    ) -> Coroutine[Any, Any, events.BaseEvent]:
        """Wait for specific type of event to be dispatched
        and return it as an event object using the given coroutine.

        Args:
            *event_types (Type[events.BaseEvent]): The event type/types to wait for. If
              any of its/their instances is dispatched, that instance will be returned.
            check (Optional[Callable[[events.BaseEvent], bool]], optional): A callable
              obejct used to validate if a valid event that was received meets specific
              conditions. Defaults to None.
            timeout: (Optional[float], optional): An optional timeout value in seconds
              for the maximum waiting period.

        Returns:
            Coroutine: A coroutine that evaluates to a valid `BaseEvent` event object.

        Raises:
            TimeoutError: The timeout value was exceeded.
            CancelledError: The future used to wait for an event was cancelled.
        """

        self._check_init_and_running()
        future = self._loop.create_future()

        if not all(
            issubclass(event_type, events.BaseEvent) for event_type in event_types
        ):
            raise TypeError(
                "argument 'event_types' must contain only subclasses of 'BaseEvent'"
            ) from None

        wait_list = [event_types, check, future]

        for event_type in event_types:
            if event_type._RUNTIME_ID not in self._event_waiting_queues:
                self._event_waiting_queues[event_type._RUNTIME_ID] = []

            self._event_waiting_queues[event_type._RUNTIME_ID].append(wait_list)

        return asyncio.wait_for(future, timeout)

    def stop_all_jobs(self, force: bool = False):
        """Stop all job objects that are in this job manager."""

        self._check_init_and_running()
        self._check_manager_misuse()

        for job, _ in self._job_id_map.values():
            job._STOP_EXTERNAL(force=force)

    def kill_all_jobs(self, awaken: bool = True):
        """Kill all job objects that are in this job manager."""

        self._check_init_and_running()
        self._check_manager_misuse()

        for job, _ in self._job_id_map.values():
            job._KILL_EXTERNAL(awaken=awaken)

    def resume(self):
        """Resume the execution of this job manager.

        Raises:
            RuntimeError: This job manager never stopped, or was never initialized.
        """

        self._check_init()
        if self._is_running:
            raise RuntimeError("this job manager is still running")

        self._is_running = True

    def stop(
        self,
        job_operation: Union[Literal[JobOps.KILL], Literal[JobOps.STOP]] = JobOps.KILL,
    ):
        """Stop this job manager from running, while optionally killing/stopping the jobs in it
        and shutting down its executors.

        Args:
            job_operation (Union[JobOps.KILL, JobOps.STOP]): The operation to
              perform on the jobs in this job manager. Defaults to JobOps.KILL.
              Killing will always be done by starting up jobs and killing them immediately.
              Stopping will always be done by force. For more control, use the standalone
              functions for modifiying jobs.

        Raises:
            TypeError: Invalid job operation argument.
        """

        if not isinstance(job_operation, JobOps):
            raise TypeError(
                "argument 'job_operation' must be 'KILL' or 'STOP' from the JobOps enum"
            )

        if job_operation is JobOps.STOP:
            self.stop_all_jobs(force=True)
        elif job_operation is JobOps.KILL:
            self.kill_all_jobs(awaken=True)

        self._is_running = False

    def __repr__(self):
        return f"<{self.__class__.__name__} ({len(self._job_id_map)} jobs registered)>"

    def __str__(self):
        categorized_jobs = dict(
            initialized=self.find_jobs(
                alive=True,
                is_running=False,
                stopped=False,
                _return_proxy=False,
            ),
            starting=self.find_jobs(is_starting=True, _return_proxy=False),
            running=self.find_jobs(
                is_running=True,
                is_idling=False,
                is_starting=False,
                is_restarting=False,
                _return_proxy=False,
            ),
            idling=self.find_jobs(is_idling=True, _return_proxy=False),
            stopping=self.find_jobs(
                is_stopping=True,
                is_restarting=False,
                is_completing=False,
                is_being_killed=False,
                _return_proxy=False,
            ),
            completing=self.find_jobs(is_completing=True, _return_proxy=False),
            being_killed=self.find_jobs(is_being_killed=True, _return_proxy=False),
            stopped=self.find_jobs(stopped=True, _return_proxy=False),
        )

        categorized_jobs_str = "\n\n".join(
            f"[{k.upper()}]\n" + "\n".join(str(job) for job in v)
            for k, v in categorized_jobs.items()
            if v
        )

        header_str = (
            f"/{self.__class__.__name__} ({len(self._job_id_map)} jobs registered)\\"
        )

        border_str = "_" * len(header_str)
        return "\n".join(
            (
                f"  {border_str[2:]}",
                f" {header_str}",
                f"|{border_str}|\n",
                categorized_jobs_str,
                f" {border_str}",
                f"|{border_str}|",
            )
        )


from . import proxies
