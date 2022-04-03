"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

This file defines an abstract Database interface.
Implementations and backends of different database may vary, but they must
inherit 'AbstractDB' and implement API.
"""

from abc import ABC, abstractmethod
from typing import Generic, Type, TypeVar


_T = TypeVar("_T")


class AbstractDB(ABC, Generic[_T]):
    """
    An Abstract Base Class for concrete classes that implement a DB Interface
    API. The goals of this abstract class is to facilitate common API for
    numerous different DB API backends, while exposing an easy to use, pythonic
    API
    This is a typing generic class, to help typecheckers and editors.
    Also exposes a contextmanager API.
    'obj' is a property which gives safe access to the actual object stored in
    the DB
    """

    name: str

    @abstractmethod
    def __init__(self, name: str, obj_type: Type[_T]):
        """
        The implementation of this method is responsible for constructing the
        object. This must take 2 arguments:
        'name' is the key of the record.
        'obj_type' is the type of the record. This type object is also used for
        constructing the default value of 'obj'
        """

    @abstractmethod
    async def __aenter__(self):
        """
        The implementation of this method is responsible for doing any initial
        setups needed before access to data. Based on the implementation, this
        can hold locks, initialise data or connect to an external database
        server
        """

    @abstractmethod
    async def __aexit__(self, *_):
        """
        The implementation of this method is responsible for doing cleanups
        after the data has been used and modified. Based on the implementation,
        this can release locks, finalise data or flush data to an external DB.
        """

    @property
    @abstractmethod
    def is_init(self) -> bool:
        """
        The implementation of this property should return a bool that indicates
        whether the backend used by the database is initialised. Return True if
        the backend does not need init mechanisms
        """

    @property
    @abstractmethod
    def obj(self) -> _T:
        """
        The implementation of this property should return the object stored in
        the database.
        """

    @obj.setter
    @abstractmethod
    def obj(self, set_obj: _T):
        """
        The implementation of this property should set the object to the value
        of the argument passed
        """

    @obj.deleter
    @abstractmethod
    def obj(self):
        """
        The implementation of this property should delete the object from the
        database
        """
