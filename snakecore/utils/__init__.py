"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This module defines some utility functionality for the library and general bot
development.
"""

from typing import Optional

import discord

from snakecore import config

from .utils import *
from . import embeds, pagination, regex_patterns, serializers

embed_utils = embeds


def init(global_client: discord.Client | None = None) -> None:
    """Initialize this module.

    Parameters
    ----------
    global_client : discord.Client | None, optional
        The global `discord.Client` object to set for all modules to use.
        Defaults to None.
    """
    if global_client is not None and not config.conf.is_set("global_client"):
        config.conf.global_client = global_client

    config.conf.init_mods[config.ModuleName.UTILS] = True


def quit() -> None:
    """Quit this module."""
    config.conf.init_mods[config.ModuleName.UTILS] = False


def is_init() -> bool:
    """`bool`: Whether this module has been sucessfully initialized."""
    return config.conf.init_mods.get(config.ModuleName.UTILS, False)
