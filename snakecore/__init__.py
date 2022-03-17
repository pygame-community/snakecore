__title__ = 'snakecore'
__author__ = 'PygameCommunityDiscord'
__license__ = 'MIT'
__copyright__ = 'Copyright 2022-present PygameCommunityDiscord'
__version__ = '0.1.0'

import discord
from . import config
from . import command_handler, db, events, jobs, utils

def init(client: discord.Client):
    if not isinstance(client, discord.Client):
        raise TypeError(
            f"argument 'client' must be of type discord.Client,"
            f" not {client.__class__.__name__}"
        )
    config.client = client
