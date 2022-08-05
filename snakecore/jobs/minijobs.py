"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file implements the base classes for mini job objects,
which are stripped-down versions of the regular types of job objects.
"""

import datetime
import time
from typing import Optional, Sequence, Union

import discord
from snakecore.constants import UNSET, _UnsetType, NoneType
from snakecore.constants.enums import JobBoolFlags as JF
from snakecore.exceptions import JobInitializationError, JobStateError

from snakecore.jobs.jobs import _JobBase
from snakecore.jobs.loops import JobLoop


class MiniJobBase(_JobBase):
    """Base class for interval based mini jobs.

    A mini job is a stripped-down version of a job that doesn't run in a job manager.
    This class supports only some of the API of `JobBase` subclasses, which are
    initialization, starting, running, stopping and restarting. However, it is not a
    subclass of `JobBase`.

    Mini jobs can run on their own and can be used in cases where the advanced features
    a job manager provides are not needed, or where a job wants to manage the execution
    of jobs on its own.

    Subclasses are expected to overload the `on_run()` method.
    Other methods prefixed with `on_` can optionally be overloaded.

    One can override the class variables `DEFAULT_INTERVAL`,
    `DEFAULT_COUNT` and `DEFAULT_RECONNECT` in subclasses.
    They are derived from the keyword arguments of the
    `discord.ext.tasks.Loop` constructor. These will act as
    defaults for each job object created from this class.
    """

    DEFAULT_INTERVAL = datetime.timedelta()
    DEFAULT_TIME: Optional[Union[datetime.time, Sequence[datetime.time]]] = None

    DEFAULT_COUNT: Optional[int] = None
    DEFAULT_RECONNECT = True

    __slots__ = ("_external_data",)

    def __init__(
        self,
        interval: Union[datetime.timedelta, _UnsetType] = UNSET,
        time: Union[datetime.time, Sequence[datetime.time], _UnsetType] = UNSET,
        count: Union[int, NoneType, _UnsetType] = UNSET,
        reconnect: Union[bool, _UnsetType] = UNSET,
    ):
        """Create a new `MiniJobBase` instance."""

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
            time=self._time or discord.utils.MISSING,
            count=self._count,
            reconnect=reconnect,
        )

        self._external_data = self.DATA_NAMESPACE_CLASS()

        self._job_loop.before_loop(self._on_start)
        self._job_loop.after_loop(self._on_stop)
        self._job_loop.error(self._on_run_error)

    @property
    def external_data(self):
        """The `JobNamespace` instance bound to this job
        object for storing data to be read externally.
        """
        return self._external_data

    def next_iteration(self):
        """When the next iteration of `.on_run()` will occur.
        If not known, this method will return `None`.

        Returns:
            Optional[datetime.datetime]: The time at which
              the next iteration will occur, if available.
        """
        return self._job_loop.next_iteration()

    def get_interval(self):
        """Returns a tuple of the seconds, minutes and hours at which this job
        object is executing its `.on_run()` method.

        Returns:
            tuple: `(seconds, minutes, hours)`
        """
        return self._job_loop.seconds, self._job_loop.minutes, self._job_loop.hours

    def change_interval(
        self,
        *,
        seconds: float = 0,
        minutes: float = 0,
        hours: float = 0,
        time: Union[datetime.time, Sequence[datetime.time], _UnsetType] = UNSET,
    ):
        """Change the interval at which this job will run its `on_run()` method,
        as soon as possible.

        Args:
            seconds (float, optional): Defaults to 0.
            minutes (float, optional): Defaults to 0.
            hours (float, optional): Defaults to 0.
            time (Union[datetime.time, Sequence[datetime.time]], optional):
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

    async def on_start(self):  # make this optional for subclasses
        pass

    async def _on_run(self):
        if self._bools & JF.SKIP_NEXT_RUN:
            return

        self._bools &= ~JF.IS_IDLING  # False
        self._idling_since_ts = None

        await self.on_run()
        if self._interval_secs:  # There is a task loop interval set
            self._bools |= JF.IS_IDLING  # True
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

    async def on_stop(self):  # make this optional for subclasses
        pass


async def initialize_minijob(job: MiniJobBase) -> bool:
    """Initialize the given mini job object.

    Args:
        job (MiniJobBase): The minijob.

    Returns:
        bool: Whether the operation was successful.

    Raises:
        TypeError: The given job instance was not a mini job.
        JobInitializationError: The given job object has already been initialized.
    """
    if not isinstance(job, MiniJobBase):
        raise TypeError(
            "argument 'job' must be an instance of "
            f"MiniJobBase, not {job.__class__.__name__}"
        )
    elif job._bools & JF.INITIALIZED:
        raise JobInitializationError(
            "The given job object has already been initialized"
        )

    try:
        return await job._INITIALIZE_EXTERNAL()
    except Exception as e:
        raise JobInitializationError(
            "job initialization failed due to an error: " f"{e.__class__.__name__}: {e}"
        ) from e


def start_minijob(job: MiniJobBase) -> bool:
    """Start the given mini job object.

    Args:
        job (MiniJobBase): The minijob.

    Returns:
        bool: Whether the operation was successful.

    Raises:
        TypeError: The given job instance was not a mini job.
        JobInitializationError: The given job object was not initialized.
    """
    if not isinstance(job, MiniJobBase):
        raise TypeError(
            "argument 'job' must be an instance of "
            f"MiniJobBase, not {job.__class__.__name__}"
        )
    elif not job._bools & JF.INITIALIZED:
        raise JobInitializationError("The given mini job was not initialized.")

    return job._START_EXTERNAL()


def stop_minijob(job: MiniJobBase, force: bool = False) -> bool:
    """Stop the given mini job object.

    Args:
        job (MiniJobBase): The minijob.
        force (bool): Whether to suspend all operations of the
          job forcefully.

    Returns:
        bool: Whether the operation was successful.

    Raises:
        TypeError: The given job instance was not a mini job.
    """
    if not isinstance(job, MiniJobBase):
        raise TypeError(
            "argument 'job' must be an instance of "
            f"MiniJobBase, not {job.__class__.__name__}"
        )
    return job._STOP_EXTERNAL(force=force)


def restart_minijob(job: MiniJobBase) -> bool:
    """Restart the given mini job object.

    Args:
        job (MiniJobBase): The minijob.

    Returns:
        bool: Whether the operation was successful.

    Raises:
        TypeError: The given job instance was not a mini job.
    """
    if not isinstance(job, MiniJobBase):
        raise TypeError(
            "argument 'job' must be an instance of "
            f"MiniJobBase, not {job.__class__.__name__}"
        )
    return job._RESTART_EXTERNAL()
