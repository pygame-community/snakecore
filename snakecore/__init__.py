"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

A set of core APIs to facilitate the creation of feature-rich Discord bots.
"""

from typing import Optional, Union

import discord

from . import command_handler, config, constants, db, events, jobs, utils

__title__ = "snakecore"
__author__ = "PygameCommunityDiscord"
__license__ = "MIT"
__copyright__ = "Copyright 2022-present PygameCommunityDiscord"
__version__ = "0.1.0"


async def init(client: Optional[discord.Client] = None):
    if client is not None and not config.conf.is_set("global_client"):
        config.conf.global_client = client

    utils.init()
    events.init()
    await db.init()
    config.conf.init_mods[config.ModuleName.SNAKECORE] = True


async def quit():
    # call any quit hooks here
    await db.quit()

    for key in config.conf.init_mods:
        config.conf.init_mods[key] = False


def is_init():
    return config.conf.init_mods.get(config.ModuleName.SNAKECORE, False)
