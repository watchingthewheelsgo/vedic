from __future__ import annotations

from .models import AyanamsaSetting, CalculationProfile, VargaMethodSetting
from .source_registry import active_rule_pack_version
from .varga_policy import SUPPORTED_VARGA_FACTORS


PARASHARI_LAHIRI_PROFILE_ID = "parashari-lahiri-1.1.0"


_VARGA_ALGORITHMS: dict[int, tuple[str, str, int | None]] = {
    1: ("canonical-swiss-rashi", "Swiss Ephemeris", None),
    2: ("traditional-parashara-hora-leo-cancer", "PyJHora", 2),
    3: ("traditional-parashara-drekkana", "PyJHora", 1),
    4: ("traditional-parashara-chaturthamsha", "PyJHora", 1),
    5: ("traditional-parashara-panchamsha", "PyJHora", 1),
    7: ("traditional-parashara-saptamsha", "PyJHora", 1),
    9: ("traditional-parashara-navamsha", "PyJHora", 1),
    10: ("traditional-parashara-dashamsha", "PyJHora", 1),
    12: ("traditional-parashara-dwadashamsha", "PyJHora", 1),
    16: ("traditional-parashara-shodashamsha", "PyJHora", 1),
    20: ("traditional-parashara-vimshamsha", "PyJHora", 1),
    24: ("traditional-parashara-siddhamsha", "PyJHora", 1),
    27: ("traditional-parashara-bhamsha", "PyJHora", 1),
    30: ("traditional-parashara-trimshamsha", "PyJHora", 1),
    60: ("traditional-parashara-shashtiamsha", "PyJHora", 1),
}


def varga_method_setting(factor: int) -> VargaMethodSetting:
    """Return the single product-owned algorithm choice for a supported varga."""

    try:
        algorithm_id, provider, provider_method = _VARGA_ALGORITHMS[factor]
    except KeyError as exc:
        raise ValueError(f"unsupported VedicDust varga factor: {factor}") from exc
    return VargaMethodSetting(
        factor=factor,
        algorithm_id=algorithm_id,
        provider=provider,
        provider_method=provider_method,
    )


def parashari_lahiri_profile() -> CalculationProfile:
    """Return the first product-owned, fully declared calculation profile."""

    if tuple(_VARGA_ALGORITHMS) != SUPPORTED_VARGA_FACTORS:
        raise RuntimeError("varga algorithms and domain policy declare different factors")

    return CalculationProfile(
        profile_id=PARASHARI_LAHIRI_PROFILE_ID,
        profile_version="1.1.0",
        tradition="Parashari-first product baseline",
        zodiac="sidereal",
        ayanamsa=AyanamsaSetting(
            model="lahiri",
            implementation="Swiss Ephemeris SIDM_LAHIRI",
        ),
        node_model="mean",
        rashi_house_model="whole_sign",
        bhava_cusp_model=None,
        varga_scheme="vedicdust-traditional-parashara-varga-1.0.0",
        supported_vargas=list(SUPPORTED_VARGA_FACTORS),
        varga_methods=[varga_method_setting(factor) for factor in SUPPORTED_VARGA_FACTORS],
        aspect_model="parashari-graha-drishti-1.0.0",
        dasha_model="vimshottari-moon-nakshatra-1.0.0",
        dasha_year_days=365.256364,
        coordinate_datum="WGS84",
        ephemeris_provider="Swiss Ephemeris",
        planet_position_model="geocentric_apparent",
        ephemeris_flags=["FLG_SWIEPH", "FLG_SIDEREAL", "FLG_SPEED"],
        rule_pack_version=active_rule_pack_version(),
        source_ids=[
            "astro.swisseph.programmer-manual",
            "time.iana.tzdb",
            "software.pyjhora.compatibility",
            "lineage.pvr-lessons-volume-1-2005",
            "lineage.pvr-integrated-approach-2000-2010",
            "product.vedicdust-consultation-standard-1",
        ],
    )
