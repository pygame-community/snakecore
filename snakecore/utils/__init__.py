"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2020-present PygameCommunityDiscord

This module defines some utility functionality for the library and general bot development.
"""

from typing import Optional

import discord

from snakecore import config, conf

from . import embed_utils
from .utils import *


def init(client: Optional[discord.Client] = None):
    if client is not None and not conf.is_set("global_client"):
        conf.global_client = client

    conf.init_mods[config.ModuleName.UTILS] = True


def is_init():
    return conf.init_mods.get(config.ModuleName.UTILS, False)
