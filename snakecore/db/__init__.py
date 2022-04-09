"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

This file exports the Database Interface API
"""

from typing import Optional

import discord

from .. import config

# API to be exported is imported like 'import ... as ...'
from .discorddb import DiscordDB as DiscordDB, init_discord_db, quit_discord_db
from .localdb import LocalDB as LocalDB


async def init(global_client: Optional[discord.Client] = None):
    """Initialize this module.

    Args:
        global_client (Optional[discord.Client], optional):
          The global `discord.Client` object to set for all modules to use.
          Defaults to None.
    """
    if global_client is not None and not config.conf.is_set("global_client"):
        config.conf.global_client = global_client

    if not is_init():
        await init_discord_db()
        config.conf.init_mods[config.ModuleName.DB] = True


async def quit():
    """Quit this module."""
    if is_init():
        await quit_discord_db()
        config.conf.init_mods[config.ModuleName.DB] = False


def is_init():
    """Whether this module has been sucessfully initialized.

    Returns:
        bool: True/False
    """
    return config.conf.init_mods.get(config.ModuleName.DB, False)
