"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

This module defines some utility functionality for the library and general bot
development.
"""

from typing import Optional

import discord

from .. import config

from .utils import *
from . import embed_utils, pagination


def init(global_client: Optional[discord.Client] = None):
    """Initialize this module.

    Args:
        global_client (Optional[discord.Client], optional):
          The global `discord.Client` object to set for all modules to use.
          Defaults to None.
    """
    if global_client is not None and not config.conf.is_set("global_client"):
        config.conf.global_client = global_client

    config.conf.init_mods[config.ModuleName.UTILS] = True


def quit():
    """Quit this module."""
    config.conf.init_mods[config.ModuleName.UTILS] = False


def is_init():
    """Whether this module has been sucessfully initialized.

    Returns:
        bool: True/False
    """
    return config.conf.init_mods.get(config.ModuleName.UTILS, False)
