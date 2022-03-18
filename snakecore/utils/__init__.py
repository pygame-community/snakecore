"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2020-present PygameCommunityDiscord

This module defines some utility functionality for the library and general bot development.
"""

import discord
from snakecore import config
from . import embed_utils, serializers
from .utils import *


def init(client: discord.Client):
    if not isinstance(client, discord.Client):
        raise TypeError(
            f"argument 'client' must be of type discord.Client,"
            f" not {client.__class__.__name__}"
        )
    config.client = client
    config.utils_is_init = True


def is_init() -> bool:
    return config.utils_is_init
