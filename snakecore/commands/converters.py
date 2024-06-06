"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file defines some converters for command argument parsing.
"""

import datetime
import re
import sys
import types
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Generic,
    Literal,
    Sequence,
    Tuple,
    TypeVar,
    Union,
)

import dateutil.parser
import dateutil.tz
import discord
import discord.app_commands
from discord.ext import commands
from discord.ext.commands.view import StringView
from typing_extensions import Self, TypeVarTuple, Unpack

import snakecore
from snakecore.utils import regex_patterns

from .bot import AutoShardedBot, Bot

_T = TypeVar("_T")

_BotT = Bot | AutoShardedBot
_DECBotT = commands.Bot | commands.AutoShardedBot

ellipsis = type(Ellipsis)

_ESCAPES = {
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
    "‘": "’",
    "‚": "‛",
    "“": "”",
    "„": "‟",
    "⹂": "⹂",
    "「": "」",
    "『": "』",
    "〝": "〞",
    "﹁": "﹂",
    "﹃": "﹄",
    "＂": "＂",
    "｢": "｣",
    "«": "»",
    "‹": "›",
    "《": "》",
    "〈": "〉",
}

_QUOTES = {
    '"': '"',
    "'": "'",
    "`": "`",
    "‘": "’",
    "‚": "‛",
    "“": "”",
    "„": "‟",
    "⹂": "⹂",
    "「": "」",
    "『": "』",
    "〝": "〞",
    "﹁": "﹂",
    "﹃": "﹄",
    "＂": "＂",
    "｢": "｣",
    "«": "»",
    "‹": "›",
    "《": "》",
    "〈": "〉",
}


class DateTimeConverter(commands.Converter[datetime.datetime]):
    """A converter that parses timestamps to `datetime` objects.

    Examples
    --------
    - `<t:{6969...}[:t|T|d|D|f|F|R]>` -> `datetime(seconds=6969...)`
    - `YYYY-MM-DD[*HH[:MM[:SS[.fff[fff]]]][+HH:MM[:SS[.ffffff]]]]` -> `datetime`
    - `November 18th, 2069 12:30:30.55 am; -3` -> `datetime.datetime(2029, 11, 18, 0, 30, 30, 550000, tzinfo=tzoffset(None, 10800))`
    """

    async def convert(
        self, ctx: commands.Context[_DECBotT], argument: str
    ) -> datetime.datetime:
        arg = argument.strip().replace("`", "")
        if snakecore.utils.is_markdown_timestamp(arg):
            arg = snakecore.utils.extract_markdown_timestamp(arg)
            try:
                return datetime.datetime.fromtimestamp(arg, tz=datetime.timezone.utc)
            except (ValueError, OverflowError) as v:
                raise commands.BadArgument(
                    f"failed to construct datetime: {v.__class__.__name__}:{v!s}"
                ) from v

        try:
            dt = datetime.datetime.fromisoformat(arg)
            if arg.upper().endswith("Z"):
                dt = dt.astimezone(datetime.timezone.utc)
            return dt
        except (ValueError, OverflowError) as v:
            try:
                return dateutil.parser.parse(arg)  # slowest but most accurate
            except (ValueError, OverflowError) as v:
                pass
                raise commands.BadArgument(
                    f"failed to construct datetime: {v.__class__.__name__}:{v!s}"
                ) from v


class TimeConverter(commands.Converter[datetime.time]):
    """A converter that parses time to `time` objects.

    Examples
    --------
    - `<t:{6969...}[:t|T|d|D|f|F|R]>` -> `time`
    - `HH[:MM[:SS]][+HH:MM[:SS]]` -> `time`
    - `12:30:30 am; -3` -> `datetime.time(0, 30, 30, 550000, tzinfo=tzoffset(None, -10800))`
    """

    async def convert(
        self, ctx: commands.Context[_DECBotT], argument: str
    ) -> datetime.time:

        arg = argument.strip().replace("`", "")
        if snakecore.utils.is_markdown_timestamp(arg):
            arg = snakecore.utils.extract_markdown_timestamp(arg)
            try:
                return datetime.datetime.fromtimestamp(
                    arg, tz=datetime.timezone.utc
                ).timetz()
            except (ValueError, OverflowError) as v:
                raise commands.BadArgument(
                    f"failed to construct time: {v.__class__.__name__}:{v!s}"
                ) from v

        try:
            t = datetime.time.fromisoformat(arg)
            if arg.upper().endswith("Z"):
                t = t.replace(tzinfo=datetime.timezone.utc)
            return t
        except (ValueError, OverflowError) as v:
            try:
                if not (m := re.fullmatch(regex_patterns.TIME, arg)):
                    raise ValueError(
                        f"Failed to parse time: {arg!r} is not a parsable time"
                    )

                hours = int(m.group(1))
                minutes = int(m.group(2) or "0")
                seconds = int(m.group(3) or "0")
                microseconds = int(m.group(4) or "0")
                am_pm = m.group(5) or ""
                if am_pm.lower() == "am":
                    if hours == 12:
                        hours = 0

                elif am_pm.lower() == "pm":
                    if hours < 12:
                        hours += 12

                tzinfo = datetime.timezone.utc

                if tzinfo_str := m.group(6):
                    if (
                        tzinfo_name := m.group(7)
                    ) and not tzinfo_name.upper().startswith(("Z", "UTC", "GMT")):
                        raise ValueError("only explicit UTC/GMT offsets are supported.")

                    offset_sign = m.group(8)
                    offset_hours = int(m.group(9) or "0") % 24
                    offset_minutes = int(m.group(10) or "0") % 60
                    offset_seconds = int(m.group(11) or "0") % 60
                    offset_microseconds = int(m.group(12) or "0") % 60

                    final_tzoffset_seconds = (1 if offset_sign == "+" else -1) * (
                        offset_hours * 3600
                        + offset_minutes * 60
                        + offset_seconds
                        + offset_microseconds * 1e-06
                    )
                    if final_tzoffset_seconds:
                        tzinfo = datetime.timezone(
                            datetime.timedelta(seconds=final_tzoffset_seconds)
                        )

                return datetime.time(
                    hour=hours,
                    minute=minutes,
                    second=seconds,
                    microsecond=microseconds,
                    tzinfo=tzinfo,
                )

            except (ValueError, OverflowError) as v:
                raise commands.BadArgument(
                    f"failed to construct time: {v.__class__.__name__}:{v!s}"
                ) from v


class TimeDeltaConverter(commands.Converter[datetime.timedelta]):
    """A converter that parses time intervals to `timedelta` objects.

    Examples
    --------
    - `<t:{6969...}[:t|T|d|D|f|F|R]>` -> `datetime(second=6969...) - datetime.now(timezone.utc)`
    - `HH[:MM[:SS[.fff[fff]]]][+HH:MM[:SS[.ffffff]]]` -> `time`
    - `300d[ay[s]] 40m[in[ute[s]|s]]` -> `timedelta(days=30, minutes=40)``
    - `6:30:05` -> `timedelta(hours=6, minutes=30, seconds=5)`
    """

    async def convert(
        self, ctx: commands.Context[_DECBotT], argument: str
    ) -> datetime.timedelta:

        arg = argument.strip().replace("`", "")
        if snakecore.utils.is_markdown_timestamp(arg):
            arg = snakecore.utils.extract_markdown_timestamp(arg)
            try:
                return datetime.datetime.fromtimestamp(
                    arg, tz=datetime.timezone.utc
                ) - datetime.datetime.now(datetime.timezone.utc)
            except (ValueError, OverflowError) as v:
                raise commands.BadArgument(
                    f"failed to construct time interval: {v.__class__.__name__}:{v!s}"
                ) from v
        try:
            if m := re.fullmatch(regex_patterns.TIME_INTERVAL, arg):
                weeks = 0
                days = int(m.group(1) or "0")
                hours = int(m.group(2) or "0")
                minutes = int(m.group(3) or "0")
                seconds = int(m.group(4) or "0")
                microseconds = int(m.group(5) or "0")

            elif m := re.fullmatch(regex_patterns.TIME_INTERVAL_PHRASE, arg):
                weeks = float(m.group(1) or "0")
                days = float(m.group(2) or "0")
                hours = float(m.group(3) or "0")
                minutes = float(m.group(4) or "0")
                seconds = float(m.group(5) or "0")
                microseconds = 0.0
            else:
                raise ValueError(
                    f"Failed to parse time: {arg!r} is not a parsable time interval"
                )

            return datetime.timedelta(
                weeks=weeks,
                days=days,
                hours=hours,
                minutes=minutes,
                seconds=seconds,
                microseconds=microseconds,
            )

        except (ValueError, OverflowError) as v:
            raise commands.BadArgument(
                f"failed to construct time interval: {v.__class__.__name__}:{v!s}"
            ) from v


