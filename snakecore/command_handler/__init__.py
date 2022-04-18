from typing import Optional

import discord

from snakecore import config
from . import converters, decorators, parser


def init(global_client: Optional[discord.Client] = None):
    """Initialize this module.

    Args:
        global_client (Optional[discord.Client], optional):
          The global `discord.Client` object to set for all modules to use.
          Defaults to None.
    """
    if global_client is not None and not config.conf.is_set("global_client"):
        config.conf.global_client = global_client

    config.conf.init_mods[config.ModuleName.COMMAND_HANDLER] = True


def quit():
    """Quit this module."""
    config.conf.init_mods[config.ModuleName.COMMAND_HANDLER] = False


def is_init():
    """Whether this module has been sucessfully initialized.

    Returns:
        bool: True/False
    """
    return config.conf.init_mods.get(config.ModuleName.COMMAND_HANDLER, False)
