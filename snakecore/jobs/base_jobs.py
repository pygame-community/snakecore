"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

This file implements the base classes for a task object system that
can be used to implement background processes for the bot. 
"""

from __future__ import annotations
from abc import ABC
import asyncio
from aiohttp import ClientError
from collections import deque
from contextlib import contextmanager
import datetime
import itertools
import inspect
import re
import sys
import time
from types import FunctionType, SimpleNamespace
from typing import Any, Callable, Optional, Type, Union

import discord
from discord.ext import tasks
from discord.utils import MAX_ASYNCIO_SECONDS

from snakecore.constants import UNSET, UNSET_TYPE
from snakecore import events, utils

_JOB_CLASS_MAP = {}
# A dictionary of all Job subclasses that were created. Do not access outside of this module.


def get_job_class_from_id(class_identifier: str, closest_match: bool = False):

    name, timestamp_str = class_identifier.split("-")

    if name in _JOB_CLASS_MAP:
        if timestamp_str in _JOB_CLASS_MAP[name]:
            return _JOB_CLASS_MAP[name][timestamp_str]["class"]
        elif closest_match:
            for ts_str in _JOB_CLASS_MAP[name]:
                return _JOB_CLASS_MAP[name][ts_str]["class"]

    raise KeyError(
        f"cannot find job class with an identifier of "
        f"'{class_identifier}' in the job class registry"
    )


def get_job_class_id(cls: Type[JobBase], raise_exceptions=True):

    if raise_exceptions and not issubclass(cls, JobBase):
        raise TypeError("argument 'cls' must be a subclass of a job base class")

    try:
        class_identifier = cls._IDENTIFIER
    except AttributeError:
        raise TypeError(
            "invalid job class, must be" " a subclass of a job base class"
        ) from None

    try:
        name, timestamp_str = class_identifier.split("-")
    except ValueError:
        if raise_exceptions:
            raise ValueError(
                "invalid identifier found in the given job class"
            ) from None
        return

    if name in _JOB_CLASS_MAP:
        if timestamp_str in _JOB_CLASS_MAP[name]:
            if _JOB_CLASS_MAP[name][timestamp_str]["class"] is cls:
                return class_identifier
            else:
                if raise_exceptions:
                    raise ValueError(
                        f"The given job class has the incorrect identifier"
                    )
        else:
            if raise_exceptions:
                ValueError(
                    f"The given job class is registered under "
                    "a different identifier in the job class registry"
                )

    if raise_exceptions:
        raise LookupError(
            f"The given job class does not exist in the job class registry"
        )


def get_job_class_permission_level(cls: Type[JobBase], raise_exceptions=True):
    if not issubclass(cls, JobBase):
        if raise_exceptions:
            raise TypeError("argument 'cls' must be a subclass of a job base class")
        return

    try:
        class_identifier = cls._IDENTIFIER
    except AttributeError:
        if raise_exceptions:
            raise TypeError(
                "invalid job class, must be "
                "a subclass of a job base class with an identifier"
            ) from None
        return

    try:
        name, timestamp_str = class_identifier.split("-")
    except ValueError:
        if raise_exceptions:
            raise ValueError(
                "invalid identifier found in the given job class"
            ) from None
        return

    if issubclass(cls, _SystemLevelMixinJobBase):
        return PERM_LEVELS.SYSTEM

    if name in _JOB_CLASS_MAP:
        if timestamp_str in _JOB_CLASS_MAP[name]:
            if _JOB_CLASS_MAP[name][timestamp_str]["class"] is cls:
                return _JOB_CLASS_MAP[name][timestamp_str]["permission_level"]
            else:
                if raise_exceptions:
                    raise ValueError(
                        f"The given job class has the incorrect identifier"
                    )
                return
        else:
            if raise_exceptions:
                ValueError(
                    f"The given job class is registered under "
                    "a different identifier in the job class registry"
                )
            return

    if raise_exceptions:
        raise LookupError(
            f"The given job class does not exist in the job class registry"
        )


DEFAULT_JOB_EXCEPTION_WHITELIST = (
    OSError,
    discord.GatewayNotFound,
    discord.ConnectionClosed,
    ClientError,
    asyncio.TimeoutError,
)
"""The default exceptions handled in discord.ext.tasks.Loop
upon reconnecting."""


class JOB_STATUS:
    """A class namespace of constants representing the main statuses a job
    object can be in.
    """

    FRESH = "FRESH"
    """This job object is freshly created and unmodified.
    """
    INITIALIZED = "INITIALIZED"

    STARTING = "STARTING"
    RUNNING = "RUNNING"
    AWAITING = "AWAITING"
    IDLING = "IDLING"
    COMPLETING = "COMPLETING"
    DYING = "DYING"
    RESTARTING = "RESTARTING"
    STOPPING = "STOPPING"

    STOPPED = "STOPPED"
    KILLED = "KILLED"
    COMPLETED = "COMPLETED"


class JOB_VERBS:
    """A class namespace of constants representing the operations that job
    objects can perform on each other.
    """

    CREATE = "CREATE"
    """The act of creating/instantiating a job object.
    """
    INITIALIZE = "INITIALIZE"
    """The act of initializing a job object.
    """
    REGISTER = "REGISTER"
    """The act of registering a job object.
    """
    SCHEDULE = "SCHEDULE"
    """The act of scheduling a job type for instantiation in the future.
    """
    GUARD = "GUARD"
    """The act of placing a modification guard on a job object.
    """

    FIND = "FIND"
    """The act of finding job objects based on specific parameters.
    """

    CUSTOM_EVENT_DISPATCH = "CUSTOM_EVENT_DISPATCH"
    """The act of dispatching only custom events to job objects.
    """

    EVENT_DISPATCH = "EVENT_DISPATCH"
    """The act of dispatching any type of event to job objects.
    """

    START = "START"
    """The act of starting a job object.
    """
    STOP = "STOP"
    """The act of stopping a job object.
    """
    RESTART = "RESTART"
    """The act of restarting a job object.
    """

    UNSCHEDULE = "UNSCHEDULE"
    """The act of unscheduling a specific job schedule operation.
    """
    UNGUARD = "UNGUARD"
    """The act of removing a modification guard on a job object.
    """

    KILL = "KILL"
    """The act of killing a job object.
    """

    _SIMPLE_PAST_TENSE = dict(
        CREATE="CREATED",
        INITIALIZE="INITIALIZED",
        REGISTER="REGISTERED",
        SCHEDULE="SCHEDULED",
        GUARD="GUARDED",
        FIND="FOUND",
        CUSTOM_EVENT_DISPATCH="CUSTOM_EVENT_DISPATCHED",
        EVENT_DISPATCH="EVENT_DISPATCHED",
        START="STARTED",
        STOP="STOPPED",
        RESTART="RESTARTED",
        UNSCHEDULE="UNSCHEDULED",
        UNGUARD="UNGUARDED",
        KILL="KILLED",
    )

    _PRESENT_CONTINUOUS_TENSE = dict(
        CREATE="CREATING",
        INITIALIZE="INITIALIZING",
        REGISTER="REGISTERING",
        SCHEDULE="SCHEDULING",
        GUARD="GUARDING",
        FIND="FINDING",
        CUSTOM_EVENT_DISPATCH="CUSTOM_EVENT_DISPATCHING",
        EVENT_DISPATCH="EVENT_DISPATCHING",
        START="STARTING",
        STOP="STOPPING",
        RESTART="RESTARTING",
        UNSCHEDULE="UNSCHEDULING",
        UNGUARD="UNGUARDING",
        KILL="KILLING",
    )


class JOB_STOP_REASONS:
    """A class namespace of constants representing the different reasons job
    objects might stop running.
    """

    INTERNAL = "INTERNAL"
    """Job is stopping due to an internal reason.
    """
    INTERNAL_ERROR = "INTERNAL_ERROR"
    """Job is stopping due to an internal error.
    """
    INTERNAL_RESTART = "INTERNAL_RESTART"
    """Job is stopping due to an internal restart.
    """
    INTERNAL_COUNT_LIMIT = "INTERNAL_COUNT_LIMIT"
    """Job is stopping due to hitting its maximimum execution
    count before stopping.
    """
    INTERNAL_COMPLETION = "INTERNAL_COMPLETION"
    """Job is stopping for finishing all execution, it has completed.
    """
    INTERNAL_KILLING = "INTERNAL_KILLING"
    """Job is stopping due to killing itself internally.
    """

    INTERNAL_IDLING_TIMEOUT = "INTERNAL_IDLING_TIMEOUT"
    """Job is stopping after staying idle beyond a specified timeout.
    """

    INTERNAL_EMPTY_QUEUE = "INTERNAL_EMPTY_QUEUE"
    """Job is stopping due to an empty internal queue of recieved events.
    """

    EXTERNAL = "EXTERNAL"
    """Job is stopping due to an unknown external reason.
    """
    EXTERNAL_RESTART = "EXTERNAL_RESTART"
    """Job is stopping due to an external restart.
    """
    EXTERNAL_KILLING = "EXTERNAL_KILLING"
    """Job is stopping due to being killed externally.
    """


class PERM_LEVELS:
    """A class namespace of constants representing the permission levels
    applicable to job objects.
    """

    LOWEST = 0
    """The lowest permission level.
    An Isolated job which has no information about other jobs being executed.
    Permissions:
        Can manage its own execution at will.
    """

    LOW = 1 << 1
    """A low permission level.

    Permissions:
        - Can manage its own execution at will.
        - Can discover and view all alive jobs, and request data from them.
    """

    MEDIUM = DEFAULT = 1 << 2
    """The default permission level, with simple job management permissions.

    Permissions:
        - Can manage its own execution at will.
        - Can discover and view all alive jobs, and request data from them.
        - Can instantiate, register, start and schedule jobs of a lower permission level.
        - Can stop, restart, or kill jobs instantiated by itself or unschedule its scheduled jobs.
        - Can unschedule jobs that don't have an alive job as a scheduler.
    """

    HIGH = 1 << 3
    """An elevated permission level, with additional control over jobs
    of a lower permission level.

    Permissions:
        - Can manage its own execution at will.
        - Can discover and view all alive jobs, and request data from them.
        - Can instantiate, register, start and schedule jobs of a lower permission level.
        - Can stop, restart, or kill jobs instantiated by itself or unschedule its scheduled jobs.
        - Can unschedule jobs that don't have an alive job as a scheduler.
        - Can stop, restart, kill or unschedule any job of a lower permission level.
        - Can guard and unguard jobs of a lower permission level instantiated by itself.
        - Can dispatch custom events to other jobs (`CustomEvent` subclasses).
    """

    HIGHEST = 1 << 4
    """The highest usable permission level, with additional control over jobs
    of a lower permission level. Lower permissions additionally apply to this level.

    Permissions:
        - Can manage its own execution at will.
        - Can discover and view all alive jobs, and request data from them.
        - Can instantiate, register, start and schedule jobs of a lower permission level.
        - Can stop, restart, or kill jobs instantiated by itself or unschedule its scheduled jobs.
        - Can unschedule jobs that don't have an alive job as a scheduler.
        - Can stop, restart, kill or unschedule any job of a lower permission level.
        - Can guard and unguard jobs of a lower permission level instantiated by itself.
        - Can guard and unguard jobs of the same permission level instantiated by itself.
        - Can dispatch any event to other jobs (`BaseEvent` subclasses).
        - Can instantiate, register, start and schedule jobs of the same permission level.
        - Can stop, restart, kill or unschedule any job of the same permission level.
    """

    SYSTEM = 1 << 5
    """The highest possible permission level reserved for system-level jobs. Cannot be used directly.
    Lower permissions additionally apply to this level.

    Permissions:
        - Can manage its own execution at will.
        - Can discover and view all alive jobs, and request data from them.
        - Can instantiate, register, start and schedule jobs of a lower permission level.
        - Can stop, restart, or kill jobs instantiated by itself or unschedule its scheduled jobs.
        - Can unschedule jobs that don't have an alive job as a scheduler.
        - Can stop, restart, kill or unschedule any job of a lower permission level.
        - Can guard and unguard jobs of a lower permission level instantiated by itself.
        - Can guard and unguard jobs of the same permission level instantiated by itself.
        - Can instantiate, register, start and schedule jobs of the same permission level.
        - Can stop, restart, kill or unschedule any job of the same permission level.
        - Can guard or unguard any job.
    """

    @staticmethod
    def get_name(level: int):
        if not isinstance(level, int):
            raise TypeError(
                "argument 'level' must be" f" of type 'int', not {level.__class__}"
            )
        elif level % 2 or not (PERM_LEVELS.LOWEST <= level <= PERM_LEVELS.SYSTEM):
            raise ValueError(
                "argument 'level' must be" " a valid permission level integer"
            )

        if level == PERM_LEVELS.LOWEST:
            return "LOWEST"

        elif level == PERM_LEVELS.LOW:
            return "LOW"

        elif level == PERM_LEVELS.MEDIUM:
            return "MEDIUM"

        elif level == PERM_LEVELS.HIGH:
            return "HIGH"

        elif level == PERM_LEVELS.HIGHEST:
            return "HIGHEST"

        elif level == PERM_LEVELS.SYSTEM:
            return "SYSTEM"


class JobError(Exception):
    """Generic job object error."""

    pass


class JobPermissionError(JobError):
    """Job object permisssion error."""

    pass


class JobStateError(JobError):
    """An invalid job object state is preventing an operation."""

    pass


class JobInitializationError(JobError):
    """Initialization of a job object failed, or is required."""

    pass


class JobWarning(Warning):
    """Base class for job related warnings."""

    pass


class JobNamespace(SimpleNamespace):
    """A subclass of SimpleNamespace, which is used by job objects
    to store instance-specific data.
    """

    def __contains__(self, k: str):
        return k in self.__dict__

    def __iter__(self):
        return iter(self.__dict__.items())

    def copy(self):
        return JobNamespace(**self.__dict__)

    def to_dict(self):
        return dict(self.__dict__)

    @staticmethod
    def from_dict(d):
        return JobNamespace(**d)

    __copy__ = copy


class _SystemLevelMixinJobBase(ABC):
    """An abstract base class for marking job classes as system-level."""

    pass


class _SingletonMixinJobBase(ABC):
    """An abstract base class for marking job classes as singletons,
    which can only be scheduled one at a time in a job manager.
    """

    pass


def singletonjob(cls):
    """A class decorator for marking job classes as singletons,
    meaning that their instances can only be scheduled one at a time in a job manager.
    """
    if issubclass(cls, JobBase):
        _SingletonMixinJobBase.register(cls)
    return cls


def _sysjob(cls):
    """A class decorator for marking job classes as system-level."""
    if issubclass(cls, JobBase):
        _SystemLevelMixinJobBase.register(cls)
    return cls


def publicjobmethod(func: Callable[[], Any]):
    """A simple decorator to expose a method as public to other job objects.

    Args:
        func (Callable[[Any], Any]): The job method to expose.
    """

    if isinstance(func, FunctionType):
        func.__public = True
        return func

    raise TypeError("argument 'func' must be a function")


class JobBase:
    """The base class of all job objects,
    which implements base functionality for its subclasses."""

    __slots__ = (
        "_interval_secs",
        "_count",
        "_reconnect",
        "_loop_count",
        "_manager",
        "_creator",
        "_created_at_ts",
        "_registered_at_ts",
        "_completed_at_ts",
        "_killed_at_ts",
        "_identifier",
        "_schedule_identifier",
        "_data",
        "_output_fields",
        "_output_queues",
        "_output_queue_proxies",
        "_output_field_futures",
        "_output_queue_futures",
        "_unguard_futures",
        "_done_futures",
        "_task_loop",
        "_proxy",
        "_guarded_job_proxies_dict",
        "_guardian",
        "_is_being_guarded",
        "_on_start_exception",
        "_on_run_exception",
        "_on_stop_exception",
        "_initialized",
        "_is_being_initialized",
        "_is_starting",
        "_completed",
        "_is_being_completed",
        "_killed",
        "_is_being_killed",
        "_startup_kill",
        "_skip_on_run",
        "_stopping_by_self",
        "_stopping_by_force",
        "_is_being_stopped",
        "_last_stop_reason",
        "_is_awaiting",
        "_is_being_restarted",
        "_stopped",
        "_is_idling",
        "_initialized_since_ts",
        "_alive_since_ts",
        "_awaiting_since_ts",
        "_idling_since_ts",
        "_running_since_ts",
        "_stopped_since_ts",
    )

    _CREATED_AT = datetime.datetime.now(datetime.timezone.utc)
    _IDENTIFIER = f"JobBase-{int(_CREATED_AT.timestamp()*1_000_000_000)}"
    _PERMISSION_LEVEL = PERM_LEVELS.MEDIUM

    PUBLIC_METHODS: Optional[dict[str, Callable[..., Any]]] = None

    OUTPUT_FIELDS = frozenset()
    OUTPUT_QUEUES = frozenset()

    NAMESPACE_CLASS = JobNamespace

    def __init_subclass__(cls, permission_level=None):
        for field in itertools.chain(cls.OUTPUT_FIELDS, cls.OUTPUT_QUEUES):
            if re.search(r"\s", field):
                raise ValueError(
                    "field names in 'OUTPUT_FIELDS' or 'OUTPUT_QUEUES'"
                    " cannot contain any whitespace"
                )

        cls.OUTPUT_FIELDS = frozenset(cls.OUTPUT_FIELDS)
        cls.OUTPUT_QUEUES = frozenset(cls.OUTPUT_QUEUES)

        cls._CREATED_AT = datetime.datetime.now(datetime.timezone.utc)

        is_system_job = issubclass(cls, _SystemLevelMixinJobBase)

        if is_system_job:
            permission_level = PERM_LEVELS.SYSTEM

        name = cls.__name__
        timestamp = f"{int(cls._CREATED_AT.timestamp()*1_000_000_000)}"

        if permission_level is not None:
            if isinstance(permission_level, int):
                if (
                    not permission_level % 2
                    and PERM_LEVELS.LOWEST <= permission_level <= PERM_LEVELS.HIGHEST
                ) or (is_system_job and permission_level == PERM_LEVELS.SYSTEM):
                    cls._PERMISSION_LEVEL = permission_level
                else:
                    raise ValueError(
                        "argument 'permission_level' must be a usable permission "
                        "level from the 'PERM_LEVELS' class namespace"
                    )
            else:
                raise TypeError(
                    "argument 'permission_level' must be a usable permission "
                    "level from the 'PERM_LEVELS' class namespace"
                )
        else:
            permission_level = cls._PERMISSION_LEVEL

        cls._IDENTIFIER = f"{name}-{timestamp}"

        if name not in _JOB_CLASS_MAP:
            _JOB_CLASS_MAP[name] = {}

        _JOB_CLASS_MAP[name][timestamp] = {
            "class": cls,
            "permission_level": permission_level,
        }

        public_methods = {}
        for obj in cls.__dict__.values():
            if isinstance(obj, FunctionType) and "__public" in obj.__dict__:
                public_methods[obj.__name__] = obj

        cls.PUBLIC_METHODS = public_methods

    def __init__(self):
        self._interval_secs = 0
        self._count = -1
        self._reconnect = False

        self._loop_count = 0

        self._manager: Optional[JobManagerProxy] = None  # type: ignore
        self._creator: Optional[JobProxy] = None
        self._created_at_ts = time.time()
        self._registered_at_ts = None
        self._completed_at_ts = None
        self._killed_at_ts = None
        self._identifier = f"{id(self)}-{int(self._created_at_ts*1_000_000_000)}"
        self._schedule_identifier = None
        self._data = self.NAMESPACE_CLASS()

        self._done_futures = []
        self._output_field_futures = None

        self._output_fields = None
        self._output_queue_proxies: Optional[list[JobOutputQueueProxy]] = None

        if self.OUTPUT_FIELDS:
            self._output_field_futures = {
                field_name: [] for field_name in self.OUTPUT_FIELDS
            }
            self._output_fields = {
                field_name: UNSET for field_name in self.OUTPUT_FIELDS
            }

        if self.OUTPUT_QUEUES:
            self._output_queue_proxies = []
            self._output_queue_futures = {
                queue_name: [] for queue_name in self.OUTPUT_QUEUES
            }
            self._output_queues = {queue_name: [] for queue_name in self.OUTPUT_QUEUES}

        self._task_loop: Optional[tasks.Loop] = None

        self._proxy = JobProxy(self)

        self._unguard_futures: Optional[list] = None
        self._guardian: Optional[JobBase] = None
        self._guarded_job_proxies_dict: Optional[dict] = None
        # will be assigned by job manager

        self._is_being_guarded = False

        self._on_start_exception = None
        self._on_run_exception = None
        self._on_stop_exception = None

        self._is_awaiting = False
        self._is_being_initialized = False
        self._initialized = False
        self._is_starting = False
        self._completed = False
        self._is_being_completed = False

        self._killed = False
        self._is_being_killed = False
        self._startup_kill = False
        self._skip_on_run = False

        self._stopping_by_self = False
        self._stopping_by_force = True
        self._is_being_stopped = False
        self._last_stop_reason: Optional[str] = None

        self._is_being_restarted = False
        self._stopped = False
        self._is_idling = False

        self._initialized_since_ts = None
        self._alive_since_ts: Optional[float] = None
        self._awaiting_since_ts: Optional[float] = None
        self._idling_since_ts: Optional[float] = None
        self._running_since_ts: Optional[float] = None
        self._stopped_since_ts: Optional[float] = None

    @property
    def identifier(self):
        return self._identifier

    @property
    def created_at(self):
        if self._created_at_ts:
            return datetime.datetime.fromtimestamp(
                self._created_at_ts, tz=datetime.timezone.utc
            )

    @property
    def registered_at(self):
        if self._registered_at_ts:
            return datetime.datetime.fromtimestamp(
                self._registered_at_ts, tz=datetime.timezone.utc
            )

    @property
    def permission_level(self):
        return self._PERMISSION_LEVEL

    @property
    def data(self):
        """The `JobNamespace` instance bound to this job object for storage."""
        return self._data

    @property
    def manager(self):
        """The `JobManagerProxy` object bound to this job object."""
        return self._manager

    @property
    def creator(self):
        """The `JobProxy` of the creator of this job object."""
        return self._creator

    @property
    def guardian(self):
        """The `JobProxy` of the current guardian of this job object."""
        return self._guardian

    @property
    def proxy(self):
        """The `JobProxy` object bound to this job object."""
        return self._proxy

    @property
    def schedule_identifier(self):
        """The identfier of the scheduling operation that instantiated
        this job object.
        """
        return self._schedule_identifier

    async def _on_init(self):
        try:
            self._is_being_initialized = True
            await self.on_init()
        except Exception:
            self._is_being_initialized = False
            raise
        else:
            self._is_being_initialized = False
            self._initialized = True
            self._initialized_since_ts = time.time()

    async def on_init(self):
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()`
        WITHIN THIS METHOD TO ACCESS THE SUPERCLASS METHOD.

        This method allows subclasses to initialize their job object instances.
        """
        pass

    async def _on_start(self):
        self._on_start_exception = None
        self._on_run_exception = None
        self._on_stop_exception = None

        self._stopped = False
        self._stopped_since_ts = None

        self._is_starting = True

        self._running_since_ts = time.time()

        self._is_idling = False
        self._idling_since_ts = None

        try:
            if not self._startup_kill:
                await self.on_start()
        except Exception as exc:
            self._on_start_exception = exc
            self._stopping_by_self = True
            self._is_being_stopped = True
            self._stopping_by_force = True
            await self.on_start_error(exc)
            self._stop_cleanup(JOB_STOP_REASONS.INTERNAL_ERROR)
            raise
        finally:
            self._is_starting = False

    async def on_start(self):
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        A generic hook method that subclasses can use to setup their job objects
        when they start.

        Raises:
            NotImplementedError: This method must be overloaded in subclasses.
        """
        raise NotImplementedError()

    async def _on_run(self):
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        Raises:
            NotImplementedError: This method must be overloaded in subclasses.
        """
        raise NotImplementedError()

    async def on_run(self):
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        Raises:
            NotImplementedError: This method must be overloaded in subclasses.
        """
        raise NotImplementedError()

    def _stop_cleanup(self, reason):
        self._last_stop_reason = reason
        self._skip_on_run = False
        self._is_starting = False
        self._startup_kill = False
        self._stopping_by_self = False
        self._stopping_by_force = False
        self._is_being_stopped = False
        self._is_being_restarted = False

        if self._is_being_completed or self._is_being_killed:
            self._initialized = False
            if self._is_being_guarded:
                if self._unguard_futures is not None:
                    for fut in self._unguard_futures:
                        if not fut.cancelled():
                            fut.set_result(True)

                    self._unguard_futures.clear()
                    self._manager._unguard()

            if self._guarded_job_proxies_dict is not None:
                for job_proxy in self._guarded_job_proxies_dict.values():
                    self.manager.unguard_job(job_proxy)

                self._guarded_job_proxies_dict.clear()

            if self.OUTPUT_QUEUES:
                self._output_queue_proxies.clear()

            if self._is_being_completed:
                self._is_being_completed = False
                self._completed = True
                self._completed_at_ts = time.time()

                self._alive_since_ts = None

                for fut in self._done_futures:
                    if not fut.cancelled():
                        fut.set_result(JOB_STATUS.COMPLETED)

                self._done_futures.clear()

                if self.OUTPUT_FIELDS:
                    for field_name, fut_list in self._output_field_futures.items():
                        output = self._output_fields[field_name]
                        for fut in fut_list:
                            if not fut.cancelled():
                                fut.set_result(output)

                        fut_list.clear()

                    self._output_field_futures.clear()

                if self.OUTPUT_QUEUES:
                    for fut_list in self._output_queue_futures.values():
                        for fut, cancel_if_cleared in fut_list:
                            if not fut.cancelled():
                                fut.cancel(msg=f"Job object '{self}' has completed.")

            elif self._is_being_killed:
                self._is_being_killed = False
                self._killed = True
                self._killed_at_ts = time.time()

                self._alive_since_ts = None

                for fut in self._done_futures:
                    if not fut.cancelled():
                        fut.set_result(JOB_STATUS.KILLED)

                self._done_futures.clear()

                if self.OUTPUT_FIELDS:
                    for fut_list in self._output_field_futures.values():
                        for fut in fut_list:
                            if not fut.cancelled():
                                fut.cancel(
                                    msg=f"Job object '{self}' was killed."
                                    " Job output would be incomplete."
                                )

                        fut_list.clear()

                    self._output_field_futures.clear()

                if self.OUTPUT_QUEUES:
                    for fut_list in self._output_queue_futures.values():
                        for fut, cancel_if_cleared in fut_list:
                            if not fut.cancelled():
                                fut.cancel(msg=f"Job object '{self}' was killed.")

        self._is_idling = False
        self._idling_since_ts = None

        self._running_since_ts = None

        if self._killed or self._completed:
            self._stopped = False
            self._stopped_since_ts = None
            self._manager._eject()
        else:
            self._stopped = True
            self._stopped_since_ts = time.time()

    async def _on_stop(self):
        self._is_being_stopped = True
        reason = self.is_being_stopped(get_reason=True)
        try:
            if not self._stopping_by_self:
                await asyncio.wait_for(
                    self.on_stop(reason=reason, by_force=self._stopping_by_force),
                    self._manager.get_job_stop_timeout(),
                )
            else:
                await self.on_stop(reason=reason, by_force=self._stopping_by_force)

        except asyncio.TimeoutError:
            self._on_stop_exception = exc
            if not self._stopping_by_self:
                await self.on_stop_error(exc)
            raise

        except Exception as exc:
            self._on_stop_exception = exc
            await self.on_stop_error(exc)
            raise

        finally:
            self._stop_cleanup(reason)

    async def on_stop(self, reason, by_force):
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        A method that subclasses can use to shutdown their job objects
        when they stop.

        Note that `on_stop_error()` will not be called if this method raises
        TimeoutError, and this job did not trigger the stop operation.

        Raises:
            NotImplementedError: This method must be overloaded in subclasses.
        """
        raise NotImplementedError()

    async def on_start_error(self, exc: Exception):
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        This method gets called when an error occurs while this job is starting up.

        Args:
            exc (Exception): The exception that occured.
        """
        print(
            f"{self}:\n" f"An Exception occured in 'on_start':\n\n",
            utils.format_code_exception(exc),
            file=sys.stderr,
        )

    async def _on_run_error(self, exc: Exception):
        self._on_run_exception = exc
        await self.on_run_error(exc)

    async def on_run_error(self, exc: Exception):
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        Args:
            exc (Exception): The exception that occured.
        """
        print(
            f"{self}:\n" f"An Exception occured in 'on_run':\n\n",
            utils.format_code_exception(exc),
            file=sys.stderr,
        )

    async def on_stop_error(self, exc: Exception):
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        This method gets called when an error occurs
        while this job is stopping.

        Args:
            exc (Exception): The exception that occured.
        """
        print(
            f"{self}:\n" f"An Exception occured in 'on_stop':\n\n",
            utils.format_code_exception(exc),
            file=sys.stderr,
        )

    def is_being_stopped(self, get_reason: bool = False):
        """Whether this job object is being stopped.

        Args:
            get_reason (bool, optional): Whether the reason for stopping should
              be returned as a string. Defaults to False.

        Returns:
            Union[bool, str]: Returns a boolean if `get_reason` is False, otherwise
              a string is returned. If the string is empty, no stopping is occuring.
        """
        output = self._is_being_stopped
        if get_reason:
            reason = None
            if not self._is_being_stopped:
                reason = ""
            elif self._task_loop.failed():
                reason = JOB_STOP_REASONS.INTERNAL_ERROR
            elif self._task_loop.current_loop == self._count:
                reason = JOB_STOP_REASONS.INTERNAL_COUNT_LIMIT
            elif self._stopping_by_self:
                if self._is_being_restarted:
                    reason = JOB_STOP_REASONS.INTERNAL_RESTART
                elif self._is_being_completed:
                    reason = JOB_STOP_REASONS.INTERNAL_COMPLETION
                elif self._is_being_killed:
                    reason = JOB_STOP_REASONS.INTERNAL_KILLING
                else:
                    reason = JOB_STOP_REASONS.INTERNAL
            elif not self._stopping_by_self:
                if self._is_being_restarted:
                    reason = JOB_STOP_REASONS.EXTERNAL_RESTART
                elif self._is_being_killed:
                    reason = JOB_STOP_REASONS.EXTERNAL_KILLING
                else:
                    reason = JOB_STOP_REASONS.EXTERNAL

            output = reason
        return output

    def add_to_exception_whitelist(self, *exception_types):
        """Add exceptions to a whitelist, which allows them to be ignored
        when they are raised, if reconnection is enabled.
        Args:
            *exception_types: The exception types to add.
        """
        self._task_loop.add_exception_type(*exception_types)

    def remove_from_exception_whitelist(self, *exception_types):
        """Remove exceptions from the exception whitelist for reconnection.
        Args:
            *exception_types: The exception types to remove.
        """
        self._task_loop.remove_exception_type(*exception_types)

    def clear_exception_whitelist(self, keep_default=True):
        """Clear all the exceptions whitelisted for reconnection.

        Args:
            keep_default (bool, optional): Preserve the default set of exceptions
            in the whitelist. Defaults to True.

        """
        self._task_loop.clear_exception_types()
        if keep_default:
            self._task_loop.add_exception_type(*DEFAULT_JOB_EXCEPTION_WHITELIST)

    def get_last_stop_reason(self):
        """Get the last reason this job object stopped, when applicable.

        Returns:
            Optional[str]: The reason for stopping.
        """
        return self._last_stop_reason

    def get_start_exception(self):
        """Get the exception that caused this job to fail at startup
        within the `on_start()` method, otherwise return None.

        Returns:
            Exception: The exception instance.
            None: No exception has been raised in `on_start()`.
        """
        return self._on_start_exception

    def get_run_exception(self):
        """Get the exception that caused this job to fail while running
        its main loop within the `on_run()` method. This is the same
        exception passed to `on_run_error()`, otherwise return None.

        Returns:
            Exception: The exception instance.
            None: No exception has been raised in `on_run()`.
        """
        return self._on_run_exception

    def get_stop_exception(self):
        """Get the exception that caused this job to fail while
        shutting down within the `on_stop()` method, otherwise return None.

        Returns:
            Exception: The exception instance.
            None: No exception has been raised in `on_stop()`.
        """
        return self._on_stop_exception

    async def _INITIALIZE_EXTERNAL(self):
        """DO NOT CALL THIS METHOD MANUALLY.

        This method to initializes a job using the `_on_init` method
        of the base class.
        """
        if self._manager is not None and not self._killed and not self._completed:
            await self._on_init()
            self._alive_since_ts = time.time()

    def STOP(self, force=False):
        """DO NOT CALL THIS METHOD FROM OUTSIDE YOUR JOB SUBCLASS.

        Stop this job object.

        Args:
            force (bool, optional): Whether this job object should be stopped
              forcefully instead of gracefully, thereby ignoring any exceptions
              that it might have handled if reconnecting is enabled for it.
              Defaults to False.

        Returns:
            bool: Whether the call was successful.
        """

        task = self._task_loop.get_task()
        if not self._is_being_stopped and task is not None and not task.done():
            self._stopped = False
            self._stopped_since_ts = None
            self._stopping_by_self = True
            self._is_being_stopped = True
            if force or self._is_idling:  # forceful stopping is necessary when idling
                self._stopping_by_force = True
                self._task_loop.cancel()
            else:
                self._skip_on_run = True
                # graceful stopping doesn't
                # skip `on_run()` when called in `on_start()`
                self._task_loop.stop()
            return True
        return False

    def _STOP_EXTERNAL(self, force=False):
        """DO NOT CALL THIS METHOD MANUALLY.

        Stop this job object.

        Args:
            force (bool, optional): Whether this job object should be stopped
              forcefully instead of gracefully, thereby ignoring any exceptions
              that it might have handled when reconnecting is enabled for it.
              Defaults to False.

        Returns:
            bool: Whether the call was successful.
        """
        task = self._task_loop.get_task()
        if not self._is_being_stopped and task is not None and not task.done():
            self._stopped = False
            self._stopped_since_ts = None
            self._stopping_by_self = False
            self._is_being_stopped = True
            if force or self._is_idling:  # forceful stopping is necessary when idling
                self._stopping_by_force = True
                self._task_loop.cancel()
            else:
                self._skip_on_run = True
                # graceful stopping doesn't
                # skip `on_run()` when called in `on_start()`
                self._task_loop.stop()
            return True
        return False

    def RESTART(self):
        """DO NOT CALL THIS METHOD FROM OUTSIDE YOUR JOB SUBCLASS.

        Restart this job object by forcefully stopping it
        (cancelling its task loop), before starting it again automatically.

        This will cause 'INTERNAL_RESTART' to be passed to `on_stop`.
        """
        task = self._task_loop.get_task()
        if (
            not self._is_being_restarted
            and not self._task_loop.is_being_cancelled()
            and task is not None
            and not task.done()
        ):
            self._is_being_restarted = True
            self._is_being_stopped = True
            self._stopping_by_self = True
            self._stopping_by_force = True
            self._task_loop.restart()
            return True
        return False

    def _RESTART_EXTERNAL(self):
        """DO NOT CALL THIS METHOD MANUALLY.

        Restart this job object by forcefully stopping it
        (cancelling its task loop), before starting it again automatically.

        This will cause 'EXTERNAL_RESTART' to be passed to `on_stop`.
        """
        task = self._task_loop.get_task()
        if (
            not self._is_being_restarted
            and not self._task_loop.is_being_cancelled()
            and task is not None  # disallow restart without ever starting
            and not task.done()
        ):
            self._is_being_restarted = True
            self._is_being_stopped = True
            self._stopping_by_self = False
            self._stopping_by_force = True
            self._task_loop.restart()
            return True
        return False

    def COMPLETE(self):
        """DO NOT CALL THIS METHOD FROM OUTSIDE YOUR JOB SUBCLASS.

        Stops this job object gracefully, before removing it
        from its job manager. Any job that was completed
        has officially finished execution, and all jobs waiting
        for this job to complete will be notified. If a job had
        reconnecting enabled, then it will be silently cancelled
        to ensure that it suspends all execution.
        """

        if not self._is_being_killed and not self._is_being_completed:
            if not self._is_being_stopped:
                self.STOP(force=True)

            self._is_being_completed = True
            return True

        return False

    def KILL(self):
        """
        DO NOT CALL THIS METHOD FROM OUTSIDE YOUR JOB SUBCLASS.

        Stops this job object forcefully, before removing it from its job manager.

        Returns:
            bool: Whether this method was successful.
        """

        if not self._is_being_killed and not self._is_being_completed:
            if not self._is_being_stopped:
                self.STOP(force=True)

            self._is_being_killed = True
            return True

        return False

    def _KILL_EXTERNAL(self, awaken=True):
        """DO NOT CALL THIS METHOD MANUALLY.

        Stops this job object forcefully, before removing it from its job manager.

        Args:
            awaken (bool, optional): Whether to awaken this job object before
              killing it. Defaults to True.

        Returns:
            bool: Whether this method was successful.
        """

        if not self._is_being_killed and not self._is_being_completed:
            if not self.is_running() and awaken:
                self._startup_kill = True  # start and kill immediately
                self._task_loop.start()
                return True

            if not self._is_being_stopped:
                self._STOP_EXTERNAL(force=True)

            self._is_being_killed = True
            return True

        return False

    async def wait_for(self, awaitable, timeout: Optional[float] = None):
        """Wait for a given awaitable object to complete.
        While awaiting the awaitable, this job object
        will be marked as waiting.

        Args:
            awaitable: An awaitable object

        Returns:
            Any: The result of the given coroutine.

        Raises:
            TypeError: The given object was not a coroutine.
        """
        if inspect.isawaitable(awaitable):
            try:
                self._is_awaiting = True
                self._awaiting_since_ts = time.time()
                result = await asyncio.wait_for(awaitable, timeout)
                return result
            finally:
                self._is_awaiting = False
                self._awaiting_since_ts = None

        raise TypeError("argument 'awaitable' must be an awaitable object")

    def loop_count(self):
        """The current amount of `on_run()` calls completed by this job object."""
        return self._loop_count

    def is_awaiting(self):
        """Whether this job is currently waiting
        for a coroutine to complete, which was awaited
        using `.wait_for(awaitable)`.

        Returns:
            bool: True/False
        """
        return self._is_awaiting

    def awaiting_since(self):
        """The last time at which this job object began awaiting, if available.

        Returns:
            datetime.datetime: The time, if available.
        """
        if self._awaiting_since_ts:
            return datetime.datetime.fromtimestamp(
                self._awaiting_since_ts, tz=datetime.timezone.utc
            )

    def initialized(self):
        """Whether this job has been initialized.

        Returns:
            bool: True/False
        """
        return self._initialized

    def is_being_initialized(self):
        """Whether this job object is being initialized.

        Returns:
            bool: True/False
        """

        return self._is_being_initialized

    def initialized_since(self):
        """The time at which this job object was initialized, if available.

        Returns:
            datetime.datetime: The time, if available.
        """
        if self._initialized_since_ts:
            return datetime.datetime.fromtimestamp(
                self._initialized_since_ts, tz=datetime.timezone.utc
            )

    def alive(self):
        """Whether this job is currently alive
        (initialized and bound to a job manager, not completed or killed).

        Returns:
            bool: True/False
        """
        return (
            self._manager is not None
            and self._initialized
            and not self._killed
            and not self._completed
        )

    def alive_since(self):
        """The last time at which this job object became alive, if available.

        Returns:
            datetime.datetime: The time, if available.
        """
        if self._alive_since_ts:
            return datetime.datetime.fromtimestamp(
                self._alive_since_ts, tz=datetime.timezone.utc
            )

    def is_starting(self):
        """Whether this job is currently starting to run.

        Returns:
            bool: True/False
        """
        return self._is_starting

    def is_running(self):
        """Whether this job is currently running (alive and not stopped).

        Returns:
            bool: True/False
        """
        return self.alive() and self._task_loop.is_running() and not self._stopped

    def running_since(self):
        """The last time at which this job object started running, if available.

        Returns:
            datetime.datetime: The time, if available.
        """
        if self._running_since_ts:
            return datetime.datetime.fromtimestamp(
                self._running_since_ts, tz=datetime.timezone.utc
            )

    def stopped(self):
        """Whether this job is currently stopped (alive and not running).

        Returns:
            bool: True/False
        """
        return self._stopped

    def stopped_since(self):
        """The last time at which this job object stopped, if available.

        Returns:
            datetime.datetime: The time, if available.
        """
        if self._stopped_since_ts:
            return datetime.datetime.fromtimestamp(
                self._stopped_since_ts, tz=datetime.timezone.utc
            )

    def is_idling(self):
        """Whether this task is currently idling
        (running, waiting for the next opportunity to continue execution)

        Returns:
            bool: True/False
        """
        return self._is_idling

    def idling_since(self):
        """The last time at which this job object began idling, if available.

        Returns:
            datetime.datetime: The time, if available.
        """
        if self._idling_since_ts:
            return datetime.datetime.fromtimestamp(
                self._idling_since_ts, tz=datetime.timezone.utc
            )

    def failed(self):
        """Whether this job's `.on_run()` method failed an execution attempt,
        due to an unhandled exception being raised.

        Returns:
            bool: True/False
        """
        return self._task_loop.failed()

    def killed(self):
        """Whether this job was killed."""
        return self._killed

    def killed_at(self):
        """The last time at which this job object was killed, if available.

        Returns:
            datetime.datetime: The time, if available.
        """
        if self._killed_at_ts:
            return datetime.datetime.fromtimestamp(
                self._killed_at_ts, tz=datetime.timezone.utc
            )

    def is_being_killed(self, get_reason=False):
        """Whether this job is being killed.

        Args:
            get_reason (bool, optional): If set to True, the reason
              for killing will be returned. Defaults to False.

        Returns:
            bool: True/False
            str: 'INTERNAL_KILLING' or 'EXTERNAL_KILLING' or ''
              depending on if this job is being killed or not.
        """
        if get_reason:
            reason = self.is_being_stopped(get_reason=get_reason)
            if reason in ("INTERNAL_KILLING", "EXTERNAL_KILLING"):
                return reason
            else:
                return ""

        return self._is_being_restarted

    def is_being_startup_killed(self):
        """Whether this job was started up only for it to be killed.
        This is useful for knowing if a job skipped `on_start()` and `on_run()`
        due to that, and can be checked for within `on_stop()`.
        """
        return self._is_being_killed and self._startup_kill

    def completed(self):
        """Whether this job completed successfully.

        Returns:
            bool: True/False
        """
        return self._completed

    def completed_at(self):
        """The last time at which this job object completed successfully,
        if available.

        Returns:
            datetime.datetime: The time, if available.
        """
        if self._completed_at_ts:
            return datetime.datetime.fromtimestamp(
                self._completed_at_ts, tz=datetime.timezone.utc
            )

    def is_being_completed(self):
        """Whether this job is currently completing.

        Returns:
            bool: True/False
        """
        return self._is_being_completed

    def done(self):
        """Whether this job was killed or has completed.

        Returns:
            bool: True/False
        """
        return self._killed or self._completed

    def done_since(self):
        """The last time at which this job object completed successfully or was killed, if available.

        Returns:
            datetime.datetime: The time, if available.
        """
        return self._completed_at_ts or self._killed_at_ts

    def is_being_restarted(self, get_reason=False):
        """Whether this job is being restarted.

        Args:
            get_reason (bool, optional):
                If set to True, the restart reason will be returned.
                Defaults to False.

        Returns:
            bool: True/False
            str: 'INTERNAL_RESTART' or 'EXTERNAL_RESTART' or ''
              depending on if a restart applies.
        """
        if get_reason:
            reason = self.is_being_stopped(get_reason=get_reason)
            if reason in ("INTERNAL_RESTART", "EXTERNAL_RESTART"):
                return reason
            else:
                return ""

        return self._is_being_restarted

    def is_being_guarded(self):
        """Whether this job object is being guarded.

        Returns:
            bool: True/False
        """
        return self._is_being_guarded

    def await_done(
        self, timeout: Optional[float] = None, cancel_if_killed: bool = False
    ):
        """Wait for this job object to be done (completed or killed) using the
        coroutine output of this method.

        Args:
            timeout (float, optional): Timeout for awaiting. Defaults to None.

        Raises:
            JobStateError: This job object is already done or not alive.
            asyncio.TimeoutError: The timeout was exceeded.
            asyncio.CancelledError: The job was killed.

        Returns:
            Coroutine: A coroutine that evaluates to either `KILLED`
              or `COMPLETED` from the `JOB_STATUS` class namespace.
        """
        if not self.alive():
            raise JobStateError("this job object is not alive.")
        elif self.done():
            raise JobStateError("this job object is already done and not alive.")

        fut = self._task_loop.loop.create_future()

        self._done_futures.append(fut)

        return asyncio.wait_for(fut, timeout)

    def await_unguard(self, timeout: Optional[float] = None):
        """Wait for this job object to be unguarded using the
        coroutine output of this method.

        Args:
            timeout (float, optional):
                Timeout for awaiting. Defaults to None.

        Raises:
            JobStateError: This job object is already done or not alive,
              or isn't being guarded.
            asyncio.TimeoutError: The timeout was exceeded.
            asyncio.CancelledError: The job was killed.

        Returns:
            Coroutine: A coroutine that evaluates to `True`.
        """

        if not self.alive():
            raise JobStateError("this job object is not alive")
        elif self.done():
            raise JobStateError("this job object is already done and not alive")
        elif not self._is_being_guarded:
            raise JobStateError("this job object is not being guarded by a job")

        fut = self._task_loop.loop.create_future()

        if self._unguard_futures is None:
            self._unguard_futures = []

        self._unguard_futures.append(fut)

        return asyncio.wait_for(fut, timeout)

    def get_output_queue_proxy(self):
        """Get a job output queue proxy object for more convenient
        reading of job output queues while this job is running.

        Raises:
            JobStateError: This job object is already done or not alive,
              or isn't being guarded.
            TypeError: Output queues aren't
              defined for this job type.

        Returns:
            JobOutputQueueProxy: The output queue proxy.
        """

        if not self.alive():
            raise JobStateError("this job object is not alive")
        elif self.done():
            raise JobStateError("this job object is already done and not alive")

        if self.OUTPUT_QUEUES:
            output_queue_proxy = JobOutputQueueProxy(self)
            self._output_queue_proxies.append(output_queue_proxy)
            return output_queue_proxy

        raise TypeError("this job object does not support output queues")

    def verify_output_field_support(self, field_name: str, raise_exceptions=False):
        """Verify if a specified output field name is supported by this job,
        or if it supports output fields at all.

        Args:
            field_name (str): The name of the output field to set.
            raise_exceptions (bool, optional): Whether exceptions
              should be raised. Defaults to False.

        Raises:
            TypeError: Output fields aren't supported for this job,
              or `field_name` is not a string.
            LookupError: The specified field name is not defined by this job.
        """
        if not self.OUTPUT_FIELDS:
            if raise_exceptions:
                raise TypeError(
                    f"'{self.__class__.__name__}' class does not"
                    f" define any fields in 'OUTPUT_FIELDS' class attribute"
                )
            return False

        elif field_name not in self.OUTPUT_FIELDS:
            if raise_exceptions:
                raise (
                    LookupError(
                        f"field name '{field_name}' is not defined in"
                        f" 'OUTPUT_FIELDS' of '{self.__class__.__name__}' class"
                    )
                    if isinstance(field_name, str)
                    else TypeError(
                        f"'field_name' argument must be of type str,"
                        f" not {field_name.__class__.__name__}"
                    )
                )
            return False

        return True

    def verify_output_queue_support(self, queue_name: str, raise_exceptions=False):
        """Verify if a specified output queue name is supported by this job,
        or if it supports output queues at all.

        Args:
            queue_name (str): The name of the output queue to set.
            raise_exceptions (bool, optional): Whether exceptions should be
              raised. Defaults to False.

        Raises:
            TypeError: Output queues aren't supported for this job,
              or `queue_name` is not a string.
            LookupError: The specified queue name is not defined by this job.
        """
        if not self.OUTPUT_QUEUES:
            if raise_exceptions:
                raise TypeError(
                    f"'{self.__class__.__name__}' class does not"
                    f" define any fields in 'OUTPUT_FIELDS' class attribute"
                )
            return False

        elif queue_name not in self.OUTPUT_QUEUES:
            if raise_exceptions:
                raise (
                    LookupError(
                        f"field name '{queue_name}' is not defined in"
                        f" 'OUTPUT_FIELDS' of '{self.__class__.__name__}' class"
                    )
                    if isinstance(queue_name, str)
                    else TypeError(
                        f"'queue_name' argument must be of type str,"
                        f" not {queue_name.__class__.__name__}"
                    )
                )
            return False

        return True

    def set_output_field(self, field_name: str, value: Any):
        """Set the specified output field to have the given value,
        while releasing the value to external jobs awaiting the field.

        Args:
            field_name (str): The name of the output field to set.

        Raises:
            TypeError: Output fields aren't supported for this job,
              or `field_name` is not a string.
            LookupError: The specified field name is not defined by this job.
            JobStateError: An output field value has already been set.
        """

        self.verify_output_field_support(field_name, raise_exceptions=True)

        field_value = self._output_fields[field_name]

        if field_value is not UNSET:
            raise JobStateError(
                "An output field value has already been set for the field"
                f" '{field_name}'"
            )

        self._output_fields[field_name] = value

        for fut in self._output_field_futures[field_name]:
            if not fut.cancelled():
                fut.set_result(field_value)

        self._output_field_futures[field_name].clear()

    def push_output_queue(self, queue_name: str, value: Any):
        """Add a value to the specified output queue,
        while releasing the value to external jobs
        awaiting the field.

        Args:
            queue_name (str): The name of the target output queue.

        Raises:
            TypeError: Output queues aren't supported for this job,
              or `queue_name` is not a string.
            LookupError: The specified queue name is not defined by this job.
            JobStateError: An output field value has already been set.
        """

        self.verify_output_queue_support(queue_name, raise_exceptions=True)

        queue_entries: list = self._output_queues[queue_name]
        queue_entries.append(value)

        for fut, cancel_if_cleared in self._output_queue_futures[queue_name]:
            if not fut.cancelled():
                fut.set_result(value)

        self._output_queue_futures[queue_name].clear()

    def get_output_field(self, field_name: str, default=UNSET):
        """Get the value of a specified output field.

        Args:
            field_name (str): The name of the target output field.
            default (object, optional): The value to return if the specified
              output field does not exist, has not been set,
              or if this job doesn't support them at all.
              Defaults to `UNSET`, which will
              trigger an exception.

        Raises:
            TypeError: Output fields aren't supported for this job,
              or `field_name` is not a string.
            LookupError: The specified field name is not defined by this job.
            JobStateError: An output field value is not set.

        Returns:
            object: The output field value.
        """

        if not self.OUTPUT_FIELDS:
            if default is UNSET:
                self.verify_output_field_support(field_name, raise_exceptions=True)
            return default

        elif field_name not in self.OUTPUT_FIELDS:
            if default is UNSET:
                self.verify_output_field_support(field_name, raise_exceptions=True)
            return default

        old_field_data_list: list = self._output_fields[field_name]

        if not old_field_data_list[1]:
            if default is UNSET:
                raise JobStateError(
                    "An output field value has not been set for the field"
                    f" '{field_name}'"
                )
            return default

        return old_field_data_list[0]

    def get_output_queue_contents(self, queue_name: str):
        """Get a list of all values present in the specified output queue.
        For continuous access to job output queues, consider requesting
        a `JobOutputQueueProxy` object using `.get_output_queue_proxy()`.

        Args:
            queue_name (str): The name of the target output queue.
            default (object, optional): The value to return if the specified
              output queue does not exist, is empty,
              or if this job doesn't support them at all.
              Defaults to `UNSET`, which will
              trigger an exception.

        Raises:
            TypeError: Output queues aren't supported for this job,
              or `queue_name` is not a string.
            LookupError: The specified queue name is not defined by this job.

        Returns:
            list: A list of values.
        """

        self.verify_output_queue_support(queue_name, raise_exceptions=True)

        queue_data_list: list = self._output_queues[queue_name]

        if not queue_data_list:
            raise JobStateError(f"The specified output queue '{queue_name}' is empty")

        return queue_data_list[:]

    def clear_output_queue(self, queue_name: str):
        """Clear all values in the specified output queue.

        Args:
            queue_name (str): The name of the target output field.
        """
        self.verify_output_queue_support(queue_name, raise_exceptions=True)

        for output_queue_proxy in self._output_queue_proxies:
            output_queue_proxy._queue_clear_alert(queue_name)

        for fut, cancel_if_cleared in self._output_queue_futures[queue_name]:
            if not fut.cancelled():
                if cancel_if_cleared:
                    fut.cancel(f"The job output queue '{queue_name}' was cleared")
                else:
                    fut.set_result(UNSET)

        self._output_queues[queue_name].clear()

    def get_output_field_names(self):
        """Get all output field names that this job supports.

        Returns:
            tuple: A tuple of the supported output fields.
        """
        return tuple(self.OUTPUT_FIELDS)

    def get_output_queue_names(self):
        """Get all output queue names that this job supports.

        Returns:
            tuple: A tuple of the supported output queues.
        """
        return tuple(self.OUTPUT_QUEUES)

    def has_output_field_name(self, field_name: str):
        """Whether the specified field name is supported as an
        output field.

        Args:
            field_name (str): The name of the target output field.

        Returns:
            bool: True/False
        """

        if not isinstance(field_name, str):
            raise TypeError(
                f"'field_name' argument must be of type str,"
                f" not {field_name.__class__.__name__}"
            )

        return field_name in self.OUTPUT_FIELDS

    def has_output_queue_name(self, queue_name: str):
        """Whether the specified queue name is supported as an
        output queue.

        Args:
            queue_name (str): The name of the target output queue.

        Returns:
            bool: True/False
        """

        if not isinstance(queue_name, str):
            raise TypeError(
                f"'queue_name' argument must be of type str,"
                f" not {queue_name.__class__.__name__}"
            )

        return queue_name in self.OUTPUT_QUEUES

    def output_field_is_set(self, field_name: str):
        """Whether a value for the specified output field
        has been set.

        Args:
            field_name (str): The name of the target output field.

        Raises:
            TypeError: Output fields aren't supported for this job,
              or `field_name` is not a string.
            LookupError: The specified field name is not defined by this job.

        Returns:
            bool: True/False
        """

        self.verify_output_field_support(field_name, raise_exceptions=True)

        field_value = self._output_fields[field_name]

        return field_value is not UNSET

    def output_queue_is_empty(self, queue_name: str):
        """Whether the specified output queue is empty.

        Args:
            queue_name (str): The name of the target output queue.

        Raises:
            TypeError: Output queues aren't supported for this job,
              or `queue_name` is not a string.
            LookupError: The specified queue name is not defined by this job.

        Returns:
            bool: True/False
        """

        self.verify_output_queue_support(queue_name, raise_exceptions=True)

        return not self._output_queues[queue_name]

    def await_output_field(self, field_name: str, timeout: Optional[float] = None):
        """Wait for this job object to release the value of a
        specified output field while it is running, using the
        coroutine output of this method.

        Args:
            field_name (str): The name of the target output field.
            timeout (float, optional): The maximum amount of
              time to wait in seconds. Defaults to None.

        Raises:
            TypeError: Output fields aren't supported for this job,
              or `field_name` is not a string.
            LookupError: The specified field name is not defined by this job.
            JobStateError: This job object is already done.
            asyncio.TimeoutError: The timeout was exceeded.
            asyncio.CancelledError: The job was killed.

        Returns:
            Coroutine: A coroutine that evaluates to the value of specified
              output field.
        """

        self.verify_output_field_support(field_name, raise_exceptions=True)

        if self.done():
            raise JobStateError("this job object is already done and not alive.")

        fut = self._task_loop.loop.create_future()
        self._output_field_futures[field_name].append(fut)

        return asyncio.wait_for(fut, timeout=timeout)

    def await_output_queue_add(
        self,
        queue_name: str,
        timeout: Optional[float] = None,
        cancel_if_cleared: bool = True,
    ):
        """Wait for this job object to add to the specified output queue while
        it is running, using the coroutine output of this method.

        Args:
            timeout (float, optional): The maximum amount of time to wait in
              seconds. Defaults to None.
            cancel_if_cleared (bool, optional): Whether `asyncio.CancelledError` should
              be raised if the output queue is cleared. If set to `False`,
              `UNSET` will be the result of the coroutine. Defaults to False.

        Raises:
            TypeError: Output fields aren't supported for this job,
              or `field_name` is not a string.
            LookupError: The specified field name is not defined by this job
            JobStateError: This job object is already done.
            asyncio.TimeoutError: The timeout was exceeded.
            asyncio.CancelledError: The job was killed, or the output queue
              was cleared.

        Returns:
            Coroutine: A coroutine that evaluates to the most recent output
              queue value, or `UNSET` if the queue is cleared.
        """

        self.verify_output_queue_support(queue_name, raise_exceptions=True)

        if self.done():
            raise JobStateError("this job object is already done and not alive.")

        fut = self._task_loop.loop.create_future()
        self._output_queue_futures[queue_name].append((fut, cancel_if_cleared))

        return asyncio.wait_for(fut, timeout=timeout)

    def verify_public_method_suppport(self, method_name: str, raise_exceptions=False):
        """Verify if a job has a public method exposed under the specified name is
        supported by this job, or if it supports public methods at all.

        Args:
            method_name (str): The name of the public method.
            raise_exceptions (bool, optional): Whether exceptions
              should be raised. Defaults to False.

        Raises:
            TypeError: Output fields aren't supported for this job,
              or `field_name` is not a string.
            LookupError: The specified field name is not defined by this job.
        """
        if not self.PUBLIC_METHODS:
            if raise_exceptions:
                raise TypeError(
                    f"'{self.__class__.__name__}' class does not"
                    f" support any public methods"
                )
            return False

        elif method_name not in self.PUBLIC_METHODS:
            if raise_exceptions:
                raise (
                    LookupError(
                        f"no public method under the specified name '{method_name}' is "
                        "not defined by the class of this job"
                    )
                    if isinstance(method_name, str)
                    else TypeError(
                        f"'method_name' argument must be of type str,"
                        f" not {method_name.__class__.__name__}"
                    )
                )
            return False

        return True

    def get_public_method_names(self):
        """Get the names of all public methods that this job supports.

        Returns:
            tuple: A tuple of the names of the supported methods.
        """
        return tuple(self.PUBLIC_METHODS.keys())

    def has_public_method_name(self, method_name: str):
        """Whether a public method under the specified name is supported by this job.

        Args:
            method_name (str): The name of the target method

        Returns:
            bool: True/False
        """

        if not isinstance(method_name, str):
            raise TypeError(
                f"'method_name' argument must be of type str,"
                f" not {method_name.__class__.__name__}"
            )

        return method_name in self.PUBLIC_METHODS

    def public_method_is_async(self, method_name: str):
        """Whether a public method under the specified name is a coroutine function.

        Args:
            method_name (str): The name of the target method.

        Returns:
            bool: True/False
        """

        self.verify_public_method_suppport(method_name, raise_exceptions=True)

        return inspect.iscoroutinefunction(self.PUBLIC_METHODS[method_name])

    def run_public_method(self, method_name: str, *args, **kwargs):
        """Run a public method under the specified name and return the
        result.

        Args:
            method_name (str): The name of the target method.

        Returns:
            object: The result of the call.
        """

        self.verify_public_method_suppport(method_name, raise_exceptions=True)

        method = self.PUBLIC_METHODS[method_name]

        return method(self, *args, **kwargs)

    def status(self):
        """Get the job status of this job as a value from the
        `JOB_STATUS` class namespace.

        Returns:
            str: A status value.
        """
        output = None
        if self.alive():
            if self.is_running():
                if self.is_starting():
                    output = JOB_STATUS.STARTING
                elif self.is_idling():
                    output = JOB_STATUS.IDLING
                elif self.is_awaiting():
                    output = JOB_STATUS.AWAITING
                elif self.is_being_completed():
                    output = JOB_STATUS.COMPLETING
                elif self.is_being_killed():
                    output = JOB_STATUS.DYING
                elif self.is_being_restarted():
                    output = JOB_STATUS.RESTARTING
                elif self.is_being_stopped():
                    output = JOB_STATUS.STOPPING
                else:
                    output = JOB_STATUS.RUNNING
            elif self.stopped():
                output = JOB_STATUS.STOPPED
            elif self.initialized():
                output = JOB_STATUS.INITIALIZED

        elif self.completed():
            output = JOB_STATUS.COMPLETED
        elif self.killed():
            output = JOB_STATUS.KILLED
        else:
            output = JOB_STATUS.FRESH

        return output

    def __str__(self):
        output_str = (
            f"<{self.__class__.__name__} "
            f"(ID={self._identifier} CREATED_AT={self.created_at} "
            f"PERM_LVL={PERM_LEVELS.get_name(self._PERMISSION_LEVEL)} "
            f"STATUS={self.status()})>"
        )

        return output_str


class IntervalJobBase(JobBase):
    """Base class for interval based jobs.
    Subclasses are expected to overload the `on_run()` method.
    `on_start()` and `on_stop()` and `on_run_error(exc)`
    can optionally be overloaded.

    One can override the class variables `DEFAULT_SECONDS`,
    `DEFAULT_MINUTES`, `DEFAULT_HOURS`, `DEFAULT_COUNT`
    and `DEFAULT_RECONNECT` in subclasses. They are derived
    from the keyword arguments of the `discord.ext.tasks.Loop`
    constructor. These will act as defaults for each job
    object created from this class.
    """

    DEFAULT_INTERVAL = datetime.timedelta()

    DEFAULT_COUNT: Optional[int] = None
    DEFAULT_RECONNECT = True

    def __init__(
        self,
        interval: Optional[datetime.timedelta] = None,
        count: int = -1,
        reconnect: Optional[bool] = None,
    ):
        """Create a new `IntervalJobBase` instance.

        Args:
            interval (Optional[datetime.timedelta], optional):
            count (Optional[int], optional):
            reconnect (Optional[bool], optional): Overrides for the default class
              variables for an `IntervalJobBase` instance.
        """

        super().__init__()
        self._interval_secs = (
            self.DEFAULT_INTERVAL.total_seconds()
            if interval is None
            else interval.total_seconds()
        )
        self._count = self.DEFAULT_COUNT if count <= 0 else count
        self._reconnect = not not (
            self.DEFAULT_RECONNECT if reconnect is None else reconnect
        )
        self._loop_count = 0
        self._task_loop = tasks.Loop(
            self._on_run,
            seconds=self._interval_secs,
            hours=0,
            minutes=0,
            count=self._count,
            reconnect=self._reconnect,
            loop=None,
        )

        self._task_loop.before_loop(self._on_start)
        self._task_loop.after_loop(self._on_stop)
        self._task_loop.error(self._on_run_error)

    def next_iteration(self):
        """When the next iteration of `.on_run()` will occur.
        If not known, this method will return `None`.

        Returns:
            Optional[datetime.datetime]: The time at which
              the next iteration will occur, if available.
        """
        return self._task_loop.next_iteration()

    def get_interval(self):
        """Returns a tuple of the seconds, minutes and hours at which this job
        object is executing its `.on_run()` method.

        Returns:
            tuple: `(seconds, minutes, hours)`
        """
        return self._task_loop.seconds, self._task_loop.minutes, self._task_loop.hours

    def change_interval(
        self,
        seconds: int = 0,
        minutes: int = 0,
        hours: int = 0,
    ):
        """Change the interval at which this job will run its `on_run()` method.
        This will only be applied on the next iteration of `on_run()`.

        Args:
            seconds (Optional[Union[int, float]], optional): Defaults to 0.
            minutes (Optional[Union[int, float]], optional): Defaults to 0.
            hours (Optional[Union[int, float]], optional): Defaults to 0.
        """
        self._task_loop.change_interval(
            seconds=seconds,
            minutes=minutes,
            hours=hours,
        )

        self._interval_secs = seconds + (minutes * 60.0) + (hours * 3600.0)

    async def on_start(self):
        pass

    async def _on_run(self):
        if self._startup_kill or self._skip_on_run:
            return

        self._is_idling = False
        self._idling_since_ts = None

        await self.on_run()
        if self._interval_secs:  # There is a task loop interval set
            self._is_idling = True
            self._idling_since_ts = time.time()

        self._loop_count += 1

    async def on_run(self):
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        The code to run at the set interval.
        This method must be overloaded in subclasses.

        Raises:
            NotImplementedError: This method must be overloaded in subclasses.
        """
        raise NotImplementedError()

    async def on_stop(self, reason, by_force):
        pass


