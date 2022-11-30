"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file implements a 'DiscordStorage', which loads data from a channel on discord,
stores it in memory and finally flushes data back to the channel when the bot
is shutting down.
Some pros of this implemenation are:
1) Storing data is fast because of in memory data caching
2) No dependence on external SQL API or any database server
Some cons:
1) May have a large memory footprint for large data
2) For now, only one instance of the bot is allowed to run a discord storage channel
"""

import io
from typing import TypeVar

import discord

from snakecore import config

from .local_storage import LocalStorage, _StorageLockedRecord

_T = TypeVar("_T")


class DiscordStorage(LocalStorage[_T]):
    """DiscordStorage is an implemenation of the AbstractStorage interface for storing data
    in memory just like LocalStorage, but also backing up the data on a discord
    channel
    """

    # redefine this here, so that this dict is distinct from the dict in
    # LocalStorage
    _storage_records: dict[str, _StorageLockedRecord] = {}

    @property
    def is_init(self) -> bool:
        return config.conf.init_mods.get(config.ModuleName.STORAGE, False)


async def init_discord_storage():
    """Initialise local cache and storage channel. Call this function when the
    bot boots up.
    """
    if config.conf.storage_channel is None:
        return

    async for msg in config.conf.storage_channel.history():
        if msg.attachments:
            DiscordStorage._storage_records[msg.content] = _StorageLockedRecord(
                await msg.attachments[0].read()
            )


async def quit_discord_storage():
    """Flushes local cache for moving data to the Storage, and cleans up"""
    if config.conf.storage_channel is None:
        # quit has no effect if storage_channel is None
        return

    async for msg in config.conf.storage_channel.history():
        try:
            if DiscordStorage._storage_records[msg.content].changed:
                await msg.delete()
        except KeyError:
            pass

    for name, rec in DiscordStorage._storage_records.items():
        # Access _storage_records directly here. Don't worry about locking here
        # because the bot is shutting
        if rec.changed and not rec.deleted:
            with io.BytesIO(rec.data) as fobj:
                await config.conf.storage_channel.send(name, file=discord.File(fobj))
