from typing import Optional, Union
import discord

from . import utils, command_handler, db, jobs
from .config import conf

__title__ = "snakecore"
__author__ = "PygameCommunityDiscord"
__license__ = "MIT"
__copyright__ = "Copyright 2022-present PygameCommunityDiscord"
__version__ = "0.1.0"


def init(client: Optional[discord.Client] = None):
    if client is not None and not conf.is_set("global_client"):
        conf.global_client = client

    utils.init(client=client)
    conf.init_mods[config.ModuleName.SNAKECORE] = True


def is_init():
    return conf.init_mods.get(config.ModuleName.SNAKECORE, False)
