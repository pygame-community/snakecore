"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

This file exports the Database Interface API
"""

from typing import Optional

import discord

from snakecore import config

# API to be exported is imported like 'import ... as ...'
from .discorddb import DiscordDB as DiscordDB, init_discord_db, quit_discord_db
from .localdb import LocalDB as LocalDB


async def init(client: Optional[discord.Client] = None):
    if client is not None and not config.conf.is_set("global_client"):
        config.conf.global_client = client

    if not is_init():
        await init_discord_db()
        config.conf.init_mods[config.ModuleName.DB] = True


async def quit():
    if is_init():
        await quit_discord_db()
        config.conf.init_mods[config.ModuleName.DB] = False


def is_init():
    return config.conf.init_mods.get(config.ModuleName.DB, False)
