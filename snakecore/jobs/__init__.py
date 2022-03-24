"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

A asynchronous job module based on OOP principles.
"""

import discord
from snakecore import config

from snakecore.constants import UNSET, UNSET_TYPE
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

def init(client: Union[UNSET_TYPE, discord.Client] = UNSET):
    if not isinstance(client, (discord.Client, UNSET_TYPE)):
        raise TypeError(
            f"argument 'client' must be None or of type discord.Client,"
            f" not {client.__class__.__name__}"
        )

    config.set_value("global_client", client, ignore_if_set=True)
    config.set_value("jobs_is_init", True)


def is_init() -> bool:
    return config.get_value("jobs_is_init", wanted_value_cls=bool)