class ClosedRangeConverter(commands.Converter[range]):
    """A converter that parses closed integer ranges to Python `range` objects.
    Both a hyphen-based notation is supported (as used in English phrases) which always
    includes endpoints, as well as a mathematical notation using comparison operators.

    Examples
    --------
    - `start-stop` -> `range(start, stop+1)`
    - `start-stop|[+]step` -> `range(start, stop+1, +step)` *
    - `start-stop|-step` -> `range(start, stop+1, -step)` *

    - `start>|>=|≥x>|>=|≥stop` -> `range(start[+1], stop[+1])`
    - `start>|>=|≥x>|>=|≥stop|[+]step` -> `range(start[+1], stop[+1], +step)` *
    - `start>|>=|≥x>|>=|≥stop|-step` -> `range(start[+1], stop[+1], -step)` *

    *The last '|' is considered as part of the syntax.
    """

    COMPARISON_NOTATION = re.compile(
        r"(-?\d+)([<>]=?|[≤≥])[a-zA-Z]([<>]=?|[≤≥])(-?\d+)(?:\|([-+]?\d+))?"
    )
    HYPHEN_NOTATION = re.compile(r"(-?\d+)-(-?\d+)(?:\|([-+]?\d+))?")

    async def convert(self, ctx: commands.Context[_DECBotT], argument: str) -> range:
        hyphen_match = self.HYPHEN_NOTATION.match(argument)
        comparison_match = self.COMPARISON_NOTATION.match(argument)

        if not (hyphen_match or comparison_match):
            raise commands.BadArgument(
                "failed to construct closed integer range from argument "
                f"{argument!r}\n\n"
                "Hyphen syntax:\n"
                "- `start-stop`"
                "- `start-stop|[+]step` *"
                "- `start-stop|-step` *\n\n"
                "Mathematical syntax:\n"
                "- `start>|>=|≥x>|>=|≥stop`\n"
                "- `start>|>=|≥x>|>=|≥stop|[+]step` *\n"
                "- `start>|>=|≥x>|>=|≥stop|-step` *\n\n"
                "*The last '|' is considered as part of the syntax."
            )

        start = stop = step = 0
        if hyphen_match:
            raw_start = start = int(hyphen_match.group(1))
            raw_stop = stop = int(hyphen_match.group(2))
            raw_step = step = int(hyphen_match.group(3) or "1")

            if raw_start <= raw_stop:
                stop += 1

            elif raw_start >= raw_stop:
                stop -= 1
                if not hyphen_match.group(3) and raw_step > 0:
                    step *= -1

        elif comparison_match:
            raw_start = start = int(comparison_match.group(1))
            start_comp = comparison_match.group(2)

            stop_comp = comparison_match.group(3)
            raw_stop = stop = int(comparison_match.group(4))

            raw_step = step = int(comparison_match.group(5) or "1")

            if raw_start <= raw_stop:
                if start_comp == "<":
                    start += 1
                elif start_comp not in ("<=", "≤"):  # default used in range class
                    raise commands.BadArgument(
                        f"argument {argument!r} is not a valid closed integer range"
                    )

                if stop_comp in ("<=", "≤"):
                    stop += 1
                elif stop_comp != "<":  # default used in range class
                    raise commands.BadArgument(
                        f"argument {argument!r} is not a valid closed integer range"
                    )

            elif raw_start >= raw_stop:
                if start_comp == ">":
                    start -= 1
                elif start_comp not in (">=", "≥"):  # default used in range class
                    raise commands.BadArgument(
                        f"argument {argument!r} is not a valid closed integer range"
                    )

                if stop_comp in (">=", "≥"):  # default used in range class
                    stop -= 1
                elif stop_comp != ">":
                    raise commands.BadArgument(
                        f"argument {argument!r} is not a valid closed integer range"
                    )

                if not comparison_match.group(5) and raw_step > 0:
                    step *= -1

        try:
            interval = range(
                start,
                stop,
                step,
            )
        except (ValueError, TypeError):
            raise commands.BadArgument(
                "failed to construct closed integer range from argument "
                f"{argument!r}\n\n"
                "Hyphen syntax:\n"
                "- `start-stop`"
                "- `start-stop|[+]step` *"
                "- `start-stop|-step` *\n\n"
                "Mathematical syntax:\n"
                "- `start>|>=|≥x>|>=|≥stop`\n"
                "- `start>|>=|≥x>|>=|≥stop|[+]step` *\n"
                "- `start>|>=|≥x>|>=|≥stop|-step` *\n\n"
                "*The last '|' is considered as part of the syntax."
            )

        if not interval:
            raise commands.BadArgument(f"Integer interval {argument!r} is empty.")

        return interval


