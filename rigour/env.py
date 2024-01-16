from os import environ as env
from zoneinfo import ZoneInfo
from normality import stringify


def env_str(name: str, default: str) -> str:
    """Ensure the env returns a string even on Windows (#100)."""
    value = stringify(env.get(name))
    return default if value is None else value


TZ_NAME = env_str("TZ", "UTC")
TZ = ZoneInfo(TZ_NAME)
