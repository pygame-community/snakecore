from dataclasses import dataclass

import pytest

# test only LocalStorage for now, figure out DiscordStorage later
from snakecore.storage import LocalStorage
from snakecore.exceptions import StorageException


@dataclass
class StorageRecords:
    TEST1 = ("test1", list[str])
    TEST2 = ("test2", dict[int, tuple[str, int]])


def test_local_storage_args():
    with pytest.raises(TypeError):
        # no args is type error
        LocalStorage()

    with pytest.raises(TypeError):
        # too many args is type error
        LocalStorage("abc", dict, None)


@pytest.mark.asyncio
async def test_local_storage():
    # access without lock should error
    with pytest.raises(StorageException):
        LocalStorage(*StorageRecords.TEST1).obj
    with pytest.raises(StorageException):
        LocalStorage(*StorageRecords.TEST1).obj = ["c"]
    with pytest.raises(StorageException):
        del LocalStorage(*StorageRecords.TEST1).obj

    async with LocalStorage(*StorageRecords.TEST1) as storage:
        # always true for LocalStorage
        assert storage.is_init

        # default value
        assert storage.obj == []
        storage.obj = ["a", "b"]
        assert storage.obj == ["a", "b"]
        storage.obj.append("c")

    # always true for LocalStorage even without lock
    assert storage.is_init

    # access after released lock should error
    with pytest.raises(StorageException):
        storage.obj
    with pytest.raises(StorageException):
        storage.obj = ["c"]
    with pytest.raises(StorageException):
        del storage.obj

    async with LocalStorage(*StorageRecords.TEST1) as storage:
        # retain old value
        assert storage.obj == ["a", "b", "c"]
        del storage.obj

        # should be already deleted
        with pytest.raises(AttributeError):
            storage.obj

        # should be already deleted
        with pytest.raises(AttributeError):
            del storage.obj

    async with LocalStorage(*StorageRecords.TEST1) as storage:
        # back to default value after delete
        assert storage.obj == []
        storage.obj = ["c", "d"]
        del storage.obj
        # test assign after del, should work
        storage.obj = ["e", "f"]
        assert storage.obj == ["e", "f"]


@pytest.mark.asyncio
async def test_local_storage_nested_use():
    async with LocalStorage(*StorageRecords.TEST1) as storage:
        # retained old value
        assert storage.obj == ["e", "f"]

        # test holding new lock for different Storage within lock to another Storage
        async with LocalStorage(*StorageRecords.TEST2) as storage2:
            # default val
            assert storage2.obj == {}
            storage2.obj = {1: ("test", 100)}
            assert storage2.obj == {1: ("test", 100)}

        # access after released lock should error
        with pytest.raises(StorageException):
            storage2.obj

        # remain unchanged
        assert storage.obj == ["e", "f"]
