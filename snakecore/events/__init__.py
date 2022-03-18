"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2020-present PygameCommunityDiscord

This module implements classes for representing generic event objects using OOP principles.
"""
from typing import Optional

from snakecore import config
from .base_events import BaseEvent, CustomEvent
from .client_events import *


def init(client: Optional[discord.Client] = None):
    if not isinstance(client, (discord.Client, type(None))):
        raise TypeError(
            f"argument 'client' must be None or of type discord.Client,"
            f" not {client.__class__.__name__}"
        )

    if config.client is None:
        config.client = client
    config.events_is_init = True


def is_init() -> bool:
    return config.events_is_init
