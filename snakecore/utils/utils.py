"""
This file is a part of the source code for the PygameCommunityBot.
This project has been licensed under the MIT license.
Copyright (c) 2020-present PygameCommunityDiscord

This file defines some important utility functions.
"""

from __future__ import annotations

import asyncio
import datetime
import os
import platform
import sys
import traceback
from typing import Callable, Iterable, Union, Optional

import discord
import pygame

import snakecore

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


def format_time(
    seconds: float,
    decimal_places: int = 4,
    unit_data: tuple[tuple[float, str], ...] = (
        (1.0, "s"),
        (1e-03, "ms"),
        (1e-06, "\u03bcs"),
        (1e-09, "ns"),
        (1e-12, "ps"),
        (1e-15, "fs"),
        (1e-18, "as"),
        (1e-21, "zs"),
        (1e-24, "ys"),
    ),
):
    """
    Formats time with a prefix
    """
    for fractions, unit in unit_data:
        if seconds >= fractions:
            return f"{seconds / fractions:.0{decimal_places}f} {unit}"
    return "very fast"


def format_long_time(
    seconds: int,
    unit_data: tuple[tuple[str, int], ...] = (
        ("weeks", 604800),
        ("days", 86400),
        ("hours", 3600),
        ("minutes", 60),
        ("seconds", 1),
    ),
):
    """
    Formats time into string, which is of the order of a few days
    """
    result: list[str] = []

    for name, count in unit_data:
        value = seconds // count
        if value or (not result and count == 1):
            seconds -= value * count
            if value == 1:
                name = name[:-1]
            result.append(f"{value} {name}")

    return join_readable(result)


def format_timedelta(tdelta: datetime.timedelta):
    """
    Formats timedelta object into human readable time
    """
    return format_long_time(int(tdelta.total_seconds()))


def format_byte(size: int, decimal_places: int = 3):
    """
    Formats a given size and outputs a string equivalent to B, KB, MB, or GB
    """
    if size < 1e03:
        return f"{round(size, decimal_places)} B"
    if size < 1e06:
        return f"{round(size / 1e3, decimal_places)} KB"
    if size < 1e09:
        return f"{round(size / 1e6, decimal_places)} MB"

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


def filter_id(mention: str):
    """
    Filters mention to get ID "<@!6969>" to "6969"
    Note that this function can error with ValueError on the int call, so the
    caller of this function must take care of that.
    """
    for char in ("<", ">", "@", "&", "#", "!", " "):
        mention = mention.replace(char, "")

    return int(mention)


def filter_emoji_id(name: str):
    """
    Filter emoji name to get "837402289709907978" from
    "<:pg_think:837402289709907978>"
    Note that this function can error with ValueError on the int call, in which
    case it returns the input string (no exception is raised)

    Args:
        name (str): The emoji name

    Returns:
        str|int: The emoji id or the input string if it could not convert it to
        an int.
    """

    pattern = r"<.*\:.+\:[0-9]+\>"

    try:
        return int(name)
    except ValueError:
        return name


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


def format_datetime(dt: Union[int, float, datetime.datetime], tformat: str = "f"):
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


def split_wc_scores(scores: dict[int, int]):
    """
    Split wc scoreboard into different categories
    """
    scores_list = [(score, f"<@!{mem}>") for mem, score in scores.items()]
    scores_list.sort(reverse=True)

    for title, category_score in common.WC_SCORING:
        category_list = list(filter(lambda x: x[0] >= category_score, scores_list))
        if not category_list:
            continue

        desc = ">>> " + "\n".join(
            (f"`{score}` **•** {mem} :medal:" for score, mem in category_list)
        )

        yield title, desc, False
        scores_list = scores_list[len(category_list) :]


async def give_wc_roles(member: discord.Member, score: int):
    """
    Updates the WC roles of a member based on their latest total score
    """
    got_role: bool = False
    for min_score, role_id in common.ServerConstants.WC_ROLES:
        if score >= min_score and not got_role:
            # This is the role to give
            got_role = True
            if role_id not in map(lambda x: x.id, member.roles):
                await member.add_roles(
                    discord.Object(role_id),
                    reason="Automatic bot action, adds WC event roles",
                )

        else:
            # any other event related role to be removed
            if role_id in map(lambda x: x.id, member.roles):
                await member.remove_roles(
                    discord.Object(role_id),
                    reason="Automatic bot action, removes older WC event roles",
                )
