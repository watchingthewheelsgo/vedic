from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import pytz
import swisseph as swe

from app.calculator.engine import PLANETS_SWE, SIGNS, SIGN_LORDS, calculate_full_chart
from app.calculator.provenance import calculation_runtime_provenance
from app.calculator.pyjhora_compat import ensure_pyjhora_swe_compat
from app.vedicdust.chart_record_builder import ChartRecordBuildInput, build_chart_record
from app.vedicdust.judgement import build_judgement_context
from app.vedicdust.source_registry import load_rule_catalog


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
    assert payload["calculationProfile"] == "LAHIRI mean nodes whole-sign PyJHora chart_method=1"
    return list(payload["cases"])


def test_calculation_runtime_provenance_matches_the_pinned_runtime() -> None:
    expected = {}
    lock_path = Path(__file__).parents[1] / "astrology-runtime.lock"
    for raw_line in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, package_version = line.split("==", maxsplit=1)
        expected[name] = package_version

    provenance = calculation_runtime_provenance()

    assert provenance.provider_versions == {
        name: expected[name] for name in ("PyJHora", "pysweph", "pytz", "numpy", "python-dateutil")
    }
    assert provenance.timezone_database_version
    assert provenance.ephemeris_data_fingerprint.startswith("sha256:")
    assert len(provenance.ephemeris_data_fingerprint) == 71


@pytest.mark.parametrize("case", _reference_cases(), ids=lambda case: case["id"])
def test_vedic_engine_matches_swiss_ephemeris_core_positions(case: dict[str, Any]) -> None:
    chart = _calculate_case(case)
    jd = _utc_julian_day(case)
    swe.set_sid_mode(swe.SIDM_LAHIRI)

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
def test_vedic_engine_adapter_matches_direct_pyjhora_for_all_vargas_sav_and_dasha(
    case: dict[str, Any],
) -> None:
    chart = _calculate_case(case)
    reference = _pyjhora_reference(case)

    assert chart["sav"] == reference["sav"]
    assert sum(chart["sav"].values()) == 337

    for chart_key in [
        "D1",
        "D2",
        "D3",
        "D4",
        "D5",
        "D7",
        "D9",
        "D10",
        "D12",
        "D16",
        "D20",
        "D24",
        "D27",
        "D30",
        "D60",
    ]:
        actual_chart = chart["divisional_charts"][chart_key]
        expected_chart = reference["divisional_charts"][chart_key]
        for body in [
            "Lagna",
            "Sun",
            "Moon",
            "Mars",
            "Mercury",
            "Jupiter",
            "Venus",
            "Saturn",
            "Rahu",
            "Ketu",
        ]:
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


