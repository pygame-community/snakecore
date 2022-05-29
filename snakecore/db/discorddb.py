"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

This file implements a 'DiscordDB', which loads data from a channel on discord,
stores it in memory and finally flushes data back to the channel when the bot
is shutting down.
Some pros of this implemenation are:
1) Database is fast because of data stored in memory
2) No dependence on external SQL API or any database server
Some cons:
1) May have a large memory footprint for large data
2) For now, only one instance of the bot is allowed to run a discorddb channel
"""

import io
from typing import TypeVar

import discord

from snakecore import config

from .localdb import LocalDB, _DBLockedRecord

_T = TypeVar("_T")


class DiscordDB(LocalDB[_T]):
    """
    DiscordDB is an implemenation of the AbstractDB interface for storing data
    in memory just like LocalDB, but also backing up the data on a discord
    channel
    """

    # redefine this here, so that this dict is distinct from the dict in
    # LocalDB
    _db_records: dict[str, _DBLockedRecord] = {}

    @property
    def is_init(self) -> bool:
        return config.conf.init_mods.get(config.ModuleName.DB, False)


async def init_discord_db():
    """
    Initialise local cache and db channel. Call this function when the
    bot boots up.
    """
    if config.conf.db_channel is None:
        return

    async for msg in config.conf.db_channel.history():
        if msg.attachments:
            DiscordDB._db_records[msg.content] = _DBLockedRecord(
                await msg.attachments[0].read()
            )


async def quit_discord_db():
    """
    Flushes local cache for storage to the DB, and cleans up
    """
    if config.conf.db_channel is None:
        # quit has no effect if db_channel is None
        return

    async for msg in config.conf.db_channel.history():
        try:
            if DiscordDB._db_records[msg.content].changed:
                await msg.delete()
        except KeyError:
            pass

    for name, rec in DiscordDB._db_records.items():
        # Access _db_records directly here. Don't worry about locking here
        # because the bot is shutting
        if rec.changed and not rec.deleted:
            with io.BytesIO(rec.data) as fobj:
                await config.conf.db_channel.send(name, file=discord.File(fobj))
