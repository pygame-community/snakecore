"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file defines specialized subclasses of `discord.ext.tasks.Loop`,
which are used by job objects.
"""

import asyncio
from contextvars import ContextVar
import datetime
from typing import Any, Optional, Sequence, Union

import discord
from discord.ext import tasks
from discord.backoff import ExponentialBackoff

from snakecore.constants import DEFAULT_JOB_EXCEPTION_WHITELIST

_current_job = ContextVar("current_job")


class JobLoop(tasks.Loop):
    """A small subclass of `discord.ext.tasks.Loop`
    for getting more control over the Task cancelling process among other
    things. This is meant for exclusive use by job objects.
    """

    def __init__(
        self,
        coro,
        job,
        seconds: float = discord.utils.MISSING,
        minutes: float = discord.utils.MISSING,
        hours: float = discord.utils.MISSING,
        time: Union[datetime.time, Sequence[datetime.time]] = discord.utils.MISSING,
        count: Optional[int] = None,
        reconnect: bool = True,
    ):
        super().__init__(coro, seconds, hours, minutes, time, count, reconnect)
        self.job = job
        self.clear_exception_types()
        self.add_exception_type(*DEFAULT_JOB_EXCEPTION_WHITELIST)

    def cancel(self):
        """Cancels the internal task, if it is running."""
        if self._can_be_cancelled():
            self._task.cancel(msg="CANCEL_BY_TASK_LOOP")

    def restart(self, *args, **kwargs):
        r"""A convenience method to restart the internal task.

        .. note::

            Due to the way this function works, the task is not
            returned like :meth:`start`.

        Parameters
        ------------
        \*args
            The arguments to to use.
        \*\*kwargs
            The keyword arguments to use.
        """

        def restart_when_over(fut, *, args=args, kwargs=kwargs):
            self._task.remove_done_callback(restart_when_over)
            self.start(*args, **kwargs)

        if self._can_be_cancelled():
            self._task.add_done_callback(restart_when_over)
            self._task.cancel(msg="CANCEL_BY_TASK_LOOP")

    async def _loop(self, *args: Any, **kwargs: Any) -> None:
        _current_job.set(self.job)
        backoff = None
        await self._call_loop_function("before_loop")
        self._last_iteration_failed = False
        if self._time is not discord.utils.MISSING:
            self._next_iteration = self._get_next_sleep_time()
        else:
            self._next_iteration = datetime.datetime.now(datetime.timezone.utc)
            await asyncio.sleep(0)  # allows canceling in before_loop
        try:
            if self._stop_next_iteration:  # allow calling stop() before first iteration
                return
            while True:
                # sleep before the body of the task for explicit time intervals
                if self._time is not discord.utils.MISSING:
                    await self._try_sleep_until(self._next_iteration)
                if not self._last_iteration_failed:
                    self._last_iteration = self._next_iteration
                    self._next_iteration = self._get_next_sleep_time()

                    # In order to account for clock drift, we need to ensure that
                    # the next iteration always follows the last iteration.
                    # Sometimes asyncio is cheeky and wakes up a few microseconds before our target
                    # time, causing it to repeat a run.
                    while (
                        self._time is not discord.utils.MISSING
                        and self._next_iteration <= self._last_iteration
                    ):
                        tasks._log.warn(
                            (
                                "Clock drift detected for task %s. Woke up at %s but needed to sleep until %s. "
                                "Sleeping until %s again to correct clock"
                            ),
                            self.coro.__qualname__,
                            discord.utils.utcnow(),
                            self._next_iteration,
                            self._next_iteration,
                        )
                        await self._try_sleep_until(self._next_iteration)
                        self._next_iteration = self._get_next_sleep_time()

                try:
                    await self.coro(*args, **kwargs)
                    self._last_iteration_failed = False
                except self._valid_exception:
                    self._last_iteration_failed = True
                    if not self.reconnect:
                        raise
                    elif backoff is None:
                        backoff = ExponentialBackoff()
                    await asyncio.sleep(backoff.delay())
                else:
                    if self._stop_next_iteration:
                        return

                    # sleep after the body of the task for relative time intervals
                    if self._time is discord.utils.MISSING:
                        await self._try_sleep_until(self._next_iteration)

                    self._current_loop += 1
                    if self._current_loop == self.count:
                        break

        except asyncio.CancelledError:
            self._is_being_cancelled = True
            raise
        except Exception as exc:
            self._has_failed = True
            await self._call_loop_function("error", exc)
            raise exc
        finally:
            await self._call_loop_function("after_loop")
            if self._handle:
                self._handle.cancel()
            self._is_being_cancelled = False
            self._current_loop = 0
            self._stop_next_iteration = False
            self._has_failed = False
