"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file defines powerful utilities for developing bot commands.
"""

from typing import Optional

import discord

from snakecore import config
from . import converters, decorators, parser
from .bot import *


def init(global_client: discord.Client | None = None) -> None:
    """Initialize this module.

    Parameters
    ----------
    global_client : discord.Client | None, optional
        The global `discord.Client` object to set for all submodules to use.
        Defaults to None.
    """
    if global_client is not None and not config.conf.is_set("global_client"):
        config.conf.global_client = global_client

    config.conf.init_mods[config.ModuleName.COMMANDS] = True


def quit():
    """Quit this module."""
    config.conf.init_mods[config.ModuleName.COMMANDS] = False


def is_init():
    """`bool`: Whether this module has been sucessfully initialized."""
    return config.conf.init_mods.get(config.ModuleName.COMMANDS, False)