class EventJobBase(JobBase):
    """A job base class for jobs that run in reaction to specific events
    passed to them by their job manager object.
    Subclasses are expected to overload the `on_run(self, event)` method.
    `on_start()` and `on_stop()` and `on_run_error(self, exc)` can
    optionally be overloaded.
    One can also override the class variables `DEFAULT_COUNT` and `DEFAULT_RECONNECT`
    in subclasses. They are derived from the keyword arguments of the
    `discord.ext.tasks.loop` decorator. Unlike `IntervalJobBase` class instances,
    the instances of this class depend on their job manager to trigger
    the execution of their `.on_run()` method, and will stop running if
    all ClientEvent objects passed to them have been processed.

    Attributes:
        EVENT_TYPES: A tuple denoting the set of `BaseEvent` classes whose
          instances should be recieved after their corresponding event is
          registered by the job manager of an instance of this class. By
          default, all instances of `BaseEvent` will be propagated.
    """

    EVENT_TYPES: tuple[events.BaseEvent] = (events.BaseEvent,)

    DEFAULT_INTERVAL: datetime.timedelta = datetime.timedelta()
    DEFAULT_COUNT: Optional[int] = None
    DEFAULT_RECONNECT: bool = True

    DEFAULT_MAX_EVENT_CHECKS_PER_ITERATION: Optional[int] = None

    DEFAULT_EMPTY_QUEUE_TIMEOUT: Optional[datetime.timedelta] = datetime.timedelta()

    DEFAULT_MAX_QUEUE_SIZE: Optional[int] = None

    DEFAULT_ALLOW_QUEUE_OVERFLOW: bool = False

    DEFAULT_BLOCK_QUEUE_ON_STOP: bool = False
    DEFAULT_START_ON_DISPATCH: bool = True
    DEFAULT_BLOCK_QUEUE_WHILE_STOPPED: bool = False
    DEFAULT_CLEAR_QUEUE_AT_STARTUP: bool = False

    __slots__ = (
        "_pre_event_queue",
        "_event_queue",
        "_last_event",
        "_max_event_checks_per_iteration",
        "_empty_queue_timeout_secs",
        "_max_queue_size",
        "_allow_queue_overflow",
        "_block_queue_on_stop",
        "_start_on_dispatch",
        "_block_queue_while_stopped",
        "_clear_queue_at_startup",
        "_allow_dispatch",
        "_stopping_by_empty_queue",
        "_stopping_by_idling_timeout",
    )

    def __init_subclass__(cls, permission_level=None):
        if not cls.EVENT_TYPES:
            raise TypeError("the 'EVENT_TYPES' class attribute must not be empty")

        elif not isinstance(cls.EVENT_TYPES, (list, tuple)):
            raise TypeError(
                "the 'EVENT_TYPES' class attribute must be of type 'tuple' and "
                "must contain one or more subclasses of `BaseEvent`"
            )
        elif not all(issubclass(et, events.BaseEvent) for et in cls.EVENT_TYPES):
            raise ValueError(
                "the 'EVENT_TYPES' class attribute "
                "must contain one or more subclasses of `BaseEvent`"
            )

        super().__init_subclass__(permission_level=permission_level)

    def __init__(
        self,
        interval: Optional[datetime.timedelta] = None,
        count: Union[int, UNSET_TYPE] = UNSET,
        reconnect: Optional[bool] = None,
        max_event_checks_per_iteration: Optional[Union[int, UNSET_TYPE]] = UNSET,
        empty_queue_timeout: Optional[Union[datetime.timedelta, UNSET_TYPE]] = UNSET,
        max_queue_size: Optional[int] = None,
        allow_queue_overflow: Optional[bool] = None,
        block_queue_on_stop: Optional[bool] = None,
        block_queue_while_stopped: Optional[bool] = None,
        clear_queue_at_startup: Optional[bool] = None,
        start_on_dispatch: Optional[bool] = None,
    ):
        super().__init__()

        self._interval_secs = (
            self.DEFAULT_INTERVAL.total_seconds()
            if interval is None
            else interval.total_seconds()
        )
        self._count = self.DEFAULT_COUNT if count is UNSET else count

        self._reconnect = not not (
            self.DEFAULT_RECONNECT if reconnect is None else reconnect
        )

        max_event_checks_per_iteration = (
            self.DEFAULT_MAX_EVENT_CHECKS_PER_ITERATION
            if max_event_checks_per_iteration is UNSET
            else max_event_checks_per_iteration
        )
        if isinstance(max_event_checks_per_iteration, (int, float)):
            self._max_event_checks_per_iteration = int(max_event_checks_per_iteration)
            if self._max_event_checks_per_iteration <= 0:
                self._max_event_checks_per_iteration = None
        else:
            self._max_event_checks_per_iteration = None

        empty_queue_timeout = (
            self.DEFAULT_EMPTY_QUEUE_TIMEOUT
            if empty_queue_timeout is UNSET
            else empty_queue_timeout
        )
        if isinstance(empty_queue_timeout, datetime.timedelta):
            self._empty_queue_timeout_secs = empty_queue_timeout.total_seconds()
        else:
            self._empty_queue_timeout_secs = None

        max_queue_size = (
            self.DEFAULT_MAX_QUEUE_SIZE if max_queue_size is UNSET else max_queue_size
        )
        if isinstance(max_queue_size, (int, float)):
            self._max_queue_size = int(max_queue_size)
        else:
            self._max_queue_size = None

        self._allow_queue_overflow = not not (
            self.DEFAULT_ALLOW_QUEUE_OVERFLOW
            if allow_queue_overflow is None
            else allow_queue_overflow
        )

        self._block_queue_on_stop = not not (
            self.DEFAULT_BLOCK_QUEUE_ON_STOP
            if block_queue_on_stop is None
            else block_queue_on_stop
        )
        self._start_on_dispatch = not not (
            self.DEFAULT_START_ON_DISPATCH
            if start_on_dispatch is None
            else start_on_dispatch
        )
        self._block_queue_while_stopped = not not (
            self.DEFAULT_BLOCK_QUEUE_WHILE_STOPPED
            if block_queue_while_stopped is None
            else block_queue_while_stopped
        )
        self._clear_queue_at_startup = not not (
            self.DEFAULT_CLEAR_QUEUE_AT_STARTUP
            if clear_queue_at_startup is None
            else clear_queue_at_startup
        )

        if self._block_queue_while_stopped or self._clear_queue_at_startup:
            self._start_on_dispatch = False

        self._allow_dispatch = True

        self._stopping_by_empty_queue = False
        self._stopping_by_idling_timeout = False

        self._pre_event_queue = deque()
        self._event_queue = deque(maxlen=self._max_queue_size)
        self._last_event = None

        self._task_loop = tasks.Loop(
            self._on_run,
            seconds=0,
            hours=0,
            minutes=0,
            count=None,
            reconnect=self._reconnect,
            loop=None,
        )
        self._task_loop.before_loop(self._on_start)
        self._task_loop.after_loop(self._on_stop)
        self._task_loop.error(self._on_run_error)

    def _add_event(self, event: events.BaseEvent):
        task_is_running = self._task_loop.is_running()
        if (
            not self._allow_dispatch
            or (self._block_queue_on_stop and self._is_being_stopped)
            or (self._block_queue_while_stopped and not task_is_running)
        ):
            return

        self._pre_event_queue.append(event)
        if self._start_on_dispatch and not task_is_running:
            self._task_loop.start()

    def check_event(self, event: events.BaseEvent):
        """A method for subclasses that can be overloaded to perform validations on a `BaseEvent`
        instance that was dispatched to them. Must return a boolean value indicating the
        validaiton result. If not overloaded, this method will always return `True`.

        Args:
            event (events.BaseEvent): The event object to run checks upon.
        """
        return True

    def get_last_event(self):
        """Get the last event dispatched to this event job object.

        Returns:
            BaseEvent: The event object.
        """
        return self._last_event

    def loop_count(self):
        """The current amount of `on_run()` calls completed by this job object."""
        return self._loop_count

    def _filter_events(self):
        iterator_obj = (
            range(self._max_event_checks_per_iteration)
            if self._max_event_checks_per_iteration
            else itertools.count()
        )

        for _ in iterator_obj:
            if not self._pre_event_queue:
                break
            elif (
                len(self._event_queue) == self._max_queue_size
                and not self._allow_queue_overflow
            ):
                break

            event = self._pre_event_queue.popleft()

            if self.check_event(event):
                self._event_queue.append(event)

    async def _on_start(self):
        if self._clear_queue_at_startup:
            self._event_queue.clear()

        await super()._on_start()

    async def on_start(self):
        pass

    async def _on_run(self):
        if self._startup_kill or self._skip_on_run:
            return

        if self._pre_event_queue:
            self._filter_events()

        if not self._event_queue:
            if not self._empty_queue_timeout_secs:
                if (
                    self._empty_queue_timeout_secs is None
                ):  # idle indefinitely until an event is recieved.
                    if not self._is_idling:
                        self._is_idling = True
                        self._idling_since_ts = time.time()
                        return
                    else:
                        return
                else:  # self._empty_queue_timeout_secs is zero
                    self._stopping_by_empty_queue = True
                    self.STOP()
                    return

            elif not self._is_idling:
                self._is_idling = True
                self._idling_since_ts = time.time()

            if (
                self._is_idling
                and (time.time() - self._idling_since_ts)
                > self._empty_queue_timeout_secs
            ):
                self._stopping_by_idling_timeout = True
                self.STOP()
                return
            else:
                return

        elif self._loop_count == self._count:
            self.STOP()
            return

        self._is_idling = False
        self._idling_since_ts = None

        self._stopping_by_idling_timeout = False

        event = self._event_queue.popleft()
        await self.on_run(event)
        self._last_event = event

        self._loop_count += 1

        if self._interval_secs:
            self._is_idling = True
            self._idling_since_ts = time.time()
            delta = self._interval_secs
            while delta > MAX_ASYNCIO_SECONDS:
                await asyncio.sleep(MAX_ASYNCIO_SECONDS)
                delta -= MAX_ASYNCIO_SECONDS
            await asyncio.sleep(max(delta, 0))

    async def on_run(self, event: events.BaseEvent):
        """The code to run whenever an event is recieved.
        This method must be overloaded in subclasses.

        Raises:
            NotImplementedError: This method must be overloaded in subclasses.
        """
        raise NotImplementedError()

    async def _on_stop(self):
        try:
            await super()._on_stop()
        finally:  # reset some attributes in case an exception is raised
            self._loop_count = 0
            self._stopping_by_idling_timeout = False

    async def on_stop(self, reason, by_force):
        pass

    def get_queue_size(self):
        """Get the count of events stored in the queue.

        Returns:
            int: The queue sizee.
        """
        return len(self._event_queue)

    def clear_queue(self):
        """Clear the current event queue."""
        self._pre_event_queue.clear()
        self._event_queue.clear()

    @contextmanager
    def queue_blocker(self):
        """A method to be used as a context manager for
        temporarily blocking the event queue of this event job
        while running an operation, thereby disabling event dispatch to it.
        """
        try:
            self._allow_dispatch = False
            yield
        finally:
            self._allow_dispatch = True

    def queue_is_blocked(self):
        """Whether event dispatching to this event job's event queue
        is disabled and its event queue is blocked.

        Returns:
            bool: True/False
        """
        return not self._allow_dispatch

    def block_queue(self):
        """Block the event queue of this event job, thereby disabling
        event dispatch to it.
        """
        self._allow_dispatch = False

    def unblock_queue(self):
        """Unblock the event queue of this event job, thereby enabling
        event dispatch to it.
        """
        self._allow_dispatch = True

    def is_being_stopped(self, get_reason: bool = False):
        output = self._is_being_stopped
        if get_reason:
            reason = None
            if not self._is_being_stopped:
                reason = ""
            elif self._task_loop.failed():
                reason = JOB_STOP_REASONS.INTERNAL_ERROR
            elif (
                not self._empty_queue_timeout_secs
                and self._empty_queue_timeout_secs is not None
                and self._stopping_by_empty_queue
            ):
                reason = JOB_STOP_REASONS.INTERNAL_EMPTY_QUEUE
            elif self._stopping_by_idling_timeout:
                reason = JOB_STOP_REASONS.INTERNAL_IDLING_TIMEOUT
            elif self._loop_count == self._count:
                reason = JOB_STOP_REASONS.INTERNAL_COUNT_LIMIT
            elif self._stopping_by_self:
                if self._is_being_restarted:
                    reason = JOB_STOP_REASONS.INTERNAL_RESTART
                elif self._is_being_completed:
                    reason = JOB_STOP_REASONS.INTERNAL_COMPLETION
                elif self._is_being_killed:
                    reason = JOB_STOP_REASONS.INTERNAL_KILLING
                else:
                    reason = JOB_STOP_REASONS.INTERNAL
            elif not self._stopping_by_self:
                if self._is_being_restarted:
                    reason = JOB_STOP_REASONS.EXTERNAL_RESTART
                elif self._is_being_killed:
                    reason = JOB_STOP_REASONS.EXTERNAL_KILLING
                else:
                    reason = JOB_STOP_REASONS.EXTERNAL

            output = reason
        return output


@singletonjob
@_sysjob
class JobManagerJob(IntervalJobBase):
    """A singleton job that represents the job manager. Its very high permission
    level and internal protections prevents it from being instantiated
    or modified by other jobs.
    """

    def __init__(self):
        super().__init__()

    async def on_run(self):
        await self.await_done()


JobManagerJob.__init_subclass__()


from .manager import JobManagerProxy
from .proxies import JobProxy, JobOutputQueueProxy
