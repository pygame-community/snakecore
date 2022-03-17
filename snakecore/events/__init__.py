"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2020-present PygameCommunityDiscord

This module implements classes for representing generic event objects using OOP principles.
"""

import snakecore.config

def init(client: discord.Client):
    if not isinstance(client, discord.Client):
        raise TypeError(
            f"argument 'client' must be of type discord.Client,"
            f" not {client.__class__.__name__}"
        )
    snakecore.config.client = client


from .base_events import BaseEvent, CustomEvent
from .client_events import *
