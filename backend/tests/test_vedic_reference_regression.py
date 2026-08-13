from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import pytz
import swisseph as swe

from app.calculator.engine import (
    PLANETS_SWE,
    SIGNS,
    SIGN_LORDS,
    _format_degree_in_sign,
    calc_chara_karakas_7k8k,
    calc_aspects,
    calc_house_aspects,
    calc_planet,
    calc_transits,
    calculate_full_chart,
    calculate_rectification_signature,
    combustion_status,
    has_directional_strength,
    lunar_phase_hemicycle,
)
from app.calculator.divisional_pyjhora import calculate_divisional_charts
from app.calculator.dasha_pyjhora import (
    _event_provider_coordinate,
    _period_is_current,
    _period_lord_at,
    calculate_dasha_fixed,
    calculate_dasha_lords_at,
    calculate_dasha_lords_for_intervals,
)
from app.calculator.provenance import calculation_runtime_provenance
from app.calculator.provider_runtime import (
    configure_vedicdust_pyjhora,
    serialized_provider_call,
)
from app.calculator.pyjhora_compat import ensure_pyjhora_swe_compat
from app.vedicdust.chart_record_builder import (
    ChartRecordBuildInput,
    _d1_provider_position_mismatches,
    _fact,
    _gaja_kesari_structure,
    _independent_reference_check,
    _kendra_trikona_associations,
    _parivartana_exchanges,
    _varga_charts,
    build_chart_record,
)
from app.vedicdust.judgement_kernel import _relationship_context_findings
from app.vedicdust.judgement import build_judgement_context
from app.vedicdust.claims import build_claim_graph
from app.vedicdust.independent_reference import (
    certify_independent_reference_registry,
    find_independent_reference,
)
from app.vedicdust.varga_policy import INDEPENDENT_REFERENCE_VARGA_IDS
from app.vedicdust.models import (
    ConfidenceGrade,
    ConsultationConfidence,
    ConsultationDossier,
    ConsultationScope,
    GroundedNarrative,
    ReportSection,
    VargaChart,
)
from app.vedicdust.profiles import varga_method_setting
from app.vedicdust.reporting import (
    build_agent_context,
    build_report_manifest,
    materialize_consultation_dossier,
    render_consultation_report,
)


def test_planet_calculation_rejects_silent_moshier_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    returned_flags = swe.FLG_MOSEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
    monkeypatch.setattr(
        swe,
        "calc_ut",
        lambda *_args, **_kwargs: (
            (10.0, 0.0, 1.0, 1.0, 0.0, 0.0),
            returned_flags,
            "required SwissEph file not found; using Moshier eph.",
        ),
    )

    with pytest.raises(RuntimeError, match="refusing provider fallback.*Moshier"):
        calc_planet(0.0, swe.SUN)
    with pytest.raises(RuntimeError, match="refusing provider fallback.*Moshier"):
        calc_transits(0, 0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))


from app.vedicdust.source_registry import load_rule_catalog
from app.vedicdust.validation import (
    validate_agent_context,
    validate_chart_record_provenance,
    validate_claim_graph,
    validate_consultation_dossier,
)


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


def test_degree_formatter_never_emits_an_invalid_sixtieth_minute() -> None:
    assert _format_degree_in_sign(0.0) == "0°00'"
    assert _format_degree_in_sign(12.5) == "12°30'"
    assert _format_degree_in_sign(29.9999) == "29°59'"


def test_chara_karaka_ranking_exposes_evidence_precision_ties() -> None:
    planets = {
        "Sun": {"degree": 20.1234561},
        "Moon": {"degree": 20.1234562},
        "Mars": {"degree": 18.0},
        "Mercury": {"degree": 16.0},
        "Jupiter": {"degree": 14.0},
        "Venus": {"degree": 12.0},
        "Saturn": {"degree": 10.0},
        "Rahu": {"degree": 8.0},
    }

    result = calc_chara_karakas_7k8k(planets)

    assert result["7k_ambiguities"] == [
        {
            "roles": ["AK", "AmK"],
            "grahas": ["Moon", "Sun"],
            "degreeInSign": 20.123456,
        }
    ]


def test_kendra_trikona_association_uses_declared_house_lordship_only() -> None:
    taurus_house_lords = {
        1: {"lord": "Venus"},
        4: {"lord": "Sun"},
        5: {"lord": "Mercury"},
        7: {"lord": "Mars"},
        9: {"lord": "Saturn"},
        10: {"lord": "Saturn"},
    }

    assert _kendra_trikona_associations(taurus_house_lords, "Venus", "Saturn") == [
        {
            "kendraLord": "Venus",
            "kendraHouses": [1],
            "trikonaLord": "Saturn",
            "trikonaHouses": [9],
        },
        {
            "kendraLord": "Saturn",
            "kendraHouses": [10],
            "trikonaLord": "Venus",
            "trikonaHouses": [1],
        },
    ]
    assert _kendra_trikona_associations(taurus_house_lords, "Sun", "Mars") == []


def test_parivartana_requires_exact_mutual_house_lord_placement() -> None:
    house_lords = {
        1: {"lord": "Mars", "lord_house": 7},
        2: {"lord": "Venus", "lord_house": 6},
        6: {"lord": "Mercury", "lord_house": 2},
        7: {"lord": "Venus", "lord_house": 1},
        8: {"lord": "Mars", "lord_house": 7},
    }

    assert _parivartana_exchanges(house_lords) == [
        {
            "houses": [1, 7],
            "lords": ["Mars", "Venus"],
            "placements": {"Mars": 7, "Venus": 1},
            "association": "parivartana",
        },
        {
            "houses": [2, 6],
            "lords": ["Venus", "Mercury"],
            "placements": {"Venus": 6, "Mercury": 2},
            "association": "parivartana",
        },
    ]

    house_lords[7]["lord_house"] = 2
    assert all(exchange["houses"] != [1, 7] for exchange in _parivartana_exchanges(house_lords))


def test_gaja_kesari_requires_every_source_pinned_structural_condition() -> None:
    chart: dict[str, Any] = {
        "planets": {
            "Moon": {"sign_idx": 0},
            "Jupiter": {"sign_idx": 3},
            "Venus": {"sign_idx": 9},
            "Mercury": {"sign_idx": 2},
            "Sun": {"sign_idx": 5},
            "Mars": {"sign_idx": 6},
            "Saturn": {"sign_idx": 7},
            "Rahu": {"sign_idx": 8},
            "Ketu": {"sign_idx": 2},
        },
        "moon_phase": {"waxing": True},
        "aspects": [
            {
                "source": "Venus",
                "target": "Jupiter",
                "kind": "graha_drishti",
                "aspect": 7,
                "degree_gap": 4.5,
            }
        ],
        "dignities": {
            "Jupiter": {
                "special": None,
                "natural": "friend",
                "compound": "friend",
                "effective": "friend",
            }
        },
        "combustion_statuses": {"Jupiter": {"is_combust": False, "distance": 20.0}},
    }

    result = _gaja_kesari_structure(chart)
    assert result is not None
    assert result["jupiterRelativeHouse"] == 4
    assert result["supporters"] == [
        {
            "graha": "Venus",
            "contact": "graha_drishti",
            "aspectNumber": 7,
            "degreeGap": 4.5,
        }
    ]
    assert result["interpretationPermission"] == "structure_only"

    chart["planets"]["Jupiter"]["sign_idx"] = 2
    assert _gaja_kesari_structure(chart) is None
    chart["planets"]["Jupiter"]["sign_idx"] = 3
    chart["combustion_statuses"]["Jupiter"]["is_combust"] = True
    assert _gaja_kesari_structure(chart) is None
    chart["combustion_statuses"]["Jupiter"]["is_combust"] = False
    chart["dignities"]["Jupiter"]["natural"] = "enemy"
    chart["dignities"]["Jupiter"]["compound"] = "neutral"
    assert _gaja_kesari_structure(chart) is not None
    chart["dignities"]["Jupiter"]["compound"] = "enemy"
    assert _gaja_kesari_structure(chart) is None
    chart["dignities"]["Jupiter"]["natural"] = "friend"
    chart["dignities"]["Jupiter"]["compound"] = "friend"
    chart["aspects"] = []
    assert _gaja_kesari_structure(chart) is None


def test_gaja_kesari_judgement_is_source_bound_and_context_only() -> None:
    fact = _fact(
        fact_id="fact.D1.yoga.gaja_kesari",
        fact_type="yoga.gaja_kesari.structure",
        subject_ref="D1.Moon~Jupiter",
        value={
            "yoga": "Gaja-Kesari",
            "jupiterRelativeHouse": 4,
            "supporters": [{"graha": "Venus", "contact": "graha_drishti"}],
            "interpretationPermission": "structure_only",
        },
        method_profile_id="parashari-lahiri-1.1.0",
        confidence=ConfidenceGrade.CORROBORATED,
    )

    findings = _relationship_context_findings(
        topic_id="foundation",
        association_rule_id="judge.structure.same-sign-association",
        parivartana_rule_id="judge.structure.parivartana",
        gaja_kesari_rule_id="judge.structure.gaja-kesari",
        allowed_fact_ids={fact.fact_id},
        facts_by_id={fact.fact_id: fact},
    )

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "judge.structure.gaja-kesari"
    assert finding.polarity == "context"
    assert finding.parameters == {
        "interpretation": "gaja_kesari_structure_context_only",
        "jupiterRelativeHouse": 4,
        "supporters": ["Venus"],
        "interpretationPermission": "structure_only",
        "baseWeight": 0.45,
        "evidenceConfidenceMultiplier": 0.8,
    }
    assert all(
        forbidden not in finding.technical_statement.lower()
        for forbidden in ("fame", "wealth", "status", "success")
    )


