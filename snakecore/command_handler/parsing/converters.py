
import datetime
from functools import partial
import functools
import inspect
import types
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

import snakecore
from .parser import CodeBlock, String

class DateTime(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> datetime.datetime:
        arg = argument.strip()

        if snakecore.utils.is_markdown_timestamp(arg):
            arg = snakecore.utils.extract_markdown_timestamp(arg)
        else:
            arg = arg.removesuffix("Z")

        try:
            return datetime.datetime.fromisoformat(arg)
        except ValueError as v:
            raise commands.BadArgument(f"failed to construct datetime: {v.__class__.__name__}:{v!s}") from v


class Range(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> range:
        if not argument.startswith("[") or not argument.endswith("]"):
            raise commands.BadArgument("ranges begin and end with square brackets")

        try:
            splits = [int(i.strip()) for i in argument[6:-1].split(":")]

            if splits and len(splits) <= 3:
                return range(*splits)
        except (ValueError, TypeError) as v:
            raise commands.BadArgument(f"failed to construct range: {argument!r}") from v
        
        raise commands.BadArgument(f"invalid range string: {argument!r}")


class QuotedString(commands.Converter):
    """A simple converter that enforces a quoted string as an argument.
    It removes leading and ending single or doble quotes. If those quotes
    are not found, quoting exceptions are raised.
    """
    async def convert(self, ctx: commands.Context, argument: str) -> range:
        passed = False
        if argument.startswith("\""):
            if argument.endswith("\""):
                passed = True
            else:
                raise commands.ExpectedClosingQuoteError("argument string is not properly quoted with \'\' or \"\"")

        elif argument.startswith("\'"):
            if argument.endswith("\'"):
                passed = True
            else:
                raise commands.ExpectedClosingQuoteError("argument string is not properly quoted with \'\' or \"\"")
            
        if not passed:
            raise commands.BadArgument("argument string is not properly quoted with \'\' or \"\"")
            
        return argument[1:-1]


if TYPE_CHECKING:
    DateTime = datetime.datetime
    Range = range
    QuotedString = str
