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
    Any,
    Generic,
    Iterator,
    Literal,
    Optional,
    Tuple,
    TypeVar,
    Union,
)
from typing_extensions import TypeVarTuple, Unpack

import discord
from discord.ext import commands

import snakecore
from snakecore.utils import regex_patterns

T = TypeVar("T")

_quotes = {
    '"': '"',
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


def _find_start_quote(string: str) -> Optional[str]:
    if not string:
        return None

    start = string[0]
    for start_quote in _quotes.keys():
        if start_quote == start:
            return start_quote

    return None


class DateTime(commands.Converter[datetime.datetime]):
    """A converter that parses UNIX/ISO timestamps to `datetime.datetime` objects.

    Syntax:
        - `<t:{6969...}[:t|T|d|D|f|F|R]> -> datetime.datetime(seconds=6969...)`
        - `YYYY-MM-DD[*HH[:MM[:SS[.fff[fff]]]][+HH:MM[:SS[.ffffff]]]] -> datetime.datetime`
    """

    async def convert(self, ctx: commands.Context, argument: str) -> datetime.datetime:
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


class RangeObject(commands.Converter[range]):
    """A converter that parses integer range values to `range` objects.

    Syntax:
        - `[start:stop] -> range(start, stop)`
        - `[start:stop:step] -> range(start, stop, step)`
    """

    async def convert(self, ctx: commands.Context, argument: str) -> range:
        if not argument.startswith("[") or not argument.endswith("]"):
            raise commands.BadArgument("ranges must begin and end with square brackets")

        try:
            splits = [int(i.strip()) for i in argument[6:-1].split(":")]

            if splits and len(splits) <= 3:
                return range(*splits)
        except (ValueError, TypeError) as v:
            raise commands.BadArgument(
                f"failed to construct range: {argument!r}"
            ) from v

        raise commands.BadArgument(f"invalid range string: {argument!r}")


class CodeBlock:
    """An object that represents a fenced or inline markdown code block.
    Can be used as a converter, which returns an instance of this class.
    The instance attributes can be used to obtain the code block contents.
    To get the raw code block text from an instance, convert it into a string.
    """

    multiline_pattern = re.compile(regex_patterns.CODE_BLOCK)
    inline_pattern = re.compile(regex_patterns.INLINE_CODE_BLOCK)

    def __init__(self, code: str, language: Optional[str] = None, inline: bool = False):
        self.code = code
        self.language = language
        self.inline = inline

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str):

        if argument.startswith("```"):

            if not argument.endswith("```") or (
                argument.endswith("```") and argument == "```"
            ):

                parsed_argument = argument.strip("\n").strip()
                multiline_match = cls.multiline_pattern.match(
                    ctx.view.buffer, pos=ctx.view.index - len(parsed_argument)
                )

                if multiline_match is not None:
                    parsed_argument = ctx.view.buffer[slice(*multiline_match.span())]
                    ctx.view.index = multiline_match.end()

                argument = parsed_argument

        elif argument.startswith("`"):

            if not argument.endswith("`") or (
                argument.endswith("`") and argument == "`"
            ):

                parsed_argument = argument.strip("\n").strip()
                inline_match = cls.inline_pattern.match(
                    ctx.view.buffer, pos=ctx.view.index - len(parsed_argument)
                )

                if inline_match is not None:
                    parsed_argument = ctx.view.buffer[slice(*inline_match.span())]
                    ctx.view.index = inline_match.end()

                argument = parsed_argument

        try:
            return cls.from_markdown(argument)
        except (TypeError, ValueError) as err:
            raise commands.BadArgument(
                "argument must be a string containing an inline or multiline markdown code block"
            ) from err

    @classmethod
    def from_markdown(cls, markdown: str):

        if not isinstance(markdown, str):
            raise TypeError(
                "argument 'markdown' must be of type 'str' containing a markdown code block, "
                f"not {markdown.__class__.__name__}"
            )
        elif not (markdown.startswith("`") and markdown.endswith("`")):
            raise ValueError(
                "argument 'markdown' does not contain a markdown code blockx"
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
            else f"```{self.language or ''}\n{self.code}\n```"
        )