class CodeBlock:
    """An object that represents a fenced or inline markdown code block.
    Can be used as a converter, which returns an instance of this class.
    The instance attributes `code` and `language` can be used to obtain
    the code block contents. To get the raw code block text from an
    instance, cast it into a string.

    This class does not parse successfully if specified inside a tuple
    annotation of `discord.ext.commands.flags.Flag`, when defined inside a
    subclass of `discord.ext.commands`'s default `FlagConverter`.
    To migitate this, it is recommended to subclass
    `snakecore.commands.converters.FlagConverter` instead.
    """

    _MULTILINE_PATTERN = re.compile(regex_patterns.CODE_BLOCK)
    _INLINE_PATTERN = re.compile(regex_patterns.INLINE_CODE_BLOCK)

    def __init__(
        self, code: str, language: str | None = None, inline: bool | None = None
    ) -> None:
        self.code = code
        self.language = language
        self.inline = inline if inline is not None else not (language or "\n" in code)

    @classmethod
    async def convert(cls, ctx: commands.Context[_DECBotT], argument: str) -> Self:
        view: StringView = getattr(ctx, "_current_view", ctx.view)

        if argument.startswith("```"):

            if not argument.endswith("```") or (
                argument.endswith("```") and argument == "```"
            ):

                parsed_argument = argument.strip("\n").strip()
                multiline_match = cls._MULTILINE_PATTERN.match(
                    view.buffer, pos=view.index - len(parsed_argument)
                )

                if multiline_match is not None:
                    parsed_argument = view.buffer[slice(*multiline_match.span())]
                    view.index = multiline_match.end()

                argument = parsed_argument

        elif argument.startswith("`"):

            if not argument.endswith("`") or (
                argument.endswith("`") and argument == "`"
            ):

                parsed_argument = argument.strip("\n").strip()
                inline_match = cls._INLINE_PATTERN.match(
                    view.buffer, pos=view.index - len(parsed_argument)
                )

                if inline_match is not None:
                    parsed_argument = view.buffer[slice(*inline_match.span())]
                    view.index = inline_match.end()

                argument = parsed_argument

        try:
            return cls.from_markdown(argument)
        except (TypeError, ValueError) as err:
            raise commands.BadArgument(
                "argument must be a string containing an inline or multiline markdown code block"
            ) from err

    @classmethod
    def from_markdown(cls, markdown: str) -> Self:

        if not isinstance(markdown, str):
            raise TypeError(
                "argument 'markdown' must be of type 'str' containing a markdown code block, "
                f"not {markdown.__class__.__name__}"
            )
        elif not (markdown.startswith("`") and markdown.endswith("`")):
            raise ValueError(
                "argument 'markdown' does not contain a markdown code block"
            )

        language = None
        code = markdown
        inline = False
        if markdown.startswith("```") and markdown.endswith("```"):
            if markdown[3] != "\n":
                newline_idx = markdown.find("\n")
                if newline_idx == -1:
                    raise commands.BadArgument(
                        "markdown string does not contain a valid multiline code block"
                    )

                if language is None:
                    language = markdown[3:newline_idx]
                code = markdown[newline_idx + 1 : -3]

            code = code.replace(
                "\\```", "```"
            )  # support nested code blocks that were properly escaped

        else:
            inline = True
            code = markdown[1:-1]

        return cls(code, language=language, inline=inline)

    def __str__(self):
        return (
            f"`{self.code}`"
            if self.inline
            else (
                f"```{self.language or ''}\n"
                + self.code.replace("```", "\\```")
                + "\n```"
            )
        )


StringParams = TypeVar("StringParams", int, range, ellipsis)
StringParamsTuple = TypeVar(
    "StringParamsTuple", tuple[int, int], tuple[int, ellipsis], tuple[ellipsis, int]
)


class _StringConverter(commands.Converter[str]):
    async def convert(self, ctx: commands.Context[_DECBotT], argument: str) -> str:
        try:
            string = self.escape(argument)
        except ValueError as verr:
            raise commands.BadArgument(
                f"Escaping input argument failed: {verr}"
            ) from verr

        if (
            len(string) > 1
            and string[0] in _QUOTES
            and string.endswith(_QUOTES[string[0]])
        ):
            string = string[1:-1]

        return string

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        pass

    def __or__(self, other):  # Add support for UnionType
        return self.__class__.__class__.__or__(self.__class__, other)  # type: ignore

    def __ror__(self, other):  # Add support for UnionType
        return self.__class__.__class__.__ror__(self.__class__, other)  # type: ignore

    @staticmethod
    def escape(string: str) -> str:
        """Convert a "raw" string to one where characters are escaped."""
        index = 0
        newstr = []
        while index < len(string):
            char = string[index]
            index += 1
            if char == "\\":
                # got a backslash, handle escapes
                char = string[index]
                index += 1
                if char.lower() in ("x", "u"):  # these are unicode escapes
                    if char.lower() == "x":
                        n = 2
                    else:
                        n = 4 if char == "u" else 8

                    var = string[index : index + n]
                    try:
                        if len(var) != n:
                            n = len(var)
                            raise ValueError("invalid quoted string")

                        newstr.append(chr(int(var, base=16)))
                    except (ValueError, OverflowError):
                        esc = string[index - 2 : index + n]
                        raise ValueError(
                            f"Invalid unicode escape: `{esc}` in string",
                        )
                    index += n

                elif char in _ESCAPES:
                    # general escapes
                    newstr.append(_ESCAPES[char])
                else:
                    raise ValueError(
                        "Invalid escape character",
                        f"Unknown escape `\\{char}`",
                    )
            else:
                newstr.append(char)

        return "".join(newstr)


