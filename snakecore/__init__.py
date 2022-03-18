from typing import Optional
import discord

from . import config
from . import utils, command_handler, db, events, jobs

__title__ = "snakecore"
__author__ = "PygameCommunityDiscord"
__license__ = "MIT"
__copyright__ = "Copyright 2022-present PygameCommunityDiscord"
__version__ = "0.1.0"


def init(client: Optional[discord.Client] = None):
    if not isinstance(client, (discord.Client, type(None))):
        raise TypeError(
            f"argument 'client' must be None or of type discord.Client,"
            f" not {client.__class__.__name__}"
        )

    if config.client is None:
        config.client = client

    events.init(client=client)
    utils.init(client=client)

    config.snakecore_is_init = True


def is_init() -> bool:
    return config.snakecore_is_init