class String(commands.Converter[str]):
    """A converter that parses string literals to string objects,
    thereby handling escaped characters and removing trailing quotes.

    Syntax:
        - `"'abc'" -> 'abc'`
        - `'"ab\\"c"' -> 'ab"c'`
    """

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

    async def convert(self, ctx: commands.Context, argument: str):
        try:
            s = self.escape(argument)
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

    def escape(self, string: str):
        """
        Convert a "raw" string to one where characters are escaped
        """
        index = 0
        newstr = ""
        while index < len(string):
            char = string[index]
            index += 1
            if char == "\\":
                # got a backslash, handle escapes
                char = string[index]
                index += 1
                if char.lower() in ["x", "u"]:  # these are unicode escapes
                    if char.lower() == "x":
                        n = 2
                    else:
                        n = 4 if char == "u" else 8

                    var = string[index : index + n]
                    try:
                        if len(var) != n:
                            n = len(var)
                            raise ValueError("invalid quoted string")

                        newstr += chr(int(var, base=16))
                    except (ValueError, OverflowError):
                        esc = string[index - 2 : index + n]
                        raise ValueError(
                            "Invalid escape character",
                            f"Invalid unicode escape: `{esc}` in string",
                        )
                    index += n

                elif char in self.ESCAPES:
                    # general escapes
                    newstr += self.ESCAPES[char]
                else:
                    raise ValueError(
                        "Invalid escape character",
                        f"Unknown escape `\\{char}`",
                    )
            else:
                newstr += char

        return newstr


def find_parenthesized_region(string: str, opening: str = "(", closing: str = ")"):
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


