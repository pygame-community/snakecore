"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file implements a job manager class for running and managing job objects
at runtime. 
"""

import asyncio
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager, contextmanager
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
from snakecore.constants import UNSET, _UnsetType

from snakecore.constants.enums import (
    _JOB_OPS_PRES_CONT,
    JobPermissionLevels,
    JobOps,
)
from snakecore.exceptions import (
    JobException,
    JobPermissionError,
    JobStateError,
)
from snakecore.utils import utils
from snakecore import events
from . import jobs, loops

__all__ = (
    "create_scheduling_executor",
    "shutdown_scheduling_executor",
    "scheduling_executor_exists",
)

GLOBAL_MANAGER_DATA = {
    "scheduling_executor": {
        "executor": None,
        "semaphore": None,
        "acquire_count": 0,
    },
}


def create_scheduling_executor(max_workers: int = 4):
    if not GLOBAL_MANAGER_DATA["scheduling_executor"]["executor"]:
        GLOBAL_MANAGER_DATA["scheduling_executor"]["executor"] = ProcessPoolExecutor(
            max_workers=max_workers
        )
        GLOBAL_MANAGER_DATA["scheduling_executor"]["semaphore"] = asyncio.Semaphore(
            max_workers
        )
        return

    raise RuntimeError(
        "a scheduling executor has already been created for job scheduling"
    )


def shutdown_scheduling_executor():
    if GLOBAL_MANAGER_DATA["scheduling_executor"]["acquire_count"]:
        raise RuntimeError(
            "cannot shutdown executor while it is acquired by a job manager"
        )

    if GLOBAL_MANAGER_DATA["scheduling_executor"]["executor"] is not None:
        GLOBAL_MANAGER_DATA["scheduling_executor"]["executor"].shutdown()
        GLOBAL_MANAGER_DATA["scheduling_executor"]["executor"] = None
        GLOBAL_MANAGER_DATA["scheduling_executor"]["semaphore"] = None


def scheduling_executor_exists():
    return GLOBAL_MANAGER_DATA["scheduling_executor"]["executor"] is not None


@asynccontextmanager
async def acquired_scheduling_executor() -> ProcessPoolExecutor:

    if not scheduling_executor_exists():
        create_scheduling_executor()

    await GLOBAL_MANAGER_DATA["scheduling_executor"]["semaphore"].acquire()
    GLOBAL_MANAGER_DATA["scheduling_executor"]["acquire_count"] += 1

    try:
        yield GLOBAL_MANAGER_DATA["scheduling_executor"]["executor"]
    finally:
        GLOBAL_MANAGER_DATA["scheduling_executor"]["semaphore"].release()
        GLOBAL_MANAGER_DATA["scheduling_executor"]["acquire_count"] -= 1


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
    ):
        """Create a new job manager instance.

        Args:
            loop (Optional[asyncio.AbstractEventLoop], optional): The event loop to use for this job
              manager and all of its jobs. Defaults to None.
            global_job_timeout (Optional[float], optional): The default global job timeout
              in seconds. Defaults to None.
        """
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()

        self._created_at = datetime.datetime.now(datetime.timezone.utc)
        self._runtime_identifier = (
            f"{id(self)}-{int(self._created_at.timestamp()*1_000_000_000)}"
        )

        self._loop = loop
        self._event_job_ids = {}
        self._job_class_info_dict: dict[Type[jobs.ManagedJobBase], dict[str, Union[int, JobPermissionLevels]]] = {}
        self._default_permission_level: Optional[JobPermissionLevels] = None
        self._job_id_map = {}
        self._manager_job = None
        self._event_waiting_queues = {}
        self._schedule_dict: dict[str, dict[str, Any]] = {"0": {}}
        # zero timestamp for failed scheduling attempts
        self._schedule_ids = set()
        self._schedule_dict_fails = {}
        self._schedule_dict_lock = asyncio.Lock()
        self._initialized = False
        self._is_running = False
        self._scheduling_is_initialized = False
        self._scheduling_initialized_futures = []
        self._scheduling_uninitialized_futures = []

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

    def _check_scheduling_init(self):
        if not self._scheduling_is_initialized:
            raise RuntimeError(
                "job scheduling was not initialized for this job manager"
            )

    def _check_within_job(self):
        _rand = random.getrandbits(4)
        current_job: Union[jobs.ManagedJobBase, int] = loops._current_job.get(_rand)
        
        if current_job is not _rand:
            if not isinstance(current_job, jobs.ManagedJobBase):
                raise RuntimeError("could not determine the current job of this execution context")
            elif current_job._runtime_identifier in self._job_id_map:
                raise JobPermissionError("explicitly using job managers from within their jobs is not allowed")

        return True

    def _check_job_class_registered(self, cls: Type[jobs.ManagedJobBase]):
        if not any(supercls in self._job_class_info_dict for supercls in cls.__mro__[:-1]):
            raise RuntimeError(f"class '{cls.__name__}' and none of its non-virtual "
            "superclasses are registered under this job manager for job registration")
        return True
        
    @property
    def identifier(self) -> str:
        return self._runtime_identifier

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
        
        self._check_within_job()
        self._global_job_stop_timeout = timeout

    @staticmethod
    def _unpickle_dict(byte_data):
        unpickled_data = pickle.loads(byte_data)

        if not isinstance(unpickled_data, dict):
            raise TypeError(
                f"invalid object of type '{unpickled_data.__class__}' in pickle data, "
                "must be of type 'dict'"
            )
        return unpickled_data

    @staticmethod
    def _pickle_dict(target_dict):
        if not isinstance(target_dict, dict):
            raise TypeError(
                "argument 'target_dict' must be of type 'dict', "
                f"not {target_dict.__class__}"
            )

        pickled_data = pickle.dumps(target_dict)
        return pickled_data

    def get_default_permission_level(self) -> Optional[JobPermissionLevels]:
        return self._default_permission_level

    def set_default_permission_level(self, permission_level: JobPermissionLevels):
        if not isinstance(permission_level, JobPermissionLevels):
            raise TypeError("argument 'permission_level' must be a usable enum value from the 'JobPermissionLevels' enum")
        elif permission_level >= JobPermissionLevels.SYSTEM:
            raise ValueError("argument 'permission_level' must be a usable enum value from the 'JobPermissionLevels' enum")

        self._default_permission_level = permission_level

    def register_job_class(self, cls: Type[jobs.ManagedJobBase], permission_level: Optional[JobPermissionLevels] = None, _iv: Optional[jobs.ManagedJobBase] = None) -> bool:      
        
        if not issubclass(cls, jobs.ManagedJobBase):
            raise TypeError("argument 'cls' must be an instance of 'ManagedJobBase'")

        if permission_level is None:
            if self._default_permission_level is None:
                raise TypeError("argument 'permission_level' cannot be None if no default permission level is set for job classes")
            permission_level = self._default_permission_level
        
        elif not isinstance(permission_level, JobPermissionLevels):
            raise TypeError("argument 'permission_level' must be a usable enum value from the 'JobPermissionLevels' enum")
        elif permission_level >= JobPermissionLevels.SYSTEM:
            raise ValueError("argument 'permission_level' must be a usable enum value from the 'JobPermissionLevels' enum")
        
        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.JOB_CLASS_REGISTER, register_permission_level=permission_level)
        else:
            self._check_within_job()
            _iv = self._manager_job
        
        if cls not in self._job_class_info_dict:
            self._job_class_info_dict[cls] = {"count": 0, "permission_level": permission_level}
            return True

        elif "permission_level" not in self._job_class_info_dict[cls]:
            self._job_class_info_dict[cls]["permission_level"] = permission_level
            return True

        return False

    def unregister_job_class(self, cls: Type[jobs.ManagedJobBase], _iv: Optional[jobs.ManagedJobBase] = None) -> bool:
        if cls in self._job_class_info_dict:
            if self._job_class_info_dict[cls]["count"]:
                raise RuntimeError("cannot unregister a job class which has running instances in a job manager")
            
            if isinstance(_iv, jobs.ManagedJobBase):
                self._verify_permissions(_iv, op=JobOps.JOB_CLASS_UNREGISTER, register_permission_level=self._job_class_info_dict[cls]["permission_level"])
            else:
                self._check_within_job()
                _iv = self._manager_job

            del self._job_class_info_dict[cls]
            return True

        return False

    def job_class_is_registered(self, cls: Type[jobs.ManagedJobBase]) -> bool:
        return any(supercls in self._job_class_info_dict and "permission_level" in self._job_class_info_dict[supercls] for supercls in cls.__mro__[:-1])

    def get_job_class_permission_level(self, cls: Type[jobs.ManagedJobBase], default: Any = UNSET, /) -> Union[JobPermissionLevels, Any]:
        if not issubclass(cls, jobs.ManagedJobBase):
            if default is UNSET:
                raise TypeError("argument 'cls' must be an instance of 'ManagedJobBase'")
            return default

        if cls in self._job_class_info_dict and "permission_level" in self._job_class_info_dict[cls]:
            return self._job_class_info_dict[cls]["permission_level"]

        for supercls in cls.__mro__[:-1]:
            if supercls in self._job_class_info_dict and "permission_level" in self._job_class_info_dict[supercls]:
                return self._job_class_info_dict[supercls]["permission_level"]
        else:
            if default is UNSET:
                raise RuntimeError(f"class '{cls.__name__}' and none of its non-virtual superclasses were registered in this job manager")
            return default

    async def initialize(self) -> bool:
        """Initialize this job manager, if it hasn't yet been initialized.

        Returns:
            bool: Whether the call was successful.
        """

        if not self._initialized:
            self._initialized = True
            self._is_running = True
            self._job_class_info_dict[jobs.JobManagerJob] = {"count": 0, "permission_level": JobPermissionLevels.SYSTEM}
            self._manager_job = self._get_job_from_proxy(
                await self.create_and_register_job(jobs.JobManagerJob)
            )
            self._manager_job._creator = self._manager_job._proxy
            return True

        return False

    async def job_scheduling_loop(self):
        """Run one iteration of the job scheduling loop of this
        job manager object.
        """

        self._check_init_and_running()
        self._check_scheduling_init()
        self._check_within_job()

        async with self._schedule_dict_lock:
            deletion_list = []
            for i, target_timestamp_ns_str in enumerate(
                tuple(self._schedule_dict.keys())
            ):
                timestamp_ns = int(target_timestamp_ns_str)
                if timestamp_ns <= 0:
                    continue
                if isinstance(self._schedule_dict[target_timestamp_ns_str], bytes):
                    timestamp_num_pickle_data = self._schedule_dict[
                        target_timestamp_ns_str
                    ]
                    async with acquired_scheduling_executor() as executor:
                        self._schedule_dict[
                            timestamp_ns
                        ] = await self._loop.run_in_executor(
                            executor,
                            self._unpickle_dict,
                            timestamp_num_pickle_data,
                        )

                timestamp = timestamp_ns / 1_000_000_000
                now = time.time()
                if now >= timestamp:
                    for j, schedule_kv_pair in enumerate(
                        self._schedule_dict[target_timestamp_ns_str].items()
                    ):
                        schedule_identifier, schedule_data = schedule_kv_pair

                        if isinstance(schedule_data, bytes):
                            schedule_pickle_data = schedule_data
                            async with acquired_scheduling_executor() as executor:
                                self._schedule_dict[target_timestamp_ns_str][
                                    schedule_identifier
                                ] = schedule_data = await self._loop.run_in_executor(
                                    executor,
                                    self._unpickle_dict,
                                    schedule_pickle_data,
                                )

                        if schedule_data["recur_interval"]:
                            try:
                                if now < timestamp + (
                                    (schedule_data["recur_interval"] / 1_000_000_000)
                                    * schedule_data["occurences"]
                                ):
                                    continue
                            except OverflowError as e:
                                print(
                                    f"Job scheduling for {schedule_identifier} failed: "
                                    "Too high recurring timestamp value",
                                    utils.format_code_exception(e),
                                )
                                deletion_list.append(schedule_identifier)
                                self._schedule_ids.remove(schedule_identifier)
                                self._schedule_dict[0][
                                    schedule_identifier
                                ] = schedule_data
                                continue

                        job_class = jobs.get_job_class_from_uuid(
                            schedule_data["class_uuid"], None
                        )
                        if job_class is None:
                            print(
                                "Job initiation failed: Could not find job class "
                                "with a UUID of "
                                f'\'{schedule_data["class_uuid"]}\''
                            )
                            deletion_list.append(schedule_identifier)
                            self._schedule_ids.remove(schedule_identifier)
                            self._schedule_dict[0][schedule_identifier] = schedule_data
                            continue

                        try:
                            self.register_job_class(job_class, getattr(JobPermissionLevels, str(schedule_data["permission_level"]), self._default_permission_level or JobPermissionLevels.MEDIUM))
                            job = self.create_job(
                                job_class,
                                *schedule_data["job_args"],
                                _return_proxy=False,
                                _iv=self._job_id_map.get(
                                    schedule_data["schedule_creator_identifier"]
                                ),
                                **schedule_data["job_kwargs"],
                            )
                            job._schedule_identifier = schedule_identifier
                        except Exception as e:
                            print(
                                "Job initiation failed due to an exception:\n"
                                + utils.format_code_exception(e),
                            )

                            deletion_list.append(schedule_identifier)
                            self._schedule_ids.remove(schedule_identifier)
                            self._schedule_dict[0][schedule_identifier] = schedule_data
                            continue
                        else:
                            try:
                                await self.initialize_job(job._proxy)
                            except Exception as e:
                                print(
                                    "Job initialization failed due to an exception:\n"
                                    + utils.format_code_exception(e),
                                )

                                deletion_list.append(schedule_identifier)
                                self._schedule_ids.remove(schedule_identifier)
                                self._schedule_dict[0][
                                    schedule_identifier
                                ] = schedule_data
                                continue

                            try:
                                await self.register_job(job._proxy)
                            except Exception as e:
                                print(
                                    "Job registration failed due to an exception:\n"
                                    + utils.format_code_exception(e),
                                )

                                deletion_list.append(schedule_identifier)
                                self._schedule_ids.remove(schedule_identifier)
                                self._schedule_dict[0][
                                    schedule_identifier
                                ] = schedule_data
                                continue

                            schedule_data["occurences"] += 1

                        if not schedule_data["recur_interval"] or (
                            schedule_data["max_recurrences"] != -1
                            and schedule_data["occurences"]
                            > schedule_data["max_recurrences"]
                        ):
                            deletion_list.append(schedule_identifier)
                            self._schedule_ids.remove(schedule_identifier)

                        # if j % 20:
                        #    await asyncio.sleep(0)

                    for schedule_id_key in deletion_list:
                        del self._schedule_dict[target_timestamp_ns_str][
                            schedule_id_key
                        ]

                    deletion_list.clear()

                if not self._schedule_dict[target_timestamp_ns_str]:
                    del self._schedule_dict[target_timestamp_ns_str]

                if i % 20:
                    await asyncio.sleep(0)

    @staticmethod
    def _dump_job_scheduling_data_helper(data_set, data_dict):
        return pickle.dumps({"identifiers": list(data_set), "data": data_dict})

    async def dump_job_scheduling_data(self) -> bytes:
        """Return the current job scheduling data as
        a `bytes` object of pickled data. This is only
        possible while a job manager is running or it
        was quit without its executors being shut down.

        Returns:
            bytes: The scheduling data.
        """

        self._check_init()
        dump_dict = {}

        async with self._schedule_dict_lock:
            for target_timestamp_ns_str, schedules_dict in self._schedule_dict.items():
                if target_timestamp_ns_str not in dump_dict:
                    dump_dict[target_timestamp_ns_str] = {}

                if isinstance(schedules_dict, dict):
                    for scheduling_id, schedule_dict in schedules_dict.items():
                        if isinstance(schedule_dict, dict):
                            async with acquired_scheduling_executor() as executor:
                                dump_dict[target_timestamp_ns_str][
                                    scheduling_id
                                ] = await self._loop.run_in_executor(
                                    executor,
                                    self._pickle_dict,
                                    schedule_dict,
                                )

                        elif isinstance(schedule_dict, bytes):
                            dump_dict[target_timestamp_ns_str][
                                scheduling_id
                            ] = schedule_dict

                    async with acquired_scheduling_executor() as executor:
                        dump_dict[
                            target_timestamp_ns_str
                        ] = await self._loop.run_in_executor(
                            executor,
                            self._pickle_dict,
                            dump_dict[target_timestamp_ns_str],
                        )

                elif isinstance(schedules_dict, bytes):
                    dump_dict[target_timestamp_ns_str] = schedules_dict

        result = None

        del dump_dict["0"]  # don't export error schedulings

        async with acquired_scheduling_executor() as executor:
            result = await self._loop.run_in_executor(
                executor,
                self._dump_job_scheduling_data_helper,
                self._schedule_ids.copy(),
                dump_dict,
            )
        return result

    async def load_job_scheduling_data(
        self,
        data: Union[bytes, dict],
        dezerialize_mode: Union[Literal["PARTIAL"], Literal["FULL"]] = "PARTIAL",
        overwrite=False,
    ):
        """Load the job scheduling data for this job object from pickled
        `bytes` data, or an unpickled dictionary.

        The job scheduling data must be structured as follows:

        ```py
        {
            "identifiers": [..., '123456789-42069-69420', '556456789-52069-6969', ...],
            "data": {
                ...: ...,
                "420": { # unix integer timestamp string in nanoseconds
                    ...: ...,
                    '123456789-420-69420': ...,
                    '556456789-420-6969': {
                        "schedule_identifier": '556456789-420-6969696969',
                        "schedule_creator_identifier": '556456789-53223236969',
                        "schedule_timestamp_ns_str": "6969",
                        "target_timestamp_ns_str": "52069",
                        "recur_interval": 878787, # in seconds
                        "occurences": 0,
                        "max_recurrences": 10,
                        "class_uuid": "376f990e-d1a7-4405-9657-7b53db601013",
                        "job_args": (..., ...),
                        "job_kwargs": {...: ..., ...},
                        }
                    },
                    ...: ...,
                },
                ...: ...,
            }
        }
        ```

        Args:
            data (Union[bytes, dict]):
                The data.

            overwrite (bool): Whether any previous schedule data should be overwritten
              with new data.
              If set to `False`, attempting to add unto preexisting data will
              raise a `RuntimeError`. Defaults to False.

        Raises:
            RuntimeError:
                Job scheduling is already initialized, or there is
                potential schedule data that might be unintentionally overwritten.

            TypeError: Invalid type for `data`.
            TypeError: Invalid structure of `data`.
        """

        self._check_init_and_running()

        if self._scheduling_is_initialized:
            raise RuntimeError(
                "cannot load scheduling data while job scheduling is initialized."
            )

        elif len(self._schedule_dict) > 1 and not overwrite:
            raise RuntimeError(
                "unintentional overwrite of preexisting scheduling data"
                " at risk, aborted"
            )

        data_dict = None
        data_set = None

        if isinstance(data, bytes):
            async with acquired_scheduling_executor() as executor:
                data = await self._loop.run_in_executor(executor, pickle.loads, data)

        if isinstance(data, dict):
            data_set, data_dict = data["identifiers"].copy(), data["data"].copy()
            # copy for the case where unpickled data was passed in
            data_set = set(data_set)
        else:
            raise TypeError(
                "argument 'data' must be of type 'dict' or 'bytes'"
                f" (pickle data of a list), not {data.__class__.__name__}"
            )

        for target_timestamp_ns_str, schedules_dict in data_dict.items():
            if isinstance(schedules_dict, bytes) and dezerialize_mode.startswith(
                ("PARTIAL", "FULL")
            ):
                async with acquired_scheduling_executor() as executor:
                    data_dict[
                        target_timestamp_ns_str
                    ] = schedules_dict = await self._loop.run_in_executor(
                        executor,
                        self._unpickle_dict,
                        schedules_dict,
                    )

            if isinstance(schedules_dict, dict):
                for scheduling_id, schedule_dict in schedules_dict.items():
                    if isinstance(schedule_dict, bytes) and dezerialize_mode == "FULL":
                        async with acquired_scheduling_executor() as executor:
                            data_dict[target_timestamp_ns_str][
                                scheduling_id
                            ] = await self._loop.run_in_executor(
                                executor,
                                self._unpickle_dict,
                                schedule_dict,
                            )

        async with self._schedule_dict_lock:
            self._schedule_ids = data_set
            self._schedule_dict.clear()
            self._schedule_dict.update(data_dict)
            if "0" not in self._schedule_dict:
                self._schedule_dict["0"] = {}

    def initialize_job_scheduling(self) -> bool:
        """Initialize the job scheduling process of this job manager.

        Returns:
            bool: Whether the call was successful.
        """

        self._check_init_and_running()

        if not self._scheduling_is_initialized:
            self._scheduling_is_initialized = True
            for fut in self._scheduling_initialized_futures:
                if not fut.done():
                    fut.set_result(True)

            return True

        return False

    def job_scheduling_is_initialized(self) -> bool:
        """Whether the job scheduling process of this job manager is initialized."""
        return self._scheduling_is_initialized

    def wait_for_job_scheduling_initialization(
        self, timeout: Optional[float] = None
    ) -> Coroutine:
        """This method returns a coroutine that can be used to wait until job
        scheduling is initialized.

        Returns:
            Coroutine: A coroutine that evaluates to `True`.

        Raises:
            RuntimeError: Job scheduling is already initialized.
        """

        if not self._scheduling_is_initialized:
            self._check_init_and_running()
            fut = self._loop.create_future()
            self._scheduling_initialized_futures.append(fut)
            return asyncio.wait_for(fut, timeout)

        raise RuntimeError("Job scheduling is already initialized.")

    def wait_for_job_scheduling_uninitialization(
        self, timeout: Optional[float] = None
    ) -> Coroutine:
        """This method returns a coroutine that can be used to wait until job
        scheduling is uninitialized.

        Returns:
            Coroutine: A coroutine that evaluates to `True`.

        Raises:
            RuntimeError: Job scheduling is not initialized.
        """

        if self._scheduling_is_initialized:
            self._check_init_and_running()
            fut = self._loop.create_future()
            self._scheduling_uninitialized_futures.append(fut)
            return asyncio.wait_for(fut, timeout)

        raise RuntimeError("Job scheduling is not initialized.")

    def uninitialize_job_scheduling(self) -> bool:
        """End the job scheduling process of this job manager.

        Returns:
            bool: Whether the call was successful.
        """

        output = False

        if self._scheduling_is_initialized:
            self._scheduling_is_initialized = False
            output = True

            for fut in self._scheduling_initialized_futures:
                if not fut.done():
                    fut.cancel(
                        f"initialization of {self.__class__.__name__}"
                        f"(ID={self._runtime_identifier}) was aborted"
                    )

            for fut in self._scheduling_uninitialized_futures:
                if not fut.done():
                    fut.set_result(True)

        return output

    def _verify_permissions(
        self,
        invoker: jobs.ManagedJobBase,
        op: JobOps,
        target: Optional[Union[jobs.ManagedJobBase, "proxies.JobProxy"]] = None,
        target_cls: Optional[jobs.ManagedJobBase] = None,
        register_permission_level: Optional[JobPermissionLevels] = None,
        schedule_identifier: Optional[str] = None,
        schedule_creator_identifier: Optional[str] =None,
        raise_exceptions=True,
    ) -> bool:

        if invoker is self._manager_job:
            return True

        invoker_cls = invoker.__class__

        self._check_job_class_registered(invoker_cls)

        if target is not None:
            if isinstance(target, proxies.JobProxy):
                target = self._get_job_from_proxy(target)

            elif not isinstance(target, jobs.ManagedJobBase):
                raise TypeError(
                    "argument 'target' must be a an instance of a job object or a job proxy"
                )
            
        target_cls = target.__class__ if target else target_cls
        target_cls_permission_level = None
        
        if target_cls is not None:
            self._check_job_class_registered(target_cls)

        invoker_cls_permission_level = self.get_job_class_permission_level(invoker_cls)

        if not isinstance(op, JobOps):
            raise TypeError(
                "argument 'op' must be an enum value defined in the 'JobOps' " "enum"
            )

        elif (
            op is JobOps.FIND
            and invoker_cls_permission_level < JobPermissionLevels.LOW
        ):
            if raise_exceptions:
                raise JobPermissionError(
                    f"insufficient permission level of {invoker_cls.__qualname__} "
                    f"({invoker_cls_permission_level.name}) "
                    f"for {_JOB_OPS_PRES_CONT[op.name].lower()} "
                    "job objects"
                )
            return False

        elif (
            op is JobOps.CUSTOM_EVENT_DISPATCH
            and invoker_cls_permission_level < JobPermissionLevels.HIGH
        ):
            if raise_exceptions:
                raise JobPermissionError(
                    f"insufficient permission level of {invoker_cls.__qualname__} "
                    f"({invoker_cls_permission_level.name}) "
                    "for dispatching custom events to job objects "
                )
            return False

        elif (
            op is JobOps.EVENT_DISPATCH
            and invoker_cls_permission_level < JobPermissionLevels.HIGH
        ):
            if raise_exceptions:
                raise JobPermissionError(
                    f"insufficient permission level of {invoker_cls.__qualname__} "
                    f"({invoker_cls_permission_level.name}) "
                    "for dispatching non-custom events to job objects "
                )
            return False

        elif op is JobOps.UNSCHEDULE:
            if schedule_identifier is None or schedule_creator_identifier is None:
                raise TypeError(
                    "argument 'schedule_identifier' and 'schedule_creator_identifier' "
                    "cannot be None if enum 'op' is 'UNSCHEDULE'"
                )

            if invoker_cls_permission_level < JobPermissionLevels.MEDIUM:
                if raise_exceptions:
                    raise JobPermissionError(
                        f"insufficient permission level of {invoker_cls.__qualname__} "
                        f"({invoker_cls_permission_level.name}) "
                        f"for {_JOB_OPS_PRES_CONT[op.name].lower()} "
                        "job objects"
                    )
                return False

            if (
                schedule_creator_identifier in self._job_id_map
            ):  # the schedule operation belongs to an alive job
                target = self._job_id_map[schedule_creator_identifier]
                # the target is now the job that scheduled a specific operation
                target_cls = target.__class__

                target_cls_permission_level = self.get_job_class_permission_level(target_cls)

                if (
                    invoker_cls_permission_level == JobPermissionLevels.MEDIUM
                    and invoker._runtime_identifier != schedule_creator_identifier
                ):
                    if raise_exceptions:
                        raise JobPermissionError(
                            f"insufficient permission level of '{invoker_cls.__qualname__}' "
                            f"({invoker_cls_permission_level.name}) "
                            f"for {_JOB_OPS_PRES_CONT[op.name].lower()} "
                            "jobs that were scheduled by the class "
                            f"'{target_cls.__qualname__}' "
                            f"({target_cls_permission_level.name}) "
                            "when the scheduler job is still alive and is not the "
                            "invoker job"
                        )
                    return False

                elif (
                    invoker_cls_permission_level == JobPermissionLevels.HIGH
                    and target_cls_permission_level >= JobPermissionLevels.HIGH
                ):
                    if raise_exceptions:
                        raise JobPermissionError(
                            f"insufficient permission level of '{invoker_cls.__qualname__}' "
                            f"({invoker_cls_permission_level.name}) "
                            f"for {_JOB_OPS_PRES_CONT[op.name].lower()} "
                            f"jobs that were scheduled by the class '{target_cls.__qualname__}' "
                            f"({target_cls_permission_level.name}) "
                        )
                    return False

        if op in (
            JobOps.CREATE,
            JobOps.INITIALIZE,
            JobOps.REGISTER,
            JobOps.SCHEDULE,
        ):
            target_cls_permission_level = self.get_job_class_permission_level(target_cls)

            if invoker_cls_permission_level < JobPermissionLevels.MEDIUM:
                if raise_exceptions:
                    raise JobPermissionError(
                        f"insufficient permission level of {invoker_cls.__qualname__} "
                        f"({invoker_cls_permission_level.name}) "
                        f"for {_JOB_OPS_PRES_CONT[op.name].lower()} job objects"
                    )
                return False

            err_msg = (
                f"insufficient permission level of '{invoker_cls.__qualname__}' "
                f"({invoker_cls_permission_level.name}) "
                f"for {_JOB_OPS_PRES_CONT[op.name].lower()} "
                f"job objects of the specified class '{target_cls.__qualname__}' "
                f"({target_cls_permission_level.name})"
            )

            if invoker_cls_permission_level == JobPermissionLevels.MEDIUM:
                if target_cls_permission_level >= JobPermissionLevels.MEDIUM:
                    if raise_exceptions:
                        raise JobPermissionError(err_msg)
                    return False

            elif (
                invoker_cls_permission_level == JobPermissionLevels.HIGH
                and target_cls_permission_level > JobPermissionLevels.HIGH
            ) or (
                invoker_cls_permission_level == JobPermissionLevels.HIGHEST
                and target_cls_permission_level > JobPermissionLevels.HIGHEST
            ):
                if raise_exceptions:
                    raise JobPermissionError(err_msg)
                return False
        
        elif op in (JobOps.JOB_CLASS_REGISTER, JobOps.JOB_CLASS_UNREGISTER):
            if register_permission_level is None:
                raise TypeError(
                    "argument 'register_permission_level'"
                    "cannot be None if enum 'op' is 'JOB_CLASS_REGISTER' "
                    "or 'JOB_CLASS_UNREGISTER'"
                )

            if invoker_cls_permission_level < JobPermissionLevels.HIGHEST:
                if raise_exceptions:
                    raise JobPermissionError(
                        f"insufficient permission level of {invoker_cls.__qualname__} "
                        f"({invoker_cls_permission_level.name}) "
                        f"for (un)registering job classes"
                    )
                return False 

            if (
                invoker_cls_permission_level == JobPermissionLevels.HIGHEST
                and register_permission_level > JobPermissionLevels.HIGHEST
            ):
                if raise_exceptions:
                    raise JobPermissionError(
                        f"insufficient permission level of '{invoker_cls.__qualname__}' "
                        f"({invoker_cls_permission_level.name}) "
                        f"for (un)registering job classes at/of a permission level of "
                        f"({register_permission_level.name})"
                    )
                return False

        elif op in (JobOps.GUARD, JobOps.UNGUARD):
            if target is None:
                raise TypeError(
                    "argument 'target'"
                    " cannot be None if enum 'op' is 'START',"
                    " 'RESTART', 'STOP' 'KILL', 'GUARD' or 'UNGUARD'"
                )

            target_cls_permission_level = self.get_job_class_permission_level(target_cls)

            if invoker_cls_permission_level < JobPermissionLevels.HIGH:
                if raise_exceptions:
                    raise JobPermissionError(
                        f"insufficient permission level of {invoker_cls.__qualname__} "
                        f"({invoker_cls_permission_level.name}) "
                        f"for {_JOB_OPS_PRES_CONT[op.name].lower()} job objects"
                    )
                return False

            elif invoker_cls_permission_level in (
                JobPermissionLevels.HIGH,
                JobPermissionLevels.HIGHEST,
            ):
                if target._creator is not invoker._proxy:
                    if raise_exceptions:
                        raise JobPermissionError(
                            f"insufficient permission level of '{invoker_cls.__qualname__}' "
                            f"({invoker_cls_permission_level.name}) "
                            f"for {_JOB_OPS_PRES_CONT[op.name].lower()} "
                            f"job objects of the specified class '{target_cls.__qualname__}' "
                            f"({target_cls_permission_level.name}) "
                            "its instance did not create."
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

            target_cls_permission_level = self.get_job_class_permission_level(target_cls)

            if invoker_cls_permission_level < JobPermissionLevels.MEDIUM:
                raise JobPermissionError(
                    f"insufficient permission level of {invoker_cls.__qualname__}"
                    f" ({invoker_cls_permission_level.name})"
                    f" for {_JOB_OPS_PRES_CONT[op.name].lower()} job objects"
                )
            
            elif invoker_cls_permission_level == JobPermissionLevels.MEDIUM:
                if (
                    target_cls_permission_level < JobPermissionLevels.MEDIUM
                    and target._creator is not invoker._proxy
                ):
                    if raise_exceptions:
                        raise JobPermissionError(
                            f"insufficient permission level of '{invoker_cls.__qualname__}' "
                            f"({invoker_cls_permission_level.name}) "
                            f"for {_JOB_OPS_PRES_CONT[op.name].lower()} "
                            f"job objects of the specified class '{target_cls.__qualname__}' "
                            f"({target_cls_permission_level.name}) that "
                            "its instance did not create."
                        )
                    return False

                elif target_cls_permission_level >= JobPermissionLevels.MEDIUM:
                    if raise_exceptions:
                        raise JobPermissionError
                    return False

            else:
                err_msg = (
                    f"insufficient permission level of '{invoker_cls.__qualname__}' "
                    f"({invoker_cls_permission_level.name}) "
                    f"for {_JOB_OPS_PRES_CONT[op.name].lower()} "
                    f"job objects of the specified class '{target_cls.__qualname__}' "
                    f"({target_cls_permission_level.name})"
                )
                if invoker_cls_permission_level == JobPermissionLevels.HIGH:
                    if target_cls_permission_level >= JobPermissionLevels.HIGH:
                        if raise_exceptions:
                            raise JobPermissionError(err_msg)
                        return False

                elif invoker_cls_permission_level == JobPermissionLevels.HIGHEST:
                    if target_cls_permission_level > JobPermissionLevels.HIGHEST:
                        if raise_exceptions:
                            raise JobPermissionError(err_msg)
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
            if not self.job_class_is_registered(cls) and self._default_permission_level is not None:
                self.register_job_class(cls, self._default_permission_level, _iv=self._manager_job)
            self._verify_permissions(_iv, op=JobOps.CREATE, target_cls=cls)
        else:
            self._check_within_job()
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
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.INITIALIZE, target=job)
        else:
            self._check_within_job()
            _iv = self._manager_job

        if job._guardian is not None and _iv._proxy is not job._guardian:
            raise JobStateError(
                "the given target job object is being guarded by another job"
            ) from None

        if not job._initialized:
            try:
                await job._INITIALIZE_EXTERNAL()
                job._initialized = True
            except (
                ValueError,
                TypeError,
                LookupError,
                JobException,
                AssertionError,
                discord.DiscordException,
            ):
                job._initialized = False
                if raise_exceptions:
                    raise
        else:
            if raise_exceptions:
                raise JobStateError("this job object is already initialized") from None
            else:
                return False

        return job._initialized

    async def register_job(
        self,
        job_proxy: "proxies.JobProxy",
        start: bool = True,
        _iv: Optional[jobs.ManagedJobBase] = None,
    ):
        """Register a job object to this JobManager,
        while initializing it if necessary.

        Args:
            job (JobProxy): The job object to be registered.
            start (bool): Whether the given job object should start automatically
              upon registration.

        Raises:
            JobStateError: Invalid job state for registration.
            JobException: job-specific errors preventing registration.
            RuntimeError: This job manager object is not initialized.
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.REGISTER, target=job)
        else:
            self._check_within_job()
            _iv = self._manager_job

        if job._guardian is not None and _iv._proxy is not job._guardian:
            raise JobStateError(
                "the given target job object is being guarded by another job"
            ) from None

        if job._killed or job._completed:
            raise JobStateError("cannot register a killed/completed job object")

        if not job._initialized:
            await self.initialize_job(job._proxy, _iv=self._manager_job)

        if (
            job.__class__._SINGLE
            and job.__class__ in self._job_class_info_dict
            and self._job_class_info_dict[job.__class__]["count"]
        ):
            raise JobException(
                "cannot have more than one instance of a"
                f" '{job.__class__.__qualname__}' job registered at a time."
            )

        self._add_job(job, start=start)
        job._registered_at_ts = time.time()

    async def create_and_register_job(
        self,
        cls: Type[jobs.ManagedJobBase],
        *args,
        _return_proxy: bool = True,
        _iv: Optional[jobs.ManagedJobBase] = None,
        **kwargs,
    ) -> "proxies.JobProxy":
        """Create an instance of a job class, register it to this job manager,
        and start it.

        Args:
            cls (Type[jobs.ManagedJobBase]): The job class to instantiate.
            *args (Any): Positional arguments for the job constructor.
            **kwargs (Any): Keyword-pnly arguments for the job constructor.

        Returns:
            JobProxy: A job proxy object.
        """
        j = self.create_job(cls, *args, _return_proxy=False, _iv=_iv, **kwargs)
        await self.register_job(j._proxy, start=True, _iv=_iv)
        if _return_proxy:
            return j._proxy
        return j

    async def create_job_schedule(
        self,
        cls: Type[jobs.ManagedJobBase],
        timestamp: Union[int, float, datetime.datetime],
        recur_interval: Optional[Union[int, float, datetime.timedelta]] = None,
        max_recurrences: int = -1,
        job_args: tuple = (),
        job_kwargs: Optional[dict] = None,
        _iv: Optional[jobs.ManagedJobBase] = None,
    ) -> str:
        """Schedule a job of a specific type to be instantiated and to run at
        one or more specific periods of time. Each job can receive positional
        or keyword arguments which are passed to this method.
        Those arguments must be pickleable.

        Args:
            cls (Type[jobs.ManagedJobBase]): The job type to
              schedule.
            timestamp (Union[int, float, datetime.datetime]): The exact timestamp
              or offset at which to instantiate a job.
            recur_interval (Optional[Union[int, float, datetime.timedelta]], optional):
              The interval at which a job should be rescheduled in seconds. `None` or
              0 means that no recurrences will occur. -1 means that the smallest
              possible recur interval should be used. Defaults to None.
            max_recurrences (int, optional): The maximum amount of recurrences for
              rescheduling. A value of -1 means that no maximum is set. Otherwise,
              the value of this argument must be a non-zero positive integer. If no
              `recur_interval` value was provided, the value of this argument will
              be ignored during scheduling and set to -1. Defaults to -1.
            job_args (tuple, optional): Positional arguments to pass to the
              scheduled job upon instantiation. Defaults to ().
            job_kwargs (dict, optional): Keyword arguments to pass to the scheduled
              job upon instantiation. Defaults to None.

        Returns:
            str: The string identifier of the scheduling operation.

        Raises:
            RuntimeError: The job manager has not yet initialized job scheduling,
              or this job manager object is not initialized.
            TypeError: Invalid argument types were given.
        """

        self._check_init_and_running()
        self._check_scheduling_init()

        if not issubclass(cls, jobs.ManagedJobBase):
            raise TypeError(
                "argument 'cls' must be of a subclass of "
                f"'ManagedJobBase', not '{cls}'"
            ) from None

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.SCHEDULE, target_cls=cls)
        else:
            self._check_within_job()
            _iv = self._manager_job

        class_scheduling_identifier = jobs.get_job_class_uuid(cls, None)
        if class_scheduling_identifier is None:
            raise TypeError(f"job class '{cls.__qualname__}' is not schedulable")

        if isinstance(timestamp, datetime.datetime):
            timestamp = timestamp.astimezone(datetime.timezone.utc)
        elif isinstance(timestamp, (int, float)):
            timestamp = datetime.datetime.fromtimestamp(
                timestamp, tz=datetime.timezone.utc
            )
        else:
            raise TypeError(
                "argument 'timestamp' must be a datetime.datetime or a positive real number"
            ) from None

        timestamp_ns = int(timestamp.timestamp() * 1_000_000_000)  # save time in ns
        target_timestamp_ns_str = f"{timestamp_ns}"

        recur_interval_num = None

        if recur_interval is None or recur_interval == 0:
            recur_interval_num = 0

        elif isinstance(recur_interval, (int, float)) and (
            recur_interval == -1 or recur_interval > 0
        ):
            if recur_interval > 0:
                recur_interval_num = int(recur_interval * 1_000_000_000)
                # save time difference in ns
            else:
                recur_interval_num = -1

        elif isinstance(recur_interval, datetime.timedelta) and (
            recur_interval.total_seconds() == -1 or recur_interval.total_seconds() >= 0
        ):
            if recur_interval.total_seconds() >= 0:
                recur_interval_num = int(recur_interval.total_seconds() * 1_000_000_000)
            else:
                recur_interval_num = -1
        else:
            raise TypeError(
                "argument 'recur_interval' must be None, 0, -1, a positive real number"
                " (in seconds) or a datetime.timedelta object with either a value"
                " of -1 seconds, or a positive value"
            ) from None

        if not isinstance(max_recurrences, int) or (
            max_recurrences != -1 and max_recurrences <= 0
        ):
            raise TypeError(
                "argument 'max_recurrences' must be -1 or a non-zero positive real"
                f" number of type 'int', not {type(job_args).__name__}"
            ) from None

        if not isinstance(job_args, (list, tuple)):
            if job_args is None:
                job_args = ()
            else:
                raise TypeError(
                    f"'job_args' must be of type 'tuple', not {type(job_args).__name__}"
                ) from None

        elif not isinstance(job_kwargs, dict):
            if job_kwargs is None:
                job_kwargs = {}
            else:
                raise TypeError(
                    f"'job_kwargs' must be of type 'dict', not {type(job_kwargs)}"
                ) from None

        schedule_timestamp_ns_str = str(
            int(
                datetime.datetime.now(datetime.timezone.utc).timestamp() * 1_000_000_000
            )
        )

        new_data = {
            "schedule_creator_identifier": _iv._runtime_identifier,
            "schedule_identifier": "",
            "schedule_timestamp_ns_str": schedule_timestamp_ns_str,
            "target_timestamp_ns_str": target_timestamp_ns_str,
            "permission_level": self.get_job_class_permission_level(cls, JobPermissionLevels.MEDIUM),
            "recur_interval": recur_interval_num,
            "occurences": 0,
            "max_recurrences": max_recurrences,
            "class_uuid": class_scheduling_identifier,
            "job_args": tuple(job_args),
            "job_kwargs": job_kwargs if job_kwargs is not None else {},
        }

        new_data[
            "schedule_identifier"
        ] = (
            schedule_identifier
        ) = f"{self._runtime_identifier}-{target_timestamp_ns_str}-{schedule_timestamp_ns_str}"

        async with self._schedule_dict_lock:
            if target_timestamp_ns_str not in self._schedule_dict:
                self._schedule_dict[target_timestamp_ns_str] = {}

            self._schedule_dict[target_timestamp_ns_str][schedule_identifier] = new_data
            self._schedule_ids.add(schedule_identifier)

        return schedule_identifier

    def get_job_schedule_identifiers(self) -> Optional[tuple[str]]:
        """Return a tuple of all job schedule identifiers pointing to
        scheduling data.

        Returns:
            tuple: The job schedule identifiers.
        """

        return tuple(self._schedule_ids)

    def job_schedule_has_failed(self, schedule_identifier: str) -> bool:
        """Whether the job schedule operation with the specified schedule
        identifier failed.

        Args:
            schedule_identifier (str): A string identifier following this structure:
              'JOB_MANAGER_IDENTIFIER-TARGET_TIMESTAMP_IN_NS-SCHEDULING_TIMESTAMP_IN_NS'

        Returns:
            bool: True/False

        Raises:
            ValueError: Invalid schedule identifier.
        """

        split_id = schedule_identifier.split("-")

        if len(split_id) != 4 and not all(s.isnumeric() for s in split_id):
            raise ValueError("invalid schedule identifier")

        return schedule_identifier in self._schedule_dict[0]

    def has_job_schedule(self, schedule_identifier: str) -> bool:
        """Whether the job schedule operation with the specified schedule
        identifier exists.

        Args:
            schedule_identifier (str): A string identifier following this structure:
              'JOB_MANAGER_IDENTIFIER-TARGET_TIMESTAMP_IN_NS-SCHEDULING_TIMESTAMP_IN_NS'

        Returns:
            bool: Whether the schedule identifier leads to existing scheduling data.

        Raises:
            ValueError: Invalid schedule identifier.
        """

        split_id = schedule_identifier.split("-")

        if len(split_id) != 4 and not all(s.isnumeric() for s in split_id):
            raise ValueError("invalid schedule identifier")

        return schedule_identifier in self._schedule_ids

    async def remove_job_schedule(
        self,
        schedule_identifier: str,
        _iv: Optional[jobs.ManagedJobBase] = None,
    ) -> bool:
        """Remove a job schedule operation using the string identifier
        of the schedule operation.

        Args:
            schedule_identifier (str): A string identifier following
              this structure:
              'JOB_MANAGER_IDENTIFIER-TARGET_TIMESTAMP_IN_NS-SCHEDULING_TIMESTAMP_IN_NS'

        Returns:
            bool: Whether the call was successful.

        Raises:
            ValueError: Invalid schedule identifier.
            KeyError: No operation matching the given schedule identifier was found.
            JobPermissionError: Insufficient permissions.
        """

        self._check_init_and_running()
        self._check_scheduling_init()

        split_id = schedule_identifier.split("-")

        if len(split_id) != 4 and not all(s.isnumeric() for s in split_id):
            raise ValueError("invalid schedule identifier")

        (
            mgr_id_start,
            mgr_id_end,
            target_timestamp_num_str,
            schedule_num_str,
        ) = split_id

        mgr_identifier = f"{mgr_id_start}-{mgr_id_end}"

        async with self._schedule_dict_lock:
            if target_timestamp_num_str in self._schedule_dict:
                schedules_data = self._schedule_dict[target_timestamp_num_str]
                if isinstance(schedules_data, bytes):
                    async with acquired_scheduling_executor() as executor:
                        self._schedule_dict[
                            target_timestamp_num_str
                        ] = await self._loop.run_in_executor(
                            executor,
                            self._unpickle_dict,
                            schedules_data,
                        )

                if schedule_identifier in self._schedule_dict[target_timestamp_num_str]:
                    if isinstance(_iv, jobs.ManagedJobBase):
                        schedule_creator_identifier = self._schedule_dict[
                            target_timestamp_num_str
                        ][schedule_identifier]["schedule_creator_identifier"]
                        self._verify_permissions(
                            _iv,
                            op=JobOps.UNSCHEDULE,
                            schedule_identifier=schedule_identifier,
                            schedule_creator_identifier=schedule_creator_identifier,
                        )
                    else:
                        self._check_within_job()
                        _iv = self._manager_job

                    del self._schedule_dict[target_timestamp_num_str][
                        schedule_identifier
                    ]
                    self._schedule_ids.remove(schedule_identifier)
                    return True

            raise KeyError(
                "cannot find any scheduled operation with the identifier "
                f"'{schedule_identifier}'"
            )

    async def clear_job_schedules(
        self,
        _iv: Optional[jobs.ManagedJobBase] = None,
    ):
        """Remove all job schedule operations. This obviously can't
        be undone. This will stop job scheduling, clear data, and restart
        it again when done if it was running.
        """

        was_init = self._scheduling_is_initialized

        if was_init:
            self.uninitialize_job_scheduling()

        async with self._schedule_dict_lock:
            fails = self._schedule_dict[0]
            fails.clear()
            self._schedule_dict.clear()
            self._schedule_dict[0] = fails
            self._schedule_ids.clear()

        if was_init:
            self.initialize_job_scheduling()

    def __iter__(self):
        return iter(job._proxy for job in self._job_id_map.values())

    def _add_job(
        self,
        job: jobs.ManagedJobBase,
        start: bool = True,
    ):
        """THIS METHOD IS ONLY MEANT FOR INTERNAL USE BY THIS CLASS.

        Add the given job object to this job manager, and start it.

        Args:
            job: jobs.ManagedJobBase:
                The job to add.
            start (bool, optional):
                Whether a given interval job object should start immediately
                after being added. Defaults to True.
        Raises:
            TypeError: An invalid object was given as a job.
            JobStateError: A job was given that had already ended.
            RuntimeError:
                A job was given that was already present in the
                manager, or this job manager has not been initialized.
            JobStateError: An uninitialized job was given as input.
        """

        if job._runtime_identifier in self._job_id_map:
            raise RuntimeError(
                "the given job is already present in this manager"
            ) from None

        if isinstance(job, jobs.EventJobMixin):
            for ev_type in job.EVENTS:
                if ev_type._RUNTIME_IDENTIFIER not in self._event_job_ids:
                    self._event_job_ids[ev_type._RUNTIME_IDENTIFIER] = set()
                self._event_job_ids[ev_type._RUNTIME_IDENTIFIER].add(
                    job._runtime_identifier
                )

        elif not isinstance(job, jobs.ManagedJobBase):
            raise TypeError(
                "expected an instance of a ManagedJobBase subclass, "
                f"not {job.__class__.__qualname__}"
            ) from None

        if job.__class__ not in self._job_class_info_dict:
            self._job_class_info_dict[job.__class__] = {"count": 0}

        self._job_class_info_dict[job.__class__]["count"] += 1

        self._job_id_map[job._runtime_identifier] = job

        job._registered_at_ts = time.time()

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
                    ev_type._RUNTIME_IDENTIFIER in self._event_job_ids
                    and job._runtime_identifier
                    in self._event_job_ids[ev_type._RUNTIME_IDENTIFIER]
                ):
                    self._event_job_ids[ev_type._RUNTIME_IDENTIFIER].remove(
                        job._runtime_identifier
                    )
                if not self._event_job_ids[ev_type._RUNTIME_IDENTIFIER]:
                    del self._event_job_ids[ev_type._RUNTIME_IDENTIFIER]

        if job._runtime_identifier in self._job_id_map:
            del self._job_id_map[job._runtime_identifier]

        self._job_class_info_dict[job.__class__]["count"] -= 1

        if self._job_class_info_dict[job.__class__]["count"] == 0 and "permission_level" not in self._job_class_info_dict[job.__class__]:
            del self._job_class_info_dict[job.__class__]

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

        return job in self._job_id_map.values()

    def has_job_identifier(self, identifier: str) -> bool:
        """Whether a job with the given identifier is contained in this job manager.

        Args:
            identifier (str): The job identifier.

        Returns:
            bool: True/False
        """

        self._check_init_and_running()

        return identifier in self._job_id_map

    def find_job(
        self,
        *,
        identifier: Union[str, _UnsetType] = None,
        created_at: Union[datetime.datetime, _UnsetType] = None,
        _return_proxy: bool = True,
        _iv: Optional[jobs.ManagedJobBase] = None,
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

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.FIND)
        else:
            self._check_within_job()
            _iv = self._manager_job

        if identifier is not None:
            if isinstance(identifier, str):
                if identifier in self._job_id_map:
                    if _return_proxy:
                        return self._job_id_map[identifier]._proxy
                    return self._job_id_map[identifier]
                return None

            raise TypeError(
                f"'identifier' must be of type 'str', not {type(identifier)}"
            ) from None

        elif created_at is not None:
            if isinstance(created_at, datetime.datetime):
                for job in self._job_id_map.values():
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
        was_scheduled: Union[bool, _UnsetType] = UNSET,
        schedule_identifier: Union[str, _UnsetType] = UNSET,
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
        _iv: Optional[jobs.ManagedJobBase] = None,
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

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.FIND)
        else:
            self._check_within_job()
            _iv = self._manager_job

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

        if was_scheduled is not UNSET:
            was_scheduled = bool(was_scheduled)
            filter_functions.append(lambda job: job.was_scheduled() is was_scheduled)

        if schedule_identifier is not UNSET:
            if isinstance(schedule_identifier, str):
                filter_functions.append(
                    lambda job: job.schedule_identifier == schedule_identifier
                )
            else:
                raise TypeError(
                    "'schedule_identifier' must be of type 'str', not "
                    f"{type(created_before)}"
                ) from None

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
                    for job in self._job_id_map.values()
                    if bool_func(filter_func(job) for filter_func in filter_functions)
                )
            return tuple(
                job
                for job in self._job_id_map.values()
                if bool_func(filter_func(job) for filter_func in filter_functions)
            )

        if _return_proxy:
            return tuple(job._proxy for job in self._job_id_map.values())

        return tuple(self._job_id_map.values())

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
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        if not job._initialized:
            raise JobStateError("the given job was not initialized") from None

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.START, target=job)
        else:
            self._check_within_job()
            _iv = self._manager_job

        if job._guardian is not None and _iv._proxy is not job._guardian:
            raise JobStateError(
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
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        if not job._initialized:
            raise JobStateError("the given job was not initialized") from None

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.RESTART, target=job)
        else:
            self._check_within_job()
            _iv = self._manager_job

        if job._guardian is not None and _iv._proxy is not job._guardian:
            raise JobStateError(
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
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        if not job._initialized:
            raise JobStateError("the given job was not initialized") from None

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.STOP, target=job)
        else:
            self._check_within_job()
            _iv = self._manager_job

        if job._guardian is not None and _iv._proxy is not job._guardian:
            raise JobStateError(
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
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        if not job._initialized:
            raise JobStateError("the given job was not initialized") from None

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.KILL, target=job)
        else:
            self._check_within_job()
            _iv = self._manager_job

        if job._guardian is not None and _iv._proxy is not job._guardian:
            raise JobStateError(
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
            JobStateError: The given target job object is already being guarded.
        """

        self._check_init_and_running()

        job = self._get_job_from_proxy(job_proxy)

        if not job._initialized:
            raise JobStateError("the given job was not initialized") from None

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.GUARD, target=job)
        else:
            self._check_within_job()
            _iv = self._manager_job

        if job._guardian is not None:
            raise JobStateError(
                "the given target job object is already being guarded by a job"
            )

        if _iv._guarded_job_proxies_dict is None:
            _iv._guarded_job_proxies_dict = {}

        if job._runtime_identifier not in _iv._guarded_job_proxies_dict:
            job._guardian = _iv._proxy
            _iv._guarded_job_proxies_dict[job._runtime_identifier] = job._proxy
        else:
            raise JobStateError(
                "the given target job object is already"
                " being guarded by the invoker job object"
            )

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

        if not job._initialized:
            raise JobStateError("the given job was not initialized") from None

        if isinstance(_iv, jobs.ManagedJobBase):
            self._verify_permissions(_iv, op=JobOps.UNGUARD, target=job)
        else:
            self._check_within_job()
            _iv = self._manager_job

        if job._guardian is None:
            raise JobStateError("the given job object is not being guarded by a job")

        if (
            _iv._guarded_job_proxies_dict is not None
            and job._runtime_identifier in _iv._guarded_job_proxies_dict
        ):
            job._guardian = None
            del _iv._guarded_job_proxies_dict[job._runtime_identifier]

        elif _iv is self._manager_job:
            guardian = job._guardian
            job._guardian = None

            del guardian._guarded_job_proxies_dict[job._runtime_identifier]

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
    def guarding_job(
        self,
        job_proxy: "proxies.JobProxy",
        _iv: Optional[jobs.ManagedJobBase] = None,
    ):
        """A context manager for automatically guarding and unguarding a job object.
        If the given job object is already unguarded or guarded by another job when
        this context manager is ending, it will not atttempt to unguard.

        This method is meant to be used with the `with` statement:
        ```py
        with manager.guarding_job(job):
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
        return job._runtime_identifier in self._job_id_map

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
            self._check_within_job()
            _iv = self._manager_job

        if _iv is not None:
            # for cases where the default _iv might not yet be set
            event._dispatcher = _iv._proxy

        event_class_identifier = event.__class__._RUNTIME_IDENTIFIER

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
                event_job = self._job_id_map[identifier]
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
            if event_type._RUNTIME_IDENTIFIER not in self._event_waiting_queues:
                self._event_waiting_queues[event_type._RUNTIME_IDENTIFIER] = []

            self._event_waiting_queues[event_type._RUNTIME_IDENTIFIER].append(wait_list)

        return asyncio.wait_for(future, timeout)

    def stop_all_jobs(self, force: bool = False):
        """Stop all job objects that are in this job manager."""

        self._check_init_and_running()
        self._check_within_job()

        for job in self._job_id_map.values():
            job._STOP_EXTERNAL(force=force)

    def kill_all_jobs(self, awaken: bool = True):
        """Kill all job objects that are in this job manager."""

        self._check_init_and_running()
        self._check_within_job()

        for job in self._job_id_map.values():
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
        job_operation: Union[
            Literal[JobOps.KILL], Literal[JobOps.STOP]
        ] = JobOps.KILL,
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
                alive=True, is_running=False, stopped=False, _return_proxy=False,
                _iv=self._manager_job
            ),
            starting=self.find_jobs(is_starting=True, _return_proxy=False, _iv=self._manager_job),
            running=self.find_jobs(
                is_running=True,
                is_idling=False,
                is_starting=False,
                is_restarting=False,
                _return_proxy=False,
                _iv=self._manager_job,
            ),
            idling=self.find_jobs(is_idling=True, _return_proxy=False, _iv=self._manager_job),
            stopping=self.find_jobs(
                is_stopping=True,
                is_restarting=False,
                is_completing=False,
                is_being_killed=False,
                _return_proxy=False,
                _iv=self._manager_job,
            ),
            completing=self.find_jobs(is_completing=True, _return_proxy=False, _iv=self._manager_job),
            being_killed=self.find_jobs(is_being_killed=True, _return_proxy=False, _iv=self._manager_job),
            stopped=self.find_jobs(stopped=True, _return_proxy=False, _iv=self._manager_job),
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
