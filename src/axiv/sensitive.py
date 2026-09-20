from pydantic import JsonValue

_SENSITIVE_KEY_SUFFIXES = ("apikey", "token", "secret", "cookie", "authorization")


def is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("_", "").replace("-", "")
    return normalized.endswith(_SENSITIVE_KEY_SUFFIXES)


def contains_sensitive_key(value: JsonValue) -> bool:
    if isinstance(value, dict):
        return any(is_sensitive_key(key) or contains_sensitive_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(contains_sensitive_key(item) for item in value)
    return False