@pytest.mark.parametrize("case", _reference_cases(), ids=lambda case: case["id"])
def test_reference_calculation_builds_a_typed_chart_record(case: dict[str, Any]) -> None:
    chart = _calculate_case(case)
    birth_date = f"{int(case['year']):04d}-{int(case['month']):02d}-{int(case['day']):02d}"
    birth_time = f"{int(case['hour']):02d}:{int(case['minute']):02d}"
    confidence = {
        f"D{factor}": {"confidence": "high", "useAsPrimaryEvidence": factor != 60}
        for factor in [1, 2, 3, 4, 5, 7, 9, 10, 12, 16, 20, 24, 27, 30, 60]
    }
    result = build_chart_record(
        ChartRecordBuildInput(
            chart_record_id=f"chart.{case['id']}",
            reading_session_id=f"session.{case['id']}",
            revision=1,
            subject_id=f"subject.{case['id']}",
            created_at=datetime.now(timezone.utc),
            locale="en",
            birth_date=birth_date,
            birth_time=birth_time,
            birth_place=str(case["label"]),
            birth_time_precision="exact",
            time_source="reference fixture",
            gender_context="not specified",
            relationship_status="not specified",
            place_label=str(case["label"]),
            latitude=float(case["lat"]),
            longitude=float(case["lon"]),
            timezone_id=str(case["tz"]),
            place_source="reference fixture",
            place_accuracy="coordinate",
            place_confidence="high",
            place_matched=None,
            calculation_version="test",
            ephemeris_version="test",
            provider_versions={"PyJHora": "4.8.6", "pysweph": "2.10.3.6"},
            timezone_database_version="test",
            ephemeris_data_fingerprint="sha256:" + "0" * 64,
            chart=chart,
            input_context={
                "time": {
                    "window": {
                        "start": f"{birth_date} {birth_time}",
                        "end": _one_minute_later(birth_date, birth_time),
                    }
                }
            },
            sensitivity_scan={
                "summary": {"divisionalConfidence": confidence},
                "reportReadiness": {
                    "mode": "standard_after_prevalidation",
                    "blockingFactors": [],
                },
            },
        )
    )

    assert result.status == "ready_for_judgement"
    assert result.astronomy is not None
    assert result.astronomy.calculation_provider == "Swiss Ephemeris + PyJHora"
    assert result.astronomy.calculation_adapter_version == "test"
    assert len(result.astronomy.grahas) == 9
    assert {varga.factor for varga in result.charts} == {
        1,
        2,
        3,
        4,
        5,
        7,
        9,
        10,
        12,
        16,
        20,
        24,
        27,
        30,
        60,
    }
    for varga in result.charts:
        assert [entry.house for entry in varga.house_lords] == list(range(1, 13))
        assert all(entry.lord_house is not None for entry in varga.house_lords)
        placement_houses = {placement.object_id: placement.house for placement in varga.placements}
        for entry in varga.house_lords:
            expected_sign = (varga.lagna.position.sign_index + entry.house - 1) % 12
            expected_lord = SIGN_LORDS[expected_sign]
            assert entry.sign_index == expected_sign
            assert entry.lord == expected_lord
            assert entry.lord_house == placement_houses[expected_lord]
    assert not any(check.status == "failed" for check in result.quality_checks)
    assert any(
        check.check_id == "varga.d1-provider-sign-alignment" for check in result.quality_checks
    )
    independent_reference = next(
        check
        for check in result.quality_checks
        if check.check_id == "calculation.independent-golden-reference"
    )
    assert independent_reference.status == "warning"
    registered_rules = {rule.rule_id for rule in load_rule_catalog().rules}
    assert {fact.provenance.rule_id for fact in result.facts} <= registered_rules
    assert {period.provenance.rule_id for period in result.timing_periods} <= registered_rules
    fact_types = {fact.fact_type for fact in result.facts}
    assert "rashi.house.occupant" in fact_types
    assert "varga.house.lord" in fact_types
    assert "relationship.same_sign" in fact_types
    assert "ashtakavarga.bav.graha" in fact_types
    assert "karaka.chara" in fact_types
    assert "point.arudha" in fact_types
    assert "strength.bhava_bala" in fact_types
    assert "point.special_lagna" in fact_types
    assert "timing.transit.position" in fact_types
    assert "timing.transit.sade_sati" in fact_types
    assert "timing.transit.double_transit" in fact_types
    assert any(period.level == "pratyantardasha" for period in result.timing_periods)
    assert result.rectification is not None
    assert result.rectification.decision.status == "not_required"

    judgement_context = build_judgement_context(
        result,
        load_rule_catalog(),
        now=datetime.now(timezone.utc),
    )
    facts_by_id = {fact.fact_id: fact for fact in result.facts}
    career_unit = next(unit for unit in judgement_context.units if unit.topic_id == "career")
    required_varga_subjects = {
        "D10.Lagna",
        "D10.Sun",
        "D10.Mercury",
        "D10.Jupiter",
        "D10.Saturn",
        "D10.H2",
        "D10.H6",
        "D10.H10",
        "D10.H11",
    }
    varga_subjects = {facts_by_id[fact_id].subject_ref for fact_id in career_unit.varga_fact_ids}
    assert required_varga_subjects <= varga_subjects
    assert {subject for subject in varga_subjects if subject.startswith("D10.H")} == {
        "D10.H2",
        "D10.H6",
        "D10.H10",
        "D10.H11",
    }
    assert len(varga_subjects) < 22


def test_calculator_rejects_ambiguous_civil_time() -> None:
    from app.calculator.engine import to_jd

    with pytest.raises(ValueError, match="ambiguous"):
        to_jd(2021, 11, 7, 1, 30, "America/New_York")


def test_calculator_rejects_nonexistent_civil_time() -> None:
    from app.calculator.engine import to_jd

    with pytest.raises(ValueError, match="does not exist"):
        to_jd(2021, 3, 14, 2, 30, "America/New_York")


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


def test_pyjhora_swisseph_compatibility_patch_is_idempotent() -> None:
    from app.calculator.dasha_pyjhora import _setup_jhora
    from app.calculator.extras_pyjhora import _setup
    from app.calculator.pyjhora_compat import ensure_pyjhora_swe_compat

    ensure_pyjhora_swe_compat()
    patched_calc_ut = swe.calc_ut
    patched_calc = swe.calc
    patched_houses = swe.houses_ex

    for _ in range(3):
        _setup()
        _setup_jhora()
        ensure_pyjhora_swe_compat()

    assert swe.calc_ut is patched_calc_ut
    assert swe.calc is patched_calc
    assert swe.houses_ex is patched_houses


def test_transit_snapshot_uses_explicit_utc_instant() -> None:
    from datetime import timedelta

    from app.calculator.engine import calc_transits

    instant = datetime(2026, 7, 31, 12, 30, tzinfo=timezone.utc)
    same_instant = instant.astimezone(timezone(timedelta(hours=8)))

    first = calc_transits(0, 1, as_of=instant)
    second = calc_transits(0, 1, as_of=same_instant)

    assert first == second
    assert first["as_of_utc"] == "2026-07-31T12:30:00+00:00"


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


def _one_minute_later(birth_date: str, birth_time: str) -> str:
    value = datetime.fromisoformat(f"{birth_date}T{birth_time}")
    return (value + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M")


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
    from jhora.panchanga import drik
    from jhora.panchanga.drik import Place

    # Explicit, not inherited from whatever a prior test call left in the
    # shared PyJHora/swisseph global ayanamsa state.
    drik.set_ayanamsa_mode("LAHIRI")

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
    for factor in [1, 2, 3, 4, 5, 7, 9, 10, 12, 16, 20, 24, 27, 30, 60]:
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

    ensure_pyjhora_swe_compat()

    from jhora import const
    from jhora.panchanga import drik

    drik.set_ayanamsa_mode("LAHIRI")
    const._DEFAULT_AYANAMSA_MODE = "LAHIRI"
    const._use_true_nodes_for_rahu_ketu = False


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
