from dataclasses import dataclass

import pytest

# test only LocalDB for now, figure out DiscordDB later
from snakecore.db import LocalDB
from snakecore.exceptions import DBException


@dataclass
class DBRecords:
    TEST1 = ("test1", list[str])
    TEST2 = ("test2", dict[int, tuple[str, int]])


def test_local_db_args():
    with pytest.raises(TypeError):
        # no args is type error
        LocalDB()

    with pytest.raises(TypeError):
        # too many args is type error
        LocalDB("abc", dict, None)


@pytest.mark.asyncio
async def test_local_db():
    # access without lock should error
    with pytest.raises(DBException):
        LocalDB(*DBRecords.TEST1).obj
    with pytest.raises(DBException):
        LocalDB(*DBRecords.TEST1).obj = ["c"]
    with pytest.raises(DBException):
        del LocalDB(*DBRecords.TEST1).obj

    async with LocalDB(*DBRecords.TEST1) as db:
        # always true for LocalDB
        assert db.is_init

        # default value
        assert db.obj == []
        db.obj = ["a", "b"]
        assert db.obj == ["a", "b"]
        db.obj.append("c")

    # always true for LocalDB even without lock
    assert db.is_init

    # access after released lock should error
    with pytest.raises(DBException):
        db.obj
    with pytest.raises(DBException):
        db.obj = ["c"]
    with pytest.raises(DBException):
        del db.obj

    async with LocalDB(*DBRecords.TEST1) as db:
        # retain old value
        assert db.obj == ["a", "b", "c"]
        del db.obj

        # should be already deleted
        with pytest.raises(AttributeError):
            db.obj

        # should be already deleted
        with pytest.raises(AttributeError):
            del db.obj

    async with LocalDB(*DBRecords.TEST1) as db:
        # back to default value after delete
        assert db.obj == []
        db.obj = ["c", "d"]
        del db.obj
        # test assign after del, should work
        db.obj = ["e", "f"]
        assert db.obj == ["e", "f"]


@pytest.mark.asyncio
async def test_local_db_nested_use():
    async with LocalDB(*DBRecords.TEST1) as db:
        # retained old value
        assert db.obj == ["e", "f"]

        # test holding new lock for different DB within lock to another DB
        async with LocalDB(*DBRecords.TEST2) as db2:
            # default val
            assert db2.obj == {}
            db2.obj = {1: ("test", 100)}
            assert db2.obj == {1: ("test", 100)}

        # access after released lock should error
        with pytest.raises(DBException):
            db2.obj

        # remain unchanged
        assert db.obj == ["e", "f"]
