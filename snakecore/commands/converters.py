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
    Iterator,
    Literal,
    Optional,
    Sequence,
    SupportsIndex,
    Tuple,
    TypeVar,
    Union,
    overload,
)
from typing_extensions import Self, TypeVarTuple, Unpack

import discord.app_commands
import discord
from discord.ext import commands
from discord.ext.commands import flags as _flags
from discord.ext.commands.view import StringView

import snakecore
from snakecore.utils import regex_patterns
from .bot import Bot, AutoShardedBot

_T = TypeVar("_T")
_T_co = TypeVar("_T_co", covariant=True)
_PT = TypeVarTuple("_PT")
DECBotT = Union[Bot, AutoShardedBot]
DECDECBotT = Union[commands.Bot, commands.AutoShardedBot]


class DateTimeConverter(commands.Converter[datetime.datetime]):
    """A converter that parses UNIX/ISO timestamps to `datetime` objects.

    Syntax:
        - `<t:{6969...}[:t|T|d|D|f|F|R]> -> datetime(seconds=6969...)`
        - `YYYY-MM-DD[*HH[:MM[:SS[.fff[fff]]]][+HH:MM[:SS[.ffffff]]]] -> datetime`
    """

    async def convert(
        self, ctx: commands.Context[DECBotT], argument: str
    ) -> datetime.datetime:
        arg = argument.strip()

        if snakecore.utils.is_markdown_timestamp(arg):
            arg = snakecore.utils.extract_markdown_timestamp(arg)
            try:
                return datetime.datetime.fromtimestamp(arg)
            except ValueError as v:
                raise commands.BadArgument(
                    f"failed to construct datetime: {v.__class__.__name__}:{v!s}"
                ) from v
        else:
            arg = arg.removesuffix("Z")

        try:
            return datetime.datetime.fromisoformat(arg)
        except ValueError as v:
            raise commands.BadArgument(
                f"failed to construct datetime: {v.__class__.__name__}:{v!s}"
            ) from v


