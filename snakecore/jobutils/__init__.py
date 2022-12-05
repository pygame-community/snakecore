"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This module implements utility job classes. 
"""
import datetime
from typing import Any, Callable, Coroutine, Optional, Sequence, Union

from snakecore import jobs
from snakecore.constants import UNSET, _UnsetType, NoneType

from . import messaging


class GenericManagedJob(jobs.ManagedJobBase):
    """A subclass of `ManagedJobBase` that uses callbacks passed to its
    constructor to manage its state. This can be a useful alternative
    to creating a subclass for every new job to implement.
    """

    __slots__ = (
        "_name",
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
        name: str | None = None,
        on_init: Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        | None = None,
        on_start: Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        | None = None,
        on_start_error: Callable[
            [jobs.ManagedJobBase, Exception], Coroutine[Any, Any, None]
        ]
        | None = None,
        on_run: Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        | None = None,
        on_run_error: Callable[
            [jobs.ManagedJobBase, Exception], Coroutine[Any, Any, None]
        ]
        | None = None,
        on_stop: Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        | None = None,
        on_stop_error: Callable[
            [jobs.ManagedJobBase, Exception], Coroutine[Any, Any, None]
        ]
        | None = None,
        interval: datetime.timedelta = UNSET,
        time: datetime.time | Sequence[datetime.time] = UNSET,
        count: int | NoneType = UNSET,
        reconnect: bool = UNSET,
    ) -> None:
        supercls = jobs.ManagedJobBase
        supercls.__init__(self, interval, time, count, reconnect)
        self._name = name or self.__class__.__qualname__
        self._on_init_func = on_init or supercls.on_init
        self._on_start_func = on_start or supercls.on_start
        self._on_start_error_func = on_start_error or supercls.on_start_error
        self._on_run_func = on_run or supercls.on_run
        self._on_run_error_func = on_run_error or supercls.on_run_error
        self._on_stop_func = on_stop or supercls.on_stop
        self._on_stop_error_func = on_stop_error or supercls.on_stop_error

    @property
    def name(self):
        return self._name

    async def on_init(self):
        return await self._on_init_func(self)

    async def on_start(self):
        return await self._on_start_func(self)

    async def on_start_error(self, exc: Exception):
        return await self._on_start_error_func(self, exc)

    async def on_run(self):
        return await self._on_run_func(self)

    async def on_run_error(self, exc: Exception):
        return await self._on_run_error_func(self, exc)

    async def on_stop(self):
        return await self._on_stop_func(self)

    async def on_stop_error(self, exc: Exception):
        return await self._on_stop_error_func(self, exc)

    def __str__(self):
        return (
            f"<{self._name} "
            + f"(id={self._runtime_id} created_at={self.created_at} "
            + (
                f"permission_level={self._permission_level.name} "
                if self._permission_level is not None
                else ""
            )
            + f"status={self.status().name})>"
        )


class SingleRunJob(jobs.ManagedJobBase):
    """A subclass of `ManagedJobBase` whose subclasses's
    job objects will only run once and then complete themselves
    if they fail automatically. For more control, use `ManagedJobBase` directly.
    """

    DEFAULT_COUNT = 1

    async def on_stop(self):
        self.complete()
