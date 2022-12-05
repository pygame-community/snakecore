"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

A asynchronous job module based on OOP principles.
"""

from typing import Optional

import discord

from snakecore import config, events
from .jobs import (
    get_job_class_from_runtime_id,
    JobNamespace,
    singletonjob,
    publicjobmethod,
    JobBase,
    ManagedJobBase,
    JobManagerJob,
)


from .minijobs import (
    MiniJobBase,
    initialize_minijob,
    start_minijob,
    stop_minijob,
    restart_minijob,
)

from . import manager, mixins, minijobs
from .manager import JobManager
from .proxies import JobProxy, JobOutputQueueProxy, JobManagerProxy
from .groupings import JobGroup


def init(global_client: discord.Client | None = None) -> None:
    """Initialize this module.

    Parameters
    ----------
    global_client : discord.Client | None, optional
        The global `discord.Client` object to set for all modules to use.
        Defaults to None.
    """
    if global_client is not None and not config.conf.is_set("global_client"):
        config.conf.global_client = global_client

    events.init()
    config.conf.init_mods[config.ModuleName.JOBS] = True


def quit() -> None:
    """Quit this module."""
    config.conf.init_mods[config.ModuleName.JOBS] = False


def is_init() -> bool:
    """`bool`: Whether this module has been sucessfully initialized."""
    return config.conf.init_mods.get(config.ModuleName.JOBS, False)