class IntervalConverter(commands.Converter[range]):
    """A converter that parses closed integer intervals to Python `range` objects.
    Both a hyphen-based notation is supported (as used in English phrases) which always
    includes endpoints, as well as a mathematical notation using comparison operators.

    Syntax:
        - `start-stop -> range(start, stop+1)`
        - `start-stop|[+]step -> range(start, stop+1, +step)` *
        - `start-stop|-step -> range(start, stop+1, -step)` *

        - `start>|>=|≥x>|>=|≥stop -> range(start[+1], stop[+1])`
        - `start>|>=|≥x>|>=|≥stop|[+]step -> range(start[+1], stop[+1], +step)` *
        - `start>|>=|≥x>|>=|≥stop|-step -> range(start[+1], stop[+1], -step)` *

    *The last '|' is considered as part of the syntax.
    """

    COMPARISON_NOTATION = re.compile(
        r"(-?\d+)([<>]=?|[≤≥])[a-zA-Z]([<>]=?|[≤≥])(-?\d+)(?:\|([-+]?\d+))?"
    )
    HYPHEN_NOTATION = re.compile(r"(-?\d+)-(-?\d+)(?:\|([-+]?\d+))?")

    _comparison_inverses = {
        ">": "<",
        "<": ">",
        "<=": ">=",
        ">=": "<=",
        "≤": "≥",
        "≥": "≤",
    }

    async def convert(self, ctx: commands.Context[DECBotT], argument: str) -> range:
        hyphen_match = self.HYPHEN_NOTATION.match(argument)
        comparison_match = self.COMPARISON_NOTATION.match(argument)

        if not (hyphen_match or comparison_match):
            raise commands.BadArgument(
                "failed to construct closed integer interval from argument "
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
            step_specified = bool(hyphen_match.group(3))

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
                        f"argument {argument!r} is not a valid closed integer interval"
                    )

                if stop_comp in ("<=", "≤"):
                    stop += 1
                elif stop_comp != "<":  # default used in range class
                    raise commands.BadArgument(
                        f"argument {argument!r} is not a valid closed integer interval"
                    )

            elif raw_start >= raw_stop:
                if start_comp == ">":
                    start -= 1
                elif start_comp not in (">=", "≥"):  # default used in range class
                    raise commands.BadArgument(
                        f"argument {argument!r} is not a valid closed integer interval"
                    )

                if stop_comp in (">=", "≥"):  # default used in range class
                    stop -= 1
                elif stop_comp != ">":
                    raise commands.BadArgument(
                        f"argument {argument!r} is not a valid closed integer interval"
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
                "failed to construct closed integer interval from argument "
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

    This converter does not parse successfully if specified inside a tuple
    annotation of `discord.ext.commands.flags.Flag`, inside a subclass of
    `discord.ext.commands`'s default `FlagConverter`. To migitate this, it
    is recommended to subclass `snakecore.commands.converters.FlagConverter`
    instead.
    """

    _MULTILINE_PATTERN = re.compile(regex_patterns.CODE_BLOCK)
    _INLINE_PATTERN = re.compile(regex_patterns.INLINE_CODE_BLOCK)

    def __init__(
        self, code: str, language: Optional[str] = None, inline: Optional[bool] = None
    ):
        self.code = code
        self.language = language
        self.inline = inline if inline is not None else not (language or "\n" in code)

    @classmethod
    async def convert(cls, ctx: commands.Context[DECBotT], argument: str) -> Self:
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


class StringConverter:
    """A converter that parses string literals to string objects,
    thereby handling escaped characters and removing trailing quotes.

    Can be used over the default `str` converter for less greedy argument
    parsing.

    Syntax:
        - `"'abc'" -> 'abc'`
        - `'"ab\\"c"' -> 'ab"c'`
    """

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

    @classmethod
    async def convert(cls, ctx: commands.Context[DECBotT], argument: str) -> str:
        try:
            s = cls.escape(argument)
        except ValueError as verr:
            raise commands.BadArgument(
                f"Escaping input argument failed: {verr}"
            ) from verr
        s = s.strip()

        if (s.startswith('"') and s.endswith('"')) or (
            s.startswith("'") and s.endswith("'")
        ):
            s = s[1:-1]
        return s

    @classmethod
    def escape(cls, string: str) -> str:
        """
        Convert a "raw" string to one where characters are escaped
        """
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
                            "Invalid escape character",
                            f"Invalid unicode escape: `{esc}` in string",
                        )
                    index += n

                elif char in cls._ESCAPES:
                    # general escapes
                    newstr.append(cls._ESCAPES[char])
                else:
                    raise ValueError(
                        "Invalid escape character",
                        f"Unknown escape `\\{char}`",
                    )
            else:
                newstr.append(char)

        return "".join(newstr)


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

    Syntax:
        - `"( 1 2 4 5.5 )" -> (1, 2, 4, 5.5)`
        - `'( 1 ( 4 ) () ( ( 6 ( "a" ) ) ) 0 )' -> (1, (4,), (), ((6,("a",),),), 0)`
    """

    OPENING = "("
    CLOSING = ")"

    def __init__(self, converters) -> None:
        super().__init__()
        self.converters = converters
        self.parens_depth = 1
        self._increment_nested_parens_depth()

    def _increment_nested_parens_depth(self):
        for converter in self.converters:
            if isinstance(converter, self.__class__):
                converter.parens_depth = self.parens_depth + 1
                converter._increment_nested_parens_depth()

    def __class_getitem__(cls, params: Any):
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
                converter = Union[args]  # type: ignore

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
            return slice(bstart, bend)
        for i, s in enumerate(string):
            if s == opening:
                scope_level += 1
                if scope_level == 0:
                    bstart = i
            elif s == closing:
                if scope_level == 0:
                    bend = i + 1
                    return slice(bstart, bend)
                scope_level -= 1
        return slice(bstart, bend)

    async def convert(
        self, ctx: commands.Context[DECBotT], argument: str
    ) -> tuple[Any, ...]:
        if not argument.startswith(self.OPENING):
            raise commands.BadArgument(
                "Parsing parenthesized argument failed "
                f"(at depth {self.parens_depth}): Failed to find parenthesized region, must be enclosed as "
                f"'{self.OPENING} ... {self.CLOSING}'"
            )
        elif argument == f"{self.OPENING}{self.CLOSING}":
            return ()

        if len(argument) > 1 and not argument[1].isspace():
            raise commands.BadArgument(
                "Parsing parenthesized argument failed "
                f"(at depth {self.parens_depth}): Content of parenthesized "
                "region must be surrounded by whitespace"
            )

        view: StringView = getattr(ctx, "_current_view", ctx.view)

        parsed_argument = argument.strip("\n").strip()
        parens_slice = self._find_parenthesized_region(
            view.buffer[view.index - len(parsed_argument) :],
            self.OPENING,
            self.CLOSING,
        )
        if parens_slice.start == parens_slice.stop == 0:
            raise commands.BadArgument(
                "Parsing parenthesized argument failed "
                f"(at depth {self.parens_depth}): Could not find parenthesized "
                "region, must be enclosed as "
                f"'{self.OPENING} ... {self.CLOSING}'"
            )

        parens_slice = slice(
            parens_slice.start + view.index,
            parens_slice.stop + view.index,
        )  # offset slice to match the view's buffer string
        parsed_argument = view.buffer[parens_slice]

        old_previous = view.previous
        old_index = view.index
        original_parameter = ctx.current_parameter
        fake_parameter = commands.parameter()

        view.index -= len(argument)
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
                ctx.current_argument = fake_argument = view.get_quoted_word()

            except commands.ArgumentParsingError:

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
                transformed = await commands.run_converters(
                    ctx, converter, fake_argument, fake_parameter  # type: ignore
                )  # fake_argument won't become None
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
                in fake_parameter.annotation.__args__  # check for Optional[...]  # type: ignore
                and transformed is None
            ):
                view.index = previous_index  # view.undo() does not revert properly for Optional[...]
                view.previous = previous_previous

        ctx.current_parameter = original_parameter
        return tuple(outputs)

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        pass

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


