"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file defines command function decorators to enhance
their behavior.
"""

import functools
import inspect
import sys
from typing import Any, Callable, Coroutine, Optional, Type, TypeVar, Union

import discord
from discord.ext import commands
from discord import app_commands

import snakecore.commands.bot as sc_bot
from snakecore.commands.parser import parse_command_str
from ._types import AnyCommandType

_T = TypeVar("_T")

if sys.version_info >= (3, 10):
    from typing import ParamSpec
else:
    from typing_extensions import ParamSpec

_P = ParamSpec("_P")


def flagconverter_kwargs(
    *,
    prefix: Optional[str] = "",
    delimiter: str = ":",
    cls: Type[commands.FlagConverter] = commands.FlagConverter,
) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    """Wraps a `discord.ext.commands` command function using a wrapper function
    that fakes its signature, whilst mapping the `.__dict__`s key-value pairs from
    an implicitly generated `commands.FlagConverter` subclass's object to its
    keyword-only arguments. Variable keyword arguments are ignored.

    This decorator must be applied as the very first decorator when defining a command.

    This is a convenience decorator that handles the creation of `FlagConverter`
    subclasses for you, whilst allowing you to support keyword argument syntax
    from a command invocation from Discord. Note that the output wrapper function
    will have a different signature than the input command function, and hence is
    not meant to be called directly.

    The generated wrapper function doesn't expose the wrapped command function
    using a `__wrapped__` attribute, but by using a custom `__wrapped_func__`
    attribute instead. It also has a modified `__signature__` attribute
    to customize the way a command object processes its signature, as well as
    using another direct signature.

    Args:
        prefix (Optional[str], optional): The prefix to pass to the `FlagConverter`
          subclass. Defaults to `""`.
        delimiter (Optional[str], optional): The delimiter to pass to the `FlagConverter`
          subclass. Defaults to `":"`.

    Returns:
        Callable[..., Coroutine[Any, Any, Any]]: The generated
          wrapper function.
    """

    if not issubclass(cls, commands.FlagConverter):
        raise TypeError("argument 'cls' must be a subclass of FlagConverter")

    def flagconverter_kwargs_inner_deco(func: Callable[_P, _T]) -> Callable[_P, _T]:
        sig = inspect.signature(func)

        flag_dict = {"__annotations__": {}}

        new_param_list = []

        for k, param in sig.parameters.items():
            if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
                new_param_list.append(
                    commands.Parameter(
                        param.name,
                        param.kind,
                        default=param.default,
                        annotation=param.annotation,
                    )
                )

            elif param.kind == param.VAR_POSITIONAL:
                new_annotation = param.annotation
                if isinstance(new_annotation, str):
                    if not new_annotation.startswith(
                        (
                            "commands.Greedy",
                            "discord.ext.commands.Greedy",
                            commands.Greedy.__qualname__,
                        )
                    ):
                        new_annotation = f"commands.Greedy[{param.annotation}]"

                elif not isinstance(new_annotation, commands.Greedy):
                    new_annotation = commands.Greedy(converter=param.annotation)

                new_param_list.append(
                    commands.Parameter(
                        param.name,
                        param.kind,
                        default=param.default,
                        annotation=new_annotation,
                    )
                )

            elif param.kind == param.KEYWORD_ONLY:
                flag_dict[k] = commands.flag(
                    name=k,
                    default=(
                        param.default
                        if param.default is not param.empty
                        else discord.utils.MISSING
                    ),
                )

                if param.annotation != param.empty:
                    flag_dict["__annotations__"][k] = (
                        eval(param.annotation, func.__globals__)
                        if isinstance(param.annotation, str)
                        else param.annotation
                    )

        if not flag_dict:
            raise TypeError(
                "decorated function/method must define keyword-only "
                "arguments to be used as flags"
            )

        FlagsMeta = type(commands.FlagConverter)

        flags_cls = FlagsMeta.__new__(
            FlagsMeta,
            func.__name__ + ".KeywordOnlyFlags",
            (commands.FlagConverter,),
            attrs=flag_dict
            | dict(__qualname__=func.__qualname__ + ".KeywordOnlyFlags"),
            prefix=prefix or discord.utils.MISSING,
            delimiter=delimiter or discord.utils.MISSING,
        )

        new_param_list.append(
            commands.Parameter(
                "flags",
                inspect.Parameter.KEYWORD_ONLY,
                annotation=flags_cls,
            )
        )

        new_sig = inspect.Signature(
            parameters=new_param_list, return_annotation=sig.return_annotation
        )

        async def flagconverter_kwargs_wrapper(*args, flags: flags_cls, **kwargs):  # type: ignore
            return await func(*args, **(flags.__dict__ | kwargs))  # type: ignore

        functools.update_wrapper(flagconverter_kwargs_wrapper, func)
        del (
            flagconverter_kwargs_wrapper.__wrapped__
        )  # don't reveal wrapped function here

        flagconverter_kwargs_wrapper.__signature__ = (
            new_sig  # fake signature for wrapper function
        )
        flagconverter_kwargs_wrapper.__wrapped_func__ = func
        flagconverter_kwargs_wrapper.__wrapped_func_signature__ = sig
        flagconverter_kwargs_wrapper.KeywordOnlyFlags = flags_cls

        return flagconverter_kwargs_wrapper  # type: ignore

    return flagconverter_kwargs_inner_deco  # type: ignore


def custom_parsing(
    *, inside_class: bool = False, inject_message_reference: bool = False
) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    """A decorator that registers a `discord.ext.commands` command function to
    use snakecore's custom argument parser. This returns a wrapper function that
    bypasses `discord.ext.commands` parsing system, parses the input string from
    a command invocation using the signature of the command function and calls the
    command function with the parsed arguments. The input string will remain
    available in an injected `raw_command_input` attribute of the `Context` object
    passed into the input command function.

    This decorator must be applied as the very first decorator when defining a command.

    Note that since the command invocation context
    (`commands.Context`) is always passed in as the first argument in a command,
    The first argument of the given command function will always be `commands.Context`
    object. Note that the output wrapper function will have a different signature
    than the input command function, and hence is not meant to be called directly.

    The generated wrapper function doesn't expose the wrapped function
    using a `__wrapped__` attribute, but by using a custom `__wrapped_func__`
    attribute instead.

    Args:
        inside_class (bool): Whether the input function is being defined inside a
          class, such as a `commands.Cog` subclass. Defaults to False.
        inject_message_reference (bool): Whether the referenced message of the
          command invocation message should be, if available, injected as the
          first argument of a command function if that function's signature allows
          for it. Defaults to False.

    Returns:
        Callable[..., Coroutine[Any, Any, Any]]: A wrapper callable object.
    """

    def custom_parsing_inner_deco(func: Callable[_P, _T]) -> Callable[_P, _T]:
        if inside_class:

            async def cmd_func_wrapper(  # type: ignore
                self, ctx: commands.Context, *, raw_command_input: str = ""
            ):
                signature = cmd_func_wrapper.__wrapped_func_signature__
                setattr(ctx, "raw_command_input", raw_command_input)
                parsed_args, parsed_kwargs = await parse_command_str(
                    ctx,
                    raw_command_input,
                    signature,
                    inject_message_reference=inject_message_reference,
                )

                return await func(self, ctx, *parsed_args, **parsed_kwargs)  # type: ignore

        else:

            async def cmd_func_wrapper(
                ctx: commands.Context, *, raw_command_input: str = ""
            ):
                signature = cmd_func_wrapper.__wrapped_func_signature__
                setattr(ctx, "raw_command_input", raw_command_input)
                parsed_args, parsed_kwargs = await parse_command_str(
                    ctx,
                    raw_command_input,
                    signature,
                    inject_message_reference=inject_message_reference,
                )

                return await func(ctx, *parsed_args, **parsed_kwargs)  # type: ignore

        functools.update_wrapper(cmd_func_wrapper, func)
        del cmd_func_wrapper.__wrapped__  # don't reveal wrapped function here

        old_sig = inspect.signature(func)

        new_sig = old_sig.replace(
            parameters=tuple(old_sig.parameters.values())[2:]
            if inside_class
            else tuple(old_sig.parameters.values())[1:],
            return_annotation=old_sig.return_annotation,
        )

        cmd_func_wrapper.__wrapped_func__ = func
        cmd_func_wrapper.__wrapped_func_signature__ = new_sig

        return cmd_func_wrapper  # type: ignore

    return custom_parsing_inner_deco  # type: ignore


def with_extras(**extras: Any) -> Callable[[AnyCommandType], AnyCommandType]:
    """A convenience decorator for adding data into the `extras`
    attribute of a command object.

    Args:
        **extras: The extras.
    """

    def inner_with_extras(cmd: AnyCommandType) -> AnyCommandType:
        cmd.extras.update(extras)
        return cmd

    return inner_with_extras


def with_config_kwargs(setup: Callable[_P, Any]) -> Callable[[commands.Bot], Any]:
    """A convenience decorator that allows extension `setup()` functions to support
    receiving arguments from the `Ext(AutoSharded)Bot.get_extension_config(...)`
    function's output mapping, if available.

    Args:
        func (Callable[[Union[sc_bot.ExtBot, sc_bot.ExtAutoShardedBot], ...], None]):
          The `setup()` function.
    """

    async def setup_wrapper(bot: commands.Bot):
        if isinstance(bot, (sc_bot.ExtBot, sc_bot.ExtAutoShardedBot)):
            config_mapping = bot.get_extension_config(setup.__module__, {})
            return await setup(
                bot,  # type: ignore
                **{
                    param.name: config_mapping[param.name]
                    for param in tuple(inspect.signature(setup).parameters.values())[1:]
                    if param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY)
                    and param.name in config_mapping
                },
            )

        return await setup(bot)  # type: ignore

    return setup_wrapper
