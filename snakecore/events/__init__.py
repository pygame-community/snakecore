"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2020-present PygameCommunityDiscord

This module implements classes for representing generic event objects using OOP principles.
"""
from typing import Optional

from snakecore import conf

from .base_events import BaseEvent, CustomEvent
from .client_events import *


def init(client: Optional[discord.Client] = None):
    if client is not None and not conf.is_set("global_client"):
        conf.global_client = client

    conf.init_mods[config.ModuleName.EVENTS] = True


def is_init():
    return conf.init_mods.get(config.ModuleName.EVENTS, False)