DateTime = Annotated[datetime.datetime, DateTimeConverter]
Interval = Annotated[range, IntervalConverter]

if TYPE_CHECKING:
    String = str
    Parens = tuple
else:
    String = StringConverter
    Parens = ParensConverter


async def tuple_convert_all(
    ctx: commands.Context[DECBotT], argument: str, flag: commands.Flag, converter: Any
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


async def tuple_convert_flag(
    ctx: commands.Context[DECBotT], argument: str, flag: commands.Flag, converters: Any
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


async def convert_flag(
    ctx: commands.Context[DECBotT],
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
                return await tuple_convert_all(
                    ctx, argument, flag, annotation.__args__[0]
                )
            else:
                return await tuple_convert_flag(
                    ctx, argument, flag, annotation.__args__
                )
        elif origin is list:
            # typing.List[x]
            annotation = annotation.__args__[0]
            return await convert_flag(ctx, argument, flag, annotation)
        elif origin is Union and type(None) in annotation.__args__:
            # typing.Optional[x]
            annotation = Union[tuple(arg for arg in annotation.__args__ if arg is not type(None))]  # type: ignore
            return await commands.run_converters(ctx, annotation, argument, param)
        elif origin is dict:
            # typing.Dict[K, V] -> typing.Tuple[K, V]
            return await tuple_convert_flag(ctx, argument, flag, annotation.__args__)

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
    async def convert(cls, ctx: commands.Context[DECBotT], argument: str) -> Self:
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
                value = await convert_flag(ctx, values[0], flag)
                setattr(self, flag.attribute, value)
                continue

            # Another special case, tuple parsing.
            # Tuple parsing is basically converting arguments within the flag
            # So, given flag: hello 20 as the input and Tuple[str, int] as the type hint
            # We would receive ('hello', 20) as the resulting value
            # This uses the same whitespace and quoting rules as regular parameters.
            values = [await convert_flag(ctx, value, flag) for value in values]

            if flag.cast_to_dict:
                values = dict(values)

            setattr(self, flag.attribute, values)

        return self
