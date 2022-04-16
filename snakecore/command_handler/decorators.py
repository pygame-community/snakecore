from __future__ import annotations
from ast import Call

import functools
import inspect
from re import T
import types
from typing import Any, Callable, Coroutine, Optional, Union

import discord
from discord.ext import commands
from discord.ext.commands import flags

from snakecore.command_handler.parsing.parser import parse_command_str


def kwarg_command(func: Callable[..., Coroutine[Any, Any, Any]]):
    sig = inspect.signature(func)

    flag_dict = {"__annotations__": {}}

    new_param_list = []
    # var_kwargs = {"name": None, "parameter": None}

    for k, param in sig.parameters.items():
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
            new_param_list.append(commands.parameters.Parameter(param.name, param.kind, default=param.default, annotation=param.annotation))

        elif param.kind == param.VAR_POSITIONAL:
            new_annotation = param.annotation
            if isinstance(new_annotation, str):
                if not new_annotation.startswith(("commands.Greedy", "discord.ext.commands.Greedy", commands.Greedy.__qualname__)):
                    new_annotation = f"commands.Greedy[{param.annotation}]"

            elif not isinstance(new_annotation, commands.Greedy):
                new_annotation = commands.Greedy(converter=param.annotation)

            new_param_list.append(commands.parameters.Parameter(param.name, param.kind, default=param.default, annotation=new_annotation))
        
        elif param.kind == param.KEYWORD_ONLY:
            flag_dict[k] = commands.flag(name=k, default=(param.default if param.default is not param.empty else discord.utils.MISSING))
            
            if param.annotation != param.empty:
                flag_dict["__annotations__"][k] = eval(param.annotation, func.__globals__) if isinstance(param.annotation, str) else param.annotation
        
        # elif param.kind == param.VAR_KEYWORD:
        #     var_kwargs["name"] = k
        #     var_kwargs["parameter"] = param

        #     flag_dict[k] = commands.flag(name=k, default=lambda ctx: {})
            
        #     if param.annotation != param.empty:
        #         flag_dict["__annotations__"][k] = eval(param.annotation, func.__globals__) if isinstance(param.annotation, str) else param.annotation
    
    flags_cls = flags.FlagsMeta.__new__(flags.FlagsMeta, func.__name__+"_KwargOnlyFlags", (commands.FlagConverter,), attrs=flag_dict | dict(__qualname__=func.__qualname__ + "_KwargOnlyFlags"), delimiter="=")

    new_param_list.append(commands.parameters.Parameter("__keyword_only_flag__", inspect.Parameter.KEYWORD_ONLY, annotation=flags_cls))
    
    new_sig = commands.parameters.Signature(parameters=new_param_list, return_annotation=sig.return_annotation)
    
    async def kwarg_command_wrapper(*args, __keyword_only_flag__: flags_cls, **kwargs):
        #print("inside wrapper. args:", args, "flag:", __keyword_only_flag__)
        #last_pair_tuple = next(reversed(__keyword_only_flag__.__dict__.items()))
        last_pair_dict = {}
        
        #if last_pair_tuple[0] == var_kwargs["name"]:
        #    last_pair_dict = last_pair_tuple[1]
        #    del __keyword_only_flag__.__dict__[var_kwargs["name"]]
        #
        return await func(*args, **(__keyword_only_flag__.__dict__ | last_pair_dict | kwargs))

    
    functools.update_wrapper(kwarg_command_wrapper, func)

    kwarg_command_wrapper.__signature__ = new_sig  #fake signature for wrapper function 

    kwarg_command_wrapper.__original_func__ = func
    kwarg_command_wrapper.__is_kwarg_command_func__ = True
    kwarg_command_wrapper.__keyword_only_flag_class__ = flags_cls

    return kwarg_command_wrapper


def custom_parsing(*, inside_class: bool = False):
    """Registers a command function to use snakecore's custom
    parser. This returns a wrapper function that bypasses `discord.ext.commands`
    parsing system, parses the input string from a command invocation using the
    signature of the command function and calls the command function with the 
    parsed arguments. Note that since the command invocation context
    (`commands.Context`) is always passed in as the first argument in a command,
    The first argument of the given command function will always be `commands.Context`
    object.

    Args:
        inside_class (bool): Whether the input function is being defined inside a class,
          such as a `commands.Cog` subclass. Defaults to False.

    Returns:
        Callable[..., Coroutine[Any, Any, Any]]: A wrapper callable object.
    """

    def inner(func: Callable[..., Coroutine[Any, Any, Any]]):
        if inside_class:
            async def cmd_func_wrapper(self, ctx: commands.Context, *, raw_input):
                signature = cmd_func_wrapper.__wrapped_func_signature__
                parsed_args, parsed_kwargs = await parse_command_str(ctx, raw_input, signature)

                return await func(self, ctx, *parsed_args, **parsed_kwargs)

        else:
            async def cmd_func_wrapper(ctx: commands.Context, *, raw_input):
                signature = cmd_func_wrapper.__wrapped_func_signature__
                parsed_args, parsed_kwargs = await parse_command_str(ctx, raw_input, signature)

                return await func(ctx, *parsed_args, **parsed_kwargs)
        
        functools.update_wrapper(cmd_func_wrapper, func)
        del cmd_func_wrapper.__wrapped__ # don't reveal wrapped function

        old_sig = inspect.signature(func)

        new_sig = old_sig.replace(parameters=tuple(old_sig.parameters.values())[2:] if inside_class else tuple(old_sig.parameters.values())[1:], return_annotation=old_sig.return_annotation)

        cmd_func_wrapper.__wrapped_func_signature__ = new_sig

        return cmd_func_wrapper
    

    return inner
