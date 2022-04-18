"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

This file defines command function decorators to enhance
their behavior.
"""

import functools
import inspect
from typing import Any, Callable, Coroutine, Optional, Union

import discord
from discord.ext import commands

from snakecore.command_handler.parser import parse_command_str

FlagsMeta = type(commands.FlagConverter)


def kwarg_command(
    func: Callable[..., Coroutine[Any, Any, Any]]
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Wrap the given input function using a wrapper function that
    fakes its signature, whilst mapping `__dict__` values from an
    implicitly generated `commands.FlagConverter` subclass's object
    to the keyword arguments of the given input function. Variable
    keyword arguments are ignored.

    This is a convenience decorator that handles the creation of
    `FlagConverter` subclasses for you, whilst allowing you to
    support keyword argument syntax from a command invocation
    from Discord.

    Args:
        func (Callable[..., Coroutine[Any, Any, Any]]): The function
          to wrap.

    Returns:
        Callable[..., Coroutine[Any, Any, Any]]: The generated
          wrapper function.
    """
    sig = inspect.signature(func)

    flag_dict = {"__annotations__": {}}

    new_param_list = []

    for k, param in sig.parameters.items():
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
            new_param_list.append(
                commands.parameters.Parameter(
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
                commands.parameters.Parameter(
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

    flags_cls = FlagsMeta.__new__(
        FlagsMeta,
        func.__name__ + "_KwargOnlyFlags",
        (commands.FlagConverter,),
        attrs=flag_dict | dict(__qualname__=func.__qualname__ + "_KwargOnlyFlags"),
        delimiter="=",
    )

    new_param_list.append(
        commands.parameters.Parameter(
            "__keyword_only_flag__",
            inspect.Parameter.KEYWORD_ONLY,
            annotation=flags_cls,
        )
    )

    new_sig = commands.parameters.Signature(
        parameters=new_param_list, return_annotation=sig.return_annotation
    )

    async def kwarg_command_wrapper(*args, __keyword_only_flag__: flags_cls, **kwargs):
        return await func(*args, **(__keyword_only_flag__.__dict__ | kwargs))

    functools.update_wrapper(kwarg_command_wrapper, func)

    kwarg_command_wrapper.__signature__ = new_sig  # fake signature for wrapper function

    kwarg_command_wrapper.__original_func__ = func
    kwarg_command_wrapper.__is_kwarg_command_func__ = True
    kwarg_command_wrapper.__keyword_only_flag_class__ = flags_cls

    return kwarg_command_wrapper


def custom_parsing(
    *, inside_class: bool = False, inject_message_reference: bool = False
):
    """A decorator that registers a command function to use snakecore's custom argument
    parser. This returns a wrapper function that bypasses `discord.ext.commands`
    parsing system, parses the input string from a command invocation using the
    signature of the command function and calls the command function with the
    parsed arguments. Note that since the command invocation context
    (`commands.Context`) is always passed in as the first argument in a command,
    The first argument of the given command function will always be `commands.Context`
    object.

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

    def inner(func: Callable[..., Coroutine[Any, Any, Any]]):
        if inside_class:

            async def cmd_func_wrapper(
                self, ctx: commands.Context, *, raw_input: str = ""
            ):
                signature = cmd_func_wrapper.__wrapped_func_signature__
                setattr(ctx, "raw_command_input", raw_input)
                parsed_args, parsed_kwargs = await parse_command_str(
                    ctx,
                    raw_input,
                    signature,
                    inject_message_reference=inject_message_reference,
                )

                return await func(self, ctx, *parsed_args, **parsed_kwargs)

        else:

            async def cmd_func_wrapper(ctx: commands.Context, *, raw_input: str = ""):
                signature = cmd_func_wrapper.__wrapped_func_signature__
                setattr(ctx, "raw_command_input", raw_input)
                parsed_args, parsed_kwargs = await parse_command_str(
                    ctx,
                    raw_input,
                    signature,
                    inject_message_reference=inject_message_reference,
                )

                return await func(ctx, *parsed_args, **parsed_kwargs)

        functools.update_wrapper(cmd_func_wrapper, func)
        del cmd_func_wrapper.__wrapped__  # don't reveal wrapped function

        old_sig = inspect.signature(func)

        new_sig = old_sig.replace(
            parameters=tuple(old_sig.parameters.values())[2:]
            if inside_class
            else tuple(old_sig.parameters.values())[1:],
            return_annotation=old_sig.return_annotation,
        )

        cmd_func_wrapper.__wrapped_func_signature__ = new_sig

        return cmd_func_wrapper

    return inner