class StringConverter(_StringConverter, Generic[_T]):
    """A converter that parses string literals to string objects,
    thereby handling escaped characters and removing trailing quotes.

    Can be used over the default `str` converter for less greedy argument
    parsing.

    It parameterized with 1-2 integers, it will enforce the length of arguments
    to be within the range (inclusive) of parameterized integer literals given.
    To omit an upper/lower range, use `...`.

    Note that some Unicode glyphs, e.g. emojis, may consist of 2 or more characters.

    Examples
    --------
    - `"'abc'"` -> `'abc'`
    - `'"ab\\"c"'` -> `'ab"c'`
    """

    def __init__(self, size: Any = None) -> None:
        super().__init__()
        self.size: tuple = (..., ...) if size is None else size

    def __class_getitem__(cls, size: StringParams | StringParamsTuple) -> Self:
        size_tuple = (..., ...)

        if getattr(size, "__origin__", None) is Literal:
            if size.__args__ and len(size.__args__) == 1:  # type: ignore
                size = (..., int(size.__args__[0]))  # type: ignore
            else:
                raise ValueError(
                    "'Literal' type argument must contain one positive integer"
                )

        if isinstance(size, int):
            if size < 0:
                raise ValueError(
                    f"integer type argument for '{cls.__name__}' must be positive"
                )

            size_tuple = (..., size)

        elif isinstance(size, tuple):
            if not len(size) == 2:
                raise ValueError(
                    f"tuple type argument for '{cls.__name__}' must have length 2"
                )

            if getattr(size[0], "__origin__", None) is Literal:
                if size[0].__args__ and len(size.__args__) == 1:  # type: ignore
                    size = (int(size[0].__args__[0]), size[1])  # type: ignore
                else:
                    raise ValueError(
                        "First and second 'Literal' type arguments must contain one positive integer"
                    )
                assert isinstance(size, tuple)

            if getattr(size[1], "__origin__", None) is Literal:  # type: ignore
                if size[1].__args__ and len(size[1].__args__) == 1:  # type: ignore
                    size = (size[0], int(size[1].__args__[0]))  # type: ignore
                else:
                    raise ValueError(
                        "First and second 'Literal' type arguments must contain one positive integer"
                    )
                assert isinstance(size, tuple)

            min_size, max_size = ..., ...

            if isinstance(size[0], int) and isinstance(size[1], int):
                if not 0 < size[0] <= size[1]:
                    raise ValueError(
                        f"tuple type argument for '{cls.__name__}' must have the structure"
                        " (m, n), (m, ...), or (..., n), where 'm' and 'n' are positive "
                        "integers and 0 < m <= n"
                    )

                min_size, max_size = size

            elif isinstance(size[0], int) and isinstance(size[1], ellipsis):
                if size[0] < 0:
                    raise ValueError(
                        f"tuple type argument for '{cls.__name__}' must have the structure"
                        " (m, n), (m, ...), or (..., n), where 'm' and 'n' are positive "
                        "integers and 0 < m <= n"
                    )

                min_size = size[0]

            elif isinstance(size[0], ellipsis) and isinstance(size[1], int):
                if size[1] < 0:
                    raise ValueError(
                        f"tuple type argument for '{cls.__name__}' must have the structure"
                        " (m, n), (m, ...), or (..., n), where 'm' and 'n' are positive "
                        "integers and 0 < m <= n"
                    )

                max_size = size[1]
            else:
                raise ValueError(
                    f"tuple type argument for '{cls.__name__}' must have the structure"
                    " (m, n), (m, ...), or (..., n), where 'm' and 'n' are positive "
                    "integers and 0 < m <= n"
                )

            size_tuple = min_size, max_size

        elif isinstance(size, range):
            if not 0 < size.start <= size.stop:
                raise ValueError(
                    f"range object type argument for '{cls.__name__}' must be a positive range"
                )

            size_tuple = size.start, size.stop - 1

        elif not isinstance(size, ellipsis):
            raise ValueError(
                f"type argument for '{cls.__name__}' must be literal instances of "
                "'int', 'range', 'tuple' or 'ellipsis' ('...')"
            )

        return cls(size=size_tuple)

    async def convert(self, ctx: commands.Context[_DECBotT], argument: str) -> str:
        string = await super().convert(ctx, argument)
        if (
            isinstance(self.size[0], int)
            and isinstance(self.size[1], int)
            and not self.size[0] <= len(string) <= self.size[1]
        ):
            raise commands.BadArgument(
                f"string argument must be {self.size[0]} character(s) long."
                if self.size[0] == self.size[1]
                else f"string argument must be {self.size[0]}-{self.size[1]} "
                "character(s) long."
            )
        elif (
            isinstance(self.size[0], ellipsis)
            and isinstance(self.size[1], int)
            and not len(string) <= self.size[1]
        ):
            raise commands.BadArgument(
                f"string argument must be {self.size[1]} or less characters long."
            )
        elif (
            isinstance(self.size[0], int)
            and isinstance(self.size[1], ellipsis)
            and not self.size[0] <= len(string)
        ):
            raise commands.BadArgument(
                f"string argument must be {self.size[0]} or more characters long."
            )

        return string

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}" + (
            f"[{', '.join(self.size)}]" if self.size != (..., ...) else ""
        )


_TVT = TypeVarTuple("_TVT")


class StringExprConverter(_StringConverter, Generic[Unpack[_TVT]]):  # type: ignore
    def __init__(self, regex: str, examples: tuple[str, ...]) -> None:
        super().__init__()
        self.regex_pattern = re.compile(regex)
        self.examples = examples

    def __class_getitem__(cls, regex_and_examples: str | tuple[str, ...]) -> Self:
        regex = None
        examples = ()
        if isinstance(regex_and_examples, tuple) and regex_and_examples:
            regex = regex_and_examples[0]
            examples = regex_and_examples[1:]
        elif isinstance(regex_and_examples, str):
            regex = regex_and_examples
        else:
            raise TypeError(
                f"'{cls.__name__}' must be parameterized with one or more strings"
            )

        return cls(regex, examples)

    async def convert(self, ctx: commands.Context[_DECBotT], argument: str) -> str:
        string = await super().convert(ctx, argument)
        if not self.regex_pattern.fullmatch(string):
            raise commands.BadArgument(
                f"argument {argument!r} has an invalid structure/format"
                + (
                    ". Example formats: "
                    + ", ".join(repr(exp) for exp in self.examples)
                    if self.examples
                    else ""
                )
                + ". Check command documentation to see the correct formats."
            )
        return string


