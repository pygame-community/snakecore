"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file defines some important utility functions for the library.
"""

from collections import ChainMap, defaultdict
import datetime
import os
import platform
import re
import sys
import traceback
from typing import Any, Callable, Iterable, Optional, Sequence, Union

import discord

from snakecore.constants import UNSET, _UnsetType


def join_readable(joins: list[str]):
    """
    Join a list of strings, in a human readable way
    """
    if not joins:
        return ""

    preset = ", ".join(joins[:-1])
    if preset:
        return f"{preset} and {joins[-1]}"

    return joins[-1]


def clamp(value, min_, max_):
    """
    Returns the value clamped between a maximum and a minumum
    """
    value = value if value > min_ else min_
    return value if value < max_ else max_


def is_emoji_equal(
    partial_emoji: discord.PartialEmoji,
    emoji: Union[str, discord.Emoji, discord.PartialEmoji],
):
    """
    Utility to compare a partial emoji with any other kind of emoji
    """
    if isinstance(emoji, discord.PartialEmoji):
        return partial_emoji == emoji

    if isinstance(emoji, discord.Emoji):
        if partial_emoji.is_unicode_emoji():
            return False

        return emoji.id == partial_emoji.id

    return str(partial_emoji) == emoji


def format_discord_link(link: str, guild_id: int):
    """
    Format a discord link to a channel or message
    """
    link = link.lstrip("<").rstrip(">").rstrip("/")

    for prefix in (
        f"https://discord.com/channels/{guild_id}/",
        f"https://www.discord.com/channels/{guild_id}/",
    ):
        if link.startswith(prefix):
            link = link[len(prefix) :]

    return link


def progress_bar(
    pct: float, full_bar: str = "█", empty_bar: str = "░", divisions: int = 10
):
    """
    A simple horizontal progress bar generator.
    """
    pct = 0 if pct < 0 else 1 if pct > 1 else pct
    return full_bar * (int(divisions * pct)) + empty_bar * (
        divisions - int(divisions * pct)
    )


TIME_UNITS = (
    ("w", "weeks", 604800),
    ("d", "days", 86400),
    ("h", "hours", 3600),
    ("m", "minutes", 60),
    ("s", "seconds", 1),
    ("ms", "miliseconds", 1e-03),
    ("\u03bcs", "microseconds", 1e-06),
    ("ns", "nanoseconds", 1e-09),
)


def format_time_by_units(
    dt: Union[datetime.timedelta, int, float],
    decimal_places: int = 4,
    value_unit_space: bool = True,
    full_unit_names: bool = False,
    multi_units: bool = False,
    whole_units: bool = True,
    fract_units: bool = True,
):
    """Format the given relative time in seconds into a string of whole and/or
    fractional time unit(s). The time units range from nanoseconds to weeks.


    Args:
        dt (Union[datetime.timedelta, int, float]): The relative input time in seconds.
        decimal_places (int, optional): The decimal places to be used in the formatted output
          time. Only applies when `multi_units` is `False`. Defaults to 4.
        value_unit_space (bool, optional): Whether to add a whitespace character before the name
          of a time unit. Defaults to True.
        full_unit_names (bool, optional): Use full unit names (like 'week' instead of 'w').
          Defaults to False.
        multi_units (bool, optional): Whether the formatted output string should use multiple
          units in descending order to divide up the input time. Defaults to False.
        whole_units (bool, optional): Whether whole units above or equal to one should be
          used as units. Defaults to True.
        fractional_units (bool, optional): Whether fractional units less than or equal to one
          should be used as units. Defaults to True.

    Returns:
        str: The formatted time string.

    Raises:
        ValueError: `dt` was not positive.
    """

    if isinstance(dt, datetime.timedelta):
        dt = dt.total_seconds()

    if dt < 0:
        raise ValueError("argument 'seconds' must be a positive number")

    name_idx = 1 if full_unit_names else 0
    space = " " if value_unit_space else ""

    if multi_units:
        result: list[str] = []
        start_idx = 0
        stop_idx = 7

        if whole_units and not fract_units:
            start_idx = 0
            stop_idx = 4

        elif not whole_units and fract_units:
            start_idx = 4
            stop_idx = 7

        elif not whole_units and not fract_units:
            raise ValueError(
                "the arguments 'whole_units' and 'fract_units' cannot both be False"
            )

        for i in range(start_idx, stop_idx + 1):
            unit_tuple = TIME_UNITS[i]
            name = unit_tuple[name_idx]
            unit_value = unit_tuple[2]

            value = dt // unit_value
            if value or (not result and unit_value == 1):
                dt -= value * unit_value
                if full_unit_names and value == 1:
                    name = name[:-1]
                result.append(f"{value}{space}{name}")

        return join_readable(result)

    else:
        for unit_tuple in TIME_UNITS:
            name = unit_tuple[name_idx]
            unit_value = unit_tuple[2]
            if dt >= unit_value:
                return f"{dt / unit_value:.0{decimal_places}f}{space}{name}"


STORAGE_UNITS = (
    ("GB", "gigabytes", 1_000_000_000),
    ("MB", "megabytes", 1_000_000),
    ("KB", "kilobytes", 1_000),
    ("B", "bytes", 1),
)

BASE_2_STORAGE_UNITS = (
    ("GiB", "gibibytes", 1073741824),
    ("MiB", "mebibytes", 1048576),
    ("KiB", "kibibytes", 1024),
    ("B", "bytes", 1),
)


def format_byte(
    size: int,
    decimal_places: Optional[int] = None,
    full_unit_names: bool = False,
    base_2_units: bool = False,
):
    """Format the given storage size in bytes into a string denoting
    the storage size with an equal or larger size unit. The units
    range from bytes to gigabytes.

    Args:
        size (int): THe storage size in bytes.
        decimal_places (Optional[int], optional): The exact decimal places to display in the
          formatting output. If omitted, the Python `float` class's string version
          will be used to automatically choose the needed decimal places.
          Defaults to None.
        full_unit_names (bool, optional): Use full unit names (like 'gigabyte'
          instead of 'GB'). Defaults to False.
        base_2_units (bool, optional): Whether powers of 2 should be used as size units.
          Defaults to False.

    Returns:
        str: The formatted storage size string.
    """

    name_idx = 1 if full_unit_names else 0

    units = BASE_2_STORAGE_UNITS if base_2_units else STORAGE_UNITS

    for unit_tuple in units:
        name = unit_tuple[name_idx]
        unit_value = unit_tuple[2]
        if size >= unit_value:
            if decimal_places is None:
                return f"{size / unit_value} {name}"
            else:
                return f"{size / unit_value:.0{decimal_places}f} {name}"


def split_long_message(message: str, limit: int = 2000):
    """
    Splits message string by 2000 characters with safe newline splitting
    """
    split_output: list[str] = []
    lines = message.split("\n")
    temp = ""

    for line in lines:
        if len(temp) + len(line) + 1 > limit:
            split_output.append(temp[:-1])
            temp = line + "\n"
        else:
            temp += line + "\n"

    if temp:
        split_output.append(temp)

    return split_output


def format_code_exception(exc, pops: int = 1):
    """
    Provide a formatted exception for code snippets
    """
    tbs = traceback.format_exception(type(exc), exc, exc.__traceback__)
    # Pop out the first entry in the traceback, because that's
    # this function call itself

    if len(tbs) >= pops + 1:
        for _ in range(pops):
            tbs.pop(1)

    ret = "".join(tbs).replace(os.getcwd(), "Bot")
    if platform.system() == "Windows":
        # Hide path to python on windows
        ret = ret.replace(os.path.dirname(sys.executable), "Python")

    return ret


def extract_markdown_mention_id(markdown_mention: str) -> int:
    """Extract the id '123456789696969' from a Discord role, user or channel markdown
    mention string with the structures '<@{6969...}>', '<@!{6969...}>', '<@&{6969...}>'
    or '<#{6969...}>'.
    Does not validate for the existence of those ids.

    Args:
        markdown_mention (str): The mention string.

    Returns:
        int: The extracted integer id.

    Raises:
        ValueError: Invalid Discord markdown mention string.
    """

    men_pattern = r"\<((\@[&!]?)|\#){1}[0-9]+\>"
    id_pattern = r"[0-9]+"

    match = re.match(men_pattern, markdown_mention)
    if match is None:
        raise ValueError(
            "invalid Discord markdown mention string: Must be a guild role, channel "
            "or user mention"
        )

    id_str = markdown_mention[slice(*re.search(id_pattern, markdown_mention).span())]

    return int(id_str)


def is_markdown_mention(string: str) -> bool:
    """Whether the given input string matches one of the structures of a valid Discord
    markdown mention string which are '<@{6969...}>', '<@!{6969...}>', '<@&{6969...}>'
    or '<#{6969...}>'.
    Does not validate for the actual existence of the mention targets.

    Args:
        string (str): The string to check for.

    Returns:
        bool: True/False
    """
    return bool(re.match(r"\<((\@[&!]?)|\#){1}[0-9]+\>", string))


def extract_markdown_custom_emoji_id(markdown_emoji: str) -> int:
    """
    Extract the id '123456789696969' from a Discord markdown custom emoji string with
    the structure '<:custom_emoji:123456789696969>'. Also includes animated emojis.
    Does not validate for the existence of the ids.

    Args:
        markdown_emoji (str): The markdown custom emoji string.

    Returns:
        int: The extracted integer id.

    Raises:
        ValueError: Invalid Discord markdown custom emoji string.
    """

    emoji_pattern = r"<a?\:\S+\:[0-9]+\>"
    id_pattern = r"[0-9]+"

    match = re.match(emoji_pattern, markdown_emoji)
    if match is None:
        raise ValueError(
            "invalid Discord markdown custom emoji string: Must have the structure "
            "'<[a]:emoji_name:emoji_id>'"
        )

    id_str = markdown_emoji[slice(*re.search(id_pattern, markdown_emoji).span())]
    return int(id_str)


def is_markdown_custom_emoji(string: str) -> bool:
    """
    Whether the given string matches the structure of a custom Discord markdown emoji
    string with the structure '<:custom_emoji:123456789696969>'. Also includes animated
    emojis.
    Does not validate for the existence of the specified emoji markdown.

    Args:
        string (str): The string to check for.

    Returns:
        bool: True/False
    """
    return bool(re.match(r"<a?\:\S+\:[0-9]+\>", string))


def is_emoji_shortcode(string: str) -> bool:
    """Whether the given string matches the structure of an emoji shortcode,
    which is ':{unicode_characters}:'. No whitespace is allowed.
    Does not validate for the existence of the emoji shortcodes on Discord.

    Args:
        string (str): The string to check for.

    Returns:
        bool: True/False
    """
    return bool(re.match(r"\:\S+\:", string))


def extract_markdown_timestamp(markdown_timestamp: str) -> int:
    """Extract the UNIX timestamp '123456789696969' from a Discord markdown
    timestamp string with the structure '<t:{6969...}>' or
    '<t:{6969...}[:t|T|d|D|f|F|R]>'.
    Does not check the extracted timestamps for validity.

    Args:
        markdown_timestamp (str): The markdown timestamp string.

    Returns:
        int: The extracted UNIX timestamp.

    Raises:
        ValueError: Invalid Discord markdown timestamp string.
    """

    ts_md_pattern = r"\<t\:-?[0-9]+(\:[tTdDfFR])?\>"
    ts_pattern = r"-?[0-9]+"

    match = re.match(ts_md_pattern, markdown_timestamp)
    if match is None:
        raise ValueError("invalid Discord markdown timestamp string")

    return int(
        markdown_timestamp[slice(*re.search(ts_pattern, markdown_timestamp).span())]
    )


def is_markdown_timestamp(string: str) -> int:
    """Whether the given string matches the structure of a Discord markdown timestamp
    string with the structure '<t:{6969...}>' or '<t:{6969...}[:t|T|d|D|f|F|R]>'.
    Does not check timestamps for validity.

    Args:
        string (str): The string to check for.

    Returns:
        bool: True/False

    Raises:
        ValueError: Invalid Discord markdown timestamp string.
    """

    return bool(re.match(r"\<t\:-?[0-9]+(\:[tTdDfFR])?\>", string))


def code_block(string: str, max_characters: int = 2048, code_type: str = "") -> str:
    """
    Formats text into discord code blocks
    """
    string = string.replace("```", "\u200b`\u200b`\u200b`\u200b")
    len_ticks = 7 + len(code_type)

    if len(string) > max_characters - len_ticks:
        return f"```{code_type}\n{string[:max_characters - len_ticks - 4]} ...```"
    else:
        return f"```{code_type}\n{string}```"


def have_permissions_in_channels(
    members_or_roles: Union[
        discord.Member, discord.Role, Sequence[Union[discord.Member, discord.Role]]
    ],
    channels: Union[discord.abc.GuildChannel, Sequence[discord.abc.GuildChannel]],
    *permissions: str,
    member_role_bool_func: Callable[[Iterable[bool]], bool] = all,
    permission_bool_func: Callable[[Iterable[bool]], bool] = all,
    channel_bool_func: Callable[[Iterable[bool]], bool] = all,
) -> bool:
    """Checks if the given permission(s) apply to the given member(s) or role in the
    given Discord channel(s) and returns a boolean value. This function allows you
    to evaluate this kind of query: Does ... of the given member(s) or role(s) have ...
    of the given permissions in ... of the given channels?

    Args:
        members_or_roles (Union[
            discord.Member, discord.Role, Sequence[Union[discord.Member, discord.Role]]
        ]):
          The target Discord member(s) or role(s).
        channels (Union[discord.abc.GuildChannel, Sequence[discord.abc.GuildChannel]]):
          The target guild channel(s) to check permissions on.
        *permissions (str): The lowercase attribute name(s) to check for
          the `discord.Permissions` data class, which represent the different available
          permissions.
        member_role_bool_func (Callable[[Iterable[bool]], bool], optional): A function
          that takes in the result of `channel_bool_func()` for every of the given
          role(s) or member(s) as an iterable and returns a boolean value. Defaults to
          the built-in `all()` function.
        permission_bool_func (Callable[[Iterable[bool]], bool], optional): A function
          that takes in an iterable of the boolean values for every permission
          and returns a boolean value. Defaults to the built-in `all()` function.
        channel_bool_func (Callable[[Iterable[bool]], bool], optional): A function
          that takes in the result of `permission_bool_func()` for every of the given
          channel(s) as an iterable and returns a boolean value. Defaults to
          the built-in `all()` function.

    Returns:
        bool: True/False
    """

    if isinstance(channels, discord.abc.Messageable):
        channels = (channels,)

    if isinstance(members_or_roles, (discord.Member, discord.Role)):
        members_or_roles = (members_or_roles,)

    return member_role_bool_func(
        channel_bool_func(
            permission_bool_func(
                getattr(channel_perms, perm_name) for perm_name in permissions
            )
            for channel_perms in (ch.permissions_for(m_or_r) for ch in channels)
        )
        for m_or_r in members_or_roles
    )


def create_markdown_timestamp(
    dt: Union[int, float, datetime.datetime], tformat: str = "f"
) -> str:
    """
    Get a discord timestamp formatted string that renders it correctly on the
    discord end. dt can be UNIX timestamp or datetime object while tformat
    can be one of:
    "f" (default) short datetime
    "F" long datetime
    "t" short time
    "T" long time
    "d" short date
    "D" long date
    "R" relative time (does not have much precision)
    """
    if isinstance(dt, datetime.datetime):
        dt = dt.replace(tzinfo=datetime.timezone.utc).timestamp()
    return f"<t:{int(dt)}:{tformat}>"


def recursive_dict_compare(
    source_dict: dict,
    target_dict: dict,
    compare_func: Optional[Callable[[Any, Any], bool]] = None,
    ignore_keys_missing_in_source: bool = False,
    ignore_keys_missing_in_target: bool = False,
    _final_bool: bool = True,
):
    """
    Compare the key and values of one dictionary with those of another,
    But recursively do the same for dictionary values that are dictionaries as well.
    based on the answers in
    https://stackoverflow.com/questions/3232943/update-value-of-a-nested-dictionary-of-varying-depth
    """

    if compare_func is None:
        compare_func = lambda d1, d2: d1 == d2

    if not ignore_keys_missing_in_source and (target_dict.keys() >= source_dict.keys()):
        return False

    for k, v in source_dict.items():
        if isinstance(v, dict) and isinstance(target_dict.get(k, None), dict):
            _final_bool = recursive_dict_compare(
                target_dict[k],
                v,
                compare_func=compare_func,
                ignore_keys_missing_in_source=ignore_keys_missing_in_source,
                ignore_keys_missing_in_target=ignore_keys_missing_in_target,
                _final_bool=_final_bool,
            )
            if not _final_bool:
                return False
        else:
            if k not in target_dict:
                if ignore_keys_missing_in_target:
                    continue
                _final_bool = False
            else:
                _final_bool = compare_func(v, target_dict[k])
                if not _final_bool:
                    return False

    return _final_bool


def recursive_dict_update(
    old_dict: dict,
    update_dict: dict,
    add_new_keys: bool = True,
    skip_value: Union[str, _UnsetType] = UNSET,
):
    """
    Update one dictionary with another, similar to dict.update(),
    But recursively update dictionary values that are dictionaries as well.
    based on the answers in
    https://stackoverflow.com/questions/3232943/update-value-of-a-nested-dictionary-of-varying-depth
    """
    for k, v in update_dict.items():
        if isinstance(v, dict):
            new_value = recursive_dict_update(
                old_dict.get(k, {}), v, add_new_keys=add_new_keys, skip_value=skip_value
            )
            if new_value != skip_value:
                if k not in old_dict:
                    if not add_new_keys:
                        continue
                old_dict[k] = new_value

        elif v != skip_value:
            if k not in old_dict:
                if not add_new_keys:
                    continue
            old_dict[k] = v

    return old_dict


def recursive_dict_delete(
    old_dict: dict,
    update_dict: dict,
    skip_value: Union[str, _UnsetType] = UNSET,
    inverse: bool = False,
):
    """
    Delete dictionary attributes present in another,
    But recursively do the same dictionary values that are dictionaries as well.
    based on the answers in
    https://stackoverflow.com/questions/3232943/update-value-of-a-nested-dictionary-of-varying-depth
    """
    if inverse:
        for k, v in tuple(old_dict.items()):
            if isinstance(v, dict):
                lower_update_dict = None
                if isinstance(update_dict, dict):
                    lower_update_dict = update_dict.get(k, {})

                new_value = recursive_dict_delete(
                    v, lower_update_dict, skip_value=skip_value, inverse=inverse
                )
                if (
                    new_value != skip_value
                    and isinstance(update_dict, dict)
                    and k not in update_dict
                ):
                    old_dict[k] = new_value
                    if not new_value:
                        del old_dict[k]
            elif (
                v != skip_value
                and isinstance(update_dict, dict)
                and k not in update_dict
            ):
                del old_dict[k]
    else:
        for k, v in update_dict.items():
            if isinstance(v, dict):
                new_value = recursive_dict_delete(
                    old_dict.get(k, {}), v, skip_value=skip_value
                )
                if new_value != skip_value and k in old_dict:
                    old_dict[k] = new_value
                    if not new_value:
                        del old_dict[k]

            elif v != skip_value and k in old_dict:
                del old_dict[k]
    return old_dict


def chainmap_getitem(map: ChainMap, key: Any):
    """A better approach to looking up from
    ChainMap objects, by treating inner
    defaultdict maps as a rare special case.
    Args:
        map (ChainMap): The ChainMap.
        key (Any): The key.
    Returns:
        object: The lookup result.
    Raises:
        KeyError: key not found.
    """
    for mapping in map.maps:
        if not isinstance(mapping, defaultdict):
            if key in mapping:
                return mapping[key]
            continue

        try:
            return mapping[key]  # can't use 'key in mapping' with defaultdict
        except KeyError:
            pass
    return map.__missing__(key)


def class_getattr_unique(
    cls: type,
    name: str,
    filter_func: Callable[[Any], bool] = lambda obj: True,
    check_dicts_only: bool = False,
    _id_set=None,
) -> list[Any]:
    values = []
    value_obj = UNSET

    if _id_set is None:
        _id_set = set()

    if check_dicts_only:
        if name in cls.__dict__:
            value_obj = cls.__dict__[name]
    else:
        if hasattr(cls, name):
            value_obj = getattr(cls, name)

    if (
        value_obj is not UNSET
        and id(value_obj) not in _id_set
        and filter_func(value_obj)
    ):
        values.append(value_obj)
        _id_set.add(id(value_obj))

    for base_cls in cls.__mro__[1:]:
        values.extend(
            class_getattr_unique(
                base_cls,
                name,
                filter_func=filter_func,
                check_dicts_only=check_dicts_only,
                _id_set=_id_set,
            )
        )
    return values


def class_getattr(
    cls: type,
    name: str,
    default: Any = UNSET,
    /,
    filter_func: Callable[[Any], bool] = lambda obj: True,
    check_dicts_only: bool = False,
    _is_top_lvl=True,
):
    value_obj = UNSET
    if check_dicts_only:
        if name in cls.__dict__:
            value_obj = cls.__dict__[name]
    else:
        if hasattr(cls, name):
            value_obj = getattr(cls, name)

    if value_obj is not UNSET and filter_func(value_obj):
        return value_obj

    for base_cls in cls.__mro__[1:]:
        value_obj = class_getattr(
            base_cls, name, check_dicts_only=check_dicts_only, _is_top_lvl=False
        )
        if value_obj is not UNSET:
            return value_obj

    if default is UNSET:
        if not _is_top_lvl:
            return UNSET
        raise AttributeError(
            f"could not find the attribute '{name}' in the __mro__ hierarchy of class "
            f"'{cls.__name__}'"
        ) from None

    return default