class _Parens(commands.Converter[tuple]):

    OPENING_BRACKET = "("
    CLOSING_BRACKET = ")"

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

    async def convert(self, ctx: commands.Context, argument: str) -> tuple[Any, ...]:
        if not argument.startswith(self.OPENING_BRACKET):
            raise commands.BadArgument(
                "Parsing parenthesized argument failed "
                f"(at depth {self.parens_depth}): Failed to find parenthesized region, must be enclosed as "
                f"'{self.OPENING_BRACKET} ... {self.CLOSING_BRACKET}'"
            )
        elif argument == f"{self.OPENING_BRACKET}{self.CLOSING_BRACKET}":
            return ()

        if len(argument) > 1 and not argument[1].isspace():
            raise commands.BadArgument(
                "Parsing parenthesized argument failed "
                f"(at depth {self.parens_depth}): Content of parenthesized "
                "region must be surrounded by whitespace"
            )

        parsed_argument = argument.strip("\n").strip()
        parens_slice = self._find_parenthesized_region(
            ctx.view.buffer[ctx.view.index - len(parsed_argument) :],
            self.OPENING_BRACKET,
            self.CLOSING_BRACKET,
        )
        if parens_slice.start == parens_slice.stop == 0:
            raise commands.BadArgument(
                "Parsing parenthesized argument failed "
                f"(at depth {self.parens_depth}): Could not find parenthesized "
                "region, must be enclosed as "
                f"'{self.OPENING_BRACKET} ... {self.CLOSING_BRACKET}'"
            )

        parens_slice = slice(
            parens_slice.start + ctx.view.index,
            parens_slice.stop + ctx.view.index,
        )  # offset slice to match the view's buffer string
        parsed_argument = ctx.view.buffer[parens_slice]

        old_previous = ctx.view.previous
        old_index = ctx.view.index
        original_parameter = ctx.current_parameter
        fake_parameter = commands.parameter()

        ctx.view.index -= len(argument)
        ctx.view.read(1)  # move right after starting bracket '('

        outputs = []
        converter_index = 0

        is_variadic = self.converters[-1] is Ellipsis

        while True:
            if ctx.view.index >= parens_slice.stop - 1:
                break

            ctx.view.skip_ws()

            if (
                ctx.view.current == self.CLOSING_BRACKET
                and converter_index < len(self.converters) - 1
            ):
                # reset any StringView changes done by this converter
                ctx.current_parameter = original_parameter
                ctx.current_argument = argument
                ctx.view.previous = old_previous
                ctx.view.index = old_index
                raise commands.BadArgument(
                    "Parsing parenthesized argument failed "
                    f"(at depth {self.parens_depth}): Too few arguments in "
                    "parenthesized region"
                )

            if converter_index == len(self.converters) - 1 and is_variadic:
                if ctx.view.current == self.CLOSING_BRACKET:
                    ctx.view.get()
                    break

                converter_index -= 1
            elif (
                converter_index == len(self.converters)
                and ctx.view.current == self.CLOSING_BRACKET
            ):  # end of parenthesized region
                ctx.view.get()
                break

            try:
                converter = self.converters[converter_index]
            except IndexError:
                ctx.current_parameter = original_parameter
                ctx.current_argument = argument
                ctx.view.previous = old_previous
                ctx.view.index = old_index
                raise commands.BadArgument(
                    "Parsing parenthesized argument failed "
                    f"(at depth {self.parens_depth}): Too many arguments in "
                    "parenthesized region"
                )

            converter_index += 1

            fake_parameter._annotation = converter
            ctx.current_parameter = fake_parameter

            previous_previous = ctx.view.previous
            previous_index = ctx.view.index
            try:
                ctx.current_argument = fake_argument = ctx.view.get_quoted_word()

            except commands.ArgumentParsingError:

                ctx.current_parameter = original_parameter
                ctx.current_argument = argument
                ctx.view.previous = old_previous
                ctx.view.index = old_index
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
                ctx.view.previous = old_previous
                ctx.view.index = old_index
                if isinstance(converter, self.__class__):
                    raise
                elif (
                    fake_argument
                    and len(fake_argument) > 1
                    and (
                        fake_argument.startswith(self.OPENING_BRACKET)
                        and not fake_argument[1].isspace()
                        or fake_argument.endswith(self.CLOSING_BRACKET)
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
                ctx.view.index = previous_index  # view.undo() does not revert properly for Optional[...]
                ctx.view.previous = previous_previous

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


if TYPE_CHECKING:
    _PT = TypeVarTuple("_PT")

    class Parens(Tuple[Unpack[_PT]]):
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

        Syntax:
            - `"( 1 2 4 5.5 )" -> (1, 2, 4, 5.5)`
            - `'( 1 ( 4 ) () ( ( 6 ( "a" ) ) ) 0 )' -> (1, (4,), (), ((6,("a",),),), 0)`

        """

        def __init__(self, converters: Tuple[Unpack[_PT]]) -> None:
            ...

        def __iter__(self) -> Iterator[Any]:
            ...

        def __class_getitem__(cls, params: tuple[Unpack[_PT]]) -> "Parens[Unpack[_PT]]":
            ...

        async def convert(
            self, ctx: commands.Context, argument: str
        ) -> tuple[Any, ...]:
            ...

        def __call__(self, *args: Any, **kwds: Any) -> Any:
            ...

else:
    _Parens.__name__ = "Parens"
    Parens = _Parens


class QuotedString(commands.Converter[str]):
    """A simple converter that enforces a quoted string as an argument.
    It removes leading and ending single or doble quotes. If those quotes
    are not found, exceptions are raised.

    Syntax:
        - `"abc" -> str("abc")`
        - `'abc' -> str('abc')`
    """

    async def convert(self, ctx: commands.Context, argument: str) -> str:
        passed = False
        if argument:
            start_quote = _find_start_quote(argument)
            if start_quote:
                if argument.endswith(_quotes[start_quote]):
                    passed = True
                else:
                    raise commands.BadArgument(
                        f"argument string quote '{start_quote}' was not "
                        f"closed with '{_quotes[start_quote]}'"
                    )

        if not passed:
            raise commands.BadArgument(
                "argument string is not properly quoted with "
                f"'{start_quote}{_quotes[start_quote]}'"
            )

        return argument[1:-1]
