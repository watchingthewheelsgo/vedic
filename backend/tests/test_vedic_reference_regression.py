from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import pytz
import swisseph as swe

from app.calculator.engine import PLANETS_SWE, SIGNS, calculate_full_chart


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "vedic_reference" / "reference_cases.json"
PLANET_ID_TO_NAME = {
    "L": "Lagna",
    0: "Sun",
    1: "Moon",
    2: "Mars",
    3: "Mercury",
    4: "Jupiter",
    5: "Venus",
    6: "Saturn",
    7: "Rahu",
    8: "Ketu",
}


def _reference_cases() -> list[dict[str, Any]]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert (
        payload["calculationProfile"] == "TRUE_CITRA mean nodes whole-sign PyJHora chart_method=1"
    )
    return list(payload["cases"])


@pytest.mark.parametrize("case", _reference_cases(), ids=lambda case: case["id"])
def test_vedic_engine_matches_swiss_ephemeris_core_positions(case: dict[str, Any]) -> None:
    chart = _calculate_case(case)
    jd = _utc_julian_day(case)
    swe.set_sid_mode(swe.SIDM_TRUE_CITRA)

    assert chart["ayanamsa"] == pytest.approx(swe.get_ayanamsa_ut(jd), abs=1e-7)

    _, ascmc = swe.houses_ex(
        jd,
        float(case["lat"]),
        float(case["lon"]),
        b"W",
        swe.FLG_SIDEREAL,
    )
    _assert_close_degrees(chart["lagna"]["longitude"], ascmc[0], tolerance_degrees=1e-7)

    flags = swe.FLG_SIDEREAL | swe.FLG_SPEED
    for name, planet_id in PLANETS_SWE.items():
        expected_longitude = _swe_calc_ut_longitude(jd, planet_id, flags)
        _assert_close_degrees(
            chart["planets"][name]["longitude"],
            expected_longitude,
            tolerance_degrees=1e-7,
        )

    rahu = _swe_calc_ut_longitude(jd, swe.MEAN_NODE, flags)
    _assert_close_degrees(chart["planets"]["Rahu"]["longitude"], rahu, tolerance_degrees=1e-7)
    _assert_close_degrees(
        chart["planets"]["Ketu"]["longitude"],
        (rahu + 180.0) % 360.0,
        tolerance_degrees=1e-7,
    )


