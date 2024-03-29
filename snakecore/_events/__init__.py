"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This module implements classes for representing generic event objects using OOP principles.
"""
from snakecore import config

from .base_events import BaseEvent, CustomEvent
from .client_events import *


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

    config.conf.init_mods[config.ModuleName._EVENTS] = True


def quit() -> None:
    """Quit this module."""
    config.conf.init_mods[config.ModuleName._EVENTS] = False


def is_init() -> bool:
    """`bool`: Whether this module has been sucessfully initialized."""
    return config.conf.init_mods.get(config.ModuleName._EVENTS, False)
