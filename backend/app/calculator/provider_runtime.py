"""Process-wide guards for stateful astronomy providers.

Swiss Ephemeris and PyJHora expose process-global configuration. Every product
entry point that reads or mutates that state must share this re-entrant lock.
"""

from __future__ import annotations

from functools import lru_cache, wraps
from pathlib import Path
from threading import RLock
from typing import Any, Callable, TypeVar, cast


_PROVIDER_LOCK = RLock()
_F = TypeVar("_F", bound=Callable[..., Any])


def serialized_provider_call(function: _F) -> _F:
    """Serialize a complete provider transaction, including nested adapters."""

    @wraps(function)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        with _PROVIDER_LOCK:
            return function(*args, **kwargs)

    return cast(_F, guarded)


@lru_cache(maxsize=1)
def canonical_ephemeris_path() -> Path:
    import jhora

    path = Path(jhora.__file__).resolve().parent / "data" / "ephe"
    if not path.is_dir():
        raise RuntimeError(f"Pinned PyJHora ephemeris directory is missing: {path}")
    return path


def configure_lahiri_swisseph() -> None:
    """Restore the profile's canonical ephemeris path and sidereal mode."""

    import swisseph as swe

    swe.set_ephe_path(str(canonical_ephemeris_path()))
    swe.set_sid_mode(swe.SIDM_LAHIRI)


def canonical_planet_flags() -> int:
    """Return the exact geocentric-apparent flags declared by the profile."""

    import swisseph as swe

    return swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED


def require_canonical_ephemeris_result(result: object, *, object_name: str) -> None:
    """Reject Swiss Ephemeris' silent Moshier fallback outside retained file coverage."""

    import swisseph as swe

    if not isinstance(result, tuple) or len(result) < 2:
        raise RuntimeError(f"Swiss Ephemeris returned an invalid result for {object_name}")
    returned_flags = int(result[1])
    if returned_flags & swe.FLG_SWIEPH and not returned_flags & swe.FLG_MOSEPH:
        return
    provider_message = (
        str(result[2]).strip().replace("\n", " ")
        if len(result) > 2 and result[2]
        else "provider did not return a diagnostic"
    )
    raise RuntimeError(
        f"Swiss Ephemeris file-backed calculation unavailable for {object_name}; "
        f"refusing provider fallback (returned flags={returned_flags}): {provider_message}"
    )


def configure_vedicdust_pyjhora() -> None:
    """Align PyJHora's stateful astronomy layer with the canonical Swiss profile."""

    import swisseph as swe
    from jhora import const
    from jhora.panchanga import drik

    configure_lahiri_swisseph()
    drik.set_ayanamsa_mode("LAHIRI")
    const._DEFAULT_AYANAMSA_MODE = "LAHIRI"
    const._use_true_nodes_for_rahu_ketu = False

    # PyJHora defaults to true/geometric positions while the canonical VedicDust
    # Swiss path uses apparent geocentric positions. Keep both providers on one
    # declared coordinate model so varga boundaries cannot silently diverge.
    const.PLANET_POSITIONS_GEOCENTRIC = True
    const.PLANET_POSITIONS_TRUE = False
    const.PLANET_POSITIONS_USE_ABERRATION = True
    const.PLANET_POSITIONS_USE_DEFLECTION = True
    const.PLANET_POSITIONS_USE_NUTATION = True
    drik.PLANET_FLAGS = canonical_planet_flags()
    swe.set_sid_mode(swe.SIDM_LAHIRI)
