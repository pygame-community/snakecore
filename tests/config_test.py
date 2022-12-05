from typing import Optional

import pytest

# import public API, all should be defined
from snakecore.config import ConfigurationBase, ConstantField, Field


def test_fail_config():
    class FailConfiguration(ConfigurationBase):
        with pytest.raises(ValueError) as e_info:
            # expected error, no args
            Field()

        # errors for wrong argument combinations
        with pytest.raises(ValueError) as e_info:
            Field(init_val=(1, 2, 3), init_constr=list)

        with pytest.raises(ValueError) as e_info:
            Field(init_val=(1, 2, 3), write_once=True)

        with pytest.raises(ValueError) as e_info:
            Field(init_constr=dict, write_once=True)

        with pytest.raises(ValueError) as e_info:
            Field(init_constr=dict)

        with pytest.raises(ValueError) as e_info:
            Field(write_once=True)

        # expected error, mismatching types. This fails when the class is
        # instantiated
        f = Field(init_val=1, var_type=list[int])

    with pytest.raises(TypeError) as e_info:
        # expected error
        FailConfiguration()


def test_config_with_init():
    class Configuration(ConfigurationBase):
        # regular class var, no Field restrictions
        a = 6

        # 'd' looks like 'Field[float | None]' at typecheck time.
        b = Field(init_val=4.5, var_type=float | None)

        # 'c' looks like Field[list[str]] at typecheck time.
        c = Field(init_constr=list, var_type=list[str])

        # 'd' looks like 'ConstantField[str]' at typecheck time. Will also fail
        # at runtime if this is modified
        d = ConstantField("test")

        # 'e' looks like 'Field[tuple[int, int, int]]' at typecheck time,
        # will be a tuple and checked for tuple at runtime
        e = Field(init_val=(1, 2, 3), var_type=tuple[int, int, int])

    conf = Configuration()
    for char in "bcde":
        # test __contains__ for 'Configuration'
        assert char in conf

    for char in "wxyz":
        assert char not in conf

    assert conf.a == 6

    assert conf.is_set("b")
    assert not conf.is_read_only("b")
    assert not conf.is_write_once("b")
    assert conf.b == pytest.approx(4.5)
    conf.b = 1.414
    assert conf.b == pytest.approx(1.414)
    conf.b = None
    assert conf.b == None
    with pytest.raises(TypeError) as e_info:
        conf.b = "wrong type"

    assert conf.is_set("c")
    assert not conf.is_read_only("c")
    assert not conf.is_write_once("c")
    assert conf.c == []
    conf.c.append("name")
    assert conf.c == ["name"]
    conf.c = ["foo", "baz"]
    assert conf.c == ["foo", "baz"]

    with pytest.raises(TypeError) as e_info:
        conf.c = ("foo", "baz")

    assert conf.is_set("d")
    assert conf.is_read_only("d")
    assert conf.d == "test"
    with pytest.raises(AttributeError) as e_info:
        # expected error, modifying ConstantField
        conf.d = "sus".replace("s", "u")

    # test modification
    assert conf.e == (1, 2, 3)
    conf.e = (4, 5, 6)
    assert conf.e == (4, 5, 6)
    with pytest.raises(TypeError) as e_info:
        conf.e = None


def test_config_no_init():
    class Configuration(ConfigurationBase):
        # 'f' looks like 'Field[dict[str, int]]' at typecheck time,
        # will be undefined initially, but will be write once
        f = Field(var_type=dict[str, int], write_once=True)

        # 'g' looks like 'Field[tuple[str, int]]' at typecheck time,
        # will be undefined initially, can be overwritten
        g = Field(var_type=tuple[str, int])

    conf = Configuration()
    for char in "fg":
        # test __contains__ for 'Configuration'
        assert char in conf

    for char in "wxyz":
        assert char not in conf

    assert not conf.is_set("f")
    assert conf.is_write_once("f")
    with pytest.raises(AttributeError) as e_info:
        # initially undefined
        conf.f

    with pytest.raises(TypeError) as e_info:
        # wrong time
        conf.f = "amog"

    conf.f = {"test": 42}
    assert conf.f == {"test": 42}
    assert conf.is_set("f")

    with pytest.raises(AttributeError) as e_info:
        # write once
        conf.f = {"test": 10}

    assert not conf.is_set("g")
    assert not conf.is_write_once("g")
    with pytest.raises(AttributeError) as e_info:
        # initially undefined
        conf.g

    conf.g = ("test", 10)
    assert conf.g == ("test", 10)
    assert conf.is_set("g")

    with pytest.raises(TypeError) as e_info:
        # wrong time
        conf.g = ["foo", "baz"]

    # hold previous value
    assert conf.g == ("test", 10)

    conf.g = ("amog", 0)
    assert conf.g == ("amog", 0)

    with pytest.raises(TypeError) as e_info:
        # wrong time
        conf.g = "test"