def _reference_cases() -> list[dict[str, Any]]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["calculationProfile"] == "VedicDust parashari-lahiri-1.1.0 per-varga methods"
    return list(payload["cases"])


def test_dasha_period_boundaries_are_half_open() -> None:
    start = datetime(2020, 1, 1)
    boundary = datetime(2021, 1, 1)
    end = datetime(2022, 1, 1)

    assert _period_is_current(start, boundary, boundary) is False
    assert _period_is_current(boundary, end, boundary) is True


def test_dasha_lord_boundary_belongs_to_the_new_period() -> None:
    starts = {"old": 100.0, "new": 200.0}

    assert _period_lord_at(199.999, starts) == "old"
    assert _period_lord_at(200.0, starts) == "new"


def test_profile_uses_traditional_parashara_hora_not_provider_method_one() -> None:
    case = _reference_cases()[0]
    chart = _calculate_case(case)

    assert {placement["sign"] for placement in chart["divisional_charts"]["D2"].values()} <= {
        "Cancer",
        "Leo",
    }
    assert varga_method_setting(2).provider_method == 2


def test_full_chart_preserves_second_level_birth_time_across_providers() -> None:
    case = _reference_cases()[0]
    calculation_as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)
    chart_at_zero = calculate_full_chart(
        int(case["year"]),
        int(case["month"]),
        int(case["day"]),
        int(case["hour"]),
        int(case["minute"]),
        float(case["lat"]),
        float(case["lon"]),
        str(case["tz"]),
        second=0,
        calculation_as_of=calculation_as_of,
    )
    chart_at_thirty = calculate_full_chart(
        int(case["year"]),
        int(case["month"]),
        int(case["day"]),
        int(case["hour"]),
        int(case["minute"]),
        float(case["lat"]),
        float(case["lon"]),
        str(case["tz"]),
        second=30,
        calculation_as_of=calculation_as_of,
    )

    assert chart_at_thirty["julian_day_ut"] - chart_at_zero["julian_day_ut"] == pytest.approx(
        30 / 86400, abs=1e-9
    )
    assert (
        chart_at_thirty["planets"]["Moon"]["longitude"]
        != chart_at_zero["planets"]["Moon"]["longitude"]
    )
    assert chart_at_thirty["dashas"][0]["start_exact"] != chart_at_zero["dashas"][0]["start_exact"]
    assert _d1_provider_position_mismatches(chart_at_thirty) == []
    signature_at_thirty = calculate_rectification_signature(
        int(case["year"]),
        int(case["month"]),
        int(case["day"]),
        int(case["hour"]),
        int(case["minute"]),
        float(case["lat"]),
        float(case["lon"]),
        str(case["tz"]),
        chart_factors=[1],
        second=30,
    )
    assert signature_at_thirty["charaKaraka7k"] == {
        role: graha for role, graha, _degree in chart_at_thirty["karakas"]["7k"]
    }


def test_dasha_adapter_preserves_exact_period_boundaries() -> None:
    chart = _calculate_case(_reference_cases()[0])
    first_md = chart["dashas"][0]
    first_ad = first_md["antardashas"][0]
    first_pd = first_ad["pratyantardashas"][0]

    assert "T" in first_md["start_exact"]
    assert "T" in first_ad["start_exact"]
    assert "T" in first_pd["start_exact"]
    assert first_md["start_exact"].endswith("-04:00")
    assert first_md["antardashas"][1]["start_exact"] == first_ad["end_exact"]
    assert first_ad["pratyantardashas"][1]["start_exact"] == first_pd["end_exact"]


def test_dasha_boundaries_render_with_the_historical_iana_offset() -> None:
    dashas = calculate_dasha_fixed(
        2000,
        4,
        9,
        17,
        55,
        42.5,
        -71.2,
        -4.0,
        include_pratyantara=False,
        as_of=datetime(2020, 1, 1, tzinfo=timezone.utc),
        timezone_id="America/New_York",
    )
    venus_ad = next(
        antardasha for antardasha in dashas[0]["antardashas"] if antardasha["planet"] == "Venus"
    )

    assert venus_ad["start_exact"].endswith("-05:00")
    assert venus_ad["end_exact"].endswith("-04:00")


def test_dasha_event_lookup_uses_absolute_instants_across_dst() -> None:
    event_local = pytz.timezone("America/New_York").localize(datetime(2018, 12, 15, 12))
    event_utc = event_local.astimezone(timezone.utc)
    args = (2000, 4, 9, 17, 55, 42.5, -71.2, -4.0)

    assert calculate_dasha_lords_at(*args, [event_local]) == calculate_dasha_lords_at(
        *args, [event_utc]
    )
    assert _event_provider_coordinate(event_local, timezone(timedelta(hours=-4))) == datetime(
        2018, 12, 15, 13
    )


def test_dasha_event_lookup_rejects_naive_moments() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        calculate_dasha_lords_at(
            2000,
            4,
            9,
            17,
            55,
            42.5,
            -71.2,
            -4.0,
            [datetime(2018, 12, 15, 12)],
        )


def test_dasha_interval_lookup_detects_boundaries_missed_by_three_samples() -> None:
    args = (1990, 3, 15, 12, 0, 31.2304, 121.4737, 8.0)
    samples = [
        datetime(2055, 1, 1, 4, tzinfo=timezone.utc),
        datetime(2055, 7, 1, 4, tzinfo=timezone.utc),
        datetime(2055, 12, 31, 4, tzinfo=timezone.utc),
    ]
    sampled = calculate_dasha_lords_at(*args, samples)

    # All three old sample points report Rahu PD, even though multiple AD/PD
    # boundaries occur during the year. Exact boundary coverage must withhold it.
    assert {item["pratyantardasha"] for item in sampled} == {"Rahu"}
    interval = calculate_dasha_lords_for_intervals(
        *args,
        [
            (
                datetime(2054, 12, 31, 16, tzinfo=timezone.utc),
                datetime(2055, 12, 31, 15, 59, 59, tzinfo=timezone.utc),
            )
        ],
    )[0]
    assert interval == {
        "mahadasha": "Ketu",
        "antardasha": None,
        "pratyantardasha": None,
        "unstableLevels": ["ad", "pd"],
    }


def test_dasha_adapter_uses_the_profile_mean_sidereal_year() -> None:
    chart = _calculate_case(_reference_cases()[0])
    first_md = chart["dashas"][0]
    start = datetime.fromisoformat(first_md["start_exact"])
    end = datetime.fromisoformat(first_md["end_exact"])
    observed_year_days = (end - start).total_seconds() / 86400 / float(first_md["years"])

    assert observed_year_days == pytest.approx(365.256364, abs=2e-6)


@pytest.mark.parametrize(
    ("planet", "retrograde", "threshold"),
    [
        ("Moon", False, 12.0),
        ("Mars", False, 17.0),
        ("Mercury", False, 14.0),
        ("Mercury", True, 12.0),
        ("Jupiter", False, 11.0),
        ("Venus", False, 10.0),
        ("Venus", True, 8.0),
        ("Saturn", False, 15.0),
    ],
)
def test_combustion_policy_has_explicit_inclusive_boundaries(
    planet: str,
    retrograde: bool,
    threshold: float,
) -> None:
    at_boundary = combustion_status(planet, 360 - threshold, 0, retrograde)
    outside = combustion_status(planet, threshold + 0.001, 0, retrograde)

    assert at_boundary == {
        "is_combust": True,
        "distance": threshold,
        "threshold": threshold,
    }
    assert outside["is_combust"] is False


@pytest.mark.parametrize(
    ("moon_longitude", "sun_longitude", "expected"),
    [
        (0.0, 0.0, {"waxing": True, "sun_moon_diff": 0.0}),
        (179.94, 0.0, {"waxing": True, "sun_moon_diff": 179.94}),
        (180.0, 0.0, {"waxing": False, "sun_moon_diff": 180.0}),
        (359.96, 0.0, {"waxing": False, "sun_moon_diff": 359.96}),
        (1.0, 359.0, {"waxing": True, "sun_moon_diff": 2.0}),
    ],
)
def test_lunar_phase_hemicycle_boundary(
    moon_longitude: float, sun_longitude: float, expected: dict[str, float | bool]
) -> None:
    assert lunar_phase_hemicycle(moon_longitude, sun_longitude) == expected


