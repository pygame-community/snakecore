"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2020-present PygameCommunityDiscord

This file defines some important utility functions.
"""

import datetime
import fractions
import os
import platform
import re
import sys
import traceback
from typing import Callable, Iterable, Union

import discord


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


UNIT_DATA = (
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
    seconds: float,
    decimal_places: int = 4,
    long_unit_names: bool = False,
    multi_units: bool = False,
    whole_units: bool = True,
    fract_units: bool = True,
):
    """_summary_

    Args:
        seconds: _description_
        decimal_places: _description_. Defaults to 4.
        long_unit_names: _description_. Defaults to False.
        multi_units: _description_. Defaults to False.
        whole_units: _description_. Defaults to True.
        fractional_units: _description_. Defaults to True.

    Returns:
        str: The formatted time string.

    Raises:
        ValueError: 'seconds' was not positive.
    """

    if seconds < 0:
        raise ValueError("argument 'seconds' must be a positive number")

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

        elif whole_units and fract_units:
            pass


        for name, count in unit_data:
            value = seconds // count
            if value or (not result and count == 1):
                seconds -= value * count
                if value == 1:
                    name = name[:-1]
                result.append(f"{value} {name}")

        return join_readable(result)

    else:
        for unit, fractions in unit_data:
            if seconds >= fractions:
                return f"{seconds / fractions:.0{decimal_places}f} {unit}"

        return f"{seconds/1e-09:.0{decimal_places}f} ns"


def format_time_by_long_units(
    seconds: float,
    decimal_places: int = 4,
    multi_units: bool = False,
    unit_data: tuple[tuple[float, str], ...] = (
        ("weeks", 604800)
        ("days", 86400),
        ("hours", 3600),
        ("minutes", 60),
        ("seconds", 1),
        ("miliseconds", 1e-03),
        ("microseconds", 1e-06),
        ("nanoseconds", 1e-09),
    ),
):
    """_summary_

    Args:
        seconds: _description_
        decimal_places: _description_. Defaults to 4.
        multi_units: _description_. Defaults to False.
        unit_data: _description_. Defaults to ( ("w", 604800) ("d", 86400), ("h", 3600), ("m", 60), ("s", 1), ("ms", 1e-03), ("\u03bcs", 1e-06), ("ns", 1e-09), ).
    """


def format_timedelta(tdelta: datetime.timedelta):
    """
    Formats timedelta object into human readable time
    """
    return format_long_time(int(tdelta.total_seconds()))


def format_byte(size: int, decimal_places: int = 3):
    """
    Formats a given size and outputs a string equivalent to B, KB, MB, or GB
    """
    fact = 1
    for unit in ("B", "KB", "MB"):
        if size < fact * 1000:
            return f"{size/fact:.0{decimal_places}f} {unit}"

        fact *= 1000

    return f"{round(size / 1e9, decimal_places)} GB"


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


def format_code_exception(e, pops: int = 1):
    """
    Provide a formatted exception for code snippets
    """
    tbs = traceback.format_exception(type(e), e, e.__traceback__)
    # Pop out the first entry in the traceback, because that's
    # this function call itself
    for _ in range(pops):
        tbs.pop(1)

    ret = "".join(tbs).replace(os.getcwd(), "PgBot")
    if platform.system() == "Windows":
        # Hide path to python on windows
        ret = ret.replace(os.path.dirname(sys.executable), "Python")

    return ret


def extract_mention_id(mention: str) -> int:
    """Extract the id '123456789696969' from a Discord role, user or channel mention
    markdown string with the structures '<@{6969...}>', '<@!{6969...}>',
    '<@!{6969...}>' or '<#{6969...}>'.
    Does not validate for the existence of those ids.

    Args:
        mention (str): The mention string.

    Returns:
        int: The extracted integer id.

    Raises:
        ValueError: Invalid mention string.
    """

    men_pattern = r"\<((\@[&!]?)|\#){1}[0-9]+\>"
    id_pattern = r"[0-9]+"

    match = re.match(men_pattern, mention)
    if match is None:
        raise ValueError(
            "invalid Discord mention string: Must be a guild role, channel or user mention"
        )

    id_str = mention[slice(*re.search(id_pattern, mention).span())]

    return int(id_str)


def is_valid_mention(mention: str) -> bool:
    """Whether the given input string matches one of the structures of a valid Discord
    mention markdown string which are '<@{6969...}>', '<@!{6969...}>',
    '<@&{6969...}>' or '<#{6969...}>'.
    Does not validate for the actual existence of the mention targets.

    Args:
        mention (str): The mention string.

    Returns:
        bool: True/False
    """
    return bool(re.match(r"\<((\@[&!]?)|\#){1}[0-9]+\>", mention))


def is_emoji_code(emoji_code: str) -> bool:
    """Whether the given string matches the structure of an emoji code,
    which is ':{unicode_characters}:'. No whitespace is allowed.
    Does not validate for the existence of the emoji codes
    of the input strings.

    Args:
        emoji_code (str): The emoji code string.

    Returns:
        bool: True/False
    """
    return bool(re.match(r"\:\S+\:", emoji_code))


def extract_custom_emoji_id(emoji_markdown: str) -> int:
    """
    Extract the id '123456789696969' from a custom Discord emoji markdown string with
    the structure '<:custom_emoji:123456789696969>'. Also includes animated emojis.
    Does not validate for the existence of the ids.

    Args:
        emoji_markdown (str): The emoji markdown string.

    Returns:
        int: The extracted integer id.

    Raises:
        ValueError: Invalid emoji markdown string.
    """

    emoji_pattern = r"<a?\:\S+\:[0-9]+\>"
    id_pattern = r"[0-9]+"

    match = re.match(emoji_pattern, emoji_markdown)
    if match is None:
        raise ValueError(
            "invalid emoji markdown string: Must have the structure '<[a]:emoji_name:emoji_id>'"
        )

    id_str = emoji_markdown[slice(*re.search(id_pattern, emoji_markdown).span())]
    return int(id_str)


def is_valid_custom_emoji(emoji_markdown: str) -> bool:
    """
    Whether the given string matches the structure for a custom Discord emoji markdown
    string with the structure '<:custom_emoji:123456789696969>'. Also includes animated
    emojis.
    Does not validate for the existence of the specified emoji markdown.

    Args:
        emoji_markdown (str): The emoji markdown string.

    Returns:
        bool: True/False
    """
    return bool(re.match(r"<a?\:\S+\:[0-9]+\>", emoji_markdown))


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


def check_channel_permissions(
    member: Union[discord.Member, discord.User],
    channel: discord.abc.GuildChannel,
    bool_func: Callable[[Iterable], bool] = all,
    permissions: Iterable[str] = (
        "view_channel",
        "send_messages",
    ),
) -> bool:

    """
    Checks if the given permissions apply to the given member in the given channel.
    """

    channel_perms = channel.permissions_for(member)
    return bool_func(getattr(channel_perms, perm_name) for perm_name in permissions)


def check_channels_permissions(
    member: Union[discord.Member, discord.User],
    *channels: discord.abc.GuildChannel,
    bool_func: Callable[[Iterable], bool] = all,
    skip_invalid_channels: bool = False,
    permissions: Iterable[str] = (
        "view_channel",
        "send_messages",
    ),
) -> tuple[bool, ...]:

    """
    Checks if the given permissions apply to the given member in the given channels.
    """

    if skip_invalid_channels:
        booleans = tuple(
            bool_func(getattr(channel_perms, perm_name) for perm_name in permissions)
            for channel_perms in (
                channel.permissions_for(member)
                for channel in channels
                if isinstance(channel, discord.TextChannel)
            )
        )
    else:
        booleans = tuple(
            bool_func(getattr(channel_perms, perm_name) for perm_name in permissions)
            for channel_perms in (
                channel.permissions_for(member) for channel in channels
            )
        )
    return booleans


def create_timestamp_markdown(dt: Union[int, float, datetime.datetime], tformat: str = "f"):
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
