from typing import TypeVar

from discord import app_commands
from discord.ext import commands


AnyCommandType = TypeVar(
    "AnyCommandType",
    commands.Command,
    commands.Group,
    commands.HybridCommand,
    commands.HybridGroup,
    app_commands.Command,
)