def test_stateful_astronomy_provider_calls_are_serialized() -> None:
    active = 0
    maximum_active = 0
    counter_lock = threading.Lock()

    @serialized_provider_call
    def guarded_probe() -> None:
        nonlocal active, maximum_active
        with counter_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.01)
        with counter_lock:
            active -= 1

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _index: guarded_probe(), range(12)))

    assert maximum_active == 1


@pytest.mark.parametrize(
    ("planet", "strong_house"),
    [
        ("Sun", 10),
        ("Moon", 4),
        ("Mars", 10),
        ("Mercury", 1),
        ("Jupiter", 1),
        ("Venus", 4),
        ("Saturn", 7),
    ],
)
def test_directional_strength_policy_uses_declared_full_strength_house(
    planet: str,
    strong_house: int,
) -> None:
    assert has_directional_strength(planet, strong_house) is True
    assert has_directional_strength(planet, strong_house % 12 + 1) is False


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


def test_independent_reference_comparator_requires_external_source_and_exact_fields() -> None:
    case = _reference_cases()[0]
    chart = _calculate_case(case)
    payload = _normalized_external_reference(chart)

    matched = _independent_reference_check(chart, payload)
    assert matched.status == "passed"

    payload["sourceSystem"] = "PyJHora"
    rejected = _independent_reference_check(chart, payload)
    assert rejected.status == "failed"
    assert rejected.observed["reason"] == "non-independent-source"

    payload["sourceSystem"] = "Unregistered Astrology Software"
    rejected = _independent_reference_check(chart, payload)
    assert rejected.status == "failed"
    assert rejected.observed["reason"] == "invalid-reference-contract"


def test_independent_reference_comparator_blocks_field_mismatch() -> None:
    case = _reference_cases()[0]
    chart = _calculate_case(case)
    payload = _normalized_external_reference(chart)
    payload["vargaSigns"]["D9"]["Lagna"] = "Pisces"

    result = _independent_reference_check(chart, payload)

    assert result.status == "failed"
    assert isinstance(result.observed, list)
    assert any(issue["field"] == "D9.Lagna.sign" for issue in result.observed)

    payload = _normalized_external_reference(chart)
    actual_d60_lagna = payload["vargaSigns"]["D60"]["Lagna"]
    payload["vargaSigns"]["D60"]["Lagna"] = SIGNS[(SIGNS.index(actual_d60_lagna) + 1) % 12]
    result = _independent_reference_check(chart, payload)
    assert result.status == "failed"
    assert isinstance(result.observed, list)
    assert any(issue["field"] == "D60.Lagna.sign" for issue in result.observed)

    payload = _normalized_external_reference(chart)
    final_end = datetime.fromisoformat(payload["mahadashas"][-1]["end"])
    payload["mahadashas"][-1]["end"] = (final_end + timedelta(minutes=3)).isoformat()
    result = _independent_reference_check(chart, payload)
    assert result.status == "failed"
    assert isinstance(result.observed, list)
    assert any(issue["field"] == "Vimshottari.mahadashas[8].end" for issue in result.observed)

    payload = _normalized_external_reference(chart)
    payload["mahadashas"] = payload["mahadashas"][:-1]
    result = _independent_reference_check(chart, payload)
    assert result.status == "failed"
    assert result.observed["reason"] == "invalid-reference-contract"


def test_independent_reference_comparator_fails_closed_on_malformed_active_output() -> None:
    chart = _calculate_case(_reference_cases()[0])
    payload = _normalized_external_reference(chart)
    malformed = dict(chart)
    malformed["dashas"] = [dict(period) for period in chart["dashas"]]
    malformed["dashas"][0]["start_exact"] = "not-a-datetime"

    result = _independent_reference_check(malformed, payload)

    assert result.status == "failed"
    assert result.observed["reason"] == "invalid-active-chart-output"
    assert result.observed["errorType"] == "ValueError"


def test_varga_confidence_separates_calculation_assurance_from_input_stability() -> None:
    chart = _calculate_case(_reference_cases()[0])
    sensitivity = {
        "summary": {
            "divisionalConfidence": {
                "D1": {"confidence": "medium"},
                "D9": {"confidence": "low"},
            }
        }
    }

    internal = _varga_charts(chart, sensitivity)
    d1 = next(varga for varga in internal if varga.varga_id == "D1")
    d9 = next(varga for varga in internal if varga.varga_id == "D9")
    assert d1.calculation_assurance == "astronomical_authority"
    assert d1.input_stability == ConfidenceGrade.CORROBORATED
    assert d1.confidence == ConfidenceGrade.CORROBORATED
    assert d9.calculation_assurance == "internal_provider_regression"
    assert d9.input_stability == ConfidenceGrade.PROVISIONAL
    assert d9.confidence == ConfidenceGrade.PROVISIONAL

    externally_matched = _varga_charts(
        chart,
        sensitivity,
        independent_reference_passed=True,
    )
    matched_d9 = next(varga for varga in externally_matched if varga.varga_id == "D9")
    assert matched_d9.calculation_assurance == "independent_external_match"
    assert matched_d9.input_stability == ConfidenceGrade.PROVISIONAL
    assert matched_d9.confidence == ConfidenceGrade.PROVISIONAL

    contradictory = d9.model_dump(by_alias=True)
    contradictory["confidence"] = "verified"
    with pytest.raises(ValueError, match="lower of calculation assurance and input stability"):
        VargaChart.model_validate(contradictory)

    wrong_assurance = d9.model_dump(by_alias=True)
    wrong_assurance["calculationAssurance"] = "astronomical_authority"
    with pytest.raises(ValueError, match="non-D1 varga"):
        VargaChart.model_validate(wrong_assurance)


