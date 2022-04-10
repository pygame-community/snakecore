"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

This file defines some constants used across the library.
"""

import asyncio
from typing import Any, Optional
from aiohttp import ClientError

import discord

from . import enums
from .enums import *

import sys

if sys.version_info >= (3, 10):
    from types import UnionType
else:
    UnionType = type(Optional[int])


class _SingletonMeta(type):
    def __init__(cls, name, bases, dct):
        super(_SingletonMeta, cls).__init__(name, bases, dct)
        super(_SingletonMeta, cls).__setattr__(f"_{cls.__name__}__inst", None)

    def __call__(cls, *args, **kw):
        if getattr(cls, f"_{cls.__name__}__inst", None) is None:
            super(_SingletonMeta, cls).__setattr__(
                f"_{cls.__name__}__inst",
                super(_SingletonMeta, cls).__call__(*args, **kw),
            )
        return getattr(cls, f"_{cls.__name__}__inst")

    def __setattr__(cls, name: str, value: object):
        if (
            name == f"_{cls.__name__}__inst"
            and getattr(cls, f"_{cls.__name__}__inst", None) is not None
        ):
            raise ValueError("cannot modify the specified attribute")

    def __delattr__(cls, name: str):
        if name == f"_{cls.__name__}__inst":
            raise ValueError("cannot delete the specified attribute")


class _UnsetType(metaclass=_SingletonMeta):
    __slots__ = ()

    def __eq__(self, other):
        return False

    def __bool__(self):
        return False

    def __hash__(self):
        return 0

    def __repr__(self):
        return "Unset"


# sentinel singleton for unused variables
UNSET: Any = _UnsetType()

# helpful constants
BASIC_MAX_FILE_SIZE = 8_000_000  # bytes
ZERO_SPACE = "\u200b"  # U+200B


# jobs
_SYSTEM_JOB_RUNTIME_IDENTIFIERS = {"JobManagerJob": "0-0"}
DEFAULT_JOB_EXCEPTION_WHITELIST = (
    OSError,
    discord.GatewayNotFound,
    discord.ConnectionClosed,
    ClientError,
    asyncio.TimeoutError,
)
"""The default exceptions handled in discord.ext.tasks.Loop
upon reconnecting."""
