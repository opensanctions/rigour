from rigour.env import env_str

def test_env_str():
    assert env_str("TZ_NAME_XXXX", "UTC") is not None
    assert env_str("TZ_NAME_XXXX", "UTC") == "UTC"