def test_independent_reference_registry_matches_exact_birth_assertion(tmp_path: Path) -> None:
    case = _reference_cases()[0]
    chart = _calculate_case(case)
    reference = _normalized_external_reference(chart)
    artifact = tmp_path / "jhora-export.txt"
    artifact.write_text("External JHora export used by the normalized test snapshot.\n")
    reference["sourceArtifactSha256"] = (
        "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()
    )
    registry = tmp_path / "independent-references.json"
    registry.write_text(
        json.dumps(
            {
                "schemaVersion": "vedicdust-independent-reference-registry/1.1.0",
                "entries": [
                    {
                        "caseId": "jhora-fixture-ordinary",
                        "coverageTags": ["ordinary"],
                        "selector": {
                            "localDate": "2000-04-09",
                            "localTime": "17:55",
                            "latitude": 42.5,
                            "longitude": -71.2,
                            "timezoneId": "Etc/GMT+4",
                            "methodProfileId": "parashari-lahiri-1.1.0",
                        },
                        "reference": reference,
                        "sourceArtifactPath": artifact.name,
                        "normalizationProtocol": "dual-entry-manual-v1",
                        "normalizedBy": "fixture-normalizer",
                        "reviewedBy": "fixture-reviewer",
                        "reviewedAt": "2026-08-02T00:00:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    matched = find_independent_reference(
        registry,
        local_date="2000-04-09",
        local_time="17:55:00",
        latitude=42.50005,
        longitude=-71.20005,
        timezone_id="Etc/GMT+4",
    )
    missing = find_independent_reference(
        registry,
        local_date="2000-04-09",
        local_time="17:56",
        latitude=42.5,
        longitude=-71.2,
        timezone_id="Etc/GMT+4",
    )
    wrong_second = find_independent_reference(
        registry,
        local_date="2000-04-09",
        local_time="17:55:45",
        latitude=42.5,
        longitude=-71.2,
        timezone_id="Etc/GMT+4",
    )

    assert matched is not None
    assert matched.source_system == "Jagannatha Hora"
    assert missing is None
    assert wrong_second is None

    certification = certify_independent_reference_registry(
        registry,
        minimum_cases=1,
        required_coverage_tags={"ordinary"},
        calculate_chart=lambda _selector: chart,
    )
    assert certification.status == "passed"
    assert certification.passed_cases == 1
    assert certification.failed_cases == 0
    assert certification.cases[0].selector.local_time == "17:55"
    assert certification.cases[0].source_artifact_sha256 == reference["sourceArtifactSha256"]

    valid_registry = registry.read_text(encoding="utf-8")
    registry.write_text(
        valid_registry.replace('"fixture-reviewer"', '"fixture-normalizer"'),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="distinct reviewer"):
        find_independent_reference(
            registry,
            local_date="2000-04-09",
            local_time="17:55:00",
            latitude=42.5,
            longitude=-71.2,
            timezone_id="Etc/GMT+4",
        )

    registry.write_text(valid_registry, encoding="utf-8")
    artifact.write_text("The source export changed after normalization.\n")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        find_independent_reference(
            registry,
            local_date="2000-04-09",
            local_time="17:55:00",
            latitude=42.5,
            longitude=-71.2,
            timezone_id="Etc/GMT+4",
        )


def test_independent_reference_certification_fails_policy_and_field_mismatch(
    tmp_path: Path,
) -> None:
    case = _reference_cases()[0]
    chart = _calculate_case(case)
    reference = _normalized_external_reference(chart)
    artifact = tmp_path / "jhora-export.txt"
    artifact.write_text("External JHora export used by the normalized test snapshot.\n")
    reference["sourceArtifactSha256"] = (
        "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()
    )
    registry = tmp_path / "independent-references.json"
    registry.write_text(
        json.dumps(
            {
                "schemaVersion": "vedicdust-independent-reference-registry/1.1.0",
                "entries": [
                    {
                        "caseId": "jhora-fixture-varga-boundary",
                        "coverageTags": ["varga-boundary"],
                        "selector": {
                            "localDate": "2000-04-09",
                            "localTime": "17:55:00",
                            "latitude": 42.5,
                            "longitude": -71.2,
                            "timezoneId": "Etc/GMT+4",
                            "methodProfileId": "parashari-lahiri-1.1.0",
                        },
                        "reference": reference,
                        "sourceArtifactPath": artifact.name,
                        "normalizationProtocol": "dual-entry-manual-v1",
                        "normalizedBy": "fixture-normalizer",
                        "reviewedBy": "fixture-reviewer",
                        "reviewedAt": "2026-08-02T00:00:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    mismatched_chart = json.loads(json.dumps(chart))
    current_sign = mismatched_chart["divisional_charts"]["D9"]["Lagna"]["sign"]
    mismatched_chart["divisional_charts"]["D9"]["Lagna"]["sign"] = SIGNS[
        (SIGNS.index(current_sign) + 1) % 12
    ]

    report = certify_independent_reference_registry(
        registry,
        minimum_cases=2,
        required_coverage_tags={"varga-boundary", "southern-hemisphere"},
        calculate_chart=lambda _selector: mismatched_chart,
    )

    assert report.status == "failed"
    assert report.failed_cases == 1
    assert report.policy_failures == [
        "corpus has 1 cases; minimum is 2",
        "missing required coverage tags: southern-hemisphere",
    ]
    assert any(issue.get("field") == "D9.Lagna.sign" for issue in report.cases[0].issues)


def test_pyjhora_vargas_honor_the_profile_mean_node_setting() -> None:
    case = _reference_cases()[0]
    vargas = calculate_divisional_charts(
        int(case["year"]),
        int(case["month"]),
        int(case["day"]),
        int(case["hour"]),
        int(case["minute"]),
        float(case["lat"]),
        float(case["lon"]),
        float(case["tz_offset"]),
        chart_factors=[1],
    )
    rahu = vargas["D1"]["Rahu"]
    observed_longitude = rahu["sign_idx"] * 30.0 + rahu["degree"]

    swe.set_sid_mode(swe.SIDM_LAHIRI)
    expected_longitude = swe.calc_ut(
        _utc_julian_day(case),
        swe.MEAN_NODE,
        swe.FLG_SIDEREAL | swe.FLG_SPEED,
    )[0][0]

    assert observed_longitude == pytest.approx(expected_longitude, abs=0.001)


def test_required_varga_failure_aborts_the_calculation(monkeypatch: pytest.MonkeyPatch) -> None:
    from jhora.horoscope.chart import charts

    def fail_divisional_chart(*args: object, **kwargs: object) -> object:
        raise ArithmeticError("provider failure")

    monkeypatch.setattr(charts, "divisional_chart", fail_divisional_chart)
    case = _reference_cases()[0]
    with pytest.raises(RuntimeError, match="required divisional chart D9 failed"):
        calculate_divisional_charts(
            int(case["year"]),
            int(case["month"]),
            int(case["day"]),
            int(case["hour"]),
            int(case["minute"]),
            float(case["lat"]),
            float(case["lon"]),
            float(case["tz_offset"]),
            chart_factors=[9],
        )


def test_profile_excludes_node_aspect_sources_but_keeps_them_as_targets() -> None:
    planets = {
        "Jupiter": {"sign_idx": 0, "degree": 10.0, "house": 1, "sign": "Aries"},
        "Rahu": {"sign_idx": 6, "degree": 10.0, "house": 7, "sign": "Libra"},
        "Ketu": {"sign_idx": 0, "degree": 10.0, "house": 1, "sign": "Aries"},
    }

    contacts = calc_aspects(planets)

    directed = [contact for contact in contacts if contact["kind"] == "graha_drishti"]
    assert any(
        contact["source"] == "Jupiter" and contact["target"] == "Rahu" for contact in directed
    )
    assert all(contact["source"] not in {"Rahu", "Ketu"} for contact in directed)

    same_sign = [contact for contact in contacts if contact["kind"] == "same_sign"]
    assert same_sign == [
        {
            "source": "Jupiter",
            "target": "Ketu",
            "direction": "mutual",
            "kind": "same_sign",
            "type": "同座接触",
            "aspect": 1,
            "source_house": 1,
            "target_house": 1,
            "target_sign": "Aries",
            "degree_gap": 0.0,
        }
    ]

    house_contacts = calc_house_aspects(planets, lagna_sign_idx=0)
    assert any(contact["source"] == "Jupiter" for contact in house_contacts)
    assert all(contact["source"] not in {"Rahu", "Ketu"} for contact in house_contacts)


def test_parashari_graha_drishti_matrix_matches_declared_profile() -> None:
    planets = {
        name: {"sign_idx": 0, "degree": 10.0, "house": 1, "sign": "Aries"}
        for name in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
    }

    contacts = calc_house_aspects(planets, lagna_sign_idx=0)
    observed = {
        name: sorted(contact["aspect"] for contact in contacts if contact["source"] == name)
        for name in planets
    }

    assert observed == {
        "Sun": [7],
        "Moon": [7],
        "Mars": [4, 7, 8],
        "Mercury": [7],
        "Jupiter": [5, 7, 9],
        "Venus": [7],
        "Saturn": [3, 7, 10],
    }


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

    assert _d1_provider_position_mismatches(chart) == []

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
            display_name="Reference subject",
            created_at=datetime.now(timezone.utc),
            locale="en",
            birth_date=birth_date,
            birth_time=birth_time,
            birth_place=str(case["label"]),
            birth_time_precision="exact",
            time_source="reference fixture",
            gender_context="not specified",
            relationship_status="not specified",
            reader_relationship="self",
            consultation_topics=(),
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
    assert result.subject.display_name == "Reference subject"

    assert result.status == "ready_for_judgement"
    assert result.astronomy is not None
    assert result.astronomy.calculation_provider == "Swiss Ephemeris + PyJHora"
    assert result.astronomy.calculation_adapter_version == "test"
    assert chart["planets"]["Rahu"]["speed"] == pytest.approx(
        chart["planets"]["Ketu"]["speed"], abs=1e-12
    )
    assert chart["planets"]["Rahu"]["speed"] < 0
    node_snapshots = {
        graha.graha: graha for graha in result.astronomy.grahas if graha.graha in {"Rahu", "Ketu"}
    }
    assert {graha.motion for graha in node_snapshots.values()} == {"retrograde"}
    assert node_snapshots["Rahu"].speed_deg_per_day == pytest.approx(
        node_snapshots["Ketu"].speed_deg_per_day, abs=1e-12
    )
    assert set(chart["combustion_statuses"]) == {
        "Moon",
        "Mars",
        "Mercury",
        "Jupiter",
        "Venus",
        "Saturn",
    }
    d1_vargottama_signs = {
        "Lagna": chart["lagna"]["sign"],
        **{name: placement["sign"] for name, placement in chart["planets"].items()},
    }
    assert {
        name: d1_vargottama_signs[name] == chart["divisional_charts"]["D9"][name]["sign"]
        for name in chart["vargottama"]
    } == chart["vargottama"]
    assert "fact.D1.Lagna.vargottama" in {fact.fact_id for fact in result.facts}
    combustion_facts = {
        fact.subject_ref: fact.value
        for fact in result.facts
        if fact.fact_type == "strength.combustion"
    }
    assert len(combustion_facts) == 6
    assert all(value["thresholdDeg"] is not None for value in combustion_facts.values())
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
    d1 = next(varga for varga in result.charts if varga.varga_id == "D1")
    d9 = next(varga for varga in result.charts if varga.varga_id == "D9")
    assert d1.calculation_assurance == "astronomical_authority"
    assert d1.input_stability == ConfidenceGrade.VERIFIED
    assert d1.confidence == ConfidenceGrade.VERIFIED
    assert d9.calculation_assurance == "internal_provider_regression"
    assert d9.input_stability == ConfidenceGrade.VERIFIED
    assert d9.confidence == ConfidenceGrade.CORROBORATED
    d9_facts = [fact for fact in result.facts if fact.subject_ref.startswith("D9.")]
    assert d9_facts
    assert {fact.provenance.confidence for fact in d9_facts} == {ConfidenceGrade.CORROBORATED}
    assert {fact.input_stability for fact in d9_facts} == {ConfidenceGrade.VERIFIED}
    assert result.timing_periods
    assert {period.input_stability for period in result.timing_periods} == {
        ConfidenceGrade.PROVISIONAL
    }
    assert {period.start_boundary.coverage for period in result.timing_periods} == {
        "canonical_only"
    }
    assert {period.end_boundary.coverage for period in result.timing_periods} == {"canonical_only"}
    assert {tuple(period.sensitivity_dependencies) for period in result.timing_periods} == {
        ("currentDasha", "moonNakshatra", "moonPada")
    }
    stability_drift = result.model_copy(deep=True)
    next(
        fact for fact in stability_drift.facts if fact.subject_ref.startswith("D9.")
    ).input_stability = ConfidenceGrade.PROVISIONAL
    with pytest.raises(ValueError, match="input stability drift"):
        validate_chart_record_provenance(stability_drift, load_rule_catalog())
    timing_stability_drift = result.model_copy(deep=True)
    timing_stability_drift.timing_periods[0].input_stability = ConfidenceGrade.VERIFIED
    with pytest.raises(ValueError, match="timing input stability drift"):
        validate_chart_record_provenance(timing_stability_drift, load_rule_catalog())
    assert not any(check.status == "failed" for check in result.quality_checks)
    checks_by_id = {check.check_id: check for check in result.quality_checks}
    assert checks_by_id["calculation.position-integrity"].status == "passed"
    assert checks_by_id["calculation.varga-integrity"].status == "passed"
    assert checks_by_id["calculation.vimshottari-continuity"].status == "passed"
    assert checks_by_id["calculation.interpretive-input-integrity"].status == "passed"
    assert checks_by_id["calculation.chara-karaka-ranking"].status == "passed"
    assert any(
        check.check_id == "varga.d1-provider-sign-alignment" for check in result.quality_checks
    )
    position_alignment = next(
        check
        for check in result.quality_checks
        if check.check_id == "varga.d1-provider-position-alignment"
    )
    assert position_alignment.status == "passed"
    assert position_alignment.observed == []
    independent_reference = next(
        check
        for check in result.quality_checks
        if check.check_id == "calculation.independent-golden-reference"
    )
    assert independent_reference.status == "warning"
    registered_rules = {rule.rule_id for rule in load_rule_catalog().rules}
    assert {fact.provenance.rule_id for fact in result.facts} <= registered_rules
    assert {period.provenance.rule_id for period in result.timing_periods} <= registered_rules
    expected_provenance = {
        "varga.vargottama": "derive.varga.d1-d9-vargottama",
        "strength.combustion": "derive.capacity.combustion-threshold",
        "strength.digbala": "derive.capacity.directional-strength-house",
        "karaka.chara": "derive.role.chara-karaka-7k",
        "point.arudha": "derive.point.arudha-al-ul",
        "state.moon_phase": "derive.state.lunar-phase-hemicycle",
        "strength.bhava_bala": "derive.strength.bhava-bala-pyjhora",
        "strength.vargeeya_bala": "derive.strength.vargeeya-bala-pyjhora",
        "point.special_lagna": "derive.point.special-lagna-pyjhora",
        "timing.transit.position": "derive.timing.transit-position-swisseph",
        "timing.transit.house": "derive.timing.transit-whole-sign-house",
        "timing.transit.sade_sati": "derive.timing.sade-sati-phase",
        "timing.transit.double_transit": "derive.timing.saturn-jupiter-double-transit",
    }
    for fact_type, rule_id in expected_provenance.items():
        matching = [fact for fact in result.facts if fact.fact_type == fact_type]
        assert matching
        assert {fact.provenance.rule_id for fact in matching} == {rule_id}
    fact_types = {fact.fact_type for fact in result.facts}
    yoga_facts = [fact for fact in result.facts if fact.fact_type == "yoga.raja.kendra_trikona"]
    assert len(yoga_facts) == case["expectedSnapshot"]["kendraTrikonaYogaCount"]
    assert {fact.provenance.rule_id for fact in yoga_facts} <= {
        "derive.yoga.kendra-trikona-association"
    }
    assert "rashi.house.occupant" in fact_types
    assert "role.house_ownership" in fact_types
    assert "relationship.dispositor_chain" in fact_types
    assert "varga.house.lord" in fact_types
    assert "relationship.same_sign" in fact_types
    assert "ashtakavarga.bav.graha" in fact_types
    assert "karaka.chara" in fact_types
    assert "point.arudha" in fact_types
    assert "strength.bhava_bala" in fact_types
    assert "point.special_lagna" in fact_types
    assert "timing.transit.position" in fact_types
    assert "timing.transit.house" in fact_types
    assert "timing.transit.sade_sati" in fact_types
    assert "timing.transit.double_transit" in fact_types
    dignity_facts = [fact for fact in result.facts if fact.fact_type == "strength.dignity"]
    bhava_bala_facts = [fact for fact in result.facts if fact.fact_type == "strength.bhava_bala"]
    assert dignity_facts and {fact.provenance.confidence for fact in dignity_facts} == {
        ConfidenceGrade.CORROBORATED
    }
    assert bhava_bala_facts and {fact.provenance.confidence for fact in bhava_bala_facts} == {
        ConfidenceGrade.PROVISIONAL
    }
    transit_positions = [
        fact for fact in result.facts if fact.fact_type == "timing.transit.position"
    ]
    transit_houses = [fact for fact in result.facts if fact.fact_type == "timing.transit.house"]
    assert transit_positions and all("house" not in fact.value for fact in transit_positions)
    assert transit_houses and all("house" in fact.value for fact in transit_houses)
    assert any(period.level == "pratyantardasha" for period in result.timing_periods)
    assert result.rectification is not None
    assert result.rectification.decision.status == "not_required"

    reference_time = datetime.now(timezone.utc)
    judgement_context = build_judgement_context(
        result,
        load_rule_catalog(),
        now=reference_time,
    )
    assert judgement_context.presentation_policy.model_dump() == {
        "policyId": "vedicdust-presentation-selection/1.0.0",
        "scoreSemantics": "presentation_salience_not_astrological_strength",
        "foundationAlwaysIncluded": True,
        "requestedTopicsFirst": True,
        "timingClaimsForRequestedTopicsOnly": True,
        "structuralTopicLimit": 8,
        "totalClaimLimit": 10,
        "minimumStructuralCoverage": 5,
        "foundationBaseline": 95,
        "domainBaseline": 45,
        "requestedTopicTarget": 100,
        "savNeutralReference": 28.0,
        "savDeviationMultiplier": 3,
        "savDeviationCap": 24,
        "aspectPointsPerFact": 2,
        "aspectPointsCap": 12,
        "eligibleVargaBoost": 8,
    }
    assert all(
        topic.priority_score == sum(reason.applied_points for reason in topic.priority_reasons)
        for topic in judgement_context.topics
    )
    assert all(
        set(reason.evidence_fact_ids)
        <= set(
            topic.natal_fact_ids
            + topic.capacity_fact_ids
            + topic.varga_fact_ids
            + topic.timing_fact_ids
        )
        for topic in judgement_context.topics
        for reason in topic.priority_reasons
    )
    assert {unit.topic_id: unit.primary_rule_id for unit in judgement_context.units} == {
        "foundation": "judge.foundation.integrated",
        "identity": "judge.identity.integrated",
        "career": "judge.career.d1-d10",
        "finance": "judge.finance.d1-d2-d4",
        "relationship": "judge.relationship.d1-d9",
        "home": "judge.home.d1-d4",
        "learning": "judge.learning.d1-d24",
        "children": "judge.children.d1-d7",
        "health": "judge.health.d1-d30",
        "dharma": "judge.dharma.d1-d9-d20",
        "family": "judge.family.d1-d12",
    }
    timing_restricted_context = build_judgement_context(
        result,
        load_rule_catalog(),
        restrict_timing=True,
        now=reference_time,
    )
    restricted_timing_rule = next(
        rule
        for rule in timing_restricted_context.rules
        if rule.rule_id == "judge.timing.vimshottari-activation"
    )
    assert restricted_timing_rule.evaluation_status == "ineligible"
    assert "requiredEvidenceLayers:timing" in restricted_timing_rule.failed_predicates
    all_findings = [finding for unit in judgement_context.units for finding in unit.findings]
    assert {
        "judge.structure.lagna-sun-moon-reference-points",
        "judge.structure.house-lord-placement",
        "judge.structure.house-occupancy",
        "judge.structure.graha-drishti",
        "judge.structure.varga-confirmation",
    } <= {finding.rule_id for finding in all_findings}
    foundation_unit = next(
        unit for unit in judgement_context.units if unit.topic_id == "foundation"
    )
    reference_points = next(
        finding
        for finding in foundation_unit.findings
        if finding.finding_code == "foundation.reference_points.lagna_sun_moon"
    )
    assert reference_points.rule_id == "judge.structure.lagna-sun-moon-reference-points"
    assert reference_points.polarity == "context"
    assert reference_points.fact_ids == [
        "fact.D1.Lagna.position",
        "fact.D1.Sun.position",
        "fact.D1.Moon.position",
    ]
    foundation_conclusion = next(
        conclusion
        for conclusion in foundation_unit.conclusions
        if conclusion.scope == "natal_promise"
    )
    foundation_context_fact_ids = {
        fact_id
        for finding in foundation_unit.findings
        if finding.polarity == "context"
        for fact_id in finding.fact_ids
    }
    foundation_conclusion_fact_ids = set(
        foundation_conclusion.supporting_fact_ids
        + foundation_conclusion.context_fact_ids
        + foundation_conclusion.counter_fact_ids
    )
    assert foundation_context_fact_ids <= foundation_conclusion_fact_ids
    assert set(foundation_conclusion.context_fact_ids).isdisjoint(
        foundation_conclusion.supporting_fact_ids
    )
    assert set(foundation_conclusion.context_fact_ids).isdisjoint(
        foundation_conclusion.counter_fact_ids
    )
    assert "D1 reference points are Lagna in" in foundation_conclusion.plain_statement
    assert all(
        finding.rule_id == "judge.structure.house-lord-placement"
        for finding in all_findings
        if finding.finding_code.endswith(".lord_path") and "varga" not in finding.parameters
    )
    assert all(
        finding.rule_id == "judge.structure.house-occupancy"
        for finding in all_findings
        if ".occupant." in finding.finding_code
    )
    assert all(
        finding.rule_id == "judge.structure.graha-drishti"
        for finding in all_findings
        if ".aspect." in finding.finding_code or ".lord_aspect." in finding.finding_code
    )
    assert all(
        finding.rule_id == "judge.structure.varga-confirmation"
        for finding in all_findings
        if "varga" in finding.parameters
    )
    assert all(
        finding.rule_id == "judge.structure.same-sign-association"
        for finding in all_findings
        if finding.parameters.get("interpretation")
        in {"same_sign_context_only", "raja_yoga_structure_context_only"}
    )
    gaja_kesari_facts = [
        fact for fact in result.facts if fact.fact_type == "yoga.gaja_kesari.structure"
    ]
    for yoga_fact in gaja_kesari_facts:
        yoga_findings = [
            finding
            for unit in judgement_context.units
            for finding in unit.findings
            if yoga_fact.fact_id in finding.fact_ids
        ]
        assert yoga_findings
        assert {finding.rule_id for finding in yoga_findings} == {"judge.structure.gaja-kesari"}
        assert {finding.polarity for finding in yoga_findings} == {"context"}
        assert {finding.parameters.get("interpretation") for finding in yoga_findings} == {
            "gaja_kesari_structure_context_only"
        }
        assert all(
            forbidden not in finding.technical_statement.lower()
            for finding in yoga_findings
            for forbidden in ("fame", "wealth", "status", "success")
        )
    for yoga_fact in yoga_facts:
        yoga_findings = [
            finding
            for unit in judgement_context.units
            for finding in unit.findings
            if yoga_fact.fact_id in finding.fact_ids
        ]
        assert yoga_findings
        assert {finding.polarity for finding in yoga_findings} == {"context"}
        assert {finding.parameters.get("interpretation") for finding in yoga_findings} == {
            "raja_yoga_structure_context_only"
        }
    facts_by_id = {fact.fact_id: fact for fact in result.facts}
    career_unit = next(unit for unit in judgement_context.units if unit.topic_id == "career")
    structural_conclusion = next(
        conclusion for conclusion in career_unit.conclusions if conclusion.scope == "natal_promise"
    )
    assert structural_conclusion.time_scope is None
    assert structural_conclusion.timing_period_ids == []
    assert all(
        finding.polarity == "context"
        for finding in career_unit.findings
        if ".d10_lord_path" in finding.finding_code
    )
    career_topic = next(topic for topic in judgement_context.topics if topic.topic_id == "career")
    h10_lord_fact = next(
        facts_by_id[fact_id]
        for fact_id in career_topic.natal_fact_ids
        if facts_by_id[fact_id].fact_type == "rashi.house.lord"
        and facts_by_id[fact_id].subject_ref == "D1.H10"
    )
    assert isinstance(h10_lord_fact.value, dict)
    h10_lord = str(h10_lord_fact.value["lord"])
    karaka_subjects = {"D1.Sun", "D1.Mercury", "D1.Jupiter", "D1.Saturn"}
    expected_context_fact_ids = {
        fact_id
        for fact_id in [*career_topic.natal_fact_ids, *career_topic.capacity_fact_ids]
        if (
            facts_by_id[fact_id].subject_ref.startswith("D1.H10.occupant.")
            or facts_by_id[fact_id].subject_ref.endswith("->H10")
            or facts_by_id[fact_id].subject_ref.endswith(f"->{h10_lord}")
            or (
                facts_by_id[fact_id].subject_ref in karaka_subjects
                and facts_by_id[fact_id].fact_type
                in {
                    "rashi.graha.position",
                    "strength.dignity",
                    "strength.shadbala",
                    "strength.combustion",
                }
            )
        )
    }
    compiled_context_fact_ids = {
        fact_id
        for finding in career_unit.findings
        if finding.polarity == "context"
        for fact_id in finding.fact_ids
    }
    assert expected_context_fact_ids <= compiled_context_fact_ids
    assert any(
        finding.finding_code.startswith("career.karaka.")
        and finding.parameters["interpretation"] == "natural_karaka_context_only"
        and finding.rule_id == "judge.structure.natural-karaka"
        for finding in career_unit.findings
    )
    assert any(
        finding.finding_code == "career.anchor.h10.lord_dispositor_chain"
        and finding.rule_id == "judge.structure.dispositor-path"
        and finding.polarity == "context"
        for finding in career_unit.findings
    )
    timing_conclusions = [
        conclusion
        for unit in judgement_context.units
        for conclusion in unit.conclusions
        if conclusion.scope == "timing"
    ]
    relevant_antardashas = [
        period
        for period in result.timing_periods
        if period.level == "antardasha"
        and period.interval.end > reference_time
        and period.interval.start < reference_time + timedelta(days=365 * 5)
    ]
    if relevant_antardashas:
        assert timing_conclusions
        for conclusion in timing_conclusions:
            assert conclusion.certainty_cap == "low"
            assert conclusion.time_scope is not None
            assert len(conclusion.timing_period_ids) == 1
            assert "judge.timing.vimshottari-activation" in conclusion.rule_ids
            assert "sop.promise-capacity-before-timing" in conclusion.rule_ids
            source_unit = next(
                unit for unit in judgement_context.units if conclusion in unit.conclusions
            )
            structural = next(
                item for item in source_unit.conclusions if item.scope == "natal_promise"
            )
            assert set(structural.rule_ids) <= set(conclusion.rule_ids)
            timing_finding = next(
                finding
                for finding in source_unit.findings
                if finding.finding_code.endswith("timing.vimshottari_anchor_activation")
            )
            selected_period = next(
                period
                for period in result.timing_periods
                if period.period_id == conclusion.timing_period_ids[0]
            )
            assert timing_finding.parameters["antardashaLord"] == selected_period.lords[-1]
            assert timing_finding.parameters["activatingLords"] == [selected_period.lords[-1]]
            assert set(timing_finding.parameters["activationDimensions"]) <= {
                "house_lord",
                "occupant",
                "graha_drishti",
            }
            assert timing_finding.parameters["activationDimensions"]
    else:
        assert timing_conclusions == []

    localized = result.model_copy(deep=True)
    localized.subject.locale = "zh"
    localized.subject.current_age = 12
    localized.subject.life_stage = "child"
    localized.subject.reader_relationship = "parent"
    localized.subject.consultation_topics = ["事业"]
    localized_context = build_judgement_context(
        localized,
        load_rule_catalog(),
        requested_topics=["career"],
        now=reference_time,
    )
    localized_career = next(
        unit for unit in localized_context.units if unit.topic_id == "career"
    ).conclusions[0]
    assert localized_career.title == "事业与社会贡献"
    assert localized_career.user_relevance == "你在本次咨询中明确关注了事业与社会贡献。"
    assert "第10宫" in localized_career.plain_statement
    assert "盘面条件" in localized_career.plain_statement
    assert "Integrated direction=" in localized_career.technical_statement
    localized_foundation = next(
        unit for unit in localized_context.units if unit.topic_id == "foundation"
    ).conclusions[0]
    assert "D1基础坐标为上升" in localized_foundation.plain_statement
    assert "太阳" in localized_foundation.plain_statement
    assert "月亮" in localized_foundation.plain_statement
    assert "宿第" in localized_foundation.plain_statement
    graph = build_claim_graph(localized, localized_context)
    validate_claim_graph(localized, graph, load_rule_catalog(), localized_context)
    assert 5 <= len(graph.claims) <= 10
    assert {"foundation", "career"} <= {claim.topic for claim in graph.claims}
    conclusions = {
        conclusion.conclusion_id: conclusion
        for unit in localized_context.units
        for conclusion in unit.conclusions
    }
    for claim in graph.claims:
        conclusion = conclusions[claim.conclusion_id]
        assert claim.evidence_confidence in {
            ConfidenceGrade.VERIFIED,
            ConfidenceGrade.CORROBORATED,
            ConfidenceGrade.PROVISIONAL,
            ConfidenceGrade.DISPUTED,
            ConfidenceGrade.UNAVAILABLE,
        }
        assert claim.plain_statement == conclusion.plain_statement
        assert claim.technical_statement == conclusion.technical_statement
        assert claim.supporting_fact_ids == conclusion.supporting_fact_ids
        assert claim.context_fact_ids == conclusion.context_fact_ids
        assert claim.counter_statements == conclusion.counter_statements
        assert claim.rule_ids == conclusion.rule_ids

    foundation_claim = next(
        claim for claim in graph.claims if claim.topic == "foundation" and claim.scope != "timing"
    )
    timing_claims = [claim for claim in graph.claims if claim.scope == "timing"]
    domain_claims = [
        claim
        for claim in graph.claims
        if claim.claim_id != foundation_claim.claim_id and claim.scope != "timing"
    ]
    assert len(domain_claims) >= 4
    executive_claims = domain_claims[:3]
    decision_claim = domain_claims[3]
    remaining_claims = domain_claims[4:]
    sections = [
        ReportSection(
            sectionId="scope",
            sectionKind="scope",
            title="Scope",
            purpose="Render consultation scope",
            priority=1,
        ),
        ReportSection(
            sectionId="executive",
            sectionKind="executive_synthesis",
            title="Executive synthesis",
            purpose="Render priority conclusions",
            claimIds=[claim.claim_id for claim in executive_claims],
            priority=2,
        ),
        ReportSection(
            sectionId="foundation",
            sectionKind="chart_foundation",
            title="Chart foundation",
            purpose="Render chart foundation",
            claimIds=[foundation_claim.claim_id],
            priority=3,
        ),
        *[
            ReportSection(
                sectionId=f"domain-{index}",
                sectionKind="priority_domain",
                title=claim.title,
                purpose="Render a secondary domain",
                claimIds=[claim.claim_id],
                priority=10 + index,
            )
            for index, claim in enumerate(remaining_claims, start=1)
        ],
        ReportSection(
            sectionId="timing",
            sectionKind="timing_outlook",
            title="Timing outlook",
            purpose="Render eligible timing windows",
            claimIds=[claim.claim_id for claim in timing_claims],
            priority=20,
        ),
        ReportSection(
            sectionId="decision",
            sectionKind="decision_support",
            title="Decision support",
            purpose="Render practical decision support",
            claimIds=[decision_claim.claim_id],
            priority=30,
        ),
        ReportSection(
            sectionId="follow-up",
            sectionKind="follow_up",
            title="Follow-up",
            purpose="Render follow-up questions",
            priority=40,
        ),
        ReportSection(
            sectionId="evidence",
            sectionKind="technical_evidence",
            title="Technical evidence",
            purpose="Render technical evidence",
            priority=50,
        ),
    ]
    sections[1].narratives = [
        GroundedNarrative(
            narrativeId="narrative.executive.1",
            kind="synthesis",
            text="These approved patterns are most useful when read together rather than as isolated placements.",
            claimIds=[claim.claim_id for claim in executive_claims],
        )
    ]
    for section in sections[2:]:
        if not section.claim_ids:
            continue
        section.narratives = [
            GroundedNarrative(
                narrativeId=f"narrative.{section.section_id}.1",
                kind="integration",
                text="This section presents the approved patterns together with their stated limits.",
                claimIds=section.claim_ids[:4],
            )
        ]
    dossier = ConsultationDossier(
        dossierId=f"dossier.{case['id']}",
        chartRecordId=localized.chart_record_id,
        chartRevision=localized.revision,
        methodProfileId=localized.calculation_profile.profile_id,
        claimGraphVersion=graph.schema_version,
        generatedAt=datetime.now(timezone.utc),
        locale="en",
        audience="self",
        scope=ConsultationScope(),
        confidence=ConsultationConfidence(
            overall="low",
            inputConfidence="provisional",
            rectificationConfidence="provisional",
            judgementConfidence="low",
            rationale=["Draft value replaced by the backend."],
        ),
        executiveClaimIds=[claim.claim_id for claim in executive_claims],
        sections=sections,
        releaseStatus="draft",
    )
    dossier = materialize_consultation_dossier(localized, graph, localized_context, dossier)
    assert dossier.release_status == "approved"
    assert dossier.dossier_id == f"dossier.{localized.chart_record_id}.r{localized.revision}"
    assert [section.priority for section in dossier.sections] == sorted(
        section.priority for section in dossier.sections
    )
    assert dossier.unresolved_questions == (
        localized.rectification.decision.unresolved_questions if localized.rectification else []
    )
    assert {check.status for check in dossier.quality_checks} == {"passed"}
    validate_consultation_dossier(localized, graph, dossier, localized_context)
    manifest = build_report_manifest(dossier)
    assert manifest.release_status == "approved"
    agent_context = build_agent_context(localized, graph, dossier)
    validate_agent_context(localized, graph, dossier, agent_context)
    assert agent_context.generated_at == dossier.generated_at
    assert agent_context.subject == localized.subject
    assert agent_context.reported_birth_date == localized.birth_assertion.local_date
    assert agent_context.rejected_hypotheses == []
    report = render_consultation_report(localized, graph, dossier)
    assert "# VedicDust" in report
    assert "用户报告的出生信息" in report
    assert "本次盘面采用的计算依据" in report
    assert "12岁 · 儿童 · 由父母阅读" in report
    assert "这对当事人可能意味着什么" in report
    assert foundation_claim.plain_statement in report
    assert "most useful when read together" in report
    assert localized.calculation_profile.profile_id not in report.split("##", 1)[0]
    claim_drift = agent_context.model_copy(deep=True)
    claim_drift.approved_claims[0].statement = "A stronger claim invented after release."
    with pytest.raises(ValueError, match="agent context claim drift"):
        validate_agent_context(localized, graph, dossier, claim_drift)
    projection_drift = agent_context.model_copy(deep=True)
    projection_drift.rejected_hypotheses = ["An omitted report claim was rejected."]
    with pytest.raises(ValueError, match="deterministic projection drifted"):
        validate_agent_context(localized, graph, dossier, projection_drift)
    subject_drift = agent_context.model_copy(deep=True)
    subject_drift.subject.life_stage = "adult"
    with pytest.raises(ValueError, match="subject framing"):
        validate_agent_context(localized, graph, dossier, subject_drift)
    section_drift = dossier.model_copy(deep=True)
    section_drift.sections[0].title = "A model-authored prediction in the heading"
    with pytest.raises(ValueError, match="section presentation"):
        validate_consultation_dossier(localized, graph, section_drift, localized_context)
    question_drift = dossier.model_copy(deep=True)
    question_drift.unresolved_questions = ["Will a guaranteed event happen next year?"]
    with pytest.raises(ValueError, match="unresolved questions"):
        validate_consultation_dossier(localized, graph, question_drift, localized_context)
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

    def career_conclusion_with_capacity(
        *, sav: float, dignity: str, shadbala_percentage: float, combust: bool
    ) -> tuple[
        str,
        str,
        str,
        set[str],
        set[str],
        set[str],
        list[str],
        str,
        list[str],
        dict[str, str],
    ]:
        scenario = result.model_copy(deep=True)
        scenario.subject.locale = "zh"
        scenario_facts = {fact.fact_id: fact for fact in scenario.facts}
        tenth_lord = scenario_facts["fact.D1.H10.lord"].value["lord"]
        scenario_facts["fact.D1.H10.sav"].value = sav
        scenario_facts[f"fact.D1.{tenth_lord}.dignity"].value["effective"] = dignity
        scenario_facts[f"fact.D1.{tenth_lord}.shadbala"].value["strength_pct"] = shadbala_percentage
        combustion_fact = scenario_facts.get(f"fact.D1.{tenth_lord}.combustion")
        if combustion_fact is not None:
            combustion_fact.value["isCombust"] = combust
        context = build_judgement_context(
            scenario,
            load_rule_catalog(),
            now=datetime.now(timezone.utc),
        )
        unit = next(item for item in context.units if item.topic_id == "career")
        conclusion = unit.conclusions[0]
        return (
            conclusion.conclusion_code,
            conclusion.direction,
            conclusion.certainty_cap,
            set(conclusion.supporting_fact_ids),
            set(conclusion.context_fact_ids),
            set(conclusion.counter_fact_ids),
            conclusion.counter_statements,
            conclusion.plain_statement,
            conclusion.limitations,
            {
                finding.finding_code: finding.polarity
                for finding in unit.findings
                if finding.finding_code.endswith(
                    (".lord_dignity", ".lord_shadbala", ".lord_combustion", ".sav")
                )
            },
        )

    (
        supportive_code,
        supportive_direction,
        supportive_cap,
        supportive_facts,
        supportive_context,
        supportive_counters,
        supportive_counter_text,
        supportive_plain,
        supportive_limitations,
        supportive_polarities,
    ) = career_conclusion_with_capacity(
        sav=36,
        dignity="exalted",
        shadbala_percentage=150,
        combust=False,
    )
    (
        challenging_code,
        challenging_direction,
        challenging_cap,
        challenging_facts,
        challenging_context,
        challenging_counters,
        challenging_counter_text,
        challenging_plain,
        challenging_limitations,
        challenging_polarities,
    ) = career_conclusion_with_capacity(
        sav=20,
        dignity="debilitated",
        shadbala_percentage=50,
        combust=True,
    )
    (
        mixed_code,
        mixed_direction,
        mixed_cap,
        mixed_facts,
        mixed_context,
        mixed_counters,
        mixed_counter_text,
        mixed_plain,
        mixed_limitations,
        mixed_polarities,
    ) = career_conclusion_with_capacity(
        sav=36,
        dignity="debilitated",
        shadbala_percentage=100,
        combust=False,
    )

    assert supportive_code == "career.supportive_structure"
    assert supportive_direction == "supportive"
    assert supportive_cap == "low"
    assert challenging_code == "career.challenging_structure"
    assert challenging_direction == "challenging"
    assert challenging_cap == "low"
    assert mixed_code == "career.descriptive_structure"
    assert mixed_direction == "descriptive"
    assert mixed_cap == "moderate"
    assert not mixed_facts
    assert "fact.D1.H10.lord" in supportive_facts
    assert "fact.D1.H10.lord" in challenging_facts
    assert "fact.D1.H10.sav" in supportive_context
    assert "fact.D1.H10.sav" in challenging_context
    tenth_lord = facts_by_id["fact.D1.H10.lord"].value["lord"]
    assert f"fact.D1.{tenth_lord}.dignity" in supportive_facts
    assert f"fact.D1.{tenth_lord}.shadbala" in supportive_facts
    assert f"fact.D1.{tenth_lord}.dignity" in challenging_facts
    assert f"fact.D1.{tenth_lord}.shadbala" in challenging_facts
    assert supportive_context.isdisjoint(supportive_counters)
    assert challenging_context.isdisjoint(challenging_counters)
    assert "fact.D1.H10.sav" in mixed_context
    assert not mixed_counters
    assert mixed_context.isdisjoint(mixed_counters)
    assert bool(supportive_counters) == bool(supportive_counter_text)
    assert bool(challenging_counters) == bool(challenging_counter_text)
    assert not mixed_counter_text
    assert "第10宫" in supportive_plain
    assert "第10宫" in challenging_plain
    assert "方向证据不足" in mixed_plain
    assert "支持因素占优" in supportive_plain
    assert "压力因素占优" in challenging_plain
    assert "另有可核查结构" in supportive_plain
    assert "擢升状态" in supportive_plain
    assert "Sarvashtakavarga为36点" in supportive_plain
    assert "落陷状态" in challenging_plain
    assert "Sarvashtakavarga为20点" in challenging_plain
    assert "不代表事件必然发生" in supportive_plain
    assert any("not passed independent professional" in item for item in supportive_limitations)
    assert any("not passed independent professional" in item for item in challenging_limitations)
    assert not any("not passed independent professional" in item for item in mixed_limitations)
    assert supportive_polarities["career.anchor.h10.lord_dignity"] == "supportive"
    assert supportive_polarities["career.anchor.h10.lord_shadbala"] == "supportive"
    assert challenging_polarities["career.anchor.h10.lord_dignity"] == "challenging"
    assert challenging_polarities["career.anchor.h10.lord_shadbala"] == "challenging"
    assert mixed_polarities["career.anchor.h10.lord_dignity"] == "context"
    assert mixed_polarities["career.anchor.h10.lord_shadbala"] == "context"
    assert supportive_polarities["career.anchor.h10.sav"] == "context"
    assert challenging_polarities["career.anchor.h10.sav"] == "context"
    assert all(
        finding.polarity == "context"
        for finding in career_unit.findings
        if finding.finding_code.endswith(".sav")
    )
    assert all(
        finding.parameters.get("directionWithheld") is True
        for finding in career_unit.findings
        if finding.finding_code.endswith(".sav")
        and float(finding.parameters["sav"]) not in range(27, 30)
    )


def test_calculator_rejects_ambiguous_civil_time() -> None:
    from app.calculator.engine import to_jd

    with pytest.raises(ValueError, match="ambiguous"):
        to_jd(2021, 11, 7, 1, 30, "America/New_York")


def test_to_jd_preserves_sub_minute_seconds() -> None:
    from app.calculator.engine import to_jd

    first = to_jd(1990, 1, 1, 8, 30, "UTC", second=0)
    second = to_jd(1990, 1, 1, 8, 30, "UTC", second=30)

    assert (second - first) * 86400 == pytest.approx(30, abs=0.001)


def test_ambiguous_civil_time_exposes_both_real_instants() -> None:
    from app.calculator.civil_time import AmbiguousCivilTimeError, resolve_civil_time

    with pytest.raises(AmbiguousCivilTimeError) as captured:
        resolve_civil_time(datetime(2021, 11, 7, 1, 30), "America/New_York")

    choices = captured.value.choices
    assert [choice.utc_offset_seconds for choice in choices] == [-4 * 3600, -5 * 3600]
    assert (choices[1].utc_datetime - choices[0].utc_datetime).total_seconds() == 3600


def test_explicit_fold_offsets_produce_distinct_julian_days() -> None:
    from app.calculator.engine import to_jd

    first = to_jd(
        2021,
        11,
        7,
        1,
        30,
        "America/New_York",
        utc_offset_seconds=-4 * 3600,
    )
    second = to_jd(
        2021,
        11,
        7,
        1,
        30,
        "America/New_York",
        utc_offset_seconds=-5 * 3600,
    )

    assert (second - first) * 24 == pytest.approx(1.0)


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
    expected_positions = {
        "Saturn": ("Pisces", 11, 12, 350.5001279551),
        "Jupiter": ("Cancer", 3, 4, 102.6245450995),
        "Rahu": ("Aquarius", 10, 11, 306.7399979194),
        "Ketu": ("Leo", 4, 5, 126.7399979194),
    }
    for graha, (sign, sign_index, house, longitude) in expected_positions.items():
        assert first[graha]["sign"] == sign
        assert first[graha]["sign_idx"] == sign_index
        assert first[graha]["house"] == house
        assert first[graha]["longitude"] == pytest.approx(longitude, abs=1e-9)
        assert first[graha]["degree"] == pytest.approx(longitude % 30, abs=1e-9)
    assert first["Rahu"]["speed"] == pytest.approx(first["Ketu"]["speed"], abs=1e-12)
    assert first["Rahu"]["retrograde"] is True
    assert first["Ketu"]["retrograde"] is True
    assert first["sade_sati"] == "inactive"
    assert first["double_transit_houses"] == [12]


@pytest.mark.parametrize(
    ("moon_sign_index", "expected_phase"),
    [(0, "phase1_rising"), (11, "phase2_peak"), (10, "phase3_fading"), (1, "inactive")],
)
def test_sade_sati_sign_phase_boundaries(moon_sign_index: int, expected_phase: str) -> None:
    from app.calculator.engine import calc_transits

    instant = datetime(2026, 7, 31, 12, 30, tzinfo=timezone.utc)

    assert calc_transits(0, moon_sign_index, as_of=instant)["sade_sati"] == expected_phase


def _normalized_external_reference(chart: dict[str, Any]) -> dict[str, Any]:
    d1 = {"Lagna": chart["lagna"], **chart["planets"]}
    return {
        "sourceSystem": "Jagannatha Hora",
        "sourceVersion": "comparator-contract-test",
        "sourceArtifactSha256": "sha256:" + "1" * 64,
        "methodProfileId": "parashari-lahiri-1.1.0",
        "d1Positions": {
            body: {"sign": value["sign"], "degreeInSign": value["degree"]}
            for body, value in d1.items()
        },
        "vargaSigns": {
            varga_id: {
                body: value["sign"]
                for body, value in chart["divisional_charts"][varga_id].items()
                if body
                in {
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
                }
            }
            for varga_id in INDEPENDENT_REFERENCE_VARGA_IDS
        },
        "savBySign": chart["sav"],
        "shadbalaRupas": {body: value["total_rupas"] for body, value in chart["shadbala"].items()},
        "mahadashas": [
            {
                "lord": period["planet"],
                "start": period["start_exact"],
                "end": period["end_exact"],
            }
            for period in chart["dashas"]
        ],
    }


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

    from jhora import const
    from jhora.horoscope.chart import ashtakavarga, charts
    from jhora.horoscope.dhasa.graha import vimsottari
    from jhora.panchanga import drik
    from jhora.panchanga.drik import Place

    # Explicit, not inherited from whatever a prior test call left in the
    # shared PyJHora/swisseph global ayanamsa state.
    configure_vedicdust_pyjhora()
    vimsottari.year_duration = const.sidereal_year

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
        method = varga_method_setting(factor)
        positions = charts.divisional_chart(
            jd_local,
            place,
            divisional_chart_factor=factor,
            chart_method=method.provider_method or 1,
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

    configure_vedicdust_pyjhora()


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
