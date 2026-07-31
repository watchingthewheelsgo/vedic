from __future__ import annotations

from collections.abc import Callable
from typing import Any

import swisseph as swe


_PATCH_MARKER = "_vedicdust_pyjhora_compat"


def ensure_pyjhora_swe_compat() -> None:
    """Normalize pyswisseph return shapes exactly once per process."""

    for function_name in ("calc_ut", "calc"):
        original = getattr(swe, function_name)
        if getattr(original, _PATCH_MARKER, False):
            continue
        setattr(swe, function_name, _calculation_wrapper(original))

    if hasattr(swe, "houses_ex"):
        original_houses = swe.houses_ex
        if not getattr(original_houses, _PATCH_MARKER, False):
            swe.houses_ex = _houses_wrapper(original_houses)


def _calculation_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    def patched(jd: float, planet: int, flags: int = 0) -> Any:
        result = original(jd, planet, flags=flags)
        return (result[0], result[1]) if len(result) == 3 else result

    setattr(patched, _PATCH_MARKER, True)
    setattr(patched, "_vedicdust_original", original)
    return patched


def _houses_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    def patched(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        return (result[0], result[1]) if len(result) == 3 else result

    setattr(patched, _PATCH_MARKER, True)
    setattr(patched, "_vedicdust_original", original)
    return patched
