"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2020-present PygameCommunityDiscord

This module defines some internal configuration variables used across the whole
codebase. It is not meant to be used with `from ... import` statements, since the
values of the variables defined in it can change at runtime.

These configuration variables are only meant to be accessed and
modified with the `get_value()` and `set_value()` functions.
"""

from typing import Any, Optional, Type, Union
import discord

from snakecore.constants import UNSET, UNSET_TYPE
from snakecore import config


EllipsisType = type(Ellipsis)
NoneType = type(None)

_all_vars = globals()

# helper functions
def get_value(
    name: str,
    default: Union[UNSET_TYPE, Any] = UNSET,
    wanted_value_cls: Optional[Type] = None,
) -> Any:
    """Get the current value of the specified configuration variable.

    Args:
        name (str): The name of the target configuration variable.
        default (Any): The value to return if no configuration variable was set.
        wanted_value_cls (Optional[Type]): An optional type to indicate as the desired
          type in the `RuntimeError` exception raised when a configuration value is
          not set. `None` will be ignored as an argument. Defaults to None.

     Returns:
        object: The value of the specified configuration variable, or the `default`
          return value, if set.

    Raises:
        KeyError: Argument `name` is not a valid configuration variable name.
        RuntimeError: The value for the speficied configuration variable is not set.
    """

    real_name = name

    if not name.startswith("config_"):
        real_name = "config_" + name

    if real_name not in _all_vars:
        raise KeyError(f"Invalid configuration variable name: {name}")

    value = _all_vars[real_name]

    if value is UNSET:
        if default is not UNSET:
            return default

        raise RuntimeError(
            f"the value for the configuration variable name '{name}' is not set"
            + (
                f" as an instance of class {wanted_value_cls.__name__}"
                if wanted_value_cls is not None
                else ""
            )
            + ", it is required for proper functioning of the module calling this function"
        )

    return value


def set_value(name: str, value: Any, ignore_if_set: bool = False):
    """Set the new value for the specified configuration variable.

    Args:
        name (str): The name of the target configuration variable.
        value (Any): The new value to set.
        ignore_if_set (bool, optional): Whether to only set a new value
          if another value has not already been set. Defaults to False.

    Raises:
        KeyError: Argument `name` is not a valid configuration variable name.
    """

    real_name = name

    if not name.startswith("config_"):
        real_name = "config_" + name

    if real_name not in _all_vars:
        raise KeyError(f"Invalid configuration variable name: {name}")

    old_value = _all_vars[real_name]

    if old_value is UNSET or not ignore_if_set:
        config.__dict__[real_name] = value


# configuration variables

# default client object
config_global_client: Union[UNSET_TYPE, discord.Client] = UNSET

# init-flags
config_snakecore_is_init = False
config_utils_is_init = False
