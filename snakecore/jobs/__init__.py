"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

A asynchronous job module based on OOP principles.
"""

from typing import Optional

import discord

from snakecore import config, events
from .jobs import (
    get_job_class_from_runtime_identifier,
    get_job_class_permission_level,
    DEFAULT_JOB_EXCEPTION_WHITELIST,
    JobNamespace,
    singletonjob,
    publicjobmethod,
    JobBase,
    IntervalJobBase,
    EventJobBase,
    JobManagerJob,
)
from .manager import JobManager
from .proxies import JobProxy, JobOutputQueueProxy, JobManagerProxy
from .groupings import JobGroup
from . import jobutils


def init(client: Optional[discord.Client] = None):
    if client is not None and not config.conf.is_set("global_client"):
        config.conf.global_client = client

    events.init(client=client)
    config.conf.init_mods[config.ModuleName.JOBS] = True


def is_init():
    return config.conf.init_mods.get(config.ModuleName.JOBS, False)
