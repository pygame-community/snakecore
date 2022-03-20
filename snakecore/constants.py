"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2020-present PygameCommunityDiscord

This file defines some constants used across the library.
"""

from typing import Any


class _UnsetValue:
    __slots__ = ()

    def __eq__(self, other):
        return False

    def __bool__(self):
        return False

    def __hash__(self):
        return 0

    def __repr__(self):
        return "UnsetValue"


UNSET: Any = _UnsetValue()
UNSET_TYPE = _UnsetValue


# helpful constants
BASIC_MAX_FILE_SIZE = 8_000_000  # bytes
ZERO_SPACE = "\u200b"  # U+200B
