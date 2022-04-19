"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

This file defines some converters for command argument parsing.
"""

import datetime
from typing import TYPE_CHECKING

from discord.ext import commands

import snakecore
from .parser import CodeBlock, String


class DateTime(commands.Converter):
    """A converter that parses UNIX/ISO timestamps to `datetime.datetime` objects.

    Syntax:
        - `<t:{6969...}[:t|T|d|D|f|F|R]> -> datetime.datetime(seconds=6969...)`
        - `YYYY-MM-DD[*HH[:MM[:SS[.fff[fff]]]][+HH:MM[:SS[.ffffff]]]] -> datetime.datetime`
    """

    async def convert(self, ctx: commands.Context, argument: str) -> datetime.datetime:
        arg = argument.strip()

        if snakecore.utils.is_markdown_timestamp(arg):
            arg = snakecore.utils.extract_markdown_timestamp(arg)
            try:
                return datetime.datetime.fromtimestamp(arg)
            except ValueError as v:
                raise commands.BadArgument(
                    f"failed to construct datetime: {v.__class__.__name__}:{v!s}"
                ) from v
        else:
            arg = arg.removesuffix("Z")

        try:
            return datetime.datetime.fromisoformat(arg)
        except ValueError as v:
            raise commands.BadArgument(
                f"failed to construct datetime: {v.__class__.__name__}:{v!s}"
            ) from v


class RangeObject(commands.Converter):
    """A converter that parses integer range values to `range` objects.

    Syntax:
        - `[start:stop] -> range(start, stop)`
        - `[start:stop:step] -> range(start, stop, step)`
    """

    async def convert(self, ctx: commands.Context, argument: str) -> range:
        if not argument.startswith("[") or not argument.endswith("]"):
            raise commands.BadArgument("ranges begin and end with square brackets")

        try:
            splits = [int(i.strip()) for i in argument[6:-1].split(":")]

            if splits and len(splits) <= 3:
                return range(*splits)
        except (ValueError, TypeError) as v:
            raise commands.BadArgument(
                f"failed to construct range: {argument!r}"
            ) from v

        raise commands.BadArgument(f"invalid range string: {argument!r}")


class QuotedString(commands.Converter):
    """A simple converter that enforces a quoted string as an argument.
    It removes leading and ending single or doble quotes. If those quotes
    are not found, exceptions are raised.

    Syntax:
        - `"abc" -> str("abc")`
        - `'abc' -> str('abc')`
    """

    async def convert(self, ctx: commands.Context, argument: str) -> range:
        passed = False
        if argument.startswith('"'):
            if argument.endswith('"'):
                passed = True
            else:
                raise commands.BadArgument(
                    "argument string quote '\"' was not closed with \""
                )

        elif argument.startswith("'"):
            if argument.endswith("'"):
                passed = True
            else:
                raise commands.BadArgument(
                    "argument string quote \"'\" was not closed with '"
                )

        if not passed:
            raise commands.BadArgument(
                "argument string is not properly quoted with '' or \"\""
            )

        return argument[1:-1]


if TYPE_CHECKING:
    DateTime = datetime.datetime
    RangeObject = range
    QuotedString = str
