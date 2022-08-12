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

    __slots__ = (
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
        on_init: Optional[
            Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        ] = None,
        on_start: Optional[
            Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        ] = None,
        on_start_error: Optional[
            Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        ] = None,
        on_run: Optional[
            Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        ] = None,
        on_run_error: Optional[
            Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        ] = None,
        on_stop: Optional[
            Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        ] = None,
        on_stop_error: Optional[
            Callable[[jobs.ManagedJobBase], Coroutine[Any, Any, None]]
        ] = None,
        interval: Union[datetime.timedelta, _UnsetType] = UNSET,
        time: Union[datetime.time, Sequence[datetime.time], _UnsetType] = UNSET,
        count: Union[int, NoneType, _UnsetType] = UNSET,
        reconnect: Union[bool, _UnsetType] = UNSET,
    ):
        supercls = jobs.ManagedJobBase
        supercls.__init__(interval, time, count, reconnect)
        self._on_init_func = on_init or supercls.on_init
        self._on_start_func = on_start or supercls.on_start
        self._on_start_error_func = on_start_error or supercls.on_start_error
        self._on_run_func = on_run or supercls.on_run
        self._on_run_error_func = on_run_error or supercls.on_run_error
        self._on_stop_func = on_stop or supercls.on_stop
        self._on_stop_error_func = on_stop_error or supercls.on_stop_error

    async def on_init(self):
        return await self._on_init_func(self)

    async def on_start(self):
        return await self._on_start_func(self)

    async def on_start_error(self):
        return await self._on_start_error_func(self)

    async def on_run(self):
        return await self._on_run_func(self)

    async def on_run_error(self):
        return await self._on_run_error_func(self)

    async def on_stop(self):
        return await self._on_stop_func(self)

    async def on_stop_error(self):
        return await self._on_stop_error_func(self)


class SingleRunJob(jobs.ManagedJobBase):
    """A subclass of `ManagedJobBase` whose subclasses's
    job objects will only run once and then complete themselves
    if they fail automatically. For more control, use `ManagedJobBase` directly.
    """

    DEFAULT_COUNT = 1

    async def on_stop(self):
        self.COMPLETE()
