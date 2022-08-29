"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file defines a customized drop-in replacement for `discord.ext.commands.Bot`
and `discord.ext.commands.AutoShardedBot` with more features.
"""

import importlib
import inspect
import sys
import types
from typing import Any, Dict, Mapping, Optional, Union
from discord.ext import commands
from discord.ext.commands import errors

from snakecore.constants import UNSET

__all__ = (
    "ExtBot",
    "ExtAutoShardedBot",
    "Bot",
    "AutoShardedBot",
)


def _is_submodule(parent: str, child: str) -> bool:
    return parent == child or child.startswith(parent + ".")


class ExtBotBase(commands.bot.BotBase):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._extension_configs: dict[str, dict[str, Any]] = {}

    def set_extension_config(self, absolute_name: str, config: Mapping[str, Any]):
        """Set a configuration mapping that an extension should be loaded with, under
        the given absolute name.

        Args:
            absolute_name (str): The extension's absolute name.
            config (Mapping[str, Any]): A mapping containing the configuration data
              to be read by the extension.

        Raises:
            TypeError: Invalid argument types.
        """
        if not isinstance(absolute_name, str):
            raise TypeError(
                "'absolute_name' must be of type 'str', not "
                f"'{absolute_name.__class__.__name__}'"
            )

        elif not isinstance(config, Mapping):
            raise TypeError(
                "'config' must be of type 'Mapping', not "
                f"'{config.__class__.__name__}'"
            )

        self._extension_configs[absolute_name] = config

    def get_extension_config(
        self, absolute_name: str, default: Any = UNSET, /
    ) -> Union[Mapping[str, Any], Any]:
        """Get the configuration mapping that an extension should be loaded with, under
        the given absolute name.

        Args:
            absolute_name (str): The extension's absolute name.
            default (Any, optional): A default value to return if no configuration
              mapping was found. Omission will lead to a LookupError being raised.

        Raises:
            LookupError: No configuration mapping was found.

        Returns:
            Union[Mapping[str, Any], Any]: The mapping or a default value.
        """
        config = self._extension_configs.get(absolute_name, None)

        if config is not None:
            return config

        elif default is not UNSET:
            return default

        raise LookupError(
            f"could not find configuration data for extension named '{absolute_name}'"
        )

    async def load_extension_with_config(
        self,
        name: str,
        *,
        package: Optional[str] = None,
        config: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """A shorthand for calling `load_extension` followed by `set_extension_config`."""
        name = self._resolve_name(name, package)
        if name in self.extensions:
            raise errors.ExtensionAlreadyLoaded(name)

        if config is not None:
            self.set_extension_config(name, config)

        await self.load_extension(name, package=package)


class ExtBot(ExtBotBase, commands.Bot):
    """A drop-in replacement for `discord.ext.commands.Bot` with more extension-loading features."""

    pass


class ExtAutoShardedBot(ExtBotBase, commands.AutoShardedBot):
    """A drop-in replacement for `discord.ext.commands.AutoShardedBot` with more extension-loading features."""

    pass


Bot = ExtBot  # export with familiar name
"""A drop-in replacement for `discord.ext.commands.Bot` with more features."""
AutoShardedBot = ExtAutoShardedBot
"""A drop-in replacement for `discord.ext.commands.AutoShardedBot` with more features."""