class StringExprMatchConverter(StringExprConverter, Generic[Unpack[_TVT]]):  # type: ignore
    async def convert(
        self, ctx: commands.Context[_DECBotT], argument: str
    ) -> re.Match[str]:
        string = await super().convert(ctx, argument)
        if not (match := self.regex_pattern.fullmatch(string)):
            raise commands.BadArgument(
                f"argument {argument:r} has an invalid structure/format"
                + (
                    ". Example formats: "
                    + ", ".join(repr(exp) for exp in self.examples)
                    if self.examples
                    else ""
                )
                + ". Check command documentation to see the correct formats."
            )
        return match


class ParensConverter(commands.Converter[tuple]):
    """A special converter that establishes its own scope of arguments
    and parses argument tuples.

    The recognized arguments are converted into their desired formats
    using the converters given to it as input, which are then converted
    into a tuple of arguments. This can be used to implement parsing
    of argument tuples. Nesting is also supported, as well as variadic
    parsing of argument tuples. The syntax is similar to type annotations
    using the `tuple` type (tuple[int, ...] = Parens[int, ...], etc.).

    Arguments for this converter must be surrounded by whitespace, followed
    by round parentheses on both sides (`'( ... ... ... )'`).

    This converter does not parse successfully if specified inside a tuple
    annotation of `discord.ext.commands.flags.Flag`, inside a subclass of
    `discord.ext.commands`'s default `FlagConverter`. To migitate this, it
    is recommended to subclass `snakecore.commands.converters.FlagConverter`
    instead.

    Examples
    --------
    - `"( 1 2 4 5.5 )"` -> `(1, 2, 4, 5.5)`
    - `'( 1 ( 4 ) () ( ( 6 ( "a" ) ) ) 0 )'` -> `(1, (4,), (), ((6,("a",),),), 0)`
    """

    OPENING = "("
    CLOSING = ")"

    def __init__(self, converters: Sequence[type]) -> None:
        super().__init__()
        self.converters = tuple(converters)
        self.parens_depth = 1
        self._increment_nested_parens_depth()

    def _increment_nested_parens_depth(self):
        for converter in self.converters:
            if isinstance(converter, self.__class__):
                converter.parens_depth = self.parens_depth + 1
                converter._increment_nested_parens_depth()

    def __class_getitem__(cls, params: Any) -> Self:
        if not isinstance(params, tuple):
            params = (params,)
        if len(params) == 2 and params[1] is Ellipsis:
            if params[0] is Ellipsis:
                raise TypeError(
                    f"{cls.__name__}[Ellipsis] or {cls.__name__}[Ellipsis, [<other type>,]] "
                    "is invalid."
                )

        elif len(params) > 2 and params[-1] is Ellipsis:
            raise TypeError(
                f"{cls.__name__}[<other type>, [<other type>, ...,] Ellipsis] is "
                "invalid."
            )

        converters = []

        for converter in params:
            if isinstance(converter, (int, float, str, bool)):
                converters.append(Literal[converter])  # type: ignore
                continue

            args = getattr(converter, "__args__", ())
            if sys.version_info >= (3, 10) and converter.__class__ is types.UnionType:  # type: ignore
                converter = args  # type: ignore

            origin = getattr(converter, "__origin__", None)

            if not (
                callable(converter)
                or isinstance(converter, commands.Converter)
                or converter is Ellipsis
            ):
                raise TypeError(
                    f"{cls.__name__}[...] expects a type or a Converter instance, or "
                    "a tuple of them."
                )

            if (
                converter in (commands.Greedy, type(None), discord.Attachment)
                or origin is commands.Greedy
            ):
                raise TypeError(f"{cls.__name__}[{converter.__name__}] is invalid.")  # type: ignore

            converters.append(converter)

        return cls(converters=converters)

    @staticmethod
    def _find_parenthesized_region(string: str, opening: str, closing: str):
        bstart = 0
        bend = 0
        scope_level = -1
        if string.startswith(closing):
            return slice(bstart, bend, 1)
        for i, s in enumerate(string):
            if s == opening:
                scope_level += 1
                if scope_level == 0:
                    bstart = i
            elif s == closing:
                if scope_level == 0:
                    bend = i + 1
                    return slice(bstart, bend, 1)
                scope_level -= 1
        return None

    async def convert(
        self, ctx: commands.Context[_DECBotT], argument: str
    ) -> tuple[Any, ...]:
        if not argument.startswith(self.OPENING):
            raise commands.BadArgument(
                "Parsing parenthesized argument failed "
                f"(at depth {self.parens_depth}): Failed to find parenthesized region, must be enclosed as "
                f"'{self.OPENING} ... {self.CLOSING}'"
            )
        elif (
            argument.startswith(self.OPENING)
            and argument.endswith(self.CLOSING)
            and (not argument[1:-1] or argument[1:-1].isspace())
        ):
            return ()

        view: StringView = getattr(ctx, "_current_view", ctx.view)

        parsed_argument = argument

        splintered = False

        if (
            not (
                parens_slice := self._find_parenthesized_region(  # assume that inital parsed argument is parenthesized
                    parsed_argument,
                    self.OPENING,
                    self.CLOSING,
                )
            )
            and (splintered := True)
            and not (
                parens_slice := self._find_parenthesized_region(  # if it isn't, assume that it at least starts with self.OPENING and try to find full region
                    view.buffer[view.index - len(argument) :],
                    self.OPENING,
                    self.CLOSING,
                )
            )
        ):
            raise commands.BadArgument(
                "Parsing parenthesized argument failed "
                f"(at depth {self.parens_depth}): Could not find parenthesized "
                "region, must be enclosed as "
                f"'{self.OPENING} ... {self.CLOSING}'"
            )

        old_previous = view.previous
        old_index = view.index
        original_parameter = ctx.current_parameter
        fake_parameter = commands.parameter()

        if splintered:

            parens_slice = slice(
                parens_slice.start + view.index - len(argument),
                parens_slice.stop + view.index - len(argument),
            )  # offset slice to match the view's buffer string

            view.index -= len(argument)
        else:

            parens_slice = slice(
                parens_slice.start + view.index - len(argument) - 1,
                parens_slice.stop + view.index - len(argument) - 1,
            )  # offset slice to match the view's buffer string (excluding quotes)

            view.index -= len(argument) + 1

        parsed_argument = view.buffer[parens_slice]

        view.read(1)  # move right after starting bracket '('

        outputs = []
        converter_index = 0

        is_variadic = self.converters[-1] is Ellipsis

        while True:

            if view.index >= parens_slice.stop - 1:
                break

            view.skip_ws()

            if (
                view.current == self.CLOSING
                and converter_index < len(self.converters) - 1
            ):
                # reset any StringView changes done by this converter
                ctx.current_parameter = original_parameter
                ctx.current_argument = argument
                view.previous = old_previous
                view.index = old_index
                raise commands.BadArgument(
                    "Parsing parenthesized argument failed "
                    f"(at depth {self.parens_depth}): Too few arguments in "
                    "parenthesized region"
                )

            if converter_index == len(self.converters) - 1 and is_variadic:
                if view.current == self.CLOSING:
                    view.get()
                    break

                converter_index -= 1
            elif (
                converter_index == len(self.converters) and view.current == self.CLOSING
            ):  # end of parenthesized region
                view.get()
                break

            try:
                converter = self.converters[converter_index]
            except IndexError:
                ctx.current_parameter = original_parameter
                ctx.current_argument = argument
                view.previous = old_previous
                view.index = old_index
                raise commands.BadArgument(
                    "Parsing parenthesized argument failed "
                    f"(at depth {self.parens_depth}): Too many arguments in "
                    "parenthesized region"
                )

            converter_index += 1

            fake_parameter._annotation = converter
            ctx.current_parameter = fake_parameter

            previous_previous = view.previous
            previous_index = view.index
            try:

                temp_previous = view.previous
                temp_index = view.index
                try:
                    ctx.current_argument = fake_argument = view.get_quoted_word()
                except commands.UnexpectedQuoteError as u:
                    view.previous = temp_previous
                    view.index = temp_index
                    ctx.current_argument = fake_argument = view.get_word()

            except commands.ArgumentParsingError as a:

                ctx.current_parameter = original_parameter
                ctx.current_argument = argument
                view.previous = old_previous
                view.index = old_index
                raise commands.BadArgument(
                    "Parsing parenthesized argument failed "
                    f"(at depth {self.parens_depth}): Failed to parse "
                    "parenthesized contents"
                )

            ctx.current_parameter = fake_parameter

            try:
                if view.index >= parens_slice.stop - 1:
                    assert fake_argument  # fake_argument won't become None
                    if fake_argument.endswith(self.CLOSING):
                        fake_argument = fake_argument[:-1]
                        # catch last argument ... that ended with ')':  "...)"
                    elif fake_argument.endswith(tuple(_ESCAPES.values())):
                        fake_argument = fake_argument[:-2]
                        # catch last argument ... that ended with ')' followed by '"' (or any other quote):  '...)"'
                transformed = await commands.run_converters(
                    ctx, converter, fake_argument, fake_parameter  # type: ignore
                )
                outputs.append(transformed)

            except commands.UserInputError as err:
                ctx.current_parameter = original_parameter
                ctx.current_argument = argument
                view.previous = old_previous
                view.index = old_index
                if isinstance(converter, self.__class__):
                    raise
                elif (
                    fake_argument
                    and len(fake_argument) > 1
                    and (
                        fake_argument.startswith(self.OPENING)
                        and not fake_argument[1].isspace()
                        or fake_argument.endswith(self.CLOSING)
                        and not fake_argument[-2].isspace()
                    )
                ):
                    raise commands.BadArgument(
                        "Parsing parenthesized argument failed "
                        f"(at depth {self.parens_depth}): Content of "
                        "parenthesized region must be surrounded by whitespace"
                    ) from err

                raise commands.BadArgument(
                    "Parsing parenthesized argument failed "
                    f"(at depth {self.parens_depth}): Failed to parse "
                    "parenthesized argument at position "
                    f"{converter_index+1}: {err!s}"
                ) from err

            if (
                ctx.command
                and getattr(fake_parameter.annotation, "__origin__", None) is Union
                and type(None)
                in fake_parameter.annotation.__args__  # check for ... | None  # type: ignore
                and transformed is None
            ):
                view.index = previous_index  # view.undo() does not revert properly for ... | None
                view.previous = previous_previous

        ctx.current_parameter = original_parameter
        return tuple(outputs)

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        pass

    def __or__(self, other):  # Add support for UnionType
        return self.__class__.__class__.__or__(self.__class__, other)  # type: ignore

    def __ror__(self, other):  # Add support for UnionType
        return self.__class__.__class__.__ror__(self.__class__, other)  # type: ignore

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}[{', '.join(self._repr_converter(conv) for conv in self.converters)}]"

    @staticmethod
    def _repr_converter(obj):
        if isinstance(obj, types.GenericAlias):
            return repr(obj)
        if isinstance(obj, type):
            if obj.__module__ == "builtins":
                return obj.__qualname__
            return f"{obj.__module__}.{obj.__qualname__}"
        if obj is ...:
            return "..."
        if isinstance(obj, types.FunctionType):
            return obj.__name__
        return repr(obj)


