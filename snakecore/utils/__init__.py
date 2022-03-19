"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2020-present PygameCommunityDiscord

This module defines some utility functionality for the library and general bot development.
"""

from typing import Optional
import discord
from snakecore import config
from snakecore.constants import UNSET, UNSET_TYPE
from . import embed_utils
from .utils import *


def init(client: Union[UNSET_TYPE, discord.Client] = UNSET):
    if not isinstance(client, (discord.Client, UNSET_TYPE)):
        raise TypeError(
            f"argument 'client' must be None or of type discord.Client,"
            f" not {client.__class__.__name__}"
        )

    config.set_config_value("global_client", client, ignore_if_set=True)
    config.set_config_value("utils_is_init", True)


def is_init() -> bool:
    return config.get_config_value("utils_is_init", wanted_value_cls=bool)
