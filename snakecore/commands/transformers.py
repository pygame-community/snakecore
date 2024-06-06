"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2024-present pygame-community.

This file defines some transformers for application command argument parsing.
"""

import discord
from discord import app_commands
from discord.ext import commands

_DECBotT = commands.Bot | commands.AutoShardedBot


class MessageTransformer(app_commands.Transformer):
    "Transforms to a :class:`discord.Message`."

    async def transform(
        self, interaction: discord.Interaction[_DECBotT], value: str
    ) -> discord.Message:
        try:
            return await commands.MessageConverter().convert(
                await commands.Context.from_interaction(interaction), value
            )
        except commands.BadArgument:
            raise app_commands.TransformerError(
                value, discord.AppCommandOptionType.string, self
            )


Message = app_commands.Transform[discord.Message, MessageTransformer]
"Transforms to a :class:`discord.Message`."

__all__ = ("MessageTransformer", "Message")
