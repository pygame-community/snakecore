"""
This file is a part of the source code for the PygameCommunityBot.
This project has been licensed under the MIT license.
Copyright (c) 2020-present PygameCommunityDiscord

This file defines some constants and variables used across the whole codebase
"""

from typing import Optional

import discord

# default client object
client: Optional[discord.Client] = None

# init-flags
snakecore_is_init = False
events_is_init = False
utils_is_init = False
jobs_is_init = False


BASIC_MAX_FILE_SIZE = 8_000_000  # bytes

ZERO_SPACE = "\u200b"  # U+200B

DOC_EMBED_LIMIT = 3
BROWSE_MESSAGE_LIMIT = 500
