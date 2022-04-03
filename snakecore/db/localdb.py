"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

This file implements a 'LocalDB' which implements a safe API for storing
global data with asyncio locking.
Some pros of this implemenation are:
1) Database is fast because of data stored in memory
2) No dependence on external SQL API or any database server
Some cons:
1) May have a large memory footprint for large data
"""

import asyncio
import pickle
from types import GenericAlias
from typing import Type, TypeVar

from snakecore.exceptions import DBException
from .abc import AbstractDB


class _DBLockedRecord(asyncio.Lock):
    """
    A _DBLockedRecord is an internal structure used to store a record. For data
    safety, this needs an async lock held during access to data. This inherits
    the asyncio Lock primitive and defines three attributes.

    'data' is the binary data stores in the record
    'changed' is a bool that indicates if data was modified from the time the
    record was loaded
    'deleted' is a bool that stores whether data was deleted
    """

    def __init__(self, init_data: bytes):
        super().__init__()

        # no need for lock to be held while initialising data. This stores data
        # in pickled form. Can be None when the data is deleted
        self.data: bytes = init_data

        # optimisation: store a bool on whether data was changed from init time
        # or not
        self.changed: bool = False

        # bool that stores whether data was deleted
        self.deleted: bool = False


_T = TypeVar("_T")


class LocalDB(AbstractDB[_T]):
    """
    LocalDB is an implemenation of the AbstractDB interface for storing data
    in memory in a async-safe manner.
    """

    _db_records: dict[str, _DBLockedRecord] = {}

    def __init__(self, name: str, obj_type: Type[_T] = dict):
        """
        Initialise a DiscordDB object.
        'name' is the key of the record.
        'obj_type' is the type of the record. This type object is also used for
        constructing the default value of 'obj'
        """
        self.name = name

        if isinstance(obj_type, GenericAlias):
            obj_type = obj_type.__origin__

        # init temp object with the constructor
        self._temp_obj: _T = obj_type()

        if name not in self._db_records:
            # create new record and store in record dict
            self._db_records[name] = _DBLockedRecord(pickle.dumps(self._temp_obj))

    @property
    def is_init(self) -> bool:
        """
        Indicates whether the backend used by the database is init.
        """
        return True

    @property
    def _record(self):
        """
        Get a reference to the record of the current database
        """
        return self._db_records[self.name]

    def _check_active(self):
        """
        Raise error on operation on a locked record
        """
        if not self._record.locked() or not self.is_init:
            raise DBException("Operation on unlocked data object")

    async def __aenter__(self):
        # wait for a maximum of 10 seconds for init to happen if it has not
        for _ in range(1000):
            if self.is_init:
                break
            await asyncio.sleep(0.01)
        else:
            raise DBException("db module was not init")

        await self._record.acquire()

        if self._record.deleted:
            # when deleted, do not load from pickled data, use constructor
            # default. Also reset deleted flag
            self._record.deleted = False

        else:
            self._temp_obj = pickle.loads(self._record.data)

        return self

    async def __aexit__(self, *_):
        self._check_active()
        if self._record.deleted:
            # deleted implies changed
            self._record.changed = True

            # saves memory, fill data with small binary None
            self._record.data = pickle.dumps(None)
        else:
            dumped = pickle.dumps(self._temp_obj)
            if dumped != self._record.data:
                self._record.data = dumped
                self._record.changed = True

        self._record.release()

    @property
    def obj(self):
        """
        Get object stored in a record
        """
        self._check_active()
        if self._record.deleted:
            raise AttributeError("Cannot access a deleted record")

        return self._temp_obj

    @obj.setter
    def obj(self, set_obj: _T):
        """
        Sets obj
        """
        self._check_active()
        self._temp_obj = set_obj

        # setting a value un-deletes
        self._record.deleted = False

    @obj.deleter
    def obj(self):
        """
        Deletes obj
        """
        self._check_active()
        if self._record.deleted:
            raise AttributeError("Cannot re-delete a deleted record")

        self._record.deleted = True
