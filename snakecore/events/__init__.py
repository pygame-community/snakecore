"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2020-present PygameCommunityDiscord

This module implements classes for representing generic event objects using OOP principles.
"""
from typing import Optional

from snakecore import config
from snakecore.constants import UNSET, UNSET_TYPE
from .base_events import BaseEvent, CustomEvent
from .client_events import *


def init(client: Union[UNSET_TYPE, discord.Client] = UNSET):
    if not isinstance(client, (discord.Client, UNSET_TYPE)):
        raise TypeError(
            f"argument 'client' must be None or of type discord.Client,"
            f" not {client.__class__.__name__}"
        )

    config.set_value("global_client", client, ignore_if_set=True)
    config.set_value("events_is_init", True)


def is_init() -> bool:
    return config.get_value("events_is_init", wanted_value_cls=bool)
