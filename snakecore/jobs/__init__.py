"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

A asynchronous job module based on OOP principles.
"""

import discord
from snakecore import config, conf

from snakecore.constants import UNSET
from .base_jobs import (
    get_job_class_from_id,
    get_job_class_id,
    get_job_class_permission_level,
    DEFAULT_JOB_EXCEPTION_WHITELIST,
    JOB_STATUS,
    JOB_VERBS,
    JOB_STOP_REASONS,
    PERM_LEVELS,
    JobError,
    JobPermissionError,
    JobStateError,
    JobInitializationError,
    JobWarning,
    JobNamespace,
    singletonjob,
    publicjobmethod,
    JobBase,
    IntervalJobBase,
    EventJobBase,
    JobManagerJob,
)
from .manager import JobManager
from .proxies import *
from . import utils

def init(client: Optional[discord.Client] = None):
    if client is not None and not conf.is_set("global_client"):
        conf.global_client = client

    conf.init_mods[config.ModuleName.JOBS] = True


def is_init():
    return conf.init_mods.get(config.ModuleName.JOBS, False)

