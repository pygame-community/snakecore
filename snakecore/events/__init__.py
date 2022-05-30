"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This module implements classes for representing generic event objects using OOP principles.
"""
from typing import Optional

from snakecore import config

from .base_events import BaseEvent, CustomEvent
from .client_events import *


def init(global_client: Optional[discord.Client] = None):
    """Initialize this module.

    Args:
        global_client (Optional[discord.Client], optional):
          The global `discord.Client` object to set for all modules to use.
          Defaults to None.
    """
    if global_client is not None and not config.conf.is_set("global_client"):
        config.conf.global_client = global_client

    config.conf.init_mods[config.ModuleName.EVENTS] = True


def quit():
    """Quit this module."""
    config.conf.init_mods[config.ModuleName.EVENTS] = False


def is_init():
    """Whether this module has been sucessfully initialized.

    Returns:
        bool: True/False
    """
    return config.conf.init_mods.get(config.ModuleName.EVENTS, False)
