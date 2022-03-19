"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2020-present PygameCommunityDiscord

This module defines some utility functionality for the library and general bot development.
"""

from typing import Optional
import discord
from snakecore import config
from . import embed_utils
from .utils import *


def init(client: Optional[discord.Client] = None):
    if not isinstance(client, (discord.Client, type(None))):
        raise TypeError(
            f"argument 'client' must be None or of type discord.Client,"
            f" not {client.__class__.__name__}"
        )

    if config.client is None:
        config.client = client
    config.utils_is_init = True


def is_init() -> bool:
    return config.utils_is_init
