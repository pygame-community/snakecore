"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

A asynchronous job module based on OOP principles.
"""

from typing import Optional

import discord

from snakecore import config, events
from .jobs import (
    get_job_class_from_runtime_identifier,
    JobNamespace,
    singletonjob,
    publicjobmethod,
    JobBase,
    ManagedJobBase,
    EventJobMixin,
    JobManagerJob,
)

from .minijobs import (
    MiniJobBase,
    initialize_minijob,
    start_minijob,
    stop_minijob,
    restart_minijob,
)

from . import manager, minijobs
from .manager import JobManager
from .proxies import JobProxy, JobOutputQueueProxy, JobManagerProxy
from .groupings import JobGroup


def init(global_client: Optional[discord.Client] = None):
    """Initialize this module.

    Args:
        global_client (Optional[discord.Client], optional):
          The global `discord.Client` object to set for all modules to use.
          Defaults to None.
    """
    if global_client is not None and not config.conf.is_set("global_client"):
        config.conf.global_client = global_client

    events.init()
    config.conf.init_mods[config.ModuleName.JOBS] = True


def quit():
    """Quit this module."""
    config.conf.init_mods[config.ModuleName.JOBS] = False


def is_init():
    """Whether this module has been sucessfully initialized.

    Returns:
        bool: True/False
    """
    return config.conf.init_mods.get(config.ModuleName.JOBS, False)