@pytest.mark.parametrize("case", _reference_cases(), ids=lambda case: case["id"])
def test_vedic_engine_matches_pyjhora_reference_for_vargas_sav_and_dasha(
    case: dict[str, Any],
) -> None:
    chart = _calculate_case(case)
    reference = _pyjhora_reference(case)

    assert chart["sav"] == reference["sav"]
    assert sum(chart["sav"].values()) == 337

    for chart_key in ["D4", "D5", "D9", "D10"]:
        actual_chart = chart["divisional_charts"][chart_key]
        expected_chart = reference["divisional_charts"][chart_key]
        for body in ["Lagna", "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]:
            assert actual_chart[body]["sign_idx"] == expected_chart[body]["sign_idx"]
            assert actual_chart[body]["sign"] == expected_chart[body]["sign"]
            assert actual_chart[body]["degree"] == pytest.approx(
                expected_chart[body]["degree"], abs=1e-4
            )

    actual_dashas = [
        {"planet": item["planet"], "start": item["start"], "end": item["end"]}
        for item in chart["dashas"][:3]
    ]
    assert actual_dashas == reference["first_three_mahadashas"]


@pytest.mark.parametrize("case", _reference_cases(), ids=lambda case: case["id"])
def test_vedic_engine_matches_pinned_product_reference_snapshot(case: dict[str, Any]) -> None:
    chart = _calculate_case(case)
    expected = case["expectedSnapshot"]

    assert round(float(chart["ayanamsa"]), 6) == expected["ayanamsa"]
    assert chart["lagna"]["sign"] == expected["lagna"]["sign"]
    assert round(float(chart["lagna"]["degree"]), 4) == expected["lagna"]["degree"]
    assert chart["planets"]["Moon"]["sign"] == expected["moon"]["sign"]
    assert round(float(chart["planets"]["Moon"]["degree"]), 4) == expected["moon"]["degree"]
    assert chart["planets"]["Moon"]["nakshatra"]["name"] == expected["moon"]["nakshatra"]
    assert chart["planets"]["Moon"]["nakshatra"]["pada"] == expected["moon"]["pada"]
    assert chart["planets"]["Rahu"]["sign"] == expected["rahu"]["sign"]
    assert round(float(chart["planets"]["Rahu"]["degree"]), 4) == expected["rahu"]["degree"]
    assert chart["divisional_charts"]["D9"]["Lagna"]["sign"] == expected["d9Lagna"]
    assert chart["divisional_charts"]["D10"]["Lagna"]["sign"] == expected["d10Lagna"]
    assert chart["sav"] == expected["sav"]
    assert sum(chart["sav"].values()) == expected["savTotal"]

    actual_dashas = [
        {"planet": item["planet"], "start": item["start"], "end": item["end"]}
        for item in chart["dashas"][:3]
    ]
    assert actual_dashas == expected["firstThreeMahadashas"]

    actual_rupas = {
        planet: chart["shadbala"][planet]["total_rupas"]
        for planet in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
    }
    assert actual_rupas == expected["shadbalaRupas"]


def test_pyjhora_bundled_reference_baseline_is_available() -> None:
    import jhora

    tests_root = Path(jhora.__file__).resolve().parent / "tests"
    lahiri_fixture = tests_root / "test_outputs_lahiri_mean_nodes.json"
    pvr_tests = tests_root / "pvr_tests.py"
    book_chart_data = tests_root / "book_chart_data.py"

    assert lahiri_fixture.exists()
    assert pvr_tests.exists()
    assert book_chart_data.exists()

    payload = json.loads(lahiri_fixture.read_text(encoding="utf-8"))
    assert len(payload) >= 6800
    assert payload["1"][0] == "BVRaman Shadbala rasi_planet_positions"
    assert payload["28"][0] == "BVRaman Shadbala Total"


def _calculate_case(case: dict[str, Any]) -> dict[str, Any]:
    return calculate_full_chart(
        int(case["year"]),
        int(case["month"]),
        int(case["day"]),
        int(case["hour"]),
        int(case["minute"]),
        float(case["lat"]),
        float(case["lon"]),
        str(case["tz"]),
    )


def _utc_julian_day(case: dict[str, Any]) -> float:
    timezone = pytz.timezone(str(case["tz"]))
    local_dt = timezone.localize(
        datetime(
            int(case["year"]),
            int(case["month"]),
            int(case["day"]),
            int(case["hour"]),
            int(case["minute"]),
        )
    )
    utc = local_dt.astimezone(pytz.utc)
    return swe.julday(
        utc.year,
        utc.month,
        utc.day,
        utc.hour + utc.minute / 60.0 + utc.second / 3600.0,
    )


def _swe_calc_ut_longitude(jd: float, planet_id: int, flags: int) -> float:
    result = swe.calc_ut(jd, planet_id, flags)
    return float(result[0][0])


def _assert_close_degrees(actual: float, expected: float, *, tolerance_degrees: float) -> None:
    distance = abs((float(actual) - float(expected) + 180.0) % 360.0 - 180.0)
    assert distance <= tolerance_degrees


def _pyjhora_reference(case: dict[str, Any]) -> dict[str, Any]:
    _configure_pyjhora()

    from jhora.horoscope.chart import ashtakavarga, charts
    from jhora.horoscope.dhasa.graha import vimsottari
    from jhora.panchanga.drik import Place

    local_hour = int(case["hour"]) + int(case["minute"]) / 60.0
    jd_local = swe.julday(int(case["year"]), int(case["month"]), int(case["day"]), local_hour)
    place = Place("reference", float(case["lat"]), float(case["lon"]), float(case["tz_offset"]))

    rasi = charts.rasi_chart(jd_local, place)
    house_to_planets = ["" for _ in range(12)]
    for planet_id, position in rasi:
        sign_idx = int(position[0])
        planet_label = str(planet_id)
        house_to_planets[sign_idx] = (
            f"{house_to_planets[sign_idx]}/{planet_label}"
            if house_to_planets[sign_idx]
            else planet_label
        )
    _, sav_raw, _ = ashtakavarga.get_ashtaka_varga(house_to_planets)

    divisional_charts: dict[str, dict[str, Any]] = {}
    for factor in [4, 5, 9, 10]:
        positions = charts.divisional_chart(
            jd_local,
            place,
            divisional_chart_factor=factor,
            chart_method=1,
        )
        divisional_charts[f"D{factor}"] = _map_pyjhora_positions(positions)

    md_dict = vimsottari.vimsottari_mahadasa(jd_local, place)
    md_items = list(md_dict.items())
    dashas = []
    for index, (planet_id, start_jd) in enumerate(md_items[:3]):
        sy, sm, sd, _ = swe.revjul(start_jd)
        if index + 1 < len(md_items):
            ey, em, ed, _ = swe.revjul(md_items[index + 1][1])
        else:
            ey, em, ed = sy, sm, sd
        dashas.append(
            {
                "planet": PLANET_ID_TO_NAME[planet_id],
                "start": f"{int(sy):04d}-{int(sm):02d}",
                "end": f"{int(ey):04d}-{int(em):02d}",
            }
        )

    return {
        "sav": {sign: int(sav_raw[index]) for index, sign in enumerate(SIGNS)},
        "divisional_charts": divisional_charts,
        "first_three_mahadashas": dashas,
    }


def _configure_pyjhora() -> None:
    import jhora

    pyjhora_path = Path(jhora.__file__).resolve().parents[1]
    if str(pyjhora_path) not in sys.path:
        sys.path.insert(0, str(pyjhora_path))
    swe.set_ephe_path(str(pyjhora_path / "jhora" / "data" / "ephe"))

    _patch_swe_for_pyjhora()

    from jhora import const
    from jhora.panchanga import drik

    drik.set_ayanamsa_mode("TRUE_CITRA")
    const._DEFAULT_AYANAMSA_MODE = "TRUE_CITRA"
    const._use_true_nodes_for_rahu_ketu = False


def _patch_swe_for_pyjhora() -> None:
    for fn_name in ["calc_ut", "calc"]:
        original = getattr(swe, fn_name)
        if getattr(original, "_vedic_reference_patched", False):
            continue

        def make_patch(func: Any) -> Any:
            def patched(jd: float, planet: int, flags: int = 0) -> Any:
                result = func(jd, planet, flags=flags)
                return (result[0], result[1]) if len(result) == 3 else result

            patched._vedic_reference_patched = True
            return patched

        setattr(swe, fn_name, make_patch(original))

    if hasattr(swe, "houses_ex"):
        original_houses = swe.houses_ex
        if not getattr(original_houses, "_vedic_reference_patched", False):

            def patched_houses(*args: Any, **kwargs: Any) -> Any:
                result = original_houses(*args, **kwargs)
                return (result[0], result[1]) if len(result) == 3 else result

            patched_houses._vedic_reference_patched = True
            swe.houses_ex = patched_houses


def _map_pyjhora_positions(positions: list[Any]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for planet_id, position in positions:
        name = PLANET_ID_TO_NAME.get(planet_id)
        if not name:
            continue
        sign_idx = int(position[0])
        degree = float(position[1]) if len(position) > 1 else 0.0
        mapped[name] = {
            "sign": SIGNS[sign_idx],
            "sign_idx": sign_idx,
            "degree": round(degree, 4),
        }
    return mapped
