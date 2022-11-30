"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file exports the Storage Interface API
"""

from typing import Optional

import discord

from snakecore import config

# API to be exported is imported like 'import ... as ...'
from .discord_storage import (
    DiscordStorage as DiscordStorage,
    init_discord_storage,
    quit_discord_storage,
)
from .local_storage import LocalStorage as LocalStorage


async def init(global_client: Optional[discord.Client] = None) -> None:
    """Initialize this module.

    Parameters
    ----------
    global_client : Optional[discord.Client], optional
        The global `discord.Client` object to set for all modules to use.
        Defaults to None.
    """
    if global_client is not None and not config.conf.is_set("global_client"):
        config.conf.global_client = global_client

    if not is_init():
        await init_discord_storage()
        config.conf.init_mods[config.ModuleName.STORAGE] = True


async def quit() -> None:
    """Quit this module."""
    if is_init():
        await quit_discord_storage()
        config.conf.init_mods[config.ModuleName.STORAGE] = False


def is_init() -> bool:
    """`bool`: Whether this module has been sucessfully initialized."""
    return config.conf.init_mods.get(config.ModuleName.STORAGE, False)
