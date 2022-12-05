"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file implements the base classes for job objects, which are a core part of the
asynchronous task execution system.
"""
import asyncio
import datetime
import inspect
import sys
import time
import traceback
from types import FunctionType, MappingProxyType, SimpleNamespace
from typing import (
    Any,
    Callable,
    Coroutine,
    Literal,
    Mapping,
    ParamSpec,
    Sequence,
    TypeVar,
    overload,
)

import discord.utils
from snakecore.constants import (
    _DEFAULT_JOB_EXCEPTION_ALLOWLIST,
    JobPermissionLevels,
    JobStatus,
    JobStopReasons,
    JobBoolFlags as JF,
)
from snakecore.exceptions import (
    JobIsDone,
    JobNotAlive,
    JobNotRunning,
    JobOutputError,
    JobStateError,
)
from snakecore import utils
from snakecore.constants import (
    UNSET,
)
from snakecore._jobs.loops import JobLoop
from snakecore.utils import FastChainMap

if sys.version_info >= (3, 11):  # type: ignore
    from typing import Self
else:
    from typing_extensions import Self

_P = ParamSpec("_P")
_T = TypeVar("_T")

_JOB_CLASS_MAP = {}
# A dictionary of all Job subclasses that were created.
# Do not access outside of this module.

_JOB_CLASS_UUID_MAP = {}
# A dictionary of all Job subclasses by their UUID.
# Do not access outside of this module.


def get_job_class_from_runtime_id(
    class_runtime_id: str, default: Any = UNSET, /, closest_match: bool = False
) -> "JobBase":

    name, timestamp_str = class_runtime_id.split("-")

    if name in _JOB_CLASS_MAP:
        if timestamp_str in _JOB_CLASS_MAP[name]:
            return _JOB_CLASS_MAP[name][timestamp_str]
        elif closest_match:
            for ts_str in _JOB_CLASS_MAP[name]:
                return _JOB_CLASS_MAP[name][ts_str]

    if default is UNSET:
        raise LookupError(
            f"cannot find job class with an identifier of "
            f"'{class_runtime_id}' in the job class registry"
        )
    return default


def get_job_class_from_uuid(
    class_uuid: str,
    default: Any = UNSET,
    /,
) -> "JobBase | Any":

    if class_uuid in _JOB_CLASS_UUID_MAP:
        return _JOB_CLASS_UUID_MAP[class_uuid]

    if default is UNSET:
        raise KeyError(
            f"cannot find job class with a UUID of "
            f"'{class_uuid}' in the job class registry"
        )

    return default


def get_job_class_uuid(
    cls: type["JobBase"],
    default: Any = UNSET,
    /,
) -> str | Any:
    """Get a job class by its UUID. This is the safe way
    of looking up job classes in a persistent manner.

    Parameters
    ----------
    cls : type[JobBase]
        The job class whose UUID should be fetched.
    default : Any
        A default value which will be returned if this function
        fails to produce the desired output. If omitted, exceptions will be
        raised.

    Returns
    -------
    str
        The string identifier.

    Raises
    ------
    TypeError
        'cls' does not inherit from a job base class.
    LookupError
        The given job class does not exist in the job class registry.
        This exception should not occur if job classes inherit their base classes
        correctly.
    """

    if not issubclass(cls, JobBase):
        if default is UNSET:
            raise TypeError(
                "argument 'cls' must be a subclass of a managed job base class"
            )
        return default

    try:
        class_uuid = cls._UUID
    except AttributeError:
        if default is UNSET:
            raise TypeError(
                "argument 'cls' must be a subclass of a managed job base class"
            ) from None
        return default
    else:
        if class_uuid is None:
            if default is UNSET:
                raise TypeError(f"job class '{cls.__qualname__}' has no UUID")

    if class_uuid in _JOB_CLASS_UUID_MAP and _JOB_CLASS_UUID_MAP[class_uuid] is cls:
        return class_uuid

    if default is UNSET:
        raise LookupError(
            f"The given job class does not exist in the UUID job class registry"
        )

    return default


def get_job_class_runtime_id(
    cls: type["JobBase"],
    default: Any = UNSET,
    /,
) -> str | Any:
    """Get a job class by its runtime id string. This is the safe way
    of looking up job class runtime ids.

    Parameters
    ----------
    cls : type[JobBase]
        The job class whose identifier should be fetched.
    default : Any
        A default value which will be returned if this function
        fails to produce the desired output. If omitted, exceptions will be
        raised.

    Returns
    -------
    str
        The string identifier.

    Raises
    ------
    TypeError
        'cls' does not inherit from a job base class.
    LookupError
        The given job class does not exist in the job class registry.
        This exception should not occur if job classes inherit their base classes
        correctly.
    """

    if not issubclass(cls, JobBase):
        if default is UNSET:
            raise TypeError(
                "argument 'cls' must be a subclass of a managed job base class"
            )
        return default

    try:
        class_runtime_id = cls._RUNTIME_ID
    except AttributeError:
        if default is UNSET:
            raise TypeError(
                "argument 'cls' must be a subclass of a managed job base class"
            ) from None
        return default

    try:
        name, timestamp_str = class_runtime_id.split("-")
    except (ValueError, AttributeError):
        if default is UNSET:
            raise ValueError(
                "invalid identifier found in the given job class"
            ) from None
        return default

    if name in _JOB_CLASS_MAP:
        if timestamp_str in _JOB_CLASS_MAP[name]:
            if _JOB_CLASS_MAP[name][timestamp_str] is cls:
                return class_runtime_id
            else:
                if default is UNSET:
                    raise ValueError(
                        f"The given job class has the incorrect identifier"
                    )
        else:
            if default is UNSET:
                ValueError(
                    f"The given job class is registered under "
                    "a different identifier in the job class registry"
                )

    if default is UNSET:
        raise LookupError(
            f"The given job class does not exist in the job class registry"
        )

    return default


class JobNamespace(SimpleNamespace):
    """A subclass of SimpleNamespace, which is used by job objects
    to store instance-specific data.
    """

    def __contains__(self, k: str):
        return k in self.__dict__

    def __iter__(self):
        return iter(self.__dict__.items())

    def copy(self):
        return self.__class__(**self.__dict__)

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @staticmethod
    def from_dict(dct):
        return JobNamespace(**dct)

    __copy__ = copy


@overload
def singletonjob(cls: type[_T]) -> type[_T]:
    ...


@overload
def singletonjob(
    cls: type[_T] | None = None, disabled: bool = False
) -> Callable[[type[_T]], type[_T]]:
    ...


def singletonjob(
    cls: type[_T] | None = None, disabled: bool = False
) -> type[_T] | Callable[[type[_T]], type[_T]]:
    """A class decorator for (un)marking managed job classes as singletons,
    meaning that their instances can only be running one at a time in a job manager.

    Parameters
    ----------
    cls : type[T] | None, optional
        The `ManagedJobBase` subclass.
    disabled : bool, optional
        Whether to disable singleton mode.
        Defaults to False.
    """

    def inner_deco(cls: type[_T]) -> type[_T]:
        if issubclass(cls, JobBase):
            cls._SINGLE = not disabled
        else:
            raise TypeError("argument 'cls' must be an instance of JobBase")

        return cls

    if cls is not None:
        return inner_deco(cls)

    return inner_deco


def publicjobmethod(
    func: Callable[_P, _T] | None = None,
    is_async: bool | None = None,
    disabled: bool = False,
) -> Callable[_P, _T] | Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    """A special decorator to expose a managed job class method as public to other managed
    job objects. Can be used as a decorator function with or without extra arguments.

    Parameters
    ----------
    func : Callable[P, T] | None, optional
        The function to mark as a public method.
    is_async : bool | None, optional
        An indicator for whether the returned value of the
        public method should be awaited upon being called, either because of it being a
        coroutine function or it returning an awaitable object. If set to `None`, it
        will be checked for whether it is a coroutine function.
        that the function will be checked.
    disabled : bool, optional
        Whether to mark this public job method as disabled.
        Defaults to False.
    """

    def inner_deco(func: Callable[_P, _T]) -> Callable[_P, _T]:
        if isinstance(func, FunctionType):
            func.__public = True  # type: ignore
            func.__disabled = bool(disabled)  # type: ignore
            func.__is_async = (  # type: ignore
                is_async
                if isinstance(is_async, bool)
                else inspect.iscoroutinefunction(func)
            )
            return func  # type: ignore

        raise TypeError("The first decorator function argument must be a function")

    if func is not None:
        return inner_deco(func)

    return inner_deco


class _JobCore:

    __slots__ = (
        "_bools",
        "_interval_secs",
        "_time",
        "_count",
        "_loop_count",
        "_created_at_ts",
        "_runtime_id",
        "_data",
        "_job_loop",
        "_on_start_exception",
        "_on_run_exception",
        "_on_stop_exception",
        "_stop_futures",
        "_last_stopping_reason",
        "_initialized_since_ts",
        "_idling_since_ts",
        "_running_since_ts",
        "_stopped_since_ts",
    )

    _CREATED_AT = datetime.datetime.now(datetime.timezone.utc)
    _UUID: str | None = None
    _RUNTIME_ID = f"JobBase-{int(_CREATED_AT.timestamp()*1_000_000_000)}"

    Namespace = JobNamespace

    def __init_subclass__(cls, class_uuid: str | None = None) -> None:
        if getattr(cls, f"{cls.__qualname__}_INIT", False):
            raise RuntimeError("This job class was already initialized")

        cls._CREATED_AT = datetime.datetime.now(datetime.timezone.utc)

        name = cls.__qualname__
        created_timestamp_ns_str = f"{int(cls._CREATED_AT.timestamp()*1_000_000_000)}"

        cls._RUNTIME_ID = f"{name}-{created_timestamp_ns_str}"

        if name not in _JOB_CLASS_MAP:
            _JOB_CLASS_MAP[name] = {}

        _JOB_CLASS_MAP[name][created_timestamp_ns_str] = cls

        if class_uuid is not None:
            if not isinstance(class_uuid, str):
                raise TypeError(
                    "argument 'class_uuid' must be a string unique to this job class"
                )

            elif class_uuid in _JOB_CLASS_UUID_MAP:
                raise ValueError(
                    f"the given UUID for class '{cls.__qualname__}' "
                    "must be unique to it and cannot be used by other job classes"
                )

            cls._UUID = class_uuid

            _JOB_CLASS_UUID_MAP[class_uuid] = cls

        setattr(cls, f"{cls.__qualname__}_INIT", True)

    def __init__(self) -> None:
        self._created_at_ts = time.time()
        self._data = self.Namespace()

        self._runtime_id: str = (
            f"{self.__class__._RUNTIME_ID}:{int(self._created_at_ts*1_000_000_000)}"
        )

        self._interval_secs: float = 0
        self._time = None
        self._count: int | None = None

        self._loop_count: int = 0

        self._job_loop: JobLoop = None  # type: ignore (will be set at runtime)

        self._on_start_exception: BaseException | None = None
        self._on_run_exception: BaseException | None = None
        self._on_stop_exception: BaseException | None = None

        self._bools = 0

        self._stop_futures: list[asyncio.Future[bool | JobStatus]] | None = None

        self._last_stopping_reason: JobStopReasons.Internal | JobStopReasons.External | None = (
            None
        )

        self._initialized_since_ts: float | None = None
        self._idling_since_ts: float | None = None
        self._running_since_ts: float | None = None
        self._stopped_since_ts: float | None = None

    @classmethod
    def get_class_runtime_id(cls) -> str:
        """Get the runtime id of this job class.

        Returns
        -------
        str
            The runtime id.
        """
        return cls._RUNTIME_ID

    @classmethod
    def get_class_uuid(cls) -> str | None:
        """Get the UUID of this job class.

        Returns
        -------
            str | None: The UUID.
        """
        return cls._UUID

    @property
    def runtime_id(self) -> str:
        return self._runtime_id

    @property
    def created_at(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(
            self._created_at_ts, tz=datetime.timezone.utc
        )

    @property
    def data(self) -> Namespace:
        """`JobNameSpace`: The `JobNamespace` instance bound to this job object for storage."""
        return self._data

    async def _on_init(self) -> None:
        try:
            self._bools |= JF.IS_INITIALIZING  # True
            await self.on_init()
        except Exception:
            self._bools &= ~JF.IS_INITIALIZING  # False
            raise
        else:
            self._bools &= ~JF.IS_INITIALIZING  # False
            self._bools |= JF.INITIALIZED  # True
            self._initialized_since_ts = time.time()

    async def on_init(self) -> None:
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()`
        WITHIN THIS METHOD TO ACCESS THE SUPERCLASS METHOD.

        This method allows subclasses to initialize their job object instances.
        """
        pass

    async def _on_start(self) -> None:
        self._on_start_exception = None
        self._on_run_exception = None
        self._on_stop_exception = None

        self._bools |= JF.IS_STARTING  # True
        self._bools &= ~(JF.STOPPED | JF.IS_IDLING)  # False

        self._stopped_since_ts = None
        self._idling_since_ts = None

        self._running_since_ts = time.time()

        try:
            await self.on_start()
        except Exception as exc:
            self._on_start_exception = exc
            self._bools |= (
                JF.TOLD_TO_STOP | JF.TOLD_TO_STOP_BY_SELF | JF.IS_STOPPING
            )  # True
            await self.on_start_error(exc)
            self._stop_cleanup(reason=JobStopReasons.Internal.ERROR)
            raise

        finally:
            self._bools &= ~JF.IS_STARTING  # False

    async def on_start(self) -> None:
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        A generic hook method that subclasses can use to setup their job objects
        when they start.

        Raises
        ------
        NotImplementedError
            This method must be overloaded in subclasses.
        """
        raise NotImplementedError()

    async def _on_run(self) -> None:
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        Raises
        ------
        NotImplementedError
            This method must be overloaded in subclasses.
        """
        raise NotImplementedError()

    async def on_run(self) -> None:
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        Raises
        ------
        NotImplementedError
            This method must be overloaded in subclasses.
        """
        raise NotImplementedError()

    def _stop_cleanup(
        self,
        reason: JobStopReasons.Internal | JobStopReasons.External | None = None,
    ) -> None:
        self._last_stopping_reason = (
            reason
            if isinstance(reason, (JobStopReasons.External, JobStopReasons.Internal))
            else self.get_stopping_reason()
        )

        self._loop_count = 0

        self._bools &= ~(
            JF.SKIP_NEXT_RUN
            | JF.IS_STARTING
            | JF.TOLD_TO_STOP
            | JF.TOLD_TO_STOP_BY_SELF
            | JF.TOLD_TO_STOP_BY_FORCE
            | JF.IS_STOPPING
            | JF.TOLD_TO_RESTART
            | JF.IS_IDLING
            | JF.STOPPED
        )  # False

        self._idling_since_ts = None
        self._running_since_ts = None
        self._stopped_since_ts = time.time()

        if self._stop_futures is not None:
            for fut in self._stop_futures:
                if not fut.done():
                    fut.set_result(JobStatus.STOPPED)

    async def _on_stop(self) -> None:
        self._bools |= JF.IS_STOPPING  # True

        try:
            await self.on_stop()
        except Exception as exc:
            self._on_stop_exception = exc
            await self.on_stop_error(exc)
            raise

        finally:
            self._stop_cleanup()

    async def on_stop(self) -> None:
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        A method that subclasses can use to shutdown their job objects
        when they stop.

        Note that `on_stop_error()` will not be called if this method raises
        TimeoutError, and this job did not trigger the stop operation.

        Raises
        ------
        NotImplementedError
            This method must be overloaded in subclasses.
        """
        raise NotImplementedError()

    async def on_start_error(self, exc: Exception) -> None:
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        This method gets called when an error occurs while this job is starting up.

        Parameters
        ----------
        exc : Exception
            The exception that occured.
        """
        print(
            f"An exception occured in 'on_start' method of job " f"'{self!r}':\n\n",
            traceback.format_tb(exc.__traceback__),
            file=sys.stderr,
        )

    async def _on_run_error(self, exc: Exception) -> None:
        self._on_run_exception = exc
        self._bools |= (
            JF.TOLD_TO_STOP | JF.TOLD_TO_STOP_BY_SELF | JF.IS_STOPPING
        )  # True
        await self.on_run_error(exc)

    async def on_run_error(self, exc: Exception) -> None:
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        Parameters
        ----------
        exc : Exception
            The exception that occured.
        """
        print(
            f"An exception occured in 'on_run' method of job " f"'{self!r}':\n\n",
            traceback.format_tb(exc.__traceback__),
            file=sys.stderr,
        )

    async def on_stop_error(self, exc: Exception) -> None:
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        This method gets called when an error occurs
        while this job is stopping.

        Parameters
        ----------
            exc (Exception): The exception that occured.
        """
        print(
            f"An exception occured in 'on_stop' method of job " f"'{self!r}':\n\n",
            traceback.format_tb(exc.__traceback__),
            file=sys.stderr,
        )

    def told_to_stop(self) -> bool:
        """`bool`: Whether this job object has been requested to stop from
        an internal or external source. If `True`, this job will
        attempt to stop as soon at it becomes possible, be it gracefully
        or forcefully.
        """
        return bool(self._bools & JF.TOLD_TO_STOP)

    def told_to_stop_by_force(self) -> bool:
        """`bool`: Whether this job object was told to stop forcefully.
        This also applies when it is told to restart, be killed or
        complete. Errors that occur during execution and lead
        to a job stopping do not count. This can only return `True`
        if `told_to_stop()` returns `True`.
        """
        return bool(self._bools & JF.TOLD_TO_STOP_BY_FORCE)

    def told_to_restart(self) -> bool:
        """`bool`: Whether this job object has been requested to restart from
        an internal or external source. If `True`, this job will
        attempt to restart as soon as it becomes possible.
        """
        return bool(self._bools & JF.TOLD_TO_RESTART)

    def is_stopping(self) -> bool:
        """`bool`: Whether this job object is stopping."""
        return bool(self._bools & JF.IS_STOPPING)

    def is_stopping_by_force(self) -> bool:
        """`bool`: Whether this job object is stopping forcefully.
        This also applies when it is being restarted, killed or
        completed. Errors that occur during execution and lead
        to a job stopping do not count as being forcefully stopped.
        This can only return `True` if `is_stoping()` returns `True`.
        """
        return (
            self._bools & (TRUE := JF.IS_STOPPING | JF.TOLD_TO_STOP_BY_FORCE) == TRUE
        )  # all

    def get_stopping_reason(
        self,
    ) -> JobStopReasons.Internal | JobStopReasons.External | None:
        """Get the reason this job is currently stopping, if it is the case.

        Returns
        -------
        JobStopReasons.Internal | JobStopReasons.External | None:
            An enum value from the `Internal` or `External` enums of the
            `JobStopReasons` namespace, if applicable.
        """

        if not self._bools & JF.IS_STOPPING:
            return
        elif (
            self._on_start_exception
            or self._on_run_exception
            or self._on_stop_exception
        ):
            return JobStopReasons.Internal.ERROR
        elif self._job_loop.current_loop == self._count:
            return JobStopReasons.Internal.EXECUTION_COUNT_LIMIT
        elif self._bools & JF.TOLD_TO_STOP_BY_SELF:
            if self._bools & JF.TOLD_TO_RESTART:
                return JobStopReasons.Internal.RESTART
            else:
                return JobStopReasons.Internal.UNSPECIFIC
        else:
            if self._bools & JF.TOLD_TO_RESTART:
                return JobStopReasons.External.RESTART
            else:
                return JobStopReasons.External.UNKNOWN

    def add_to_exception_whitelist(self, *exception_types: type[BaseException]) -> None:
        """Add exceptions to a whitelist, which allows them to be ignored
        when they are raised, if reconnection is enabled.
        Parameters
        ----------
        *exception_types : BaseException
            The exception types to add.
        """
        self._job_loop.add_exception_type(*exception_types)

    def remove_from_exception_whitelist(
        self, *exception_types: type[BaseException]
    ) -> None:
        """Remove exceptions from the exception whitelist for reconnection.
        Parameters
        ----------
        *exception_types: BaseException
            The exception types to remove.
        """
        self._job_loop.remove_exception_type(*exception_types)

    def clear_exception_whitelist(self, keep_default=True):
        """Clear all the exceptions whitelisted for reconnection.

        Parameters
        ----------
        keep_default : bool, optional
            Preserve the default set of exceptions
            in the whitelist. Defaults to True.
        """
        self._job_loop.clear_exception_types()
        if keep_default:
            self._job_loop.add_exception_type(*_DEFAULT_JOB_EXCEPTION_ALLOWLIST)

    def get_last_stopping_reason(
        self,
    ) -> JobStopReasons.Internal | JobStopReasons.External | None:
        """Get the last reason this job object stopped, when applicable.

        Returns
        -------
        JobStopReasons.Internal | JobStopReasons.External | None:
            The reason for stopping.
        """
        return self._last_stopping_reason

    def get_start_exception(self) -> BaseException | None:
        """Get the exception that caused this job to fail at startup
        within the `on_start()` method if it is the case,
        otherwise return None.

        Returns
        -------
        BaseException | None
            The exception, if one occured.
        """
        return self._on_start_exception

    def get_run_exception(self) -> BaseException | None:
        """Get the exception that caused this job to fail while running
        its main loop within the `on_run()` method if it is the case,
        otherwise return None.

        Returns
        -------
        BaseException | None
            The exception, if one occured.
        """
        return self._on_run_exception

    def get_stop_exception(self) -> BaseException | None:
        """Get the exception that caused this job to fail while shutting
        down with the `on_stop()` method if it is the case,
        otherwise return None.

        Returns
        -------
        BaseException | None
            The exception, if one occured.
        """
        return self._on_stop_exception

    async def _initialize_external(self) -> bool:
        """DO NOT CALL THIS METHOD MANUALLY.
        This method to initializes a job using the `_on_init` method
        of the base class.
        """
        if not self._bools & JF.INITIALIZED:
            await self._on_init()
            return True

        return False

    def _start(self) -> bool:
        if not self.is_running():
            self._job_loop.start()
            return True

        return False

    def _start_external(self) -> bool:
        return self._start()

    def stop(self, force=False) -> bool:
        """DO NOT CALL THIS METHOD FROM OUTSIDE YOUR JOB SUBCLASS.
        Stop this job object.

        Parameters
        ----------
        force : bool, optional
            Whether this job object should always be stopped forcefully instead of
            gracefully, thereby ignoring any exceptions that it might have handled
            when reconnecting is enabled for it. Job objects that are idling are
            always stopped forcefully. Defaults to False.

        Returns
        -------
        bool
            Whether the call was successful.
        """

        task = self._job_loop.get_task()

        if (
            not self._bools & (JF.TOLD_TO_STOP | JF.IS_STOPPING | JF.STOPPED)  # not any
            and task is not None
            and not task.done()
        ):
            self._bools |= JF.TOLD_TO_STOP_BY_SELF  # True
            if (
                force or self._bools & JF.IS_IDLING
            ):  # forceful stopping is necessary when idling
                self._bools |= JF.TOLD_TO_STOP_BY_FORCE  # True
                self._job_loop.cancel()
            else:
                self._bools |= JF.SKIP_NEXT_RUN  # True
                # graceful stopping doesn't
                # skip `on_run()` when called in `on_start()`
                self._job_loop.stop()

            self._bools |= JF.TOLD_TO_STOP  # True
            return True

        return False

    def _stop_external(self, force=False) -> bool:
        """DO NOT CALL THIS METHOD MANUALLY.
        See `STOP()`.
        Returns
        -------
        bool
            Whether the call was successful.
        """

        if self.stop(force=force):
            self._bools |= JF.TOLD_TO_STOP_BY_SELF  # True
            return True

        return False

    def restart(self) -> bool:
        """DO NOT CALL THIS METHOD FROM OUTSIDE YOUR JOB SUBCLASS.
        Restart this job object by forcefully stopping it, before
        starting it again automatically. Restarting a job object is
        only possible when it isn't being stopped forcefully, being
        killed, being completed or already being restarted. If a job
        object is being stopped gracefully, it will be restarted immediately
        after it stops.

        Returns
        -------
        bool
            Whether the call was successful.
        """

        task = self._job_loop.get_task()
        if (
            not self._bools & (JF.TOLD_TO_RESTART | JF.TOLD_TO_STOP_BY_FORCE)  # not any
            and task is not None
            and not task.done()
        ):

            def restart_when_over(fut):
                task.remove_done_callback(restart_when_over)
                self._start()

            if not self._bools & (JF.TOLD_TO_STOP | JF.IS_STOPPING):  # not any
                # forceful restart
                self.stop(force=True)

            task.add_done_callback(restart_when_over)
            self._bools |= JF.TOLD_TO_RESTART  # True
            return True

        return False

    def _restart_external(self) -> bool:
        """DO NOT CALL THIS METHOD MANUALLY.
        See `restart()`.
        """
        task = self._job_loop.get_task()

        if (
            not self._bools & (JF.TOLD_TO_RESTART | JF.TOLD_TO_STOP_BY_FORCE)  # not any
            and task is not None
            and not task.done()
        ):

            def restart_when_over(fut):
                task.remove_done_callback(restart_when_over)
                self._start_external()

            if not self._bools & (JF.TOLD_TO_STOP | JF.IS_STOPPING):  # not any
                # forceful restart
                self._stop_external(force=True)

            task.add_done_callback(restart_when_over)
            self._bools |= JF.TOLD_TO_RESTART  # True
            return True

        return False

    def loop_count(self) -> int:
        """`int`: The current amount of `on_run()` calls completed by this job object."""
        return self._loop_count

    def initialized(self) -> bool:
        """`bool`: Whether this job has been initialized."""
        return bool(self._bools & JF.INITIALIZED)

    def is_initializing(self) -> bool:
        """`bool`: Whether this job object is initializing."""

        return bool(self._bools & JF.IS_INITIALIZING)

    def initialized_since(self) -> datetime.datetime | None:
        """`datetime.datetime | None`: The time at which this job object was initialized, if available."""
        if self._initialized_since_ts:
            return datetime.datetime.fromtimestamp(
                self._initialized_since_ts, tz=datetime.timezone.utc
            )
        return None

    def is_starting(self) -> bool:
        """`bool`: Whether this job is currently starting to run."""
        return bool(self._bools & JF.IS_STARTING)

    def is_running(self) -> bool:
        """`bool`: Whether this job is currently running (alive and not stopped)."""
        return (
            self.initialized()
            and self._job_loop.is_running()
            and not self._bools & JF.STOPPED
        )

    def running_since(self) -> datetime.datetime | None:
        """`datetime.datetime | None`: The last time at which this job object started running, if available."""
        if self._running_since_ts:
            return datetime.datetime.fromtimestamp(
                self._running_since_ts, tz=datetime.timezone.utc
            )
        return None

    def stopped(self) -> bool:
        """`bool`: Whether this job is currently stopped (alive and not running)."""
        return bool(self._bools & JF.STOPPED)

    def stopped_since(self) -> datetime.datetime | None:
        """`datetime.datetime | None`: The last time at which this job object stopped, if available."""
        if self._stopped_since_ts:
            return datetime.datetime.fromtimestamp(
                self._stopped_since_ts, tz=datetime.timezone.utc
            )
        return None

    def is_idling(self) -> bool:
        """`bool`: Whether this task is currently idling
        (running, waiting for the next opportunity to continue execution)
        """
        return bool(self._bools & JF.IS_IDLING)

    def idling_since(self) -> datetime.datetime | None:
        """`datetime.datetime | None`: The last time at which this job object began idling, if available."""
        if self._idling_since_ts:
            return datetime.datetime.fromtimestamp(
                self._idling_since_ts, tz=datetime.timezone.utc
            )
        return None

    def run_failed(self) -> bool:
        """`bool`: Whether this job's `.on_run()` method failed an execution attempt,
        due to an unhandled exception being raised.
        """
        return self._job_loop.failed()

    def is_restarting(self) -> bool:
        """`bool`: Whether this job is restarting."""

        return (
            self._bools & (TRUE := JF.IS_STOPPING | JF.TOLD_TO_RESTART) == TRUE
        )  # any

    def was_restarted(self) -> bool:
        """`bool`: A convenience method to check if a job was restarted."""
        return self._last_stopping_reason in (
            JobStopReasons.Internal.RESTART,
            JobStopReasons.External.RESTART,
        )

    def await_stop(
        self,
        timeout: float | None = None,
    ) -> Coroutine[Any, Any, Literal[JobStatus.STOPPED]]:
        """Wait for this job object to stop using the
        coroutine output of this method.

        Parameters
        ----------
        timeout : float, optional
            Timeout for awaiting. Defaults to None.

        Returns
        -------
        Coroutine[Any, Any, Literal[JobStatus.STOPPED]]
            A coroutine that evaluates to `JobStatus.STOPPED`.

        Raises
        ------
        JobNotRunning
            This job object is not running.
        asyncio.TimeoutError
            The timeout was exceeded.
        """

        if not self.is_running():
            raise JobNotRunning("This job object is running")

        loop = asyncio.get_running_loop()

        fut = loop.create_future()

        if self._stop_futures is None:
            self._stop_futures = []

        self._stop_futures.append(fut)

        return asyncio.wait_for(fut, timeout)

    def status(self) -> JobStatus:
        """`JobStatus`: Get the job status of this job as a value from the
        `JobStatus` enum.
        """
        output = None
        if self.is_running():
            if self.is_starting():
                output = JobStatus.STARTING
            elif self.is_idling():
                output = JobStatus.IDLING
            elif self.is_stopping():
                if self.is_restarting():
                    output = JobStatus.RESTARTING
                else:
                    output = JobStatus.STOPPING
            else:
                output = JobStatus.RUNNING
        elif self.stopped():
            output = JobStatus.STOPPED
        elif self.initialized():
            output = JobStatus.INITIALIZED
        else:
            output = JobStatus.FRESH

        return output

    def __repr__(self):
        output_str = f"<{self.__class__.__qualname__} " f"(id={self._runtime_id})>"

        return output_str

    def __str__(self):
        return (
            f"<{self.__class__.__qualname__} "
            + f"(id={self._runtime_id} created_at={self.created_at} "
            + f"status={self.status().name})>"
        )


class JobCore(_JobCore):
    """The base class of all job-related interfaces,
    which implements core functionality for its
    subclasses."""

    __slots__ = (
        "_manager",
        "_creator",
        "_permission_level",
        "_registered_at_ts",
        "_done_since_ts",
        "_output_fields",
        "_output_queues",
        "_output_queue_proxies",
        "_output_field_futures",
        "_output_queue_futures",
        "_unguard_futures",
        "_done_futures",
        "_done_callbacks",
        "_proxy",
        "_guarded_job_proxies_dict",
        "_guardian",
        "_alive_since_ts",
    )

    _CREATED_AT = datetime.datetime.now(datetime.timezone.utc)
    _RUNTIME_ID = f"JobBase-{int(_CREATED_AT.timestamp()*1_000_000_000)}"
    _SINGLE: bool = False

    OutputFields: "Any | groupings.OutputNameRecord | None" = None
    OutputQueues: "Any | groupings.OutputNameRecord | None" = None
    PublicMethods: "Any | groupings.NameRecord | None" = None

    PUBLIC_METHODS_MAP: dict[str, Callable[..., Any]] | None = None
    PUBLIC_METHODS_CHAINMAP: FastChainMap | None = None

    def __init_subclass__(
        cls,
        class_uuid: str | None = None,
    ) -> None:
        super().__init_subclass__(class_uuid=class_uuid)

        name = cls.__qualname__

        if isinstance(cls.OutputFields, type):
            if not issubclass(cls.OutputFields, groupings.OutputNameRecord):
                if cls.OutputFields.__base__ is not object:
                    raise TypeError(
                        "the 'OutputFields' variable must be a subclass of 'OutputNameRecord' "
                        "or an immediate subclass of object that acts as a placeholder"
                    )

                cls.OutputFields = type(
                    "OutputFields",
                    (groupings.OutputNameRecord,),
                    dict(**cls.OutputFields.__dict__),
                )

        if isinstance(cls.OutputQueues, type):
            if not issubclass(cls.OutputQueues, groupings.OutputNameRecord):
                if cls.OutputQueues.__base__ is not object:
                    raise TypeError(
                        "the 'OutputQueues' variable must be a subclass of 'OutputNameRecord' "
                        "or an immediate subclass of object that acts as a placeholder"
                    )

                cls.OutputQueues = type(
                    "OutputQueues",
                    (groupings.OutputNameRecord,),
                    dict(**cls.OutputQueues.__dict__),
                )

        if isinstance(cls.PublicMethods, type):
            if not issubclass(cls.PublicMethods, groupings.NameRecord):
                if cls.PublicMethods.__base__ is not object:
                    raise TypeError(
                        "the 'PublicMethods' variable must be a subclass of 'NameRecord' "
                        "or an immediate subclass of object that acts as a placeholder"
                    )

                bases = (
                    groupings.NameRecord,
                    *(
                        utils.class_getattr_unique(
                            cls,
                            "PublicMethods",
                            filter_func=lambda v: isinstance(v, groupings.NameRecord),
                            check_dicts_only=True,
                        ),
                    ),
                )
                cls.PublicMethods = type(
                    "PublicMethods", bases, dict(**cls.PublicMethods.__dict__)  # type: ignore
                )
            elif issubclass(cls.PublicMethods, groupings.OutputNameRecord):
                raise TypeError(
                    "the 'PublicMethods' variable must not be a subclass of "
                    "'OutputNameRecord', but a subclass of 'NameRecord' "
                    "or an immediate subclass of object that acts as a placeholder"
                )

        public_methods_map = {}
        for obj in cls.__dict__.values():
            if isinstance(obj, FunctionType) and "__public" in obj.__dict__:
                public_methods_map[obj.__name__] = obj

        cls.PUBLIC_METHODS_MAP = public_methods_map or None

        mro_public_methods = utils.class_getattr_unique(
            cls,
            "PUBLIC_METHODS_MAP",
            filter_func=lambda v: v and isinstance(v, dict),
            check_dicts_only=True,
        )

        if mro_public_methods:
            cls.PUBLIC_METHODS_CHAINMAP = FastChainMap(
                *mro_public_methods,
                ignore_defaultdicts=True,
            )

    def __init__(self) -> None:
        super().__init__()

        self._manager: "proxies.JobManagerProxy | Any" = None
        self._creator: "proxies.JobProxy | None" = None
        self._permission_level: JobPermissionLevels | None = None

        self._registered_at_ts: float | None = None
        self._done_since_ts: float | None = None

        self._done_futures: list[asyncio.Future] | None = None
        self._done_callbacks: dict[int, Callable[["_JobCore"], Any]] | None = None

        self._output_fields: dict[str, Any] | None = None
        self._output_field_futures: dict[
            str, list[asyncio.Future[Any] | Any]
        ] | None = None

        self._output_queues: dict[str, list[Any]] | None = None
        self._output_queue_futures: dict[
            str, list[asyncio.Future[Any] | Any]
        ] | None = None
        self._output_queue_proxies: list["proxies.JobOutputQueueProxy"] | None = None

        if self.OutputFields is not None:
            self._output_field_futures = {}
            self._output_fields = {}

        if self.OutputQueues is not None:
            self._output_queue_proxies = []
            self._output_queue_futures = {}
            self._output_queues = {}

        self._unguard_futures: list[asyncio.Future[bool]] | None = None
        self._guardian: "proxies.JobProxy | None" = None

        self._guarded_job_proxies_dict: dict[str, "proxies.JobProxy"] | None = None
        # will be assigned by job manager

        self._bools &= ~(
            JF.COMPLETED | JF.TOLD_TO_COMPLETE | JF.KILLED | JF.TOLD_TO_BE_KILLED
        )  # False

        self._bools &= ~JF.INTERNAL_STARTUP_KILL  # False
        # needed for jobs to react to killing at
        # startup, to send them to `on_stop()` immediately

        self._bools &= ~JF.EXTERNAL_STARTUP_KILL  # False
        # give a job a chance to react to an external startup kill

        self._alive_since_ts: float | None = None

        self._proxy: "proxies.JobProxy" = proxies.JobProxy(self)  # type: ignore

    @classmethod
    def singleton(cls) -> bool:
        """`bool`: Whether this job class is a singleton, meaning
        that it may only be registered once per job manager.
        """
        return cls._SINGLE

    @property
    def permission_level(self) -> JobPermissionLevels:
        if self._permission_level is not None:
            return self._permission_level

        raise JobNotAlive("This job object doesn't yet have a permission level")

    @property
    def registered_at(self) -> datetime.datetime | None:
        if self._registered_at_ts:
            return datetime.datetime.fromtimestamp(
                self._registered_at_ts, tz=datetime.timezone.utc
            )
        return None

    @property
    def manager(self) -> "proxies.JobManagerProxy":
        """The `JobManagerProxy` object bound to this job object."""
        return self._manager

    @property
    def creator(self) -> "proxies.JobProxy | None":
        """`JobProxy | None`: The `JobProxy` of the creator of this job object."""
        return self._creator

    @property
    def guardian(self) -> "proxies.JobProxy | None":
        """`JobProxy | None`: The `JobProxy` of the current guardian of this job object."""
        return self._guardian

    @property
    def guarded_jobs(self) -> Mapping[int, "proxies.JobProxy"]:
        """`Mapping[int, JobProxy]`: A mapping of `JobProxy` objects of the jobs guarded by this job."""
        return MappingProxyType(self._guarded_job_proxies_dict or {})  # type: ignore

    @property
    def proxy(self) -> "proxies.JobProxy":
        """`JobProxy`: The `JobProxy` object bound to this job object."""
        return self._proxy

    async def _on_start(self) -> None:
        self._on_start_exception = None
        self._on_run_exception = None
        self._on_stop_exception = None

        self._bools |= JF.IS_STARTING  # True
        self._bools &= ~(JF.STOPPED | JF.IS_IDLING)  # False

        self._stopped_since_ts = None
        self._idling_since_ts = None

        self._running_since_ts = time.time()

        try:
            if not self._bools & JF.EXTERNAL_STARTUP_KILL:
                await self.on_start()

        except Exception as exc:
            self._on_start_exception = exc
            self._bools |= (
                JF.TOLD_TO_STOP | JF.TOLD_TO_STOP_BY_SELF | JF.IS_STOPPING
            )  # True
            await self.on_start_error(exc)
            self._stop_cleanup(reason=JobStopReasons.Internal.ERROR)
            raise

        finally:
            self._bools &= ~JF.IS_STARTING  # False

    def _stop_cleanup(
        self,
        reason: JobStopReasons.Internal | JobStopReasons.External | None = None,
    ) -> None:
        self._last_stopping_reason = (
            reason
            if isinstance(reason, (JobStopReasons.External, JobStopReasons.Internal))
            else self.get_stopping_reason()
        )

        self._loop_count = 0

        self._bools &= ~(
            JF.SKIP_NEXT_RUN
            | JF.IS_STARTING
            | JF.INTERNAL_STARTUP_KILL
            | JF.EXTERNAL_STARTUP_KILL
            | JF.TOLD_TO_STOP
            | JF.TOLD_TO_STOP_BY_SELF
            | JF.TOLD_TO_STOP_BY_FORCE
            | JF.IS_STOPPING
            | JF.TOLD_TO_RESTART
        )  # False

        if self._bools & (JF.TOLD_TO_COMPLETE | JF.TOLD_TO_BE_KILLED):  # any
            self._bools &= ~JF.INITIALIZED  # False
            if self._guardian is not None:
                if self._unguard_futures is not None:
                    for fut in self._unguard_futures:
                        if not fut.done():
                            fut.set_result(True)

                    self._unguard_futures.clear()
                    self._manager._self_ungard()

            if self._guarded_job_proxies_dict is not None:
                for job_proxy in self._guarded_job_proxies_dict.values():
                    self.manager.unguard_job(job_proxy)

                self._guarded_job_proxies_dict.clear()

            if self.OutputQueues is not None:
                self._output_queue_proxies.clear()  # type: ignore

            if self._bools & JF.TOLD_TO_COMPLETE:
                self._bools &= ~JF.TOLD_TO_COMPLETE  # False
                self._bools |= JF.COMPLETED  # True
                self._done_since_ts = time.time()

                self._alive_since_ts = None

                if self._done_futures is not None:
                    for fut in self._done_futures:
                        if not fut.done():
                            fut.set_result(JobStatus.COMPLETED)

                    self._done_futures.clear()

                if self.OutputFields is not None:
                    for fut_list in self._output_field_futures.values():  # type: ignore
                        for fut in fut_list:
                            if not fut.done():
                                fut.set_result(JobStatus.COMPLETED)

                        fut_list.clear()

                    self._output_field_futures.clear()  # type: ignore

                if self.OutputQueues is not None:
                    for fut_list in self._output_queue_futures.values():  # type: ignore
                        for fut, cancel_if_cleared in fut_list:
                            if not fut.done():
                                fut.set_result(JobStatus.COMPLETED)

            elif self._bools & JF.TOLD_TO_BE_KILLED:
                self._bools &= ~JF.TOLD_TO_BE_KILLED  # False
                self._bools |= JF.KILLED  # True
                self._done_since_ts = time.time()

                self._alive_since_ts = None

                if self._done_futures is not None:
                    for fut in self._done_futures:
                        if not fut.done():
                            fut.set_result(JobStatus.KILLED)

                    self._done_futures.clear()

                if self.OutputFields:
                    for fut_list in self._output_field_futures.values():  # type: ignore
                        for fut in fut_list:
                            if not fut.done():
                                fut.set_result(JobStatus.KILLED)

                        fut_list.clear()

                    self._output_field_futures.clear()  # type: ignore

                if self.OutputQueues:
                    for fut_list in self._output_queue_futures.values():  # type: ignore
                        for fut, cancel_if_cleared in fut_list:
                            if not fut.done():
                                fut.set_result(JobStatus.KILLED)

        self._bools &= ~JF.IS_IDLING  # False
        self._idling_since_ts = None

        self._running_since_ts = None

        if self._bools & (JF.KILLED | JF.COMPLETED):  # any
            self._bools &= ~JF.STOPPED  # False
            self._stopped_since_ts = None

            if self._stop_futures is not None:
                for fut in self._stop_futures:
                    if not fut.done():
                        fut.set_result(
                            JobStatus.KILLED
                            if self._bools & JF.KILLED
                            else JobStatus.COMPLETED
                        )

            if not (self.OutputFields or self.OutputQueues):
                self._proxy._eject_from_source()

            self._manager._eject()

        else:
            self._bools |= JF.STOPPED  # True
            self._stopped_since_ts = time.time()

            if self._stop_futures is not None:
                for fut in self._stop_futures:
                    if not fut.done():
                        fut.set_result(JobStatus.STOPPED)

    async def _on_stop(self) -> None:
        self._bools |= JF.IS_STOPPING  # True
        try:
            if not self._bools & JF.TOLD_TO_STOP_BY_SELF:
                await asyncio.wait_for(
                    self.on_stop(),
                    self._manager.get_job_stop_timeout(),
                )
            else:
                await self.on_stop()

        except asyncio.TimeoutError as exc:
            self._on_stop_exception = exc
            if not self._stop_by_self:  # type: ignore
                await self.on_stop_error(exc)
            raise

        except Exception as exc:
            self._on_stop_exception = exc
            await self.on_stop_error(exc)
            raise

        finally:
            self._stop_cleanup()

    def told_to_be_killed(self) -> bool:
        """`bool`: Whether this job object has been requested to get killed from
        an internal or external source. If `True`, this job will
        attempt to be killed as soon as it becomes possible.
        """
        return bool(self._bools & JF.TOLD_TO_BE_KILLED)

    def told_to_complete(self) -> bool:
        """`bool`: Whether this job object has been requested to complete from
        an internal source. If `True`, this job will
        attempt to complete as soon as it becomes possible.
        """
        return bool(self._bools & JF.TOLD_TO_COMPLETE)

    def get_stopping_reason(
        self,
    ) -> JobStopReasons.Internal | JobStopReasons.External | None:

        if not self._bools & JF.IS_STOPPING:
            return
        elif (
            self._on_start_exception
            or self._on_run_exception
            or self._on_stop_exception
        ):
            return JobStopReasons.Internal.ERROR
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

    def _start(self) -> bool:
        if self.done():
            raise JobIsDone("This job object is already done.")

        elif not self.is_running():
            self._job_loop.start()
            return True

        return False

    async def _initialize_external(self) -> bool:
        """DO NOT CALL THIS METHOD MANUALLY.

        This method to initializes a job using the `_on_init` method
        of the base class.
        """
        if self._manager is not None and not self._bools & (
            JF.KILLED | JF.COMPLETED
        ):  # not any
            await self._on_init()
            self._alive_since_ts = time.time()
            return True

        return False

    def restart(self) -> bool:
        task = self._job_loop.get_task()
        if (
            not self._bools
            & (
                JF.TOLD_TO_RESTART
                | JF.TOLD_TO_BE_KILLED
                | JF.TOLD_TO_COMPLETE
                | JF.TOLD_TO_STOP_BY_FORCE
            )  # not any
            and task is not None
            and not task.done()
        ):

            def restart_when_over(fut):
                task.remove_done_callback(restart_when_over)
                self._start()

            if not self._bools & (JF.TOLD_TO_STOP | JF.IS_STOPPING):  # not any
                # forceful restart
                self.stop(force=True)

            task.add_done_callback(restart_when_over)
            self._bools |= JF.TOLD_TO_RESTART  # True
            return True

        return False

    def _restart_external(self) -> bool:
        task = self._job_loop.get_task()
        if (
            not self._bools
            & (
                JF.TOLD_TO_RESTART
                | JF.TOLD_TO_BE_KILLED
                | JF.TOLD_TO_COMPLETE
                | JF.TOLD_TO_STOP_BY_FORCE
            )  # not any
            and task is not None
            and not task.done()
        ):

            def restart_when_over(fut):
                task.remove_done_callback(restart_when_over)
                self._start_external()

            if not self._bools & (JF.TOLD_TO_STOP | JF.IS_STOPPING):  # not any
                # forceful restart
                self._stop_external(force=True)

            task.add_done_callback(restart_when_over)
            self._bools |= JF.TOLD_TO_RESTART  # True
            return True

        return False

    def complete(self) -> bool:
        """DO NOT CALL THIS METHOD FROM OUTSIDE YOUR JOB SUBCLASS.

        Stops this job object forcefully, before removing it
        from its job manager. Any job that was completed
        has officially finished execution, and all jobs waiting
        for this job to complete will be notified. If a job had
        reconnecting enabled, then it will be silently cancelled
        to ensure that it suspends all execution.

        Returns
        -------
        bool
            Whether the call was successful.
        """

        if not self._bools & (JF.TOLD_TO_BE_KILLED | JF.TOLD_TO_COMPLETE):  # not any
            if not self._bools & JF.IS_STOPPING:
                self.stop(force=True)

            self._bools |= JF.TOLD_TO_COMPLETE  # True
            return True

        return False

    def kill(self) -> bool:
        """DO NOT CALL THIS METHOD FROM OUTSIDE YOUR JOB SUBCLASS.

        Stops this job object forcefully, before removing it from its job manager.

        Returns
        -------
        bool
            Whether this method was successful.
        """

        if not self._bools & (JF.TOLD_TO_BE_KILLED | JF.TOLD_TO_COMPLETE):  # not any
            if self._kill_raw():
                self._bools |= JF.TOLD_TO_BE_KILLED  # True
                return True

        return False

    def _kill_raw(self):
        success = False
        if self._bools & JF.IS_STARTING:
            # ensure that a job will always
            # notice when it is killed while it is
            # in `on_start()`
            self._bools |= JF.INTERNAL_STARTUP_KILL  # True
            success = True

        elif not self._bools & JF.IS_STOPPING:
            success = self.stop(force=True)

        return success

    def _kill_external(self, awaken=True) -> bool:
        """DO NOT CALL THIS METHOD MANUALLY.

        Stops this job object forcefully, before removing it from its job manager.
        If a job is already stopped, it can be awoken using this method, or simply
        uninitialized and removed from its job manager without it being able to
        react to the process.

        Parameters
        ----------
        awaken : bool, optional
            Whether to awaken this job object before
            killing it, if it is stopped. Defaults to True.

        Returns
        -------
        bool
            Whether this method was successful.
        """

        if not self._bools & (JF.TOLD_TO_BE_KILLED | JF.TOLD_TO_COMPLETE):  # not any
            if self._kill_external_raw(awaken=awaken):
                self._bools |= JF.TOLD_TO_BE_KILLED  # True
                return True

        return False

    def _kill_external_raw(self, awaken=True):
        success = False
        if self.is_running():
            if not self._bools & JF.IS_STOPPING:
                success = self._stop_external(force=True)

        elif awaken:
            self._bools |= (
                JF.EXTERNAL_STARTUP_KILL
            )  # True  # start and kill as fast as possible
            success = self._start_external()
            # don't set `_told_to_be_killed` to True so that this method
            # can be called again to perform the actual kill

        else:
            self._bools |= JF.TOLD_TO_BE_KILLED  # True  # required for next method
            self._stop_cleanup(reason=JobStopReasons.External.KILLING)
            success = True

        return success

    def alive(self) -> bool:
        """`bool`: Whether this job is currently alive
        (initialized and bound to a job manager, not completed or killed).
        """
        return bool(
            self._manager is not None
            and self._bools & JF.INITIALIZED
            and not self._bools & (JF.KILLED | JF.COMPLETED)  # not any
        )

    def alive_since(self) -> datetime.datetime | None:
        """`datetime.datetime | None`: The last time at which this job object became alive, if available."""
        if self._alive_since_ts:
            return datetime.datetime.fromtimestamp(
                self._alive_since_ts, tz=datetime.timezone.utc
            )
        return None

    def is_running(self) -> bool:
        """`bool`: Whether this job is currently running (alive and not stopped)."""
        return (
            self.alive()
            and self._job_loop.is_running()
            and not self._bools & JF.STOPPED
        )

    def killed(self) -> bool:
        """`bool`: Whether this job was killed."""
        return bool(self._bools & JF.KILLED)

    def is_being_killed(self) -> bool:
        """`bool`: Whether this job is being killed."""
        return (
            self._bools & (TRUE := JF.IS_STOPPING | JF.TOLD_TO_BE_KILLED) == TRUE
        )  # all

    def is_being_startup_killed(self) -> bool:
        """`bool`: Whether this job was started up only for it to be killed.
        This is useful for knowing if a job skipped `on_start()` and `on_run()`
        due to that, and can be checked for within `on_stop()`.
        """
        return (
            self._bools
            & (TRUE := JF.EXTERNAL_STARTUP_KILL | JF.IS_STOPPING | JF.TOLD_TO_BE_KILLED)
            == TRUE
        )

    def completed(self) -> bool:
        """`bool`: Whether this job completed successfully."""
        return bool(self._bools & JF.COMPLETED)

    def is_completing(self) -> bool:
        """`bool`: Whether this job is currently completing."""
        return (
            self._bools & (TRUE := JF.IS_STOPPING | JF.TOLD_TO_COMPLETE) == TRUE
        )  # all

    def done(self) -> bool:
        """`bool`: Whether this job was killed or has completed."""
        return bool(self._bools & (JF.KILLED | JF.COMPLETED))  # any

    def done_since(self) -> datetime.datetime | None:
        """`datetime.datetime | None`: The time at which this job object completed successfully or was killed, if available."""
        if self._done_since_ts is not None:
            return datetime.datetime.fromtimestamp(
                self._done_since_ts, tz=datetime.timezone.utc
            )
        return None

    killed_at = property(fget=done_since)
    """The time at which this job object was killed, if available.

    Returns
    -------
        datetime.datetime | None: The time, if available.
    """

    completed_at = killed_at
    """The time at which this job object completed successfully, if available.

    Returns
    -------
        datetime.datetime | None: The time, if available.
    """

    def is_being_guarded(self) -> bool:
        """`bool`: Whether this job object is being guarded."""
        return self._guardian is not None

    def await_stop(
        self,
        timeout: float | None = None,
    ) -> Coroutine[
        Any, Any, Literal[JobStatus.STOPPED, JobStatus.KILLED, JobStatus.COMPLETED]
    ]:
        """Wait for this job object to stop using the
        coroutine output of this method.

        Parameters
        ----------
        timeout : float, optional
            Timeout for awaiting. Defaults to None.

        Returns
        -------
        Coroutine[Any, Any, Literal[JobStatus.STOPPED, JobStatus.KILLED, JobStatus.COMPLETED]]
            A coroutine that evaluates to either `STOPPED`,
            `KILLED` or `COMPLETED` from the `JobStatus` enum.

        Raises
        ------
        JobIsDone
            This job object is already done.
        JobNotRunning
            This job object is not running.
        asyncio.TimeoutError
            The timeout was exceeded.
        """

        if not self.is_running():
            raise JobNotRunning("This job object is not running")
        elif self.done():
            raise JobIsDone("This job object is already done")

        fut = self._manager._loop.create_future()

        if self._stop_futures is None:
            self._stop_futures = []

        self._stop_futures.append(fut)

        return asyncio.wait_for(fut, timeout)

    def await_done(
        self, timeout: float | None = None, cancel_if_killed: bool = False
    ) -> Coroutine[Any, Any, Literal[JobStatus.KILLED, JobStatus.COMPLETED]]:
        """Wait for this job object to be done (completed or killed) using the
        coroutine output of this method.

        Parameters
        ----------
        timeout : float, optional
            Timeout for awaiting. Defaults to None.

        Returns
        -------
        Coroutine[Any, Any, Literal[JobStatus.KILLED, JobStatus.COMPLETED]]
            A coroutine that evaluates to either `KILLED` or `COMPLETED` from the
            `JobStatus` enum.

        Raises
        ------
        JobIsDone
            This job object is already done.
        asyncio.TimeoutError
            The timeout was exceeded.
        asyncio.CancelledError
            The job was killed.
        """
        if self.done():
            raise JobIsDone("This job object is already done")

        fut = self._manager._loop.create_future()

        if self._done_futures is None:
            self._done_futures = []

        self._done_futures.append(fut)

        return asyncio.wait_for(fut, timeout)

    def await_unguard(self, timeout: float | None = None) -> Coroutine[Any, Any, bool]:
        """Wait for this job object to be unguarded using the
        coroutine output of this method.

        Parameters
        ----------
        timeout : float, optional
            Timeout for awaiting. Defaults to None.

        Returns
        -------
        Coroutine[Any, Any, bool]
            A coroutine that evaluates to `True`.

        Raises
        ------
        JobNotAlive
            This job object is not alive.
        JobIsDone
            This job object is already done.
        JobStateError
            This job object isn't being guarded.
        asyncio.TimeoutError
            The timeout was exceeded.
        asyncio.CancelledError
            The job was killed.
        """

        if not self.alive():
            raise JobNotAlive("this job object is not alive")
        elif self.done():
            raise JobIsDone("this job object is already done")
        elif not self._guardian is not None:
            raise JobStateError("this job object is not being guarded by a job")

        fut = self._manager._loop.create_future()

        if self._unguard_futures is None:
            self._unguard_futures = []

        self._unguard_futures.append(fut)

        return asyncio.wait_for(fut, timeout)

    def get_output_queue_proxy(self) -> "proxies.JobOutputQueueProxy":
        """Get a job output queue proxy object for more convenient
        reading of job output queues while this job is running.

        Returns
        -------
        JobOutputQueueProxy
            The output queue proxy.

        Raises
        ------
        JobNotAlive
            This job object is not alive.
        JobIsDone
            This job object is already done.
        TypeError
            Output queues aren't defined for this job type.
        """

        if not self.alive():
            raise JobNotAlive("this job object is not alive")
        elif self.done():
            raise JobIsDone("this job object is already done")

        if not (self.OutputQueues is None or self._output_queue_proxies is None):
            output_queue_proxy = proxies.JobOutputQueueProxy(self)  # type: ignore
            self._output_queue_proxies.append(output_queue_proxy)
            return output_queue_proxy

        raise TypeError("this job object does not support output queues")

    @classmethod
    def verify_output_field_support(
        cls, field_name: str, raise_exceptions=False
    ) -> bool:
        """Verify if a specified output field name is supported by this job,
        or if it supports output fields at all. Disabled output field names
        are seen as unsupported.

        Parameters
        ----------
        field_name : str
            The name of the output field to set.
        raise_exceptions : bool, optional
            Whether exceptions should be raised. Defaults to False.

        Returns
        -------
        bool
            ``True`` if condition is met, ``False`` otherwise.

        Raises
        ------
        TypeError
            Output fields aren't supported for this job, or `field_name` is not a string.
        ValueError
            The specified field name was marked as disabled.
        LookupError
            The specified field name is not defined by this job.
        """

        if cls.OutputFields is None:
            if raise_exceptions:
                raise TypeError(
                    f"'{cls.__qualname__}' class does not"
                    f" implement or inherit an 'OutputFields' class namespace"
                )
            return False

        value = getattr(cls.OutputFields, field_name, None)

        if value is None:
            if raise_exceptions:
                raise (
                    LookupError(
                        f"field name '{field_name}' is not defined in"
                        f" 'OutputFields' class namespace of "
                        f"'{cls.__qualname__}' class"
                    )
                    if isinstance(field_name, str)
                    else TypeError(
                        f"'field_name' argument must be of type str,"
                        f" not {field_name.__class__.__name__}"
                    )
                )
            return False

        elif value == "DISABLED":
            if raise_exceptions:
                raise ValueError(
                    f"the output field name '{field_name}' has been marked as disabled"
                )
            return False

        return True

    @classmethod
    def verify_output_queue_support(
        cls, queue_name: str, raise_exceptions=False
    ) -> bool:
        """Verify if a specified output queue name is supported by this job,
        or if it supports output queues at all. Disabled output queue names
        are seen as unsupported.

        Parameters
        ----------
        queue_name : str
            The name of the output queue to set.
        raise_exceptions : bool, optional
            Whether exceptions should be raised. Defaults to False.

        Returns
        -------
        bool
            ``True`` if condition is met, ``False`` otherwise.

        Raises
        ------
        TypeError
            Output queues aren't supported for this job,
              or `queue_name` is not a string.
        ValueError
            The specified queue name was marked as disabled.
        LookupError
            The specified queue name is not defined by this job.
        """
        if cls.OutputQueues is None:
            if raise_exceptions:
                raise TypeError(
                    f"'{cls.__qualname__}' class does not"
                    f" implement or inherit an 'OutputQueues' class namespace"
                )
            return False

        value = getattr(cls.OutputQueues, queue_name, None)

        if value is None:
            if raise_exceptions:
                raise (
                    LookupError(
                        f"queue name '{queue_name}' is not defined in"
                        f" 'OutputQueues' class namespace of "
                        f"'{cls.__qualname__}' class"
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

    def set_output_field(self, field_name: str, value: Any) -> None:
        """Set the specified output field to have the given value,
        while releasing the value to external jobs awaiting the field.

        Parameters
        ----------
        field_name : str
            The name of the output field to set.

        Raises
        ------
        TypeError
            Output fields aren't supported for this job,
              or `field_name` is not a string.
        LookupError
            The specified field name is not defined by this job.
        JobOutputError
            An output field value has already been set.
        """

        self.verify_output_field_support(field_name, raise_exceptions=True)
        assert not (self._output_fields is None or self._output_field_futures is None)

        field_value = self._output_fields.get(field_name, UNSET)

        if field_value is not UNSET:
            raise JobOutputError(
                "An output field value has already been set for the field"
                f" '{field_name}'"
            )

        self._output_fields[field_name] = value

        if field_name in self._output_field_futures:
            for fut in self._output_field_futures[field_name]:
                if not fut.done():
                    fut.set_result(value)

            self._output_field_futures[field_name].clear()

    def push_output_queue(self, queue_name: str, value: Any) -> None:
        """Add a value to the specified output queue,
        while releasing the value to external jobs
        awaiting the field.

        Parameters
        ----------
        queue_name : str
            The name of the target output queue.

        Raises
        ------
        TypeError
            Output queues aren't supported for this job,
              or `queue_name` is not a string.
        LookupError
            The specified queue name is not defined by this job.
        JobOutputError
            An output field value has already been set.
        """

        self.verify_output_queue_support(queue_name, raise_exceptions=True)
        assert not (
            self._output_queues is None
            or self._output_queue_proxies is None
            or self._output_queue_futures is None
        )
        if queue_name not in self._output_queues:
            self._output_queues[queue_name] = queue = []
            for proxy in self._output_queue_proxies or ():
                proxy._new_output_queue_alert(queue_name, queue)

        queue_entries: list = self._output_queues[queue_name]
        queue_entries.append(value)

        if queue_name in self._output_queue_futures:
            for fut, cancel_if_cleared in self._output_queue_futures[queue_name]:
                if not fut.done():
                    fut.set_result(value)

            self._output_queue_futures[queue_name].clear()

    def get_output_field(self, field_name: str, default=UNSET, /) -> Any:
        """Get the value of a specified output field.

        Parameters
        ----------
        field_name : str
            The name of the target output field.
        default : Any, optional
            The value to return if the specified output field does not exist,
            has not been set, or if this job doesn't support them at all,
            instead of raising an exception.

        Returns
        -------
        Any
            The output field value.

        Raises
        ------
        TypeError
            Output fields aren't supported for this job,
              or `field_name` is not a string.
        LookupError
            The specified field name is not defined by this job.
        JobOutputError
            An output field value is not set.
        """

        if self.OutputFields is None:
            if default is UNSET:
                self.verify_output_field_support(field_name, raise_exceptions=True)
            return default

        elif getattr(self.OutputFields, field_name, None) in (None, "DISABLED"):
            if default is UNSET:
                self.verify_output_field_support(field_name, raise_exceptions=True)
            return default

        assert self._output_fields is not None
        if field_name not in self._output_fields:
            if default is UNSET:
                raise JobOutputError(
                    "An output field value has not been set for the field"
                    f" '{field_name}'"
                )
            return default

        old_field_data_list: list = self._output_fields[field_name]

        if not old_field_data_list[1]:
            if default is UNSET:
                raise JobOutputError(
                    "An output field value has not been set for the field"
                    f" '{field_name}'"
                )
            return default

        return old_field_data_list[0]

    def get_output_queue_contents(self, queue_name: str) -> list[Any]:
        """Get a list of all values present in the specified output queue.
        For continuous access to job output queues, consider requesting
        a `JobOutputQueueProxy` object using `.get_output_queue_proxy()`.

        Parameters
        ----------
        queue_name : str
            The name of the target output queue.
        default : Any, optional
            The value to return if the specified output queue does not exist, is
            empty, or if this job doesn't support them at all, instead of raising
            an exception.

        Returns
        -------
        list
            A list of values.

        Raises
        ------
        JobOutputError
            The specified output queue is empty.
        TypeError
            Output queues aren't supported for this job,
              or `queue_name` is not a string.
        LookupError
            The specified queue name is not defined by this job.
        """

        self.verify_output_queue_support(queue_name, raise_exceptions=True)

        assert self._output_queues is not None
        if queue_name not in self._output_queues:
            raise JobOutputError(f"The specified output queue '{queue_name}' is empty")

        queue_data_list: list = self._output_queues[queue_name]

        if not queue_data_list:
            raise JobOutputError(f"The specified output queue '{queue_name}' is empty")

        return queue_data_list[:]

    def clear_output_queue(self, queue_name: str) -> None:
        """Clear all values in the specified output queue.

        Parameters
        ----------
        queue_name : str
            The name of the target output field.
        """
        self.verify_output_queue_support(queue_name, raise_exceptions=True)

        assert not (
            self._output_queues is None
            or self._output_queue_futures is None
            or self._output_queue_proxies is None
        )

        if queue_name in self._output_queues:
            for output_queue_proxy in self._output_queue_proxies:
                output_queue_proxy._output_queue_clear_alert(queue_name)

            for fut, cancel_if_cleared in self._output_queue_futures[queue_name]:
                if not fut.done():
                    if cancel_if_cleared:
                        fut.cancel(f"The job output queue '{queue_name}' was cleared")
                    else:
                        fut.set_result(JobStatus.OUTPUT_QUEUE_CLEARED)

            self._output_queues[queue_name].clear()

    @classmethod
    def get_output_field_names(cls) -> tuple[str]:
        """Get all output field names that this job supports.
        An empty tuple means that none are supported.

        Returns
        -------
        tuple[str]
            A tuple of the supported output fields.
        """

        if cls.OutputFields is None:
            return tuple()

        return cls.OutputFields.__record_names__

    @classmethod
    def get_output_queue_names(cls) -> tuple[str]:
        """Get all output queue names that this job supports.
        An empty tuple means that none are supported.

        Returns
        -------
        tuple[str]
            A tuple of the supported output queues.
        """
        if cls.OutputQueues is None:
            return tuple()

        return cls.OutputQueues.__record_names__

    @classmethod
    def has_output_field_name(cls, field_name: str) -> bool:
        """Whether the specified field name is supported as an
        output field.

        Parameters
        ----------
        field_name : str
            The name of the target output field.

        Returns
        -------
        bool
            ``True`` if condition is met, ``False`` otherwise.
        """

        if not isinstance(field_name, str):
            raise TypeError(
                f"'field_name' argument must be of type str,"
                f" not {field_name.__class__.__name__}"
            )

        return cls.verify_output_field_support(field_name)

    @classmethod
    def has_output_queue_name(cls, queue_name: str) -> bool:
        """Whether the specified queue name is supported as an
        output queue.

        Parameters
        ----------
        queue_name : str
            The name of the target output queue.

        Returns
        -------
        bool
            ``True`` if condition is met, ``False`` otherwise.
        """

        if not isinstance(queue_name, str):
            raise TypeError(
                f"'queue_name' argument must be of type str,"
                f" not {queue_name.__class__.__name__}"
            )

        return cls.verify_output_queue_support(queue_name)

    def output_field_is_set(self, field_name: str) -> bool:
        """Whether a value for the specified output field
        has been set.

        Parameters
        ----------
        field_name : str
            The name of the target output field.

        Returns
        -------
        bool
            ``True`` if condition is met, ``False`` otherwise.

        Raises
        ------
        TypeError
            Output fields aren't supported for this job, or `field_name` is not
            a string.
        LookupError
            The specified field name is not defined by this job.
        """

        self.verify_output_field_support(field_name, raise_exceptions=True)
        field_value = self._output_fields.get(field_name, UNSET)  # type: ignore

        return field_value is not UNSET

    def output_queue_is_empty(self, queue_name: str) -> bool:
        """Whether the specified output queue is empty.

        Parameters
        ----------
        queue_name : str
            The name of the target output queue.

        Returns
        -------
        bool
            ``True`` if condition is met, ``False`` otherwise.

        Raises
        ------
        TypeError
            Output queues aren't supported for this job, or `queue_name` is not a
            string.
        LookupError
            The specified queue name is not defined by this job.
        """

        self.verify_output_queue_support(queue_name, raise_exceptions=True)

        return not self._output_queues.get(queue_name, None)  # type: ignore

    def await_output_field(
        self, field_name: str, timeout: float | None = None
    ) -> Coroutine[Any, Any, Any | Literal[JobStatus.COMPLETED, JobStatus.KILLED]]:
        """Wait for this job object to release the value of a
        specified output field while it is running, using the
        coroutine output of this method.

        Parameters
        ----------
        field_name : str
            The name of the target output field.
        timeout : float, optional
            The maximum amount of time to wait in seconds.
            Defaults to None.

        Returns
        -------
        Coroutine[Any, Any, Any | Literal[JobStatus.COMPLETED, JobStatus.KILLED]]
            A coroutine that evaluates to the value of specified
            output field.

        Raises
        ------
        TypeError
            Output fields aren't supported for this job, or `field_name` is not a string.
        LookupError
            The specified field name is not defined by this job.
        JobIsDone
            This job object is already done.
        asyncio.TimeoutError
            The timeout was exceeded.
        asyncio.CancelledError
            The job was killed.
        """

        self.verify_output_field_support(field_name, raise_exceptions=True)
        assert self._output_field_futures is not None

        if self.done():
            raise JobIsDone("This job object is already done")

        fut = self._manager._loop.create_future()

        if field_name not in self._output_field_futures:
            self._output_field_futures[field_name] = []

        self._output_field_futures[field_name].append(fut)

        return asyncio.wait_for(fut, timeout=timeout)

    def await_output_queue_add(
        self,
        queue_name: str,
        timeout: float | None = None,
        cancel_if_cleared: bool = True,
    ) -> Coroutine[
        Any,
        Any,
        Any
        | Literal[
            JobStatus.OUTPUT_QUEUE_CLEARED, JobStatus.KILLED, JobStatus.COMPLETED
        ],
    ]:
        """Wait for this job object to add to the specified output queue while
        it is running, using the coroutine output of this method.

        Parameters
        ----------
        timeout : float, optional
            The maximum amount of time to wait in
              seconds. Defaults to None.
        cancel_if_cleared : bool, optional
            Whether `asyncio.CancelledError` should
            be raised if the output queue is cleared. If set to `False`,
            `JobStatus.OUTPUT_QUEUE_CLEARED` will be the result of the coroutine.
            Defaults to False.

        Returns
        -------
        Coroutine[Any, Any, Any | Literal[JobStatus.OUTPUT_QUEUE_CLEARED, JobStatus.KILLED, JobStatus.COMPLETED]]
            A coroutine that evaluates to the most recent output
            queue value, or `JobStatus.OUTPUT_QUEUE_CLEARED` if the queue
            is cleared, `JobStatus.KILLED` if this job was killed and
            `JobStatus.COMPLETED` if this job is completed.

        Raises
        ------
        TypeError
            Output fields aren't supported for this job, or `field_name` is not a
            string.
        LookupError
            The specified field name is not defined by this job
        JobIsDone
            This job object is already done.
        asyncio.TimeoutError
            The timeout was exceeded.
        asyncio.CancelledError
            The job was killed, or the output queue was cleared.
        """

        self.verify_output_queue_support(queue_name, raise_exceptions=True)

        if self.done():
            raise JobIsDone("This job object is already done")

        assert self._output_queue_futures is not None

        if queue_name not in self._output_queue_futures:
            self._output_queue_futures[queue_name] = []

        fut = self._manager._loop.create_future()
        self._output_queue_futures[queue_name].append((fut, cancel_if_cleared))

        return asyncio.wait_for(fut, timeout=timeout)

    @classmethod
    def verify_public_method_suppport(
        cls, method_name: str, raise_exceptions=False
    ) -> bool:
        """Verify if a job has a public method exposed under the specified name is
        supported by this job, or if it supports public methods at all. Disabled
        public method names are seen as unsupported.

        Parameters
        ----------
        method_name : str
            The name of the public method.
        raise_exceptions : bool, optional
            Whether exceptions should be raised. Defaults to False.

        Returns
        -------
        bool
            ``True`` if condition is met, ``False`` otherwise.

        Raises
        ------
        TypeError
            Output fields aren't supported for this job, or `field_name` is not a
            string.
        LookupError
            No public method under the specified name is defined by this job.
        """

        if cls.PUBLIC_METHODS_CHAINMAP is None:
            if raise_exceptions:
                raise TypeError(
                    f"'{cls.__qualname__}' class does not"
                    f" support any public methods"
                )
            return False

        elif method_name not in cls.PUBLIC_METHODS_CHAINMAP:
            if raise_exceptions:
                raise (
                    LookupError(
                        f"no public method under the specified name '{method_name}' is "
                        "defined by the class of this job"
                    )
                    if isinstance(method_name, str)
                    else TypeError(
                        f"'method_name' argument must be of type str,"
                        f" not {method_name.__class__.__name__}"
                    )
                )
            return False

        elif getattr(cls, method_name).__dict__.get("__disabled", False):
            if raise_exceptions:
                raise ValueError(
                    f"the public method of this job of class '{cls.__qualname__} "
                    f"under the name '{method_name}' has been marked as disabled"
                )
            return False

        return True

    @classmethod
    def get_public_method_names(cls) -> tuple[str]:
        """Get the names of all public methods that this job supports.

        Returns
        -------
        tuple[str]
            A tuple of the names of the supported methods.
        """
        if cls.PUBLIC_METHODS_CHAINMAP is None:
            return tuple()

        return tuple(cls.PUBLIC_METHODS_CHAINMAP.keys())

    @classmethod
    def has_public_method_name(cls, method_name: str) -> bool:
        """Whether a public method under the specified name is supported by this job.

        Parameters
        ----------
        method_name : str
            The name of the target method

        Returns
        -------
        bool
            ``True`` if condition is met, ``False`` otherwise.
        """

        if not isinstance(method_name, str):
            raise TypeError(
                f"'method_name' argument must be of type str,"
                f" not {method_name.__class__.__name__}"
            )

        return cls.verify_public_method_suppport(method_name)

    @classmethod
    def public_method_is_async(cls, method_name: str) -> bool:
        """Whether a public method under the specified name is a coroutine function.

        Parameters
        ----------
        method_name : str
            The name of the target method.

        Returns
        -------
        bool
            ``True`` if condition is met, ``False`` otherwise.
        """

        cls.verify_public_method_suppport(method_name, raise_exceptions=True)

        return inspect.iscoroutinefunction(getattr(cls, method_name))

    def run_public_method(self, method_name, *args, **kwargs) -> Any:
        """Run a public method under the specified name and return the
        result. Raise a LookupError if not found.

        Parameters
        ----------
        method_name : str
            The name of the target method.
        *args
            The positional method arguments.
        **kwargs
            The keyword method arguments.

        Returns
        -------
        Any
            The result of the call.
        """

        self.verify_public_method_suppport(method_name, raise_exceptions=True)
        return getattr(self.__class__, method_name)(self, *args, **kwargs)

    def status(self) -> JobStatus:
        """`JobStatus`: Get the job status of this job as a value from the
        `JobStatus` enum.
        """
        output = JobStatus.FRESH
        if self.alive():
            if self.is_running():
                if self.is_starting():
                    output = JobStatus.STARTING
                elif self.is_idling():
                    output = JobStatus.IDLING
                elif self.is_stopping():
                    if self.is_completing():
                        output = JobStatus.COMPLETING
                    elif self.is_being_killed():
                        output = JobStatus.BEING_KILLED
                    elif self.is_restarting():
                        output = JobStatus.RESTARTING
                    else:
                        output = JobStatus.STOPPING
                else:
                    output = JobStatus.RUNNING
            elif self.stopped():
                output = JobStatus.STOPPED
            elif self.initialized():
                output = JobStatus.INITIALIZED

        elif self.completed():
            output = JobStatus.COMPLETED
        elif self.killed():
            output = JobStatus.KILLED

        return output

    def __str__(self) -> str:
        return (
            f"<{self.__class__.__qualname__} "
            + f"(id={self._runtime_id} created_at={self.created_at} "
            + (
                f"permission_level={self._permission_level.name} "
                if self._permission_level is not None
                else ""
            )
            + f"status={self.status().name})>"
        )


class JobMixin(JobCore):
    """A base class for job mixins, which implement
    additional functionality for jobs. These may involve
    additional class variables, instance variables and
    methods.

    Subclasses of this class can be integrated into
    job classes using multiple inheritance, where
    all mixin classes to integrate are specified
    as the first parameters for inheritance in the
    class definition, followed by a JobBase subclass
    at the end.
    """

    __slots__ = ()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    async def mixin_routine(self: "Self | JobBase") -> None:
        """A function to overload for running job mixin
        functionality.
        """
        raise NotImplementedError()


class JobBase(JobCore):
    __slots__ = ("_mixin_task_dict", "_mixin_future_dict")

    JOB_MIXIN_CLASSES: frozenset[type[JobMixin]] = frozenset()

    def __init_subclass__(cls, class_uuid: str | None = None):
        super().__init_subclass__(class_uuid)

        mixin_classes: list[type[JobMixin]] = []
        mro_mixin_supercls_of: dict[type[JobMixin], type[JobMixin]] = {}

        if not issubclass(cls.__bases__[-1], JobBase):
            raise TypeError(
                "Subclasses of JobBase must specify a 'JobBase' superclass as "
                "the last parameter for inheritance in their class definition"
            )

        for supercls in cls.__bases__:
            if issubclass(supercls, JobMixin):
                if not asyncio.iscoroutinefunction(supercls.mixin_routine):
                    raise TypeError(
                        f"JobMixin subclasses to inherit must define a "
                        "'mixin_routine' coroutine function' that takes "
                        "in a job instance as an argument"
                    )
                elif supercls in cls.JOB_MIXIN_CLASSES:
                    raise TypeError(
                        f"Job mixin class {supercls.__qualname__} has already been inherited"
                    )

                mixin_classes.append(supercls)

        if mixin_classes:
            all_mixin_classes = (*cls.JOB_MIXIN_CLASSES, *mixin_classes)

            if len(all_mixin_classes) > 1:
                for mixin_class in all_mixin_classes:
                    for superclass in mixin_class.__mro__:
                        if (
                            issubclass(superclass, JobMixin)
                            and superclass is not JobMixin
                        ):
                            if superclass in mro_mixin_supercls_of:
                                raise TypeError(
                                    f"Invalid job mixin class inheritance tree: "
                                    f"Job mixin class '{mixin_class.__qualname__}' "
                                    f"inherits '{superclass.__qualname__}' which is "
                                    f"already inherited by "
                                    f"'{mro_mixin_supercls_of[superclass].__qualname__}'"
                                )

                            mro_mixin_supercls_of[superclass] = mixin_class

            cls.JOB_MIXIN_CLASSES = cls.JOB_MIXIN_CLASSES | frozenset(
                mixin_classes
            )  # add variable to current class dict

    def __init__(self) -> None:
        super().__init__()
        self._mixin_task_dict: dict[type[JobMixin], asyncio.Task] = {}
        self._mixin_future_dict: dict[type[JobMixin], list[asyncio.Future]] = {}

    def handle_mixin_routines(self, *mixin_classes: type[JobMixin]) -> None:
        """Handle the mixin routines of the specified mixin classes
        by scheduling them to run once. If the tasks through which
        the mixin routines were previously scheduled are done, they
        will be replaced with new ones to reschedule the mixin routines.
        If they weren't done, `JobStateError` will be raised.

        Parameters
        ----------
        *mixin_classes : type[JobMixin])
            The mixin classes.

        Raises
        ------
        JobIsDone
            This job object is already done.
        JobNotRunning
            This job object is not running.
        TypeError
            Invalid mixin classes given as input.
        JobStateError
            The given mixin classes are already
              being handled.
        """

        if self.done():
            raise JobIsDone("This job object is already done")
        elif not self.is_running():
            raise JobNotRunning("This job object is not running")

        mixin_classes = tuple(frozenset(mixin_classes))

        if mixin_classes and not all(
            mixin_cls in self.JOB_MIXIN_CLASSES for mixin_cls in mixin_classes
        ):
            raise TypeError(
                f"Some classes passed given as arguments are not supported mixin "
                f"classes of '{self.__class__.__qualname__}'"
            )
        elif any(
            mixin_cls in self._mixin_task_dict
            and not self._mixin_task_dict[mixin_cls].done()
            for mixin_cls in mixin_classes
        ):
            raise JobStateError(
                "This job object is already handling some of the given job mixin classes"
            )

        self._handle_mixin_routines(*mixin_classes)

    def handle_all_mixin_routines(self) -> None:
        """Handle the routines of all the inherited mixin classes,
        by scheduling them to run once. If the tasks through which
        the mixin routines were previously scheduled are done,
        they will be replaced with new ones to reschedule the
        mixin routines. If they weren't done, `JobStateError`
        will be raised.

        Raises
        ------
        JobIsDone
            This job object is already done.
        JobNotRunning
            This job object is not running.
        TypeError
            Invalid mixin classes given as input.
        JobStateError
            The given mixin classes are already being handled.
        """

        if self.done():
            raise JobIsDone("This job object is already done")
        elif not self.is_running():
            raise JobNotRunning("This job object is not running")

        if any(not tsk.done() for tsk in self._mixin_task_dict.values()):
            raise JobStateError("This job object is already handling job mixins")

        self._handle_mixin_routines(*self.JOB_MIXIN_CLASSES)

    def _handle_mixin_routines(self, *mixin_classes: type[JobMixin]):
        for mixin_cls in mixin_classes:
            if mixin_cls in self._mixin_task_dict:
                del self._mixin_task_dict[mixin_cls]

        task_mixin_cls_dict = {}

        def _complete_mixin_task(task: asyncio.Task):
            mixin_cls = task_mixin_cls_dict[task]

            for fut in self._mixin_future_dict[mixin_cls]:
                if not fut.done():
                    fut.set_result({mixin_cls: task})

            self._mixin_future_dict[mixin_cls].clear()

        for mixin_cls in mixin_classes:
            tsk = asyncio.create_task(self._call_mixin_routine(mixin_cls))
            tsk.add_done_callback(_complete_mixin_task)
            self._mixin_task_dict[mixin_cls] = tsk
            task_mixin_cls_dict[tsk] = mixin_cls

    async def _call_mixin_routine(self, mixin_cls: type[JobMixin]):
        try:
            await mixin_cls.mixin_routine(self)
        except Exception as e:
            await self.on_mixin_routine_error(e, mixin_cls)
            raise

    def mixin_routine_is_running(self, mixin_cls: type[JobMixin]) -> bool:
        """Whether the mixin routine of the given mixin class is currently
        running.

        Parameters
        ----------
        mixin_cls : type[JobMixin]
            The mixin class.

        Returns
        -------
        bool
            ``True`` if condition is met, ``False`` otherwise.
        """
        return (
            mixin_cls in self._mixin_task_dict
            and not self._mixin_task_dict[mixin_cls].done()
        )

    def wait_for_mixin_routines(
        self,
        *mixin_classes: type[JobMixin],
        timeout: float | None = None,
        skip_not_running: bool = True,
    ) -> Coroutine[Any, Any, dict[type[JobMixin], asyncio.Task[None]]]:
        """Wait for the mixin routines of the specified mixin classes
        to finish running using the returned coroutine.

        Parameters
        ----------
        *mixin_classes : type[JobMixin]
            The mixin classes.
        timeout : float | None, optional
            The waiting timeout. Defaults to None.
        skip_not_running : bool, optional
            Whether to ignore the mixin classes which
            don't have their routines scheduled to run. If set to `False`,
            `JobStateError` will be raised. Defaults to True.

        Returns
        -------
        Coroutine[Any, Any, dict[type[JobMixin], asyncio.Task[None]]]
            A coroutine which returns a dictionary that maps the specified
            mixin classes to the `asyncio.Task` objects used to run their routine
            functions.

        Raises
        ------
        TypeError
            Invalid mixin class(es).
        JobStateError
            Some or none of the given mixin classes have their routines scheduled to
            run.
        """

        futs = []

        for mixin_cls in mixin_classes:

            if not mixin_cls in self.JOB_MIXIN_CLASSES:
                raise TypeError(
                    f"Class  {mixin_cls.__qualname__} given as an argument is not a valid "
                    f"mixin class of '{self.__class__.__qualname__}'"
                )
            elif (
                mixin_cls not in self._mixin_task_dict
                or self._mixin_task_dict[mixin_cls].done()
            ) and not skip_not_running:
                raise JobStateError(
                    f"Some mixin classes given as arguments don't have running routines to wait for"
                )

            elif (
                mixin_cls in self._mixin_task_dict
                and not self._mixin_task_dict[mixin_cls].done()
            ):  # mixin tasks are currently running
                fut = self._manager._loop.create_future()

                if mixin_cls not in self._mixin_future_dict:
                    self._mixin_future_dict[mixin_cls] = []

                self._mixin_future_dict[mixin_cls].append(fut)

                futs.append(fut)

        if len(futs) > 1:
            return asyncio.wait_for(
                self._wait_for_mixin_routine_futures(*futs), timeout=timeout
            )

        elif len(futs) == 1:
            return asyncio.wait_for(futs[0], timeout=timeout)

        raise JobStateError("No mixins are currently running to be awaited")

    async def _wait_for_mixin_routine_futures(self, *futures: asyncio.Future):
        results = await asyncio.gather(*futures, return_exceptions=True)

        result_dict: dict[type[JobMixin], asyncio.Task] = {}
        for result in results:
            if isinstance(result, dict):
                result_dict.update(result)

        return result_dict

    def _cancel_all_mixin_routines(self, msg: str) -> None:
        for task in self._mixin_task_dict.values():
            if not task.done():
                task.cancel(msg)

    async def run_mixin_routines(self, *mixin_classes: type[JobMixin]):
        """Handle the routines of the given mixin classes and block until
        they finish running. This method is a combination of
        `handle_mixin_routines` and `wait_for_mixin_routines`.

        Parameters
        ----------
        *mixin_classes : type[JobMixin]
            The mixin classes.

        Returns
        -------
        Coroutine[Any, Any, dict[type[JobMixin], asyncio.Task[None]]]
            A coroutine which returns a dictionary that maps the specified
            mixin classes to the `asyncio.Task` objects used to run their routine
            functions.

        Raises
        ------
        TypeError
            Invalid mixin class(es).
        JobStateError
            Some or none of the given mixin classes have their
            routines scheduled to run/Some are already being handled.
        """

        self.handle_mixin_routines(*mixin_classes)
        return await self.wait_for_mixin_routines(*mixin_classes)

    async def run_all_mixin_routines(self):
        """Handle the routines of all the inherited mixin classes and block until
        they finish running. This method is a combination of `handle_mixin_routines`
        and `wait_for_mixin_routines`.

        Returns
        -------
        Coroutine[Any, Any, dict[type[JobMixin], asyncio.Task[None]]]
            A coroutine which returns a dictionary that maps the specified
            mixin classes to the `asyncio.Task` objects used to run their routine
            functions.

        Raises
        ------
        TypeError
            Invalid mixin class(es).
        JobStateError
            Some or none of the given mixin classes have their
            routines scheduled to run/Some are already being handled.
        """
        self.handle_all_mixin_routines()
        return await self.wait_for_mixin_routines(*self.JOB_MIXIN_CLASSES)

    def cancel_mixin_routines(self, *mixin_classes: type[JobMixin]):
        """Cancel the routines of the given mixin classes, if they are
        running.

        Parameters
        ----------
        *mixin_classes : type[JobMixin]
            The mixin classes.

        Raises
        ------
        TypeError
            Invalid mixin class(es).
        """

        for mixin_cls in mixin_classes:
            if not mixin_cls in self.JOB_MIXIN_CLASSES:
                raise TypeError(
                    f"Class  {mixin_cls.__qualname__} given as an argument is not a valid "
                    f"mixin class of '{self.__class__.__qualname__}'"
                )
            elif (
                mixin_cls in self._mixin_task_dict
                and not self._mixin_task_dict[mixin_cls].done()
            ):
                self._mixin_task_dict[mixin_cls].cancel(
                    f"Job {self!r} has requested mixin routine cancellation."
                )

    def cancel_all_mixin_routines(self):
        """Cancel the routines of all given mixin classes, if they are
        running.
        """
        self._cancel_all_mixin_routines(
            f"Job {self!r} has requested mixin routine cancellation."
        )

    def get_mixin_routine_tasks(self) -> dict[type[JobMixin], asyncio.Task[None]]:
        """Get a dictionary that maps all supported mixin classes to the `asyncio.Task` objects
        used to run their routine functions. If some of the tasks are not done, a JobStateError
        exception is raised.

        Returns
        -------
        dict[type[JobMixin], asyncio.Task[None]]
            The dictionary.

        Raises
        ------
        JobStateError
            Some mixin routine tasks are not done.
        """
        if self._mixin_task_dict and not all(
            task.done() for task in self._mixin_task_dict.values()
        ):
            raise JobStateError(
                "Cannot return all mixin routine tasks while some are running"
            )

        return self._mixin_task_dict.copy()

    async def on_mixin_routine_error(self, exc: Exception, mixin_cls: type[JobMixin]):
        """A listener for reacting to failed mixin routines.

        Parameters
        ----------
        exc : Exception
            The exception.
        mixin_cls : type[JobMixin]
            The mixin class.
        """
        print(
            f"A job mixin exception occured in '{mixin_cls.__qualname__}.mixin_run()' "
            "for job "
            f"'{self!r}':\n\n",
            traceback.format_tb(exc.__traceback__),
            file=sys.stderr,
        )

    async def _on_stop(self):
        self._bools |= JF.IS_STOPPING  # True
        self._cancel_all_mixin_routines(f"Job '{self!r}' is stopping")
        await super()._on_stop()


class ManagedJobBase(JobBase):
    """Base class for interval based managed jobs.
    Subclasses are expected to overload the `on_run()` method.
    Other methods prefixed with `on_` can optionally be overloaded.

    One can override the class variables `DEFAULT_INTERVAL`,
    `DEFAULT_COUNT` and `DEFAULT_RECONNECT` in subclasses.
    They are derived from the keyword arguments of the
    `discord.ext.tasks.Loop` constructor. These will act as
    defaults for each job object created from this class.
    """

    DEFAULT_INTERVAL = datetime.timedelta()
    DEFAULT_TIME: datetime.time | Sequence[datetime.time] | None = None

    DEFAULT_COUNT: int | None = None
    DEFAULT_RECONNECT = True

    __slots__ = ()

    def __init__(
        self,
        interval: datetime.timedelta = UNSET,
        time: datetime.time | Sequence[datetime.time] = UNSET,
        count: int | None = UNSET,
        reconnect: bool = UNSET,
    ) -> None:
        """Create a new `ManagedJobBase` instance."""

        super().__init__()
        self._interval_secs = (
            self.DEFAULT_INTERVAL.total_seconds()
            if interval is UNSET
            else interval.total_seconds()
        )
        self._count = self.DEFAULT_COUNT if count is UNSET else count

        reconnect = not not (
            self.DEFAULT_RECONNECT if reconnect is UNSET else reconnect
        )

        self._time = self.DEFAULT_TIME if time is UNSET else time

        self._loop_count = 0
        self._job_loop = JobLoop(
            self._on_run,
            self,
            seconds=self._interval_secs,
            hours=0,
            minutes=0,
            time=self._time or discord.utils.MISSING,  # type: ignore
            count=self._count,
            reconnect=reconnect,
        )

        self._job_loop.before_loop(self._on_start)
        self._job_loop.after_loop(self._on_stop)
        self._job_loop.error(self._on_run_error)  # type: ignore

    def next_iteration(self) -> datetime.datetime | None:
        """`datetime.datetime | None`: When the next iteration of `.on_run()` will occur."""
        return self._job_loop.next_iteration

    def get_interval(self) -> tuple[float, float, float] | None:
        """`tuple[float, float, float] | None`: Returns a tuple of the seconds,
        minutes and hours at which this job object is executing its `.on_run()`
        method.
        """
        return (
            (
                secs,
                mins,
                hrs,
            )
            if not (
                (secs := self._job_loop.seconds) is None
                or (mins := self._job_loop.minutes) is None
                or (hrs := self._job_loop.hours) is None
            )
            else None
        )

    def change_interval(
        self,
        *,
        seconds: float = 0,
        minutes: float = 0,
        hours: float = 0,
        time: datetime.time | Sequence[datetime.time] = UNSET,
    ) -> None:
        """Change the interval at which this job will run its `on_run()` method,
        as soon as possible.

        Parameters
        ----------
        seconds : float, optional
            Defaults to 0.
        minutes : float, optional
            Defaults to 0.
        hours : float, optional
            Defaults to 0.
        time : datetime.time | Sequence[datetime.time], optional
            Defaults to 0.
        """
        self._job_loop.change_interval(
            seconds=seconds,
            minutes=minutes,
            hours=hours,
            time=time if time is not UNSET else discord.utils.MISSING,
        )

        if time is not UNSET:
            self._time = time
        else:
            self._interval_secs = seconds + (minutes * 60.0) + (hours * 3600.0)

    async def on_start(self) -> None:  # make this optional for subclasses
        pass

    async def _on_run(self) -> None:
        if self._bools & JF.EXTERNAL_STARTUP_KILL:
            self._kill_external_raw()
            return

        elif self._bools & JF.INTERNAL_STARTUP_KILL:
            self._kill_raw()
            return

        elif self._bools & JF.SKIP_NEXT_RUN:
            return

        self._bools &= ~JF.IS_IDLING  # False
        self._idling_since_ts = None

        await self.on_run()
        if self._interval_secs:  # There is a task loop interval set
            self._bools |= JF.IS_IDLING  # True
            self._idling_since_ts = time.time()

        self._loop_count += 1

    async def on_run(self) -> None:
        """DO NOT CALL THIS METHOD MANUALLY, EXCEPT WHEN USING `super()` WITHIN
        OVERLOADED VERSIONS OF THIS METHOD TO ACCESS A SUPERCLASS METHOD.

        The code to run at the set interval.
        This method must be overloaded in subclasses.

        Raises
        ------
        NotImplementedError
            This method must be overloaded in subclasses.
        """
        raise NotImplementedError()

    async def on_stop(self) -> None:  # make this optional for subclasses
        pass


@singletonjob
class JobManagerJob(ManagedJobBase):
    """A singleton managed job that represents the job manager. Its very high permission
    level and internal protections prevents it from being instantiated
    or modified by other jobs.
    """

    _RUNTIME_ID = "JobManagerJob-0"

    def __init__(self) -> None:
        super().__init__()
        self._runtime_id = "JobManagerJob-0:0"

    async def on_run(self):
        await self.await_done()


from . import proxies, groupings  # allow these modules to finish initialization
