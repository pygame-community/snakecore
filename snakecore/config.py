"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

This module defines some internal configuration classes and utilities used
throughout the codebase.
"""

from abc import ABC, abstractmethod
from enum import Enum, auto
from types import GenericAlias
from typing import Any, Callable, Generic, Optional, Protocol, TypeVar, overload

import discord

from snakecore.constants import UNSET, _UnsetType, UnionType

_T = TypeVar("_T", bound=object)


class _FieldContainer:
    """
    A dataclass to hold an internal BaseField record
    """

    def __init__(self, var: Any, read_only: bool = False, write_once: bool = False):
        self.var = var
        self.read_only = read_only
        self.write_once = write_once

    def __repr__(self):
        args = (
            f"var={self.var}, read_only={self.read_only}, write_once={self.write_once}"
        )
        return f"<{self.__class__.__name__}({args})>"


class SupportsField(Protocol):
    """
    A class that implements this protocol supports BaseField.
    This protocol is merely implemented for typechecking purposes, users
    should inherit the 'ConfigurationBase'.
    """

    _priv_desc_data: dict[str, _FieldContainer]


class BaseField(Generic[_T], ABC):
    """
    A base class for ConstantField and Field.
    """

    def __init__(self, init_val: _T):
        """
        Initialise a Field object with an initial value

        Args:
            init_val (_T): The default value for the Field.
        """
        self._init_val = init_val

    def __set_name__(self, owner: SupportsField, name: str):
        # owner unused for now
        self._name = name

    def __get__(self, obj: SupportsField, objtype=None) -> _T:
        ret = obj._priv_desc_data[self._name].var
        if ret is UNSET:
            raise AttributeError(
                f"No value was set for the configuration attribute '{self._name}'"
            )

        return ret

    @abstractmethod
    def _get_container(self) -> _FieldContainer:
        """
        Subclasses must implement a method to return a _FieldContainer record
        """


class ConstantField(BaseField[_T]):
    """
    Used to represent a field that is constant. Trying to overwrite the
    descriptor results in an error at both typechecktime and runtime
    """

    def _get_container(self):
        return _FieldContainer(self._init_val, read_only=True)


class Field(BaseField[_T]):
    """
    Used to represent a modifiable field. Fields are type checked at runtime
    during assignment to a new value
    """

    # overloads are implemented solely for the benefits of static typecheckers

    # passing init val, cannot pass constructor
    @overload
    def __init__(self, *, init_val: _T, var_type: type[_T] = _UnsetType):
        """
        Initialise a Field object with an initial value and an optional type

        Args:
            init_val (_T): The default value for the Field.
            var_type (type[_T], optional)
              The explicit type(s) to enforce on assigment to the field.
              This primarily exists to allow wider types than the default value
              If this argument is not passed, it infers type from the default
              value and only allows the specific type.

        Raises:
            ValueError: Invalid values for the specified arguments.
            TypeError: Invalid types for the specified arguments.
        """

    # passing constructor, cannot pass init val. var_type is mandatory here
    @overload
    def __init__(self, *, init_constr: Callable[[], _T], var_type: type[_T]):
        """
        Initialise a Field object with an initial constructor and type

        Args:
            init_constr (Callable[[], _T]): The constructor used to make a
              default value. Passing a constructor is useful while dealing
              with mutable types
            var_type (type[_T]): The explicit type(s) to enforce on assigment
              to the field.

        Raises:
            ValueError: Invalid values for the specified arguments.
            TypeError: Invalid types for the specified arguments.
        """

    # neither init val not constructor was passed, in this case var_type is
    # a mandatory argument, and write_once can be passed, which is false by
    # default
    @overload
    def __init__(self, *, var_type: type[_T], write_once: bool = False):
        """
        Initialise a Field object with a type. In this case, the field remains
        in unset state till the first assignment

        Args:
            var_type (type[_T]): The explicit type(s) to enforce on assigment
              to the field.
            write_once (bool=False, optional)

        Raises:
            ValueError: Invalid values for the specified arguments.
            TypeError: Invalid types for the specified arguments.
        """

    # actual implementation of __init__
    def __init__(
        self,
        *,
        init_val: _T = UNSET,
        init_constr: Callable[[], _T] = _UnsetType,
        var_type: type[_T] = _UnsetType,
        write_once: bool = False,
    ):
        self._init_val = init_val
        self._init_constr = init_constr
        self._var_type = var_type
        self._write_once = write_once

        if self._init_val is UNSET:
            if self._var_type is _UnsetType:
                raise ValueError(
                    "Argument 'var_type' must be set when 'init_val' is not passed"
                )

            if self._init_constr is not _UnsetType:
                if not callable(self._init_constr):
                    raise TypeError(
                        "Argument 'init_constr' must be a callable if passed"
                    )

                if write_once:
                    raise ValueError(
                        "Arguments 'write_once' cannot be passed when "
                        "'init_constr' is set"
                    )

        else:
            if write_once:
                raise ValueError(
                    "Arguments 'write_once' cannot be passed when 'init_val' is set"
                )

            if self._init_constr is not _UnsetType:
                # setting both is an error
                raise ValueError(
                    "Arguments 'init_val' and 'init_constr' must not be set "
                    "simultaneously"
                )

            if self._var_type is _UnsetType:
                # auto determine type when init_val is available
                self._var_type = type(init_val)

        # isinstance checks can't handle a GenericAlias
        if isinstance(self._var_type, GenericAlias):
            self._var_type: type[_T] = self._var_type.__origin__  # type: ignore

        if isinstance(self._var_type, UnionType):
            # needed for python 3.9
            self._var_type: type[_T] = self._var_type.__args__  # type: ignore

    def validate(self, obj: _T):
        """
        The setter calls this method to inspect an object before setting it.
        Subclasses can override this class and implement more logic
        """
        if not isinstance(obj, self._var_type):
            raise TypeError(
                f"Assignments to the configuration attribute '{self._name}' "
                f"must be an instance of {self._var_type}, not "
                f"{obj.__class__.__name__}"
            )

    def __set__(self, obj: SupportsField, value: _T):
        rec = obj._priv_desc_data[self._name]
        if rec.write_once and rec.var is not UNSET:
            raise AttributeError(
                "A value was already set for the write-once configuration "
                f"attribute '{self._name}'"
            )

        self.validate(value)
        rec.var = value

    def _get_container(self):
        val = self._init_val if self._init_constr is _UnsetType else self._init_constr()
        if val is not UNSET:
            self.validate(val)

        return _FieldContainer(val, write_once=self._write_once)


class ConfigurationBase(SupportsField):
    def __init__(self):
        self._priv_desc_data = {}

        for name, val in self.__class__.__dict__.items():
            if isinstance(val, BaseField):
                self._priv_desc_data[name] = val._get_container()

    def is_set(self, name: str):
        """
        Whether the speficied variable name is set

        Args:
            name (str): The name of the target variable.

        Returns:
            bool: True/False

        Raises:
            AttributeError: Unknown attribute name.
        """
        return self._priv_desc_data[name].var is not UNSET

    def is_read_only(self, name: str):
        """
        Whether the speficied variable name is read-only.

        Args:
            name (str): The name of the target variable.

        Returns:
            bool: True/False

        Raises:
            AttributeError: Unknown attribute name.
        """
        return self._priv_desc_data[name].read_only

    def is_write_once(self, name: str):
        """
        Whether the speficied variable name is write-once, which behaves like
        being read-only after one assignment has occured.

        Args:
            name (str): The name of the target variable.

        Returns:
            bool: True/False

        Raises:
            AttributeError: Unknown variable name.
        """
        return self._priv_desc_data[name].write_once

    def __contains__(self, name: Any):
        if not isinstance(name, str):
            return False

        return name in self._priv_desc_data

    def __setattr__(self, name: str, val: Any):
        if "_priv_desc_data" in dir(self) and name in self and self.is_read_only(name):
            # tried to set a read-only attribute
            raise AttributeError("Cannot modify a read-only attribute")

        super().__setattr__(name, val)

    def __repr__(self):
        return (
            f"<{self.__class__.__name__}("
            + ", ".join(f"{k}={v}" for k, v in self._priv_desc_data.items())
            + ")>"
        )


class ModuleName(Enum):
    SNAKECORE = auto()
    UTILS = auto()
    EVENTS = auto()
    DB = auto()


class CoreConfig(ConfigurationBase):
    """
    Configuration variables used by snakecore itself
    """

    global_client = Field(var_type=discord.Client, write_once=True)
    init_mods = Field(init_constr=dict, var_type=dict[ModuleName, bool])
    db_channel = Field(init_val=None, var_type=Optional[discord.TextChannel])


conf = CoreConfig()