class UnicodeEmojiConverter(commands.Converter[str]):
    """A converter that converts emoji shortcodes or unicode
    character escapes into valid unicode emojis. Already valid
    inputs are ignored.

    Syntax
    ------
    - `":eggplant:"` -> `"🍆"`
    - `"\\u270c\\u1f3fd"` -> `"✌🏽"`
    """

    async def convert(self, ctx: commands.Context[_BotT], argument: str) -> str:
        argument = StringConverter.escape(argument)

        if snakecore.utils.is_emoji_shortcode(argument):
            return snakecore.utils.shortcode_to_unicode_emoji(argument)

        elif snakecore.utils.is_unicode_emoji(argument):
            return argument

        raise commands.BadArgument(
            "argument must be a valid unicode emoji or emoji shortcode"
        )


class ReferencedMessageConverter(commands.Converter[discord.Message]):
    async def convert(
        self, ctx: commands.Context[_BotT], argument: str
    ) -> discord.Message:

        if not ctx.message.reference:
            raise commands.UserInputError(
                "The target message does not reference any other message."
            )

        message = ctx.message.reference.cached_message

        if isinstance(ctx.message.reference.resolved, discord.DeletedReferencedMessage):
            raise commands.UserInputError(
                "The target message references a deleted message."
            )

        elif isinstance(ctx.message.reference.resolved, discord.Message):
            message = ctx.message.reference.resolved

        elif ctx.message.reference.message_id:
            try:
                message = await ctx.message.channel.fetch_message(
                    ctx.message.reference.message_id
                )
            except discord.HTTPException:
                raise commands.UserInputError(
                    "Failed to retrieve the referenced message."
                )

        else:
            raise commands.UserInputError("Failed to retrieve the referenced message.")

        ctx.view.undo() # backtrack for next converter to continue from here

        return message


