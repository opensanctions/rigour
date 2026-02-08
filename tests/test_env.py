import os
from rigour.env import env_bool, env_str, env_float, env_int, env_opt


def test_env_str():
    assert env_str("TZ_NAME_XXXX", "UTC") is not None
    assert env_str("TZ_NAME_XXXX", "UTC") == "UTC"


def test_env_opt():
    assert env_opt("TZ_NAME_XXXX") is None
    os.environ["TZ_NAME_XXXX"] = "UTC"
    assert env_opt("TZ_NAME_XXXX") == "UTC"


def test_env_bool():
    assert env_bool("TZ_NAME_XXXX", True) is not None
    assert env_bool("TZ_NAME_XXXX", True) is True
    os.environ["TZ_NAME_XXXX"] = "true"
    assert env_bool("TZ_NAME_XXXX", False) is True
    os.environ["TZ_NAME_XXXX"] = "false"
    assert env_bool("TZ_NAME_XXXX", True) is False
    os.environ["TZ_NAME_XXXX"] = "banana"
    assert env_bool("TZ_NAME_XXXX", True) is True


def test_env_int():
    assert env_int("TZ_NAME_XXXX", 23) is not None
    assert env_int("TZ_NAME_XXXX", 23) == 23
    os.environ["TZ_NAME_XXXX"] = "23"
    assert env_int("TZ_NAME_XXXX", 0) == 23
    os.environ["TZ_NAME_XXXX"] = "banana"
    assert env_int("TZ_NAME_XXXX", 0) == 0


def test_env_float():
    assert env_float("TZ_NAME_XXXX", 23.0) is not None
    assert env_float("TZ_NAME_XXXX", 23.0) == 23.0
    os.environ["TZ_NAME_XXXX"] = "23.0"
    assert env_float("TZ_NAME_XXXX", 0.0) == 23.0
    os.environ["TZ_NAME_XXXX"] = "banana"
    assert env_float("TZ_NAME_XXXX", 0.0) == 0.0
