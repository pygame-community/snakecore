"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file implements snakecore's custom command parser.
"""

from __future__ import annotations
import datetime
import inspect
import re

import discord
from discord.ext import commands

from typing import Any, Optional, Union

import snakecore

# mapping of all escape characters to their escaped values
ESCAPES = {
    "0": "\0",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "b": "\b",
    "f": "\f",
    "\\": "\\",
    '"': '"',
    "'": "'",
    "`": "`",
}


# declare a dict of anno names, and the respective messages to give on error
ANNO_AND_ERROR = {
    "str": "a bare, unquoted character string",
    "CodeBlock": "a codeblock, code surrounded in 1 or 3 backticks",
    "String": 'a string, surrounded in double quotes (`""`)',
    "datetime.datetime": (
        "a string, that denotes a UNIX timestamp in the format "
        "`YYYY-MM-DD[*HH[:MM[:SS[.fff[fff]]]][+HH:MM[:SS[.ffffff]]]]`, or as a formatted "
        "Discord timestamp `<t:{6969...}[:t|T|d|D|f|F|R]>`"
    ),
    "bool": (
        "any of these bare character strings to represent a boolean value:"
        " `1, y, yes, t, true, 0, n, no, f, false`"
    ),
    "range": (
        "a range specifier with syntax `[start:stop[:step]]` (`step` is optional). "
        "See Python's `range` object for more details."
    ),
    "discord.Color": "a color, represented by a hex RGB value or a CSS color representation",
    "discord.Object": "a generic Discord Object with an ID",
    "discord.Role": "an ID or mention of a Discord server role",
    "discord.Member": "an ID or mention of a Discord server member",
    "discord.User": "an ID or mention of a Discord user",
    "discord.TextChannel": "an ID or mention of a Discord server text channel",
    "discord.VoiceChannel": "an ID or mention of a Discord server voice channel",
    "discord.StageChannel": "an ID or mention of a Discord server stage channel",
    "discord.ForumChannel": "an ID or mention of a Discord server forum channel",
    "discord.Thread": "an ID or mention of a Discord server thread",
    "discord.Guild": "an ID of a discord server (A.K.A. 'guild')",
    "discord.Message": (
        "a message ID, or a 'channel_id/message_id' combo, or a [link](#) to a message"
    ),
    "discord.PartialMessage": (
        "a message ID, or a 'channel_id/message_id' combo, or a [link](#) to a message"
    ),
}

ANNO_AND_ERROR["datetime"] = ANNO_AND_ERROR["datetime.datetime"]
ANNO_AND_ERROR["discord.colour.Color"] = ANNO_AND_ERROR[
    "discord.colour.Colour"
] = ANNO_AND_ERROR["discord.Color"]
ANNO_AND_ERROR["discord.object.Object"] = ANNO_AND_ERROR["discord.Object"]
ANNO_AND_ERROR["discord.member.Member"] = ANNO_AND_ERROR["discord.Member"]
ANNO_AND_ERROR["discord.user.User"] = ANNO_AND_ERROR["discord.User"]
ANNO_AND_ERROR["discord.channel.TextChannel"] = ANNO_AND_ERROR["discord.TextChannel"]
ANNO_AND_ERROR["discord.channel.VoiceChannel"] = ANNO_AND_ERROR["discord.VoiceChannel"]
ANNO_AND_ERROR["discord.channel.StageChannel"] = ANNO_AND_ERROR["discord.StageChannel"]
ANNO_AND_ERROR["discord.channel.ForumChannel"] = ANNO_AND_ERROR["discord.ForumChannel"]
ANNO_AND_ERROR["discord.threads.Thread"] = ANNO_AND_ERROR["discord.Thread"]
ANNO_AND_ERROR["discord.guild.Guild"] = ANNO_AND_ERROR["discord.Guild"]
ANNO_AND_ERROR["discord.message.Message"] = ANNO_AND_ERROR["discord.Message"]
ANNO_AND_ERROR["discord.message.PartialMessage"] = ANNO_AND_ERROR[
    "discord.PartialMessage"
]


class ParsingError(commands.BadArgument):
    """Base class for all parsing-related exceptions"""

    pass


class ArgError(ParsingError):
    """Base class for positional arguments related exceptions"""


class KwargError(ParsingError):
    """Base class for keyword arguments related exceptions"""


class CodeBlock:
    """Base class to represent code blocks in the argument parser.
    Supports the `discord.ext.commands` converter
    protocol and can be used as a converter.
    """

    def __init__(self, text: str, lang: str | None = None) -> None:
        """Initialise codeblock object. The text argument here is the contents of
        the codeblock. If the optional argument lang is specified, it has to be
        the language type of the codeblock, if not provided, it is determined
        from the text argument itself
        """
        self.lang = ""

        if lang is not None:
            self.lang = lang

        elif "\n" in text:
            newline_idx = text.index("\n")
            self.lang = text[:newline_idx].strip().lower()
            text = text[newline_idx + 1 :]

        # because \\ causes problems
        self.code = text.strip().replace("\\`", "`").strip("\\")

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str):
        return cls(argument)


ESCAPES = {
    "0": "\0",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "b": "\b",
    "f": "\f",
    "\\": "\\",
    '"': '"',
    "'": "'",
    "`": "`",
}


class String:
    """Base class to represent strings in the argument parser. On the discord end
    it is a string enclosed in quotes. Supports the `discord.ext.commands` converter
    protocol and can be used as a converter.
    """

    def __init__(self, string: str) -> None:
        self.string = self.escape(string)

    def __bool__(self) -> bool:
        return bool(self.string)

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str):
        s = cls(argument).string

        if (s.startswith('"') and s.endswith('"')) or (
            s.startswith("'") and s.endswith("'")
        ):
            s = s[1:-1]
        return s

    def escape(self, string: str):
        """Convert a "raw" string to one where characters are escaped"""
        cnt = 0
        newstr = ""
        while cnt < len(string):
            char = string[cnt]
            cnt += 1
            if char == "\\":
                # got a backslash, handle escapes
                char = string[cnt]
                cnt += 1
                if char.lower() in ["x", "u"]:  # these are unicode escapes
                    if char.lower() == "x":
                        n = 2
                    else:
                        n = 4 if char == "u" else 8

                    var = string[cnt : cnt + n]
                    try:
                        if len(var) != n:
                            n = len(var)
                            raise commands.BadArgument("invalid quoted string")

                        newstr += chr(int(var, base=16))
                    except (ValueError, OverflowError):
                        esc = string[cnt - 2 : cnt + n]
                        raise commands.BadArgument(
                            "Invalid escape character",
                            f"Invalid unicode escape: `{esc}` in string",
                        )
                    cnt += n

                elif char in ESCAPES:
                    # general escapes
                    newstr += ESCAPES[char]
                else:
                    raise commands.BadArgument(
                        "Invalid escape character",
                        f"Unknown escape `\\{char}`",
                    )
            else:
                newstr += char

        return newstr


SPLIT_FLAGS = (("`", CodeBlock), ('"', String), ("'", String))


def split_anno(anno: str):
    """Helper to split an anno string based on commas, but does not split commas
    within nested annotations. Returns a generator of strings.
    """
    nest_cnt = 0
    prev = 0
    for cnt, char in enumerate(anno):
        if char == "[":
            nest_cnt += 1
        elif char == "]":
            nest_cnt -= 1
        elif char == "," and not nest_cnt:
            ret = anno[prev:cnt].strip()
            prev = cnt + 1
            if ret:
                yield ret

    ret = anno[prev:].strip()
    if ret and not nest_cnt:
        yield ret


def strip_optional_anno(anno: str) -> str:
    """Helper to strip "Optional" anno"""
    anno = anno.strip()
    if anno.startswith("") and anno.endswith(" | None"):
        # call recursively to split "Optional" chains
        return strip_optional_anno(anno[9:-1])

    return anno


def split_union_anno(anno: str):
    """Helper to split a 'Union' annotation. Returns a generator of strings."""
    anno = strip_optional_anno(anno)
    if anno.startswith("") and anno.endswith(""):
        for anno in split_anno(anno[6:-1]):
            # use recursive splits to "flatten" unions
            yield from split_union_anno(anno)
    else:
        yield anno


def split_tuple_anno(anno: str):
    """Helper to split a 'tuple' annotation.
    Returns None if anno is not a valid tuple annotation
    """
    if anno.lower() == "tuple":
        anno = "tuple[Any, ...]"

    if anno.startswith("tuple[") and anno.endswith("]"):
        return list(split_anno(anno[6:-1]))


def get_anno_error(anno: str) -> str:
    """Get error message to display to user when user has passed invalid arg"""
    union_errors = []
    for subanno in split_union_anno(anno):
        tupled = split_tuple_anno(subanno)
        if tupled is None:
            union_errors.append(ANNO_AND_ERROR.get(subanno, f"of type `{subanno}`"))
            continue

        # handle tuple
        if len(tupled) == 2 and tupled[1] == "...":
            # variable length tuple
            union_errors.append(
                f"a tuple, where each element is {get_anno_error(tupled[0])}"
            )

        else:
            ret = "a tuple, where "
            for i, j in enumerate(map(get_anno_error, tupled)):
                ret += f"element at index {i} is {j}; "

            union_errors.append(ret[:-2])  # strip last two chars, which is "; "

    msg = ""
    if len(union_errors) != 1:
        # display error messages of all the union-ed annos
        msg += "either "
        msg += ", or ".join(union_errors[:-1])
        msg += ", or atleast, "

    msg += union_errors[-1]
    return msg


def split_args(split_str: str):
    """Utility function to do the first parsing step to split input string based
    on seperators like code ticks and quotes (strings).
    Returns a generator of Codeblock objects, String objects and str.
    """
    split_state = -1  # indicates parsing state, -1 means "None" parse state
    is_multiline = False  # indicates whether the block being parsed is None or not
    prev = 0  # index of last unparsed character

    for cnt, char in enumerate(split_str):
        if prev > cnt:
            # skipped a few characters, so prev is greater than cnt
            continue

        for state, (matchchar, splitfunc) in enumerate(SPLIT_FLAGS):
            if split_state != -1 and state != split_state:
                # if we are parsing one type of split, ignore all other types
                continue

            if char == "\n" and split_state != -1 and not is_multiline:
                # got newline while parsing non-multiline block
                raise ParsingError(
                    f"Invalid {splitfunc.__name__} formatting!",
                    f"Use triple quotes/ticks for multiline blocks",
                )

            if char == matchchar:
                if cnt and split_str[cnt - 1] == "\\":
                    # got split char, but is escaped, so break
                    break

                old_multiline = is_multiline
                is_multiline = split_str[cnt + 1 : cnt + 3] == 2 * matchchar

                if split_state != -1:
                    if is_multiline and not old_multiline:
                        # got closing triple quote but no opening triple quote
                        is_multiline = False

                    elif old_multiline and not is_multiline:
                        # not a close at all
                        is_multiline = True
                        continue

                ret = split_str[prev:cnt]
                if split_state == -1:
                    # start of new parse state
                    split_state = state
                    if ret:
                        yield ret  # yield any regular string segments

                else:
                    # end of a parse state, yield token and reset state
                    split_state = -1
                    yield splitfunc(ret)

                prev = cnt + 1
                if is_multiline:
                    # the next chars are skipped
                    prev += 2

                break

    if split_state != -1:
        # we were still in a parse state
        name = SPLIT_FLAGS[split_state][1].__name__
        raise ParsingError(
            f"Invalid {name}!",
            f"The {name.lower()} was not properly closed",
        )

    # yield trailing string
    ret = split_str[prev:]
    if ret:
        yield ret


def parse_args(cmd_str: str):
    """Custom parser for handling arguments. This function parses the source
    string of the command into the command name, a list of arguments and a
    dictionary of keyword arguments. Arguments will only contain strings,
    'CodeBlock' objects, 'String' objects and tuples.
    """
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    temp_list: list[Any] | None = None  # used to store the temporary tuple

    kwstart = False  # used to make sure that keyword args come after args
    prevkey = None  # temporarily store previous key name

    def append_arg(arg: Any):
        """Internal helper function to append a parsed argument into arg/kwarg/tuple"""
        nonlocal prevkey
        if temp_list is not None:
            # already in a tuple, flush arg into that
            temp = temp_list
            while temp and isinstance(temp[-1], list):
                temp = temp[-1]

            temp.append(arg)

        elif prevkey is not None:
            # had a keyword, flush arg into keyword
            kwargs[prevkey] = arg
            prevkey = None

        elif kwstart:
            raise KwargError(
                "Keyword arguments cannot come before positional arguments"
            )

        else:
            args.append(arg)

    for arg in split_args(cmd_str):
        if not isinstance(arg, str):
            append_arg(arg)
            continue

        # these string replacements are done to make parsing easier
        # ignore any commas in the source string, just treat them as spaces
        for a, b in (
            (" =", "="),
            (",", " "),
            (")(", ") ("),
            ("=(", "= ("),
        ):
            arg = arg.replace(a, b)

        for substr in arg.split():
            if not substr:
                continue

            splits = substr.split("=")
            if len(splits) == 2:
                # got first keyword, mark a flag so that future arguments are
                # all keywords
                kwstart = True
                if temp_list is not None:
                    # we were parsing a tuple, and got keyword arg
                    raise KwargError("Keyword arguments cannot come inside a tuple")

                # underscores not allowed at start of keyword names here
                if not splits[0][0].isalpha():
                    raise KwargError("Keyword argument must begin with an alphabet")

                if prevkey:
                    # we had a prevkey, and also got a new keyword in the
                    # same iteration
                    raise KwargError("Did not specify argument after '='")

                prevkey = splits[0]
                if not prevkey:
                    # we do not have keyword name
                    raise KwargError("Missing keyword before '=' symbol")

                if splits[1]:
                    # flush kwarg
                    kwargs[prevkey] = splits[1]
                    prevkey = None

            elif len(splits) == 1:
                # current substring is not a keyword (does not have =)
                while substr.startswith("("):
                    # start of a tuple
                    if temp_list is not None:
                        temp = temp_list
                        while temp and isinstance(temp[-1], list):
                            temp = temp[-1]

                        temp.append([])
                    else:
                        temp_list = []

                    substr = substr[1:]
                    if not substr:
                        continue

                oldlen = len(substr)
                substr = substr.rstrip(")")
                count = oldlen - len(substr)
                if substr:
                    append_arg(substr)

                for _ in range(count):
                    # end of a tuple
                    if temp_list is None:
                        raise ArgError("Invalid closing tuple bracket")

                    prevtemp = None
                    temp = temp_list
                    while temp and isinstance(temp[-1], list):
                        prevtemp = temp
                        temp = temp[-1]

                    if prevtemp is None:
                        arg = tuple(temp)
                        temp_list = None
                        append_arg(arg)
                    else:
                        prevtemp[-1] = tuple(temp)
            else:
                raise KwargError("Invalid number of '=' in keyword argument expression")

    if temp_list is not None:
        raise ArgError("Tuple was not closed")

    if prevkey:
        raise KwargError("Did not specify argument after '='")

    # user entered something like 'pg!', display help message
    return args, kwargs


async def cast_basic_arg(
    ctx: commands.Context[commands.Bot | commands.AutoShardedBot],
    anno: str,
    arg: Any,
) -> Any:
    """Helper to cast an argument to the type mentioned by the parameter
    annotation. This casts an argument in its "basic" form, where both argument
    and typehint are "simple", that does not contain stuff like ...,
    tuple[...], etc.
    Raises ValueError on failure to cast arguments
    """
    if isinstance(arg, tuple):
        if len(arg) != 1:
            raise ValueError()

        # got a one element tuple where we expected an arg, handle that element
        arg = arg[0]

    if isinstance(arg, CodeBlock):
        if anno == "CodeBlock":
            return arg
        raise ValueError()

    elif isinstance(arg, String):
        if anno == "String":
            return arg

        elif anno in ["datetime.datetime", "datetime"]:
            return datetime.datetime.fromisoformat(arg.string.removesuffix("Z"))

        raise ValueError()

    elif isinstance(arg, str):
        if anno in ("CodeBlock", "String"):
            raise ValueError()

        elif anno in ("datetime.datetime", "datetime"):
            if not (arg.startswith("<t:") and arg.endswith(">")):
                raise ValueError()

            timestamp = re.search(r"\d+", arg)
            if timestamp is not None:
                timestamp = float(arg[timestamp.start() : timestamp.end()])
                return datetime.datetime.utcfromtimestamp(timestamp).astimezone(
                    datetime.timezone.utc
                )

            raise ValueError()

        elif anno == "str":
            return arg

        elif anno == "bool":
            if arg.lower() not in (
                "1",
                "y",
                "yes",
                "0",
                "n",
                "no",
                "t",
                "true",
                "f",
                "false",
            ):
                raise ValueError()

            return arg.lower() in ("1", "y", "yes", "t", "true")

        elif anno == "int":
            return int(arg)

        elif anno == "float":
            return float(arg)

        elif anno == "range":
            if not arg.startswith("[") or not arg.endswith("]"):
                raise ValueError()

            splits = [int(i.strip()) for i in arg[6:-1].split(":")]

            if splits and len(splits) <= 3:
                return range(*splits)
            raise ValueError()

        elif anno in ("discord.Object", "discord.object.Object"):
            # Generic discord API Object that has an ID
            obj_id = None
            if snakecore.utils.is_markdown_mention(arg):
                obj_id = snakecore.utils.extract_markdown_mention_id(arg)
            else:
                obj_id = int(arg)

            return discord.Object(obj_id)

        elif anno in (
            "discord.Colour",
            "discord.Color",
            "discord.colour.Colour",
            "discord.colour.Color",
        ):
            try:
                return await commands.converter.ColourConverter().convert(ctx, arg)
            except commands.BadArgument as c:
                raise ValueError() from c

        elif anno in ("discord.Role", "discord.role.Role"):
            role_id = None
            if snakecore.utils.is_markdown_mention(arg):
                role_id = snakecore.utils.extract_markdown_mention_id(arg)
            else:
                role_id = int(arg)

            if not ctx.guild:
                raise ValueError()

            role = ctx.guild.get_role(role_id)
            if role is None:
                raise ValueError()
            return role

        elif anno in ("discord.Member", "discord.member.Member"):
            member_id = None
            if snakecore.utils.is_markdown_mention(arg):
                member_id = snakecore.utils.extract_markdown_mention_id(arg)
            else:
                member_id = int(arg)

            if not ctx.guild:
                raise ValueError()

            try:
                return await ctx.guild.fetch_member(member_id)
            except discord.errors.NotFound:
                raise ValueError()

        elif anno in ("discord.User", "discord.user.User"):
            user_id = None
            if snakecore.utils.is_markdown_mention(arg):
                user_id = snakecore.utils.extract_markdown_mention_id(arg)
            else:
                user_id = int(arg)

            try:
                return await snakecore.config.conf.global_client.fetch_user(user_id)
            except discord.errors.NotFound:
                raise ValueError()

        elif anno in (
            "discord.abc.GuildChannel",
            "discord.TextChannel",
            "discord.channel.TextChannel",
            "discord.VoiceChannel",
            "discord.channel.VoiceChannel",
            "discord.StageChannel",
            "discord.channel.StageChannel",
            "discord.ForumChannel",
            "discord.channel.ForumChannel",
            "discord.Thread",
            "discord.threads.Thread",
        ):
            guild = ctx.guild
            ch_id = None
            if snakecore.utils.is_markdown_mention(arg):
                ch_id = snakecore.utils.extract_markdown_mention_id(arg)
            else:
                ch_id = int(
                    snakecore.utils.format_discord_link(
                        arg, guild.id if guild else "@me"
                    )
                )

            chan = ctx.bot.get_channel(ch_id)

            if chan is None:
                try:
                    chan = await ctx.bot.fetch_channel(ch_id)
                except (discord.errors.NotFound, discord.errors.Forbidden):
                    raise ValueError()

            return chan

        elif anno in ("discord.Guild", "discord.guild.Guild"):
            guild_id = int(arg)
            guild = snakecore.config.conf.global_client.get_guild(guild_id)
            if guild is None:
                try:
                    guild = await snakecore.config.conf.global_client.fetch_guild(
                        guild_id
                    )
                except discord.HTTPException:
                    raise ValueError()
            return guild

        elif anno in ("discord.Message", "discord.message.Message"):
            guild = ctx.guild
            formatted = snakecore.utils.format_discord_link(
                arg, guild.id if guild else "@me"
            )

            a, b, c = formatted.partition("/")
            if b:
                msg = int(c)
                ch_id = int(a)
                chan = ctx.bot.get_channel(ch_id)
                if chan is None:
                    try:
                        chan = await ctx.bot.fetch_channel(ch_id)
                    except (discord.errors.NotFound, discord.errors.Forbidden):
                        raise ValueError()

                if not isinstance(
                    chan,
                    (
                        discord.TextChannel,
                        discord.VoiceChannel,
                        discord.Thread,
                        discord.DMChannel,
                    ),
                ):
                    raise ValueError()
            else:
                msg = int(a)
                chan = ctx.channel

            try:
                return await chan.fetch_message(msg)
            except discord.NotFound:
                raise ValueError()

        elif anno in ("discord.PartialMessage", "discord.message.PartialMessage"):
            guild = ctx.guild
            formatted = snakecore.utils.format_discord_link(
                arg, guild.id if guild else "@me"
            )

            a, b, c = formatted.partition("/")
            if b:
                msg = int(c)
                ch_id = int(a)
                chan = ctx.bot.get_channel(ch_id)
                if chan is None:
                    try:
                        chan = await ctx.bot.fetch_channel(ch_id)
                    except (discord.errors.NotFound, discord.errors.Forbidden):
                        raise ValueError()

                if not isinstance(
                    chan,
                    (
                        discord.TextChannel,
                        discord.VoiceChannel,
                        discord.Thread,
                        discord.DMChannel,
                    ),
                ):
                    raise ValueError()
            else:
                msg = int(a)
                chan = ctx.channel

            if isinstance(chan, discord.GroupChannel):
                raise ValueError()

            return chan.get_partial_message(msg)

        raise ParsingError(f"Internal parsing error: Invalid type annotation `{anno}`")

    raise ParsingError(
        f"Internal parsing error: Invalid argument of type `{type(arg)}`"
    )


async def cast_arg(
    ctx: commands.Context,
    param: inspect.Parameter | str,
    arg: Any,
    key: str | None = None,
    convert_error: bool = True,
) -> Any:
    """Cast an argument to the type mentioned by the paramenter annotation"""
    if isinstance(param, str):
        anno = param

    elif param.annotation == param.empty:
        # no checking/converting, do a direct return
        return arg

    else:
        anno: str = param.annotation

    if anno == "Any":
        # no checking/converting, do a direct return
        return arg

    union_annos = list(split_union_anno(anno))
    last_anno = union_annos.pop()

    for union_anno in union_annos:
        # we are in a union argument type, try to cast to each element one
        # by one
        try:
            return await cast_arg(ctx, union_anno, arg, key, False)
        except ValueError:
            pass

    tupled = split_tuple_anno(last_anno)
    try:
        if tupled is None:
            # got a basic argument
            return await cast_basic_arg(ctx, last_anno, arg)

        if not isinstance(arg, tuple):
            if len(tupled) == 2 and tupled[1] == "...":
                # specialcase where we expected variable length tuple and
                # got single element
                return (await cast_arg(ctx, tupled[0], arg, key, False),)

            raise ValueError()

        if len(tupled) == 2 and tupled[1] == "...":
            # variable length tuple
            ret = [await cast_arg(ctx, tupled[0], elem, key, False) for elem in arg]
            return tuple(ret)

        # fixed length tuple
        if len(tupled) != len(arg):
            raise ValueError()

        ret = [await cast_arg(ctx, i, j, key, False) for i, j in zip(tupled, arg)]
        return tuple(ret)

    except ValueError:
        if not convert_error:
            # Just forward value error in this case
            raise

        if key is None and not isinstance(param, str):
            if param.kind == param.VAR_POSITIONAL:
                key = "Each of the variable arguments"
            else:
                key = "Each of the variable keyword arguments"
        else:
            key = f"The argument `{key}`"

        raise ArgError(f"{key} must be {get_anno_error(anno)}.")


async def parse_command_str(
    ctx: commands.Context,
    cmd_str: str,
    signature: inspect.Signature,
    inject_message_reference: bool = False,
) -> tuple[tuple, dict[str, Any]]:
    """Parse a command invocation string to matched the types in the specified
    signature object.
    Relies on string argument annotations to cast args/kwargs to the types required.
    """
    args, kwargs = parse_args(cmd_str)

    # First check if it is a group command, and handle it.
    # get the func object

    # If user has put an attachment, check whether it's a text file, and
    # handle as code block

    sig = signature

    passed_arg_len = len(args)
    expected_arg_len = 0
    is_var_key = False
    keyword_only_args = []
    all_keywords = []

    # iterate through function parameters, arrange the given args and
    # kwargs in the order and format the function wants
    for i, key in enumerate(sig.parameters):
        param = sig.parameters[key]
        iskw = False

        if param.kind not in [param.POSITIONAL_ONLY, param.VAR_POSITIONAL]:
            all_keywords.append(key)

        if (
            inject_message_reference
            and i == 0
            and isinstance(param.annotation, str)
            and ctx.message.reference is not None
            and any(
                s in param.annotation
                for s in (
                    "discord.Message",
                    "discord.message.Message",
                    "discord.PartialMessage",
                    "discord.message.PartialMessage",
                )
            )
        ):
            # first arg is expected to be a Message object, handle reply into
            # the first argument
            msg = str(ctx.message.reference.message_id)
            if ctx.message.reference.channel_id != ctx.channel.id:
                msg = str(ctx.message.reference.channel_id) + "/" + msg

            args.insert(0, msg)
            passed_arg_len += 1

        if param.kind == param.VAR_POSITIONAL:
            expected_arg_len = len(args)
            for j in range(i, len(args)):
                args[j] = await cast_arg(ctx, param, args[j])
            continue

        elif param.kind == param.VAR_KEYWORD:
            is_var_key = True
            for j in kwargs:
                if j not in keyword_only_args:
                    kwargs[j] = await cast_arg(ctx, param, kwargs[j])
            continue

        elif param.kind == param.KEYWORD_ONLY:
            iskw = True
            keyword_only_args.append(key)
            if key not in kwargs:
                if param.default == param.empty:
                    raise KwargError(f"Missed required keyword argument `{key}`")
                kwargs[key] = param.default
                continue

        elif i == len(args):
            # ran out of args, try to fill it with something
            if key in kwargs:
                if param.kind == param.POSITIONAL_ONLY:
                    raise ArgError(f"`{key}` cannot be passed as a keyword argument")
                args.append(kwargs.pop(key))

            elif param.default == param.empty:
                raise ArgError(f"Missed required argument `{key}`")
            else:
                args.append(param.default)
                continue

        elif key in kwargs:
            raise ArgError("Positional cannot be passed again as a keyword argument")

        # cast the argument into the required type
        if iskw:
            kwargs[key] = await cast_arg(ctx, param, kwargs[key], key)
        else:
            expected_arg_len += 1
            args[i] = await cast_arg(ctx, param, args[i], key)

    # More arguments were given than required
    if passed_arg_len > expected_arg_len:
        raise ArgError(
            f"Too many args were given. Expected {expected_arg_len}"
            f" and got {passed_arg_len}",
        )

    # Iterate through kwargs to check if we received invalid ones
    if not is_var_key:
        for key in kwargs:
            if key not in all_keywords:
                raise KwargError(f"Received invalid keyword argument `{key}`")

    return args, kwargs
