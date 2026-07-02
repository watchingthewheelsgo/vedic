from __future__ import annotations

import secrets
import string
import time


def make_id(prefix: str) -> str:
    entropy = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12))
    return f"{prefix}_{base36(int(time.time() * 1000))}_{entropy}"


def base36(value: int) -> str:
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    result = ""
    current = value
    while current:
        current, remainder = divmod(current, 36)
        result = chars[remainder] + result
    return result


def stable_seed(value: str) -> int:
    hash_value = 2166136261
    for char in value:
        hash_value ^= ord(char)
        hash_value = (hash_value * 16777619) & 0xFFFFFFFF
    return abs(hash_value)


def pick(items: list, seed: int, offset: int = 0):
    return items[(seed + offset) % len(items)]
