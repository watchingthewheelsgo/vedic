from __future__ import annotations

from .models import AyanamsaSetting, CalculationProfile


def parashari_lahiri_profile() -> CalculationProfile:
    """Return the first product-owned, fully declared calculation profile."""

    return CalculationProfile(
        profile_id="parashari-lahiri-1.0.0",
        profile_version="1.0.0",
        tradition="Parashari-first product baseline",
        zodiac="sidereal",
        ayanamsa=AyanamsaSetting(
            model="lahiri",
            implementation="Swiss Ephemeris SIDM_LAHIRI",
        ),
        node_model="mean",
        rashi_house_model="whole_sign",
        bhava_cusp_model=None,
        varga_scheme="parashara-method-1",
        supported_vargas=[1, 2, 3, 4, 5, 7, 9, 10, 12, 16, 20, 24, 27, 30, 60],
        aspect_model="parashari-graha-drishti-1.0.0",
        dasha_model="vimshottari-moon-nakshatra-1.0.0",
        dasha_year_days=365.256364,
        coordinate_datum="WGS84",
        ephemeris_provider="Swiss Ephemeris",
        rule_pack_version="vedicdust-rules-1.2.0",
        source_ids=[
            "astro.swisseph.programmer-manual",
            "time.iana.tzdb",
            "classic.bphs.pending-edition",
            "lineage.pvr-integrated-approach.pending-edition",
        ],
    )