UnicodeEmoji = Annotated[str, UnicodeEmojiConverter]
"""A converter that converts emoji shortcodes or unicode
character escapes into valid unicode emojis. Already valid
inputs are ignored.

Syntax
------
- `":eggplant:"` -> `"🍆"`
- `"\\u270c\\u1f3fd"` -> `"✌🏽"`
"""
DateTime = Annotated[datetime.datetime, DateTimeConverter]
"""A converter that parses timestamps to `datetime` objects.

Examples
--------
- `<t:{6969...}[:t|T|d|D|f|F|R]>` -> `datetime(seconds=6969...)`
- `YYYY-MM-DD[*HH[:MM[:SS[.fff[fff]]]][+HH:MM[:SS[.ffffff]]]]` -> `datetime`
- `November 18th, 2069 12:30:30.55 am; -3` -> `datetime.datetime(2029, 11, 18, 0, 30, 30, 550000, tzinfo=tzoffset(None, 10800))`
"""
Time = Annotated[datetime.time, TimeConverter]
"""A converter that parses time to `time` objects.

Examples
--------
- `<t:{6969...}[:t|T|d|D|f|F|R]>` -> `time`
- `HH[:MM[:SS]][+HH:MM[:SS]]` -> `time`
- `12:30:30 am; -3` -> `datetime.time(0, 30, 30, 550000, tzinfo=tzoffset(None, -10800))`
"""
TimeDelta = Annotated[datetime.timedelta, TimeDeltaConverter]
"""A converter that parses time intervals to `timedelta` objects.

Examples
--------
- `<t:{6969...}[:t|T|d|D|f|F|R]>` -> `datetime(second=6969...) - datetime.now(timezone.utc)`
- `HH[:MM[:SS[.fff[fff]]]][+HH:MM[:SS[.ffffff]]]` -> `time`
- `300d[ay[s]] 40m[in[ute[s]|s]]` -> `timedelta(days=30, minutes=40)``
- `6:30:05` -> `timedelta(hours=6, minutes=30, seconds=5)`
"""
ClosedRange = Annotated[range, ClosedRangeConverter]
"""A converter that parses closed integer ranges to Python `range` objects.
Both a hyphen-based notation is supported (as used in English phrases) which always
includes endpoints, as well as a mathematical notation using comparison operators.

Examples
--------
- `start-stop` -> `range(start, stop+1)`
- `start-stop|[+]step` -> `range(start, stop+1, +step)` *
- `start-stop|-step` -> `range(start, stop+1, -step)` *

- `start>|>=|≥x>|>=|≥stop` -> `range(start[+1], stop[+1])`
- `start>|>=|≥x>|>=|≥stop|[+]step` -> `range(start[+1], stop[+1], +step)` *
- `start>|>=|≥x>|>=|≥stop|-step` -> `range(start[+1], stop[+1], -step)` *

*The last '|' is considered as part of the syntax.
"""

ReferencedMessage = Annotated[discord.Message, ReferencedMessageConverter]
"""A converter that retrieves a message referenced (replied to) by a command invocation
text message.

Does not actually consume command arguments.
"""


if TYPE_CHECKING:  # type checker deception
    Parens = tuple
    """A special converter that establishes its own scope of arguments
    and parses argument tuples.

    The recognized arguments are converted into their desired formats
    using the converters given to it as input, which are then converted
    into a tuple of arguments. This can be used to implement parsing
    of argument tuples. Nesting is also supported, as well as variadic
    parsing of argument tuples. The syntax is similar to type annotations
    using the `tuple` type (tuple[int, ...] = Parens[int, ...], etc.).

    Arguments for this converter must be surrounded by whitespace, followed
    by round parentheses on both sides (`'( ... ... ... )'`).

    This converter does not parse successfully if specified inside a tuple
    annotation of `discord.ext.commands.flags.Flag`, inside a subclass of
    `discord.ext.commands`'s default `FlagConverter`. To migitate this, it
    is recommended to subclass `snakecore.commands.converters.FlagConverter`
    instead.

    Examples
    --------
    - `"( 1 2 4 5.5 )"` -> `(1, 2, 4, 5.5)`
    - `'( 1 ( 4 ) () ( ( 6 ( "a" ) ) ) 0 )'` -> `(1, (4,), (), ((6,("a",),),), 0)`
    """

    class String(str):  # type: ignore
        """A converter that parses string literals to string objects,
        thereby handling escaped characters and removing trailing quotes.

        Can be used over the default `str` converter for less greedy argument
        parsing.

        It parameterized with 1-2 integers, it will enforce the length of arguments
        to be within the range (inclusive) of parameterized integer literals given.
        To omit an upper/lower range, use `...`. Specifying only one integer is the
        same as specifying `..., integer`.

        Note that some Unicode glyphs, e.g. emojis, may consist of 2 or more characters.

        Examples
        --------
        - `"'abc'"` -> `'abc'`
        - `'"ab\\"c"'` -> `'ab"c'`
        """

        def __class_getitem__(cls, size: StringParams | StringParamsTuple): ...

    class StringExpr(str):  # type: ignore
        """A subclass of the `String` converter, that enforces input strings to match the
        regular expression the class is parameterized with. If more than one string
        is passed for parameterization, the second string and others that follow will
        be treated as user-facing example formats, shown in an error message when inputs
        fail to match.

        Examples
        --------
        - `"'abc'"` -> `'abc'`
        - `'"ab\\"c"'` -> `'ab"c'`
        """

        def __class_getitem__(cls, regex_and_examples: str | tuple[str, ...]): ...

    class StringExprMatch(re.Match):  # type: ignore
        """A subclass of the `StringExpr` converter, that converts inputs into
        `re.Match` objects instead of strings.
        """

        def __class_getitem__(cls, regex_and_examples: str | tuple[str, ...]): ...

