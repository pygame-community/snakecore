from typing import Optional, Union
import discord

from .constants import UNSET, UNSET_TYPE
from . import config, utils, command_handler, db, jobs

__title__ = "snakecore"
__author__ = "PygameCommunityDiscord"
__license__ = "MIT"
__copyright__ = "Copyright 2022-present PygameCommunityDiscord"
__version__ = "0.1.0"


def init(client: Union[UNSET_TYPE, discord.Client] = UNSET):
    if not isinstance(client, (discord.Client, UNSET_TYPE)):
        raise TypeError(
            f"argument 'client' must be None or of type discord.Client,"
            f" not {client.__class__.__name__}"
        )

    config.set_config_value("global_client", client)
    utils.init(client=client)
    config.set_config_value("snakecore_is_init", True)


def is_init() -> bool:
    return config.get_config_value("snakecore_is_init", wanted_value_cls=bool)
