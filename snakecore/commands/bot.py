"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file defines a customized drop-in replacement for `discord.ext.commands.Bot`
and `discord.ext.commands.AutoShardedBot` with more features.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Mapping

from discord.ext import commands
from discord.ext.commands import errors
import discord.ext.commands.bot

from snakecore.constants import UNSET

__all__ = (
    "Bot",
    "AutoShardedBot",
)

_logger = logging.getLogger(__name__)


class BotBase(discord.ext.commands.bot.BotBase):
    if TYPE_CHECKING:  # reuse constructor of superclass
        _extension_configs: dict[str, Mapping[str, Any]]
    else:

        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._extension_configs: dict[str, Mapping[str, Any]] = {}
            self._is_closing: bool = False

    def set_extension_config(
        self, qualified_name: str, config: Mapping[str, Any]
    ) -> None:
        """Set a configuration mapping that an extension should be loaded with, under
        the given absolute name.

        Parameters
        ----------
        qualified_name : str
            The extension's qualified name.
        config : Mapping[str, Any]
            A mapping containing the configuration data to be read by the extension.

        Raises
        ------
        TypeError
            Invalid argument types.
        """
        if not isinstance(qualified_name, str):
            raise TypeError(
                "'absolute_name' must be of type 'str', not "
                f"'{qualified_name.__class__.__name__}'"
            )

        elif not isinstance(config, Mapping):
            raise TypeError(
                "'config' must be of type 'Mapping', not "
                f"'{config.__class__.__name__}'"
            )

        self._extension_configs[qualified_name] = config

    def delete_extension_config(self, qualified_name: str):
        """Delete an extension configuration mapping under
        the given qualified name, if present.

        Parameters
        ----------
        qualified_name : str
            The extension's qualified name.

        Raises
        ------
        TypeError
            Invalid argument types.
        """
        if not isinstance(qualified_name, str):
            raise TypeError(
                "'absolute_name' must be of type 'str', not "
                f"'{qualified_name.__class__.__name__}'"
            )

        if qualified_name in self._extension_configs:
            del self._extension_configs[qualified_name]

    def get_extension_config(
        self, qualified_name: str, default: Any = UNSET, /
    ) -> Mapping[str, Any] | Any:
        """Get the configuration mapping that an extension should be loaded with, under
        the given qualified name.

        Parameters
        ----------
        qualified_name : str
            The extension's qualified name.
        default : Any, optional
            A default value to return if no configuration mapping was found.
            Omission will lead to a LookupError being raised.

        Raises
        ------
        LookupError
            No configuration mapping was found.

        Returns
        -------
        Mapping[str, Any] | Any
            The mapping or a default value.
        """
        config = self._extension_configs.get(qualified_name, None)

        if config is not None:
            return config

        elif default is not UNSET:
            return default

        raise LookupError(
            f"could not find configuration data for extension named '{qualified_name}'"
        )

    async def load_extension_with_config(
        self,
        name: str,
        *,
        package: str | None = None,
        config: Mapping[str, Any] | None = None,
    ) -> None:
        """A shorthand for calling `set_extension_config` followed by `load_extension`."""
        name = self._resolve_name(name, package)
        if name in self.extensions:
            raise errors.ExtensionAlreadyLoaded(name)

        if config is not None:
            self.set_extension_config(name, config)

        await self.load_extension(name, package=package)

    async def teardown_hook(self) -> None:
        """An analogue to `setup_hook()` that is called only once, within `close()`.
        Useful for calling asynchronous teardown code before the bot disconnects.
        """
        pass

    async def close(self):
        if not self.is_closed():  # type: ignore
            self._is_closing = True
            await self.teardown_hook()
            await super().close()
            self._is_closing = False

    def is_closing(self) -> bool:
        """`bool`: Whether the bot is closing."""
        return self._is_closing

    def dispatch(
        self, event_name: str, /, *args: Any, **kwargs: Any
    ) -> list[asyncio.Task]:
        """Dispatches the specified event and returns all `asyncio.Task` objects
        generated in the process.

        Parameters
        ----------
        event_name : str
            The name of the event to dispatch.

        Returns
        -------
        list[asyncio.Task]
            The task objects generated by the dispatch operation.
        """
        _logger.debug("Dispatching event %s", event_name)
        method = "on_" + event_name

        listeners = self._listeners.get(event_name)  # type: ignore
        tsks = []
        if listeners:
            removed = []
            for i, (future, condition) in enumerate(listeners):
                if future.cancelled():
                    removed.append(i)
                    continue

                try:
                    result = condition(*args)
                except Exception as exc:
                    future.set_exception(exc)
                    removed.append(i)
                else:
                    if result:
                        if len(args) == 0:
                            future.set_result(None)
                        elif len(args) == 1:
                            future.set_result(args[0])
                        else:
                            future.set_result(args)
                        removed.append(i)

            if len(removed) == len(listeners):
                self._listeners.pop(event_name)  # type: ignore
            else:
                for idx in reversed(removed):
                    del listeners[idx]

        try:
            coro = getattr(self, method)
        except AttributeError:
            pass
        else:
            tsks.append(self._schedule_event(coro, method, *args, **kwargs))  # type: ignore

        tsks.extend(
            self._schedule_event(event, method, *args, **kwargs)  # type: ignore
            for event in self.extra_events.get(method, [])
        )  # type: ignore
        return tsks


class Bot(BotBase, commands.Bot):
    """A drop-in replacement for `discord.ext.commands.Bot` with more extension-loading features."""

    pass


class AutoShardedBot(BotBase, commands.AutoShardedBot):
    """A drop-in replacement for `discord.ext.commands.AutoShardedBot` with more extension-loading features."""

    pass