else:
    String = StringConverter
    StringExpr = StringExprConverter
    StringExprMatch = StringExprMatchConverter
    Parens = ParensConverter


async def _tuple_convert_all(
    ctx: commands.Context[_DECBotT], argument: str, flag: commands.Flag, converter: Any
) -> Tuple[Any, ...]:
    view = StringView(argument)
    results = []
    param: commands.Parameter = ctx.current_parameter  # type: ignore
    setattr(ctx, "_current_view", view)  # store temporary StringView,
    # to implement support for flag annotation 'tuple[T, ...]', where T is CodeBlock/Parens
    while not view.eof:
        view.skip_ws()
        if view.eof:
            break

        word = view.get_quoted_word()
        if word is None:
            break

        try:
            converted = await commands.run_converters(ctx, converter, word, param)
        except Exception as e:
            delattr(ctx, "_current_view")  # type: ignore
            raise commands.BadFlagArgument(flag, word, e) from e
        else:
            results.append(converted)

    delattr(ctx, "_current_view")  # type: ignore

    return tuple(results)


async def _tuple_convert_flag(
    ctx: commands.Context[_DECBotT], argument: str, flag: commands.Flag, converters: Any
) -> Tuple[Any, ...]:
    view = StringView(argument)
    results = []
    param: commands.Parameter = ctx.current_parameter  # type: ignore
    setattr(ctx, "_current_view", view)  # store temporary StringView,
    # to implement support for flag annotation 'tuple[T, ...]', where T is CodeBlock/Parens
    for converter in converters:
        view.skip_ws()
        if view.eof:
            break

        word = view.get_quoted_word()
        if word is None:
            break

        try:
            converted = await commands.run_converters(ctx, converter, word, param)
        except Exception as e:
            delattr(ctx, "_current_view")  # type: ignore
            raise commands.BadFlagArgument(flag, word, e) from e
        else:
            results.append(converted)

    delattr(ctx, "_current_view")

    if len(results) != len(converters):
        raise commands.MissingFlagArgument(flag)

    return tuple(results)


async def _convert_flag(
    ctx: commands.Context[_DECBotT],
    argument: str,
    flag: commands.Flag,
    annotation: Any = None,
) -> Any:
    param: commands.Parameter = ctx.current_parameter  # type: ignore
    annotation = annotation or flag.annotation
    try:
        origin = annotation.__origin__
    except AttributeError:
        pass
    else:
        if origin is tuple:
            if annotation.__args__[-1] is Ellipsis:
                return await _tuple_convert_all(
                    ctx, argument, flag, annotation.__args__[0]
                )
            else:
                return await _tuple_convert_flag(
                    ctx, argument, flag, annotation.__args__
                )
        elif origin is list:
            # typing.List[x]
            annotation = annotation.__args__[0]
            return await _convert_flag(ctx, argument, flag, annotation)
        elif origin is Union and type(None) in annotation.__args__:
            # typing.Optional[x]
            annotation = Union[tuple(arg for arg in annotation.__args__ if arg is not type(None))]  # type: ignore
            return await commands.run_converters(ctx, annotation, argument, param)
        elif origin is dict:
            # typing.Dict[K, V] -> typing.Tuple[K, V]
            return await _tuple_convert_flag(ctx, argument, flag, annotation.__args__)

    try:
        return await commands.run_converters(ctx, annotation, argument, param)
    except Exception as e:
        raise commands.BadFlagArgument(flag, argument, e) from e


class FlagConverter(commands.FlagConverter):
    """A drop-in replacement of `FlagConverter` from
    `discord.ext.commands`, which adds support for parsing `CodeBlock`
    and `Parens` inside of `tuple` annotations of `discord.ext.commands.flags.Flag`.
    """

    @classmethod
    async def convert(cls, ctx: commands.Context[_DECBotT], argument: str) -> Self:
        arguments = cls.parse_flags(argument)
        flags = cls.__commands_flags__

        self = cls.__new__(cls)
        for name, flag in flags.items():
            try:
                values = arguments[name]
            except KeyError:
                if flag.required:
                    raise commands.MissingRequiredFlag(flag)
                else:
                    if callable(flag.default):
                        # Type checker does not understand flag.default is a Callable
                        default = await discord.utils.maybe_coroutine(flag.default, ctx)  # type: ignore
                        setattr(self, flag.attribute, default)
                    else:
                        setattr(self, flag.attribute, flag.default)
                    continue

            if flag.max_args > 0 and len(values) > flag.max_args:
                if flag.override:
                    values = values[-flag.max_args :]
                else:
                    raise commands.TooManyFlags(flag, values)

            # Special case:
            if flag.max_args == 1:
                value = await _convert_flag(ctx, values[0], flag)
                setattr(self, flag.attribute, value)
                continue

            # Another special case, tuple parsing.
            # Tuple parsing is basically converting arguments within the flag
            # So, given flag: hello 20 as the input and Tuple[str, int] as the type hint
            # We would receive ('hello', 20) as the resulting value
            # This uses the same whitespace and quoting rules as regular parameters.
            values = [await _convert_flag(ctx, value, flag) for value in values]

            if flag.cast_to_dict:
                values = dict(values)

            setattr(self, flag.attribute, values)

        return self


__all__ = (
    "DateTimeConverter",
    "DateTime",
    "TimeConverter",
    "Time",
    "TimeDeltaConverter",
    "TimeDelta",
    "ClosedRangeConverter",
    "ClosedRange",
    "CodeBlock",
    "StringConverter",
    "String",
    "StringExprConverter",
    "StringExpr",
    "StringExprMatchConverter",
    "StringExprMatch",
    "ParensConverter",
    "Parens",
    "UnicodeEmojiConverter",
    "UnicodeEmoji",
    "ReferencedMessageConverter",
    "ReferencedMessage",
)
