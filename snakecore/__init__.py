"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

A set of core APIs to facilitate the creation of feature-rich Discord bots.
"""

from typing import Optional, Union

import discord

from . import (
    command_handler,
    config,
    constants,
    db,
    events,
    exceptions,
    jobs,
    jobutils,
    utils,
)

__title__ = "snakecore"
__author__ = "PygameCommunityDiscord"
__license__ = "MIT"
__copyright__ = "Copyright 2022-present PygameCommunityDiscord"
__version__ = "0.1.0"


async def init(
    global_client: Optional[discord.Client] = None,
    *,
    raise_module_exceptions: bool = False,
):
    """Initialize all modules that `snakecore` provides using their respective
    initialization functions with default arguments. For more control, those functions
    can be called individually. This is the same as calling `init_sync()` followed by
    `init_async()`. For modules that don't require asynchronous initialization,
    `init_sync()` can be used, however it is only a shorthand for those modules and
    does not treat snakecore as fully initialized, but only all modules that don't
    require synchronous initialization. This is similar for `init_async()`, which only
    initializes modules that require asynchronous initialization. This function will
    only attempt to initialize modules that aren't yet initialized and can be called
    multiple times.

    Args:
        global_client (Optional[discord.Client], optional):
          The global `discord.Client` object to set for all modules to use.
          Defaults to None.
        raise_module_exceptions (bool, optional): Whether all module-specific
          exceptions should be raised as they occur. Defaults to False.

    Returns:
        tuple[int, int]: A tuple of two integers, with the first one representing the
          count of successfully initialized modules and the last one the amount of
          failed modules.
    """

    if global_client is not None and not config.conf.is_set("global_client"):
        config.conf.global_client = global_client

    sync_success_failures = init_sync(raise_module_exceptions=raise_module_exceptions)
    async_success_failures = await init_async(
        raise_module_exceptions=raise_module_exceptions
    )

    return (
        sync_success_failures[0] + async_success_failures[0],
        sync_success_failures[1] + async_success_failures[1],
    )


def init_sync(
    global_client: Optional[discord.Client] = None,
    *,
    raise_module_exceptions: bool = False,
):
    """Initialize all `snakecore` modules which don't require asynchronous
    initialization. This is only a shorthand for those modules and does not fully
    initialize snakecore like `init()`. This function will only attempt to initialize
    modules that aren't yet initialized and can be called multiple times.

    Args:
        global_client (Optional[discord.Client], optional):
          The global `discord.Client` object to set for all modules to use.
          Defaults to None.
        raise_module_exceptions (bool, optional): Whether all module-specific
          exceptions should be raised as they occur. Defaults to False.

    Returns:
        tuple[int, int]: A tuple of two integers, with the first one representing the
          count of successfully initialized modules and the last one the amount of
          failed modules.
    """

    if global_client is not None and not config.conf.is_set("global_client"):
        config.conf.global_client = global_client

    success_failure_list = [0, 0]

    for module in (events, jobs, utils):  # might be extended in the future
        if not module.is_init():  # prevent multiple init calls, which can be allowed by
            # modules on an individual level

            try:
                module.init()
            except Exception:
                if raise_module_exceptions:
                    raise

                success_failure_list[1] += 1
            else:
                success_failure_list[0] += 1

    if success_failure_list[0]:
        config.conf.init_mods[config.ModuleName.SNAKECORE_SYNC] = True

    return tuple(success_failure_list)


async def init_async(
    global_client: Optional[discord.Client] = None,
    *,
    raise_module_exceptions: bool = False,
):
    """Initialize all `snakecore` modules which require asynchronous
    initialization. This is only a shorthand for those modules and does not fully
    initialize snakecore like `init()`. This function will only attempt to initialize
    modules that aren't yet initialized and can be called multiple times.

    Args:
        global_client (Optional[discord.Client], optional):
          The global `discord.Client` object to set for all modules to use.
          Defaults to None.
        raise_module_exceptions (bool, optional): Whether all module-specific
          exceptions should be raised as they occur. Defaults to False.

    Returns:
        tuple[int, int]: A tuple of two integers, with the first one representing the
          count of successfully initialized modules and the last one the amount of
          failed modules.
    """

    if global_client is not None and not config.conf.is_set("global_client"):
        config.conf.global_client = global_client

    success_failure_list = [0, 0]

    if not db.is_init():

        try:
            await db.init()
        except Exception:
            if raise_module_exceptions:
                raise

            success_failure_list[1] += 1
        else:
            success_failure_list[0] += 1

    if success_failure_list[0]:
        config.conf.init_mods[config.ModuleName.SNAKECORE_ASYNC] = True

    return tuple(success_failure_list)


async def quit():
    """A function to uninitialize `snakecore` and all modules that it provides.

    This function will call `quit_sync()` followed by `quit_async()`.
    For modules that don't require asynchronous quitting, those can be quitted using
    `quit_sync()` directly, however it is only a shorthand for those modules and does
    not fully uninitialize snakecore. This function will only attempt to quit modules
    that are still initialized and can be called multiple times.
    """
    # call any quit hooks here
    quit_sync()
    await quit_async()


def quit_sync():
    """A function to uninitialize and all modules of snakecore that don't require
    asynchronous initialization.

    This function will call the `quit()` function for all modules that require it.
    This is only a shorthand for quitting modules that don't initialize asynchronously,
    it does not fully uninitialize snakecore. This function will only attempt to quit
    modules that are still initialized and can be called multiple times.
    """

    for module in (events, utils):  # might be extended in the future
        if module.is_init():
            module.quit()

    config.conf.init_mods[config.ModuleName.SNAKECORE_SYNC] = False


async def quit_async():
    """A function to uninitialize and all modules of snakecore that required
    asynchronous ininitialization.

    This function will call the `quit()` function for all modules that require it.
    This is only a shorthand for quitting modules that initialize asynchronously,
    it does not fully uninitialize snakecore. This function will only attempt to quit
    modules that are still initialized and can be called multiple times.
    """

    if db.is_init():
        await db.quit()
    config.conf.init_mods[config.ModuleName.SNAKECORE_ASYNC] = False


def is_sync_init():
    """Whether an attempt to initialize modules that don't require asynchronous
    initialization has occured successfully. This only means that at least one
    of the modules targeted in `init_sync()` has been sucessfully initialized,
    not all of them. For more control, consider initializing modules and handling
    their errors directly.

    Returns:
        bool: True/False
    """

    return config.conf.init_mods.get(config.ModuleName.SNAKECORE_SYNC, False)


def is_async_init():
    """Whether an attempt to initialize modules that require asynchronous
    initialization has occured successfully. This only means that at least one
    of the modules targeted in `init_async()` has been sucessfully initialized,
    not all of them. For more control, consider initializing modules and handling
    their errors directly.

    Returns:
        bool: True/False
    """
    return config.conf.init_mods.get(config.ModuleName.SNAKECORE_ASYNC, False)


def is_init():
    """A shorthand for testing against `is_sync_init()` and `is_async_init()` together.
    See their documentation for more deatils.

    Returns:
        bool: True/False
    """
    return is_sync_init() and is_async_init()
