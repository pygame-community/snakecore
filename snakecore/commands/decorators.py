"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file defines command function decorators to enhance
their behavior.
"""

import functools
import inspect
import types
from typing import Any, Callable, ParamSpec, TypeVar, Union

import discord
from discord.ext import commands
from discord.ext.commands.flags import FlagsMeta, Flag
import snakecore.commands as sc_commands
from .converters import FlagConverter as _FlagConverter
from ._types import AnyCommandType

_T = TypeVar("_T")

_P = ParamSpec("_P")

UnionGenericAlias = type(Union[str, int])


def flagconverter_kwargs(
    *,
    prefix: str | None = "",
    delimiter: str = ":",
    cls: type[commands.FlagConverter] = _FlagConverter,
) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    """Wraps a `discord.ext.commands` command function using a wrapper function
    that fakes its signature, whilst mapping the `.__dict__`s key-value pairs from
    an implicitly generated `FlagConverter` subclass's instance to its keyword-only
    arguments. In essence, this allows you to define keyword-only arguments
    in your command callback, which will automatically be treated as `FlagConverter`
    flags.

    Variable keyword arguments (`**kwargs`) are ignored.

    This decorator must be applied as the very first decorator when defining a command.

    This is a convenience decorator that handles the creation of `FlagConverter`
    subclasses for you. Note that The output wrapper function
    will have a less restrictive signature than the input command function.
    If called directly, the implicitly generated `__flags__` keyword argument
    should not be specified.

    The generated wrapper function doesn't expose the wrapped command function
    using a `__wrapped__` attribute, but by using a custom `__wrapped_func__`
    attribute instead. It also has a modified `__signature__` attribute
    to customize the way a command object processes its signature, as well as
    using another direct signature.

    Parameters
    ----------
    prefix : str | None, optional
        The prefix to pass to the `FlagConverter` subclass. Defaults to `""`.
        delimiter (str | None, optional): The delimiter to pass to the `FlagConverter`
          subclass. Defaults to `":"`.
        cls (type[commands.FlagConverter], optional): The class to use as a base class for
          the resulting FlagConverter class to generate. Useful for implementing custom flag
          parsing functionality. If specified and the class is not a subclass of
          `snakecore.commands.converters.FlagConverter`, flags with annotation `tuple[T[, ...]]`
          where `T` is `CodeBlock` or `Parens` will fail to parse correctly.

    Returns
    -------
    Callable[..., Coroutine[Any, Any, Any]]:
        The generated wrapper function.
    """

    if not issubclass(cls, commands.FlagConverter):
        raise TypeError("argument 'cls' must be a subclass of FlagConverter")

    def flagconverter_kwargs_inner_deco(func: Callable[_P, _T]) -> Callable[_P, _T]:
        sig = inspect.signature(func)

        flag_dict = {"__annotations__": {}, "__module__": func.__module__}

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
                    evaluated_anno = eval(new_annotation, func.__globals__)
                    if not isinstance(
                        evaluated_anno,
                        commands.Greedy,
                    ):
                        if (
                            isinstance(
                                evaluated_anno, (UnionGenericAlias, types.UnionType)
                            )
                            and type(None) in evaluated_anno.__args__
                            or evaluated_anno in (None, type(None), str)
                        ):
                            raise TypeError(
                                "Cannot have None, NoneType or typing.Optional/or "
                                "UnionType with None as an annotation for "
                                f"'*{param.name}' when using flagconverter decorator"
                            )
                        else:
                            new_annotation = f"commands.Greedy[{param.annotation}]"

                elif not (
                    new_annotation is param.empty
                    or isinstance(new_annotation, commands.Greedy)
                ):
                    if (
                        isinstance(new_annotation, (UnionGenericAlias, types.UnionType))
                        and type(None) in new_annotation.__args__
                        or new_annotation in (None, type(None), str)
                    ):
                        raise TypeError(
                            "Cannot have None, NoneType or typing.Optional/or "
                            "UnionType with None as an annotation for "
                            f"'*{param.name}' when using flagconverter decorator"
                        )
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
                if isinstance(param.default, Flag):
                    flag_dict[k] = param.default
                else:
                    flag_dict[k] = commands.flag(
                        name=k,
                        default=(
                            param.default
                            if param.default is not param.empty
                            else discord.utils.MISSING
                        ),
                    )

                if param.annotation is not param.empty:
                    flag_dict["__annotations__"][k] = param.annotation

        if not flag_dict["__annotations__"]:
            raise TypeError(
                "decorated function/method must define keyword-only "
                "arguments to be used as flags"
            )

        flags_cls = FlagsMeta.__new__(
            FlagsMeta,
            "KeywordOnlyFlags",
            (cls,),
            attrs=flag_dict
            | dict(__qualname__=f"{func.__qualname__}.KeywordOnlyFlags"),
            prefix=prefix or discord.utils.MISSING,
            delimiter=delimiter or discord.utils.MISSING,
        )

        new_param_list.append(
            commands.Parameter(  # add generated FlagConverter class as parameter
                "_flags_",
                inspect.Parameter.KEYWORD_ONLY,
                annotation=flags_cls,
            )
        )

        new_sig = inspect.Signature(
            parameters=new_param_list, return_annotation=sig.return_annotation
        )

        async def wrapper(*args, _flags_: flags_cls = None, **kwargs):  # type: ignore
            return await func(*args, **(_flags_.__dict__ if _flags_ is not None else {} | kwargs))  # type: ignore

        # shallow-copy wrapper function to override __globals__
        flagconverter_kwargs_wrapper: Callable[_P, _T] = types.FunctionType(
            wrapper.__code__,
            func.__globals__,
            name=func.__name__,
            argdefs=wrapper.__defaults__,
            closure=wrapper.__closure__,
        )  # type: ignore

        functools.update_wrapper(flagconverter_kwargs_wrapper, func)

        del (
            flagconverter_kwargs_wrapper.__wrapped__
        )  # don't reveal wrapped function here

        flagconverter_kwargs_wrapper.__signature__ = (
            new_sig  # fake signature for wrapper function
        )
        flagconverter_kwargs_wrapper.__kwdefaults__ = wrapper.__kwdefaults__
        flagconverter_kwargs_wrapper.__wrapped_func__ = func
        flagconverter_kwargs_wrapper.__wrapped_func_signature__ = sig
        flagconverter_kwargs_wrapper.KeywordOnlyFlags = flags_cls

        return flagconverter_kwargs_wrapper  # type: ignore

    return flagconverter_kwargs_inner_deco  # type: ignore


def with_extras(**extras: Any) -> Callable[[AnyCommandType], AnyCommandType]:
    """A convenience decorator for adding data into the `extras`
    attribute of a `discord.ext.commands.Command` object.

    Parameters
    ----------
    **extras
        The extras.
    """

    def inner_with_extras(cmd: AnyCommandType) -> AnyCommandType:
        cmd.extras.update(extras)
        return cmd

    return inner_with_extras


def with_config_kwargs(
    setup_or_teardown: Callable[_P, Any]
) -> Callable[[commands.Bot], Any]:
    """A convenience decorator that allows extension `setup()` or `teardown()`
    functions to support receiving arguments from the
    `snakecore.commands.(AutoSharded)Bot.get_extension_config(...)` function's
    output mapping, if available.

    Parameters
    ----------
    setup_or_teardown : Callable[[snakecore.commands.Bot | snakecore.commands.AutoShardedBot, ...], None]
        The `setup()` or `teardown()` function.
    """

    async def setup_teardown_wrapper(bot: commands.Bot):
        if isinstance(bot, (sc_commands.Bot, sc_commands.AutoShardedBot)):
            config_mapping = bot.get_extension_config(setup_or_teardown.__module__, {})
            return await setup_or_teardown(
                bot,  # type: ignore
                **{
                    param.name: config_mapping[param.name]
                    for param in tuple(
                        inspect.signature(setup_or_teardown).parameters.values()
                    )[1:]
                    if param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY)
                    and param.name in config_mapping
                },
            )

        return await setup(bot)  # type: ignore

    return setup_teardown_wrapper


__all__ = (
    "flagconverter_kwargs",
    "with_extras",
    "with_config_kwargs",
)
