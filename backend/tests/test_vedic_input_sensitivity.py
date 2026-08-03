from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.schemas import (
    BirthInput,
    RectificationInterviewInput,
    RectificationLifeEventsInput,
    SkillArtifact,
    SkillRunInput,
)
from app.services.place_service import ResolvedPlace
from app.services.chart_rectification import ChartRectificationService
from app.services.life_event_rectification import (
    candidate_event_period_fingerprint,
    parse_life_event_ledger,
    score_candidate_events,
)
from app.services.skill_runtime import SkillRuntime
from app.services.skill_workspace import SkillWorkspace
from app.services.vedic_calculator import VedicCalculator
from app.vedicdust.chart_record_builder import _sensitivity_boundaries
from app.vedicdust.models import (
    CandidateInterval,
    ChartRecord,
    ConfidenceGrade,
    RectificationDecision,
    RectificationRecord,
    SensitivityBoundary,
    TimeRange,
)
from app.vedicdust.rectification_policy import (
    RECTIFICATION_EVENT_MAPPING_ID,
    RECTIFICATION_RULE_ID,
    RECTIFICATION_SCORING_POLICY,
    RECTIFICATION_SCORING_POLICY_ID,
)
from app.vedicdust.rule_engine import evaluate_method_rule


def _rectification_ledger() -> dict[str, object]:
    return {
        "schemaVersion": "life-event-ledger/v1",
        "eventCollectionRequired": False,
        "events": [
            {
                "eventId": "evt_1_201806_career",
                "date": "2018-06",
                "category": "career",
                "role": "calibration",
            },
            {
                "eventId": "evt_2_202009_marriage",
                "date": "2020-09",
                "category": "marriage",
                "role": "calibration",
            },
            {
                "eventId": "evt_3_202305_relocation",
                "date": "2023-05",
                "category": "relocation",
                "role": "holdout",
            },
        ],
    }


def _birth_payload() -> dict[str, Any]:
    return {
        "year": 1990,
        "month": 1,
        "day": 1,
        "hour": 8,
        "minute": 30,
        "dob": "1990-01-01",
        "time": "08:30",
        "timezone": "Asia/Shanghai",
        "lat": 31.2304,
        "lon": 121.4737,
    }


def _birth_input(place: str = "Shanghai, Shanghai, China") -> BirthInput:
    return BirthInput(
        birthDate="1990-01-01",
        birthTime="08:30",
        birthPlace=place,
        birthTimePrecision="exact",
        gender="女",
        relationship="单身",
        timeSource="birth certificate",
        lifeEvents="",
        locale="zh",
    )


def test_timing_boundary_sampling_recalculates_declared_window_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    payload = _birth_payload()
    base_dashas = [
        {
            "planet": "Venus",
            "start_exact": "1985-01-01T00:00:00+08:00",
            "end_exact": "2005-01-01T00:00:00+08:00",
            "antardashas": [],
        }
    ]
    calls: list[tuple[int, int]] = []

    def fake_calculate_dasha_fixed(
        year: int,
        month: int,
        day: int,
        hour: int,
        minute: int,
        *_args: object,
        **_kwargs: object,
    ) -> list[dict[str, object]]:
        calls.append((hour, minute))
        return base_dashas

    monkeypatch.setattr(
        "app.calculator.dasha_pyjhora.calculate_dasha_fixed",
        fake_calculate_dasha_fixed,
    )

    result = calculator._timing_boundary_sampling(
        payload,
        "exact",
        "birth certificate",
        {"dashas": base_dashas},
        datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert result["status"] == "complete"
    assert result["successfulSampleCount"] == 3
    assert calls == [(8, 28), (8, 32)]
    assert {tuple(sample["roles"]) for sample in result["samples"]} == {
        ("window-start",),
        ("reported",),
        ("window-end",),
    }


def _base_chart() -> dict[str, Any]:
    divisional_lagnas = {
        1: "Aries",
        2: "Taurus",
        3: "Gemini",
        4: "Cancer",
        5: "Leo",
        7: "Virgo",
        9: "Libra",
        10: "Capricorn",
        12: "Aquarius",
        16: "Pisces",
        20: "Aries",
        24: "Taurus",
        27: "Gemini",
        30: "Cancer",
        60: "Leo",
    }
    divisional_charts = {
        f"D{factor}": {"Lagna": {"sign": sign, "sign_idx": index % 12, "degree": 0}}
        for index, (factor, sign) in enumerate(divisional_lagnas.items())
    }
    return {
        "lagna": {"sign": "Aries", "degree": 5.0, "nakshatra": {"name": "Ashwini"}},
        "planets": {
            "Moon": {
                "sign": "Taurus",
                "longitude": 50.0,
                "nakshatra": {"name": "Rohini", "pada": 1},
            }
        },
        "dashas": [{"planet": "Moon", "is_current": True, "antardashas": []}],
        "divisional_charts": divisional_charts,
    }


def test_calculator_payload_preserves_second_level_birth_time() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    intake = _birth_input().model_copy(update={"birth_time": "08:30:45"})
    place = ResolvedPlace(
        label="Shanghai, Shanghai, China",
        lat=31.2304,
        lon=121.4737,
        timezone="Asia/Shanghai",
        source="geonames-local",
        accuracy="city",
        radius_km=25.0,
        confidence="medium",
    )
    birth_time = calculator._parse_birth_time(intake.birth_time, intake.birth_time_precision)
    payload = calculator._calculator_payload(
        intake,
        calculator._parse_birth_date(intake.birth_date),
        birth_time,
        place,
    )

    assert birth_time.second == 45
    assert birth_time.normalized == "08:30:45"
    assert payload["second"] == 45
    assert payload["time"] == "08:30:45"


def test_scan_summary_marks_changed_divisional_chart_as_high_risk() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    place = ResolvedPlace(
        label="Shanghai, Shanghai, China",
        lat=31.2304,
        lon=121.4737,
        timezone="Asia/Shanghai",
        source="geonames-local",
        accuracy="city",
        radius_km=25.0,
        confidence="medium",
    )

    summary = calculator._scan_summary(
        "approximate",
        place,
        time_variants=[{"changed": ["d9Lagna"]}],
        place_variants=[],
        boundary_flags=[],
    )

    assert summary["riskLevel"] == "high"
    assert "variant_changes:d9Lagna" in summary["riskFactors"]
    assert summary["divisionalConfidence"]["D9"]["confidence"] == "low"
    assert summary["divisionalConfidence"]["D1"]["confidence"] == "medium"
    assert summary["divisionalConfidence"]["D60"]["recommendedUse"] == "rectification_only_or_omit"
    assert summary["divisionalConfidence"]["D4"]["role"] == (
        "residence, houses, property, and fortune"
    )
    assert summary["divisionalConfidence"]["D16"]["role"] == (
        "vehicles, pleasures, comforts, and discomforts"
    )
    assert summary["divisionalConfidence"]["D4"]["policyId"] == (
        "vedicdust-varga-domain-policy/1.0.0"
    )
    assert summary["divisionalConfidence"]["D4"]["sourceIds"] == [
        "lineage.pvr-integrated-approach-2000-2010"
    ]
    assert summary["rectificationAxes"] == ["time", "place"]
    assert summary["placeRectificationAllowed"] is True


def test_scan_summary_keeps_precise_stable_coordinate_low_risk() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    place = ResolvedPlace(
        label="manual",
        lat=31.2304,
        lon=121.4737,
        timezone="Asia/Shanghai",
        source="manual",
        accuracy="coordinate",
        radius_km=0.25,
        confidence="high",
    )

    summary = calculator._scan_summary(
        "exact",
        place,
        time_variants=[{"changed": []}],
        place_variants=[{"changed": []}],
        boundary_flags=[],
    )

    assert summary["riskLevel"] == "low"
    assert summary["riskFactors"] == []
    assert summary["divisionalConfidence"]["D10"]["confidence"] == "high"


def test_scan_summary_requires_rectification_when_d1_graha_structure_changes() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    place = ResolvedPlace(
        label="manual",
        lat=31.2304,
        lon=121.4737,
        timezone="Asia/Shanghai",
        source="manual",
        accuracy="coordinate",
        radius_km=0.25,
        confidence="high",
    )

    summary = calculator._scan_summary(
        "exact",
        place,
        time_variants=[{"changed": ["d1Structure"]}],
        place_variants=[],
        boundary_flags=[],
    )

    assert summary["riskLevel"] == "high"
    assert summary["blockingChangedFields"] == ["d1Structure"]
    readiness = calculator._report_readiness(
        summary,
        calculator._stability_map({"d1Structure"}, summary["divisionalConfidence"]),
        [{"candidateId": "A"}, {"candidateId": "B"}],
        "exact",
        place,
    )
    assert readiness["mode"] == "rectification_required"
    assert readiness["coreAllowedWithoutRectification"] is False
    assert summary["divisionalConfidence"]["D60"]["recommendedUse"] == "final_confirmation_only"
    assert summary["advancedVargaPolicy"]["finalConfirmationOnly"] == ["D60"]
    assert summary["advancedVargaPolicy"]["policyId"] == ("vedicdust-varga-domain-policy/1.0.0")
    assert summary["rectificationAxes"] == ["time"]
    assert summary["placeRectificationAllowed"] is False


def test_scan_failure_blocks_rectification_until_civil_input_is_resolved() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    place = ResolvedPlace(
        label="New York, New York, United States",
        lat=40.7128,
        lon=-74.006,
        timezone="America/New_York",
        source="manual",
        accuracy="coordinate",
        radius_km=0.25,
        confidence="high",
    )
    summary = calculator._scan_summary(
        "approximate",
        place,
        time_variants=[
            {
                "label": "01:00-01:59",
                "interval": {
                    "start": "2025-11-02 01:00",
                    "end": "2025-11-02 02:00",
                },
                "error": "Ambiguous local birth time",
            }
        ],
        place_variants=[],
        boundary_flags=[],
    )
    readiness = calculator._report_readiness(
        summary,
        calculator._stability_map(set(), summary["divisionalConfidence"]),
        [],
        "approximate",
        place,
    )
    state = ChartRectificationService().initial_state(
        {
            "time": {"window": summary},
            "place": {"accuracy": "coordinate", "radiusKm": 0.25},
            "constraints": {"placeRectificationAllowed": False},
        },
        {"summary": summary, "reportReadiness": readiness, "candidateGroups": []},
    )

    assert summary["riskLevel"] == "high"
    assert summary["scanErrors"][0]["error"] == "Ambiguous local birth time"
    assert "scan_incomplete:resolve_civil_time_or_place_input" in readiness["blockingFactors"]
    assert state["status"] == "input_resolution_required"
    assert state["reportGate"]["fullReportAllowed"] is False
    assert state["rectificationPlan"]["action"] == "resolve_civil_time_or_place_input"


def test_chart_signature_tracks_all_standard_divisional_lagnas() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    signature = calculator._chart_signature(_base_chart())

    for factor in [2, 3, 4, 5, 7, 9, 10, 12, 16, 20, 24, 27, 30, 60]:
        assert signature[f"d{factor}Lagna"]
    assert signature["d7Lagna"] == "Virgo"
    assert signature["d60Lagna"] == "Leo"


def test_incomplete_candidate_scoring_blocks_rectification_questions() -> None:
    service = ChartRectificationService()
    state = service.initial_state(
        {
            "time": {"window": {"start": "1990-01-01 08:15", "end": "1990-01-01 08:45"}},
            "place": {"accuracy": "city", "radiusKm": 25},
            "lifeEvents": _rectification_ledger(),
        },
        {
            "summary": {
                "riskLevel": "high",
                "changedFields": ["d9Lagna"],
                "candidateScoringErrors": [{"candidateId": "B", "error": "provider unavailable"}],
            },
            "reportReadiness": {
                "mode": "rectification_required",
                "blockingFactors": ["candidate_scoring_incomplete:retry_deterministic_calculation"],
            },
            "candidateGroups": [
                {"candidateId": "A", "isBase": True, "aggregateScore": 0.2},
                {
                    "candidateId": "B",
                    "isBase": False,
                    "aggregateScore": None,
                    "scoringError": "provider unavailable",
                },
            ],
        },
    )

    assert state["status"] == "calculation_failed"
    assert state["reportGate"]["nextStep"] == "retry_deterministic_calculation"
    assert state["rectificationPlan"]["action"] == "retry_deterministic_calculation"


def test_place_scan_does_not_silently_inherit_timezone_when_lookup_fails() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())

    with pytest.raises(RuntimeError, match="timezone lookup failed"):
        calculator._timezone_for_scan_point(91.0, 181.0, "Asia/Shanghai")


def test_full_and_fast_signatures_share_the_same_varga_structure_shape() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    chart = _base_chart()
    for raw_chart in chart["divisional_charts"].values():
        raw_chart["Sun"] = {"sign": "Aries", "sign_idx": 0, "degree": 5.0}
    base_signature = calculator._chart_signature(chart)
    fast_signature = json.loads(json.dumps(base_signature))

    assert base_signature["vargaPlanetSignIndices"]["D9"] == {"Sun": 0}
    groups = calculator._candidate_groups(
        base_signature,
        [
            {"label": "base", "datetime": "1990-01-01 08:30", "signature": base_signature},
            {"label": "+1m", "datetime": "1990-01-01 08:31", "signature": fast_signature},
        ],
        [],
    )
    assert len(groups) == 1


def test_candidate_groups_use_rectification_vargas_but_not_d60_noise() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    base_signature = calculator._chart_signature(_base_chart())

    d7_variant = {**base_signature, "d7Lagna": "Sagittarius"}
    d60_variant = {**base_signature, "d60Lagna": "Scorpio"}

    d7_groups = calculator._candidate_groups(
        base_signature,
        [
            {"label": "base", "datetime": "1990-01-01 08:30", "signature": base_signature},
            {"label": "+1m", "datetime": "1990-01-01 08:31", "signature": d7_variant},
        ],
        [],
    )
    d60_groups = calculator._candidate_groups(
        base_signature,
        [
            {"label": "base", "datetime": "1990-01-01 08:30", "signature": base_signature},
            {"label": "+1m", "datetime": "1990-01-01 08:31", "signature": d60_variant},
        ],
        [],
    )

    assert len(d7_groups) == 2
    assert d7_groups[1]["changedFromBase"] == ["d7Lagna"]
    assert len(d60_groups) == 1


def test_candidate_fingerprint_tracks_varga_planet_structure() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    base_signature = {
        **calculator._chart_signature(_base_chart()),
        "vargaPlanetSignIndices": {"D10": {"Saturn": 2, "Sun": 5}},
    }
    changed_signature = {
        **base_signature,
        "vargaPlanetSignIndices": {"D10": {"Saturn": 3, "Sun": 5}},
    }

    assert calculator._signature_fingerprint(base_signature) != calculator._signature_fingerprint(
        changed_signature
    )
    assert calculator._signature_changes(base_signature, changed_signature) == ["d10Structure"]


def test_candidate_fingerprint_and_stability_track_d1_planet_structure() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    base_signature = {
        "lagnaSign": "Aries",
        "moonSign": "Aries",
        "moonNakshatra": "Ashwini",
        "moonPada": 1,
        "currentDasha": "Ketu-Venus",
        "planetSignIndices": {"Sun": 9, "Moon": 0},
        "vargaPlanetSignIndices": {},
    }
    changed_signature = {
        **base_signature,
        "planetSignIndices": {
            **base_signature["planetSignIndices"],
            "Moon": (base_signature["planetSignIndices"]["Moon"] + 1) % 12,
        },
        "moonSign": "Taurus",
    }

    assert calculator._signature_fingerprint(base_signature) != calculator._signature_fingerprint(
        changed_signature
    )
    changes = calculator._signature_changes(base_signature, changed_signature)
    assert changes == ["moonSign", "d1Structure"]

    stability = calculator._stability_map(set(changes), {})
    restricted = set(stability["llmRestrictedEvidence"])
    assert {"moonSign", "d1Structure"} <= restricted


def test_candidate_fingerprint_and_stability_track_chara_karaka_roles() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    base_signature = {
        "lagnaSign": "Aries",
        "moonSign": "Aries",
        "moonNakshatra": "Ashwini",
        "moonPada": 1,
        "currentDasha": "Ketu-Venus",
        "charaKaraka7k": {"AK": "Sun", "AmK": "Moon"},
        "planetSignIndices": {"Sun": 9, "Moon": 0},
        "vargaPlanetSignIndices": {},
    }
    changed_signature = {
        **base_signature,
        "charaKaraka7k": {"AK": "Moon", "AmK": "Sun"},
    }

    assert calculator._signature_fingerprint(base_signature) != calculator._signature_fingerprint(
        changed_signature
    )
    assert calculator._signature_changes(base_signature, changed_signature) == ["charaKaraka7k"]


def test_candidate_fingerprint_tracks_interpretive_state_boundaries() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    base_signature = {
        "lagnaSign": "Aries",
        "moonSign": "Aries",
        "moonNakshatra": "Ashwini",
        "moonPada": 1,
        "currentDasha": "Ketu-Venus",
        "moonPhase": True,
        "combustionStatus": {"Venus": False},
        "shadbalaClassification": {"Venus": "medium"},
        "digbalaStatus": {"Venus": False},
        "specialPointSigns": {"AL": 0},
        "specialLagnaSigns": {"hora_lagna": 0},
        "planetSignIndices": {"Sun": 9, "Moon": 0, "Venus": 6},
        "vargaPlanetSignIndices": {},
    }
    changed_signature = {
        **base_signature,
        "shadbalaClassification": {"Venus": "strong"},
    }

    assert calculator._signature_fingerprint(base_signature) != calculator._signature_fingerprint(
        changed_signature
    )
    assert calculator._signature_changes(base_signature, changed_signature) == [
        "shadbalaClassification"
    ]
    stability = calculator._stability_map({"shadbalaClassification"}, {})
    assert "shadbalaClassification" in stability["llmRestrictedEvidence"]

    stability = calculator._stability_map({"charaKaraka7k"}, {})
    assert "charaKaraka7k" in stability["llmRestrictedEvidence"]


def test_stability_contract_exposes_varga_structure_changes() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())

    stability = calculator._stability_map({"d9Structure"}, {})

    assert "d9Structure" in stability["llmRestrictedEvidence"]


def test_time_points_preserve_the_unsampled_transition_minute_as_overlap() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    base_signature = calculator._chart_signature(_base_chart())
    changed_signature = {**base_signature, "d9Lagna": "Scorpio"}

    variants = calculator._coalesce_time_points(
        [
            {"moment": datetime(1990, 1, 1, 8, 29), "signature": base_signature},
            {"moment": datetime(1990, 1, 1, 8, 30), "signature": base_signature},
            {"moment": datetime(1990, 1, 1, 8, 31), "signature": changed_signature},
        ],
        datetime(1990, 1, 1, 8, 30),
        base_signature,
    )

    assert [variant["interval"] for variant in variants] == [
        {"start": "1990-01-01 08:29", "end": "1990-01-01 08:31"},
        {"start": "1990-01-01 08:30", "end": "1990-01-01 08:32"},
    ]
    assert variants[0]["representativeDatetime"] == "1990-01-01 08:30"
    assert variants[0]["isBase"] is True
    assert variants[1]["isBase"] is False
    assert variants[1]["boundaryResolutionSeconds"] == 60
    assert variants[1]["leftBoundaryUncertainty"] == {
        "start": "1990-01-01 08:30",
        "end": "1990-01-01 08:31",
    }

    boundaries = _sensitivity_boundaries(
        SimpleNamespace(
            sensitivity_scan={"timeVariants": variants},
            timezone_id="Asia/Shanghai",
        )
    )
    assert len(boundaries) == 1
    assert boundaries[0].changed_fields == ["d9Lagna"]
    assert boundaries[0].resolution_seconds == 60
    assert boundaries[0].uncertainty_interval is not None
    assert boundaries[0].uncertainty_interval.start.isoformat() == "1990-01-01T08:30:00+08:00"
    assert boundaries[0].uncertainty_interval.end.isoformat() == "1990-01-01T08:31:00+08:00"


def test_time_intervals_split_when_event_relevant_advanced_varga_changes() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    base_signature = calculator._chart_signature(_base_chart())
    changed_signature = {**base_signature, "d24Lagna": "Scorpio"}

    variants = calculator._coalesce_time_points(
        [
            {"moment": datetime(1990, 1, 1, 8, 29), "signature": base_signature},
            {"moment": datetime(1990, 1, 1, 8, 30), "signature": changed_signature},
        ],
        datetime(1990, 1, 1, 8, 29),
        base_signature,
    )

    assert len(variants) == 2
    assert variants[1]["changed"] == ["d24Lagna"]


def test_d60_internal_change_is_reported_without_splitting_candidates() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    base_signature = calculator._chart_signature(_base_chart())
    d60_variant = {**base_signature, "d60Lagna": "Scorpio"}

    variants = calculator._coalesce_time_points(
        [
            {"moment": datetime(1990, 1, 1, 8, 29), "signature": base_signature},
            {"moment": datetime(1990, 1, 1, 8, 30), "signature": d60_variant},
        ],
        datetime(1990, 1, 1, 8, 29),
        base_signature,
    )

    assert len(variants) == 1
    assert variants[0]["internalChangedFields"] == ["d60Lagna"]
    assert variants[0]["changed"] == ["d60Lagna"]

    place = ResolvedPlace(
        label="manual",
        lat=31.2304,
        lon=121.4737,
        timezone="Asia/Shanghai",
        source="manual",
        accuracy="coordinate",
        radius_km=0.25,
        confidence="high",
    )
    summary = calculator._scan_summary("exact", place, variants, [], [])

    assert "d60Lagna" in summary["changedFields"]
    assert summary["divisionalConfidence"]["D60"]["confidence"] == "low"
    assert summary["divisionalConfidence"]["D60"]["recommendedUse"] == "rectification_only_or_omit"


def test_selected_candidate_transition_is_refined_without_claiming_an_exact_second() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    before_signature = calculator._chart_signature(_base_chart())
    after_signature = {**before_signature, "d9Lagna": "Scorpio"}
    observed_factors: list[list[int]] = []

    def signature(
        _year,
        _month,
        _day,
        _hour,
        minute,
        _lat,
        _lon,
        _timezone,
        *,
        second=0,
        chart_factors,
        **_kwargs,
    ):
        observed_factors.append(chart_factors)
        changed = minute > 30 or (minute == 30 and second >= 37)
        return dict(after_signature if changed else before_signature)

    state = {
        "selectedCandidateId": "B",
        "candidates": [
            {
                "candidateId": "A",
                "signature": before_signature,
                "interval": {
                    "start": "1990-01-01 08:28",
                    "end": "1990-01-01 08:31",
                },
                "members": [],
            },
            {
                "candidateId": "B",
                "signature": after_signature,
                "interval": {
                    "start": "1990-01-01 08:30",
                    "end": "1990-01-01 08:33",
                },
                "representativeDatetime": "1990-01-01 08:32",
                "boundaryResolutionSeconds": 60,
                "leftBoundaryUncertainty": {
                    "start": "1990-01-01 08:30",
                    "end": "1990-01-01 08:31",
                },
                "members": [
                    {
                        "axis": "time",
                        "datetime": "1990-01-01 08:32",
                        "interval": {
                            "start": "1990-01-01 08:30",
                            "end": "1990-01-01 08:33",
                        },
                    }
                ],
            },
        ],
    }
    birth_context = {
        "place": {
            "coordinates": {"lat": 31.2304, "lon": 121.4737},
            "timezone": "Asia/Shanghai",
        }
    }

    refined = calculator.refine_selected_time_boundary(
        state,
        birth_context,
        calculate_signature=signature,
    )

    selected = refined["candidates"][1]
    uncertainty = selected["leftBoundaryUncertainty"]
    lower = datetime.fromisoformat(uncertainty["startUtc"])
    upper = datetime.fromisoformat(uncertainty["endUtc"])
    transition = datetime(1990, 1, 1, 0, 30, 37, tzinfo=timezone.utc)
    assert refined["boundaryRefinement"]["status"] == "refined"
    assert refined["boundaryRefinement"]["d60Used"] is False
    assert selected["boundaryResolutionSeconds"] <= 5
    assert lower < transition <= upper
    assert (upper - lower).total_seconds() <= 5
    assert selected["interval"]["start"] == uncertainty["start"]
    assert refined["candidates"][0]["interval"]["end"] == uncertainty["end"]
    assert observed_factors
    assert all(60 not in factors for factors in observed_factors)


def test_dasha_only_transition_is_not_given_false_sub_minute_precision() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    before_signature = calculator._chart_signature(_base_chart())
    after_signature = {**before_signature, "currentDasha": "Saturn-Sun"}

    state = {
        "selectedCandidateId": "B",
        "candidates": [
            {
                "candidateId": "B",
                "signature": after_signature,
                "interval": {
                    "start": "1990-01-01 08:30",
                    "end": "1990-01-01 08:33",
                },
                "boundaryResolutionSeconds": 60,
                "leftBoundaryUncertainty": {
                    "start": "1990-01-01 08:30",
                    "end": "1990-01-01 08:31",
                },
                "members": [],
            }
        ],
    }

    refined = calculator.refine_selected_time_boundary(
        state,
        {
            "place": {
                "coordinates": {"lat": 31.2304, "lon": 121.4737},
                "timezone": "Asia/Shanghai",
            }
        },
        calculate_signature=lambda *_args, **_kwargs: dict(before_signature),
    )

    assert refined["boundaryRefinement"]["status"] == "not_applicable"
    assert refined["candidates"][0]["boundaryResolutionSeconds"] == 60


def test_selected_first_interval_refines_its_right_transition_band() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    before_signature = calculator._chart_signature(_base_chart())
    after_signature = {**before_signature, "d9Lagna": "Scorpio"}

    def signature(
        _year,
        _month,
        _day,
        _hour,
        minute,
        _lat,
        _lon,
        _timezone,
        *,
        second=0,
        **_kwargs,
    ):
        changed = minute > 30 or (minute == 30 and second >= 37)
        return dict(after_signature if changed else before_signature)

    refined = calculator.refine_selected_time_boundary(
        {
            "selectedCandidateId": "A",
            "candidates": [
                {
                    "candidateId": "A",
                    "signature": before_signature,
                    "interval": {
                        "start": "1990-01-01 08:28",
                        "end": "1990-01-01 08:31",
                    },
                    "members": [],
                },
                {
                    "candidateId": "B",
                    "signature": after_signature,
                    "interval": {
                        "start": "1990-01-01 08:30",
                        "end": "1990-01-01 08:33",
                    },
                    "boundaryResolutionSeconds": 60,
                    "leftBoundaryUncertainty": {
                        "start": "1990-01-01 08:30",
                        "end": "1990-01-01 08:31",
                    },
                    "members": [],
                },
            ],
        },
        {
            "place": {
                "coordinates": {"lat": 31.2304, "lon": 121.4737},
                "timezone": "Asia/Shanghai",
            }
        },
        calculate_signature=signature,
    )

    assert refined["selectedCandidateId"] == "A"
    assert refined["boundaryRefinement"]["status"] == "refined"
    assert [item["side"] for item in refined["boundaryRefinement"]["boundaries"]] == [
        "left",
        "right",
    ]
    assert (
        refined["candidates"][0]["interval"]["end"]
        == refined["candidates"][1]["leftBoundaryUncertainty"]["end"]
    )


def test_refined_state_boundaries_sync_to_typed_chart_record() -> None:
    original_start = datetime(1990, 1, 1, 0, 30, tzinfo=timezone.utc)
    original_end = datetime(1990, 1, 1, 0, 31, tzinfo=timezone.utc)
    candidate = CandidateInterval(
        candidateId="B",
        interval={
            "start": original_start,
            "end": datetime(1990, 1, 1, 0, 33, tzinfo=timezone.utc),
        },
        representativeMoment=datetime(1990, 1, 1, 0, 32, tzinfo=timezone.utc),
        fingerprint="fingerprint",
        boundaryResolutionSeconds=60,
        leftBoundaryUncertainty={"start": original_start, "end": original_end},
    )
    boundary = SensitivityBoundary(
        boundaryId="boundary.time.001",
        axis="time",
        at=original_end,
        uncertaintyInterval={"start": original_start, "end": original_end},
        resolutionSeconds=60,
        changedFields=["d9Lagna"],
        beforeFingerprint="before",
        afterFingerprint="after",
    )
    record = cast(
        Any,
        SimpleNamespace(
            canonical_moment=SimpleNamespace(timezone_id="Asia/Shanghai"),
            rectification=SimpleNamespace(candidates=[candidate]),
            sensitivity_boundaries=[boundary],
        ),
    )
    refined_start = datetime(1990, 1, 1, 0, 30, 34, tzinfo=timezone.utc)
    refined_end = datetime(1990, 1, 1, 0, 30, 38, tzinfo=timezone.utc)

    SkillRuntime._sync_candidate_time_bounds(
        record,
        {
            "candidates": [
                {
                    "candidateId": "B",
                    "signature": {},
                    "interval": {
                        "startUtc": refined_start.isoformat(),
                        "endUtc": datetime(1990, 1, 1, 0, 33, tzinfo=timezone.utc).isoformat(),
                    },
                    "boundaryResolutionSeconds": 4,
                    "leftBoundaryUncertainty": {
                        "startUtc": refined_start.isoformat(),
                        "endUtc": refined_end.isoformat(),
                    },
                    "members": [],
                }
            ]
        },
    )

    synced_candidate = record.rectification.candidates[0]
    synced_boundary = record.sensitivity_boundaries[0]
    assert synced_candidate.boundary_resolution_seconds == 4
    assert synced_candidate.left_boundary_uncertainty == TimeRange(
        start=refined_start,
        end=refined_end,
    )
    assert synced_boundary.resolution_seconds == 4
    assert synced_boundary.uncertainty_interval == TimeRange(
        start=refined_start,
        end=refined_end,
    )


def test_life_event_ledger_reserves_latest_event_as_holdout() -> None:
    ledger = parse_life_event_ledger("2012年9月 入学\n2018年10月 结婚\n2023年6月 跳槽")

    assert [event["role"] for event in ledger["events"]] == [
        "calibration",
        "calibration",
        "holdout",
    ]
    assert ledger["events"][-1]["category"] == "career"


def test_life_event_ledger_requires_three_events_for_independent_holdout() -> None:
    incomplete = parse_life_event_ledger("2018年10月 结婚\n2023年 跳槽")
    complete = parse_life_event_ledger("2018年10月 结婚\n2021年 搬家\n2023年 跳槽")

    assert incomplete["eventCollectionRequired"] is True
    assert complete["eventCollectionRequired"] is False


def test_structured_life_event_category_wins_over_description_keywords() -> None:
    input_data = RectificationLifeEventsInput.model_validate(
        {
            "sessionId": "session",
            "events": [
                {
                    "date": "2018-10",
                    "category": "health",
                    "description": "工作途中发生车祸并住院",
                },
                {
                    "date": "2020-06",
                    "category": "relocation",
                    "description": "因工作搬到上海",
                },
                {
                    "date": "2023-05",
                    "category": "relationship",
                    "description": "职业变化期间结束长期关系",
                },
            ],
        }
    )

    ledger = parse_life_event_ledger(input_data.ledger_text())

    assert [event["category"] for event in ledger["events"]] == [
        "health",
        "relocation",
        "relationship",
    ]


def test_structured_life_event_input_rejects_duplicate_evidence() -> None:
    duplicate = {
        "date": "2018-10",
        "category": "career",
        "description": "Started my first full-time job",
    }

    with pytest.raises(ValueError, match="must be distinct"):
        RectificationLifeEventsInput.model_validate(
            {
                "sessionId": "session",
                "events": [duplicate, duplicate, duplicate],
            }
        )


def test_holdout_failure_blocks_selected_candidate() -> None:
    service = ChartRectificationService()
    candidates = [
        {"candidateId": "A", "holdoutScore": 0.25},
        {"candidateId": "B", "holdoutScore": 0.7},
    ]

    assert service._holdout_result(candidates[0], candidates) == "failed"
    assert service._holdout_result(candidates[1], candidates) == "passed"

    tied = [
        {"candidateId": "A", "holdoutScore": 0.7},
        {"candidateId": "B", "holdoutScore": 0.68},
    ]
    weak = [{"candidateId": "A", "holdoutScore": 0.04}]
    assert service._holdout_result(tied[0], tied) == "inconclusive"
    assert service._holdout_result(weak[0], weak) == "inconclusive"


def test_report_readiness_restricts_advanced_vargas_without_blocking_d1() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    place = ResolvedPlace(
        label="manual",
        lat=31.2304,
        lon=121.4737,
        timezone="Asia/Shanghai",
        source="manual",
        accuracy="coordinate",
        radius_km=0.25,
        confidence="high",
    )
    summary = calculator._scan_summary(
        "exact",
        place,
        time_variants=[{"changed": []}],
        place_variants=[],
        boundary_flags=[],
    )
    stability = calculator._stability_map(
        set(summary["changedFields"]),
        summary["divisionalConfidence"],
    )
    readiness = calculator._report_readiness(summary, stability, [], "exact", place)

    restricted = set(readiness["llmContract"]["mustNotUseAsPrimaryEvidence"])
    allowed = set(readiness["llmContract"]["mayUseAsPrimaryEvidence"])
    assert readiness["mode"] == "standard_after_prevalidation"
    assert "lagnaSign" in allowed
    assert "d60Lagna" in restricted
    assert "D60" not in allowed


def test_birth_input_context_locks_precise_place_rectification() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    place = ResolvedPlace(
        label="上海市第一妇婴保健院东院",
        lat=31.19174,
        lon=121.54581,
        timezone="Asia/Shanghai",
        source="agent",
        accuracy="poi",
        radius_km=0.3,
        confidence="high",
    )

    context = calculator._birth_input_context(
        _birth_payload(),
        _birth_input("上海市第一妇婴保健院东院"),
        place,
    )

    assert context["place"]["rectificationAllowed"] is False
    assert context["place"]["rectificationPolicy"] == "locked_precise_coordinates"
    assert context["constraints"]["placeRectificationAllowed"] is False
    assert context["constraints"]["rectificationAxes"] == ["time"]


def test_birth_input_context_allows_city_place_rectification() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    place = ResolvedPlace(
        label="Shanghai, Shanghai, China",
        lat=31.2304,
        lon=121.4737,
        timezone="Asia/Shanghai",
        source="geonames-local",
        accuracy="city",
        radius_km=25.0,
        confidence="medium",
    )

    context = calculator._birth_input_context(
        _birth_payload(),
        _birth_input(),
        place,
    )

    assert context["place"]["rectificationAllowed"] is True
    assert context["place"]["rectificationPolicy"] == "scan_within_reported_radius"
    assert context["constraints"]["placeRectificationAllowed"] is True
    assert context["constraints"]["rectificationAxes"] == ["time", "place"]


def test_sensitivity_scan_excludes_place_candidates_for_precise_place() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    chart = _base_chart()
    place = ResolvedPlace(
        label="上海市第一妇婴保健院东院",
        lat=31.19174,
        lon=121.54581,
        timezone="Asia/Shanghai",
        source="agent",
        accuracy="poi",
        radius_km=0.3,
        confidence="high",
    )

    scan = calculator._sensitivity_scan(
        lambda *_args, **_kwargs: chart,
        chart,
        _birth_payload(),
        _birth_input("上海市第一妇婴保健院东院"),
        place,
    )

    member_axes = [
        member["axis"]
        for candidate in scan["candidateGroups"]
        for member in candidate.get("members", [])
    ]
    assert scan["summary"]["rectificationAxes"] == ["time"]
    assert scan["summary"]["placeRectificationAllowed"] is False
    assert scan["reportReadiness"]["llmContract"]["rectificationAxes"] == ["time"]
    assert scan["placeVariants"][0]["rectificationAllowed"] is False
    assert "Detailed place coordinates are locked" in scan["rectificationGuardrails"]["place"]
    assert "place" not in member_axes


def test_sensitivity_scan_keeps_place_candidates_for_city_place() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    chart = _base_chart()
    place = ResolvedPlace(
        label="Shanghai, Shanghai, China",
        lat=31.2304,
        lon=121.4737,
        timezone="Asia/Shanghai",
        source="geonames-local",
        accuracy="city",
        radius_km=25.0,
        confidence="medium",
    )

    scan = calculator._sensitivity_scan(
        lambda *_args, **_kwargs: chart,
        chart,
        _birth_payload(),
        _birth_input(),
        place,
    )

    member_axes = [
        member["axis"]
        for candidate in scan["candidateGroups"]
        for member in candidate.get("members", [])
    ]
    assert scan["summary"]["rectificationAxes"] == ["time", "place"]
    assert scan["summary"]["placeRectificationAllowed"] is True
    assert scan["reportReadiness"]["placeRectificationAllowed"] is True
    assert scan["summary"]["riskLevel"] == "high"
    assert scan["reportReadiness"]["mode"] == "guarded_after_strong_prevalidation"
    assert scan["reportReadiness"]["coreAllowedWithoutRectification"] is True
    assert scan["reportReadiness"]["stableBoundedWindow"] is True
    assert scan["reportReadiness"]["scope"] == "guarded_full_report"
    assert "City/district coordinates are approximate" in scan["rectificationGuardrails"]["place"]
    assert "place" in member_axes


def test_place_scan_uses_eight_spherical_boundary_samples() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    chart = _base_chart()
    place = ResolvedPlace(
        label="Shanghai, Shanghai, China",
        lat=31.2304,
        lon=121.4737,
        timezone="Asia/Shanghai",
        source="geonames-local",
        accuracy="city",
        radius_km=25.0,
        confidence="medium",
    )

    variants = calculator._place_scan_variants(
        lambda *_args: chart,
        chart,
        calculator._chart_signature(chart),
        _birth_payload(),
        place,
    )

    labels = {variant["label"] for variant in variants}
    assert len(variants) == 9
    assert {"north-east", "south-east", "south-west", "north-west"} <= labels


def test_place_scan_does_not_clip_the_declared_city_uncertainty_radius() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    chart = _base_chart()
    place = ResolvedPlace(
        label="wide municipality",
        lat=33.63611,
        lon=116.97889,
        timezone="Asia/Shanghai",
        source="geonames-local",
        accuracy="city",
        radius_km=85.0,
        confidence="medium",
    )

    variants = calculator._place_scan_variants(
        lambda *_args: chart,
        chart,
        calculator._chart_signature(chart),
        {**_birth_payload(), "lat": place.lat, "lon": place.lon},
        place,
    )

    assert {variant["radiusKm"] for variant in variants[1:]} == {85.0}


def test_city_sensitivity_scans_joint_time_and_place_hypotheses() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    chart = _base_chart()
    base_signature = calculator._chart_signature(chart)
    place = ResolvedPlace(
        label="Shanghai, Shanghai, China",
        lat=31.2304,
        lon=121.4737,
        timezone="Asia/Shanghai",
        source="geonames-local",
        accuracy="city",
        radius_km=25.0,
        confidence="medium",
    )
    observed_coordinates: list[tuple[float, float]] = []

    def calculate_signature(
        _year,
        _month,
        _day,
        _hour,
        minute,
        latitude,
        longitude,
        _timezone,
        *,
        second=0,
        **_kwargs,
    ):
        observed_coordinates.append((latitude, longitude))
        signature = {
            **base_signature,
            "vargaPlanetSignIndices": {},
        }
        if latitude > place.lat and minute >= 30:
            signature["d9Lagna"] = "Scorpio"
        return signature

    scan = calculator._sensitivity_scan(
        lambda *_args, **_kwargs: chart,
        chart,
        _birth_payload(),
        _birth_input(),
        place,
        calculate_signature=calculate_signature,
    )

    joint_candidates = [
        candidate
        for candidate in scan["candidateGroups"]
        if {member.get("axis") for member in candidate.get("members", [])} == {"time", "place"}
    ]
    assert scan["jointTimePlaceVariants"]
    assert joint_candidates
    assert all(candidate.get("interval") for candidate in joint_candidates)
    assert all(candidate.get("representativeDatetime") for candidate in joint_candidates)
    assert any("d9Lagna" in candidate["changedFromBase"] for candidate in joint_candidates)
    assert any(latitude != place.lat for latitude, _ in observed_coordinates)


class FakeWorkspace:
    def __init__(self, root):
        self.root = root

    def require_session_dir(self, session_id: str):
        path = self.root / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path


def runtime_with_workspace(root) -> SkillRuntime:
    runtime = cast(Any, SkillRuntime.__new__(SkillRuntime))
    runtime.workspace = FakeWorkspace(root)
    return cast(SkillRuntime, runtime)


def test_runtime_preserves_reported_input_when_materializing_rectified_context(tmp_path) -> None:
    runtime = runtime_with_workspace(tmp_path)
    original = {
        "schemaVersion": "birth-input-context/v1",
        "time": {
            "reported": "08:30",
            "date": "1990-01-01",
            "precision": "part_of_day",
            "source": "family memory",
            "normalized": "08:30:00",
            "timezone": "Asia/Shanghai",
            "window": {
                "start": "1990-01-01 06:00:00",
                "end": "1990-01-01 12:00:00",
            },
        },
        "place": {
            "reported": "Shanghai",
            "resolvedLabel": "Shanghai, China",
            "coordinates": {"lat": 31.22222, "lon": 121.45806},
            "timezone": "Asia/Shanghai",
            "accuracy": "city",
        },
        "readingFocus": "Career direction",
        "lifeEvents": {"events": [{"eventId": "event-1"}]},
        "constraints": {"timeSearchMustStayWithinReportedWindow": True},
    }
    recalculated = {
        "schemaVersion": "birth-input-context/v1",
        "time": {
            "reported": "09:42:15",
            "date": "1990-01-01",
            "precision": "exact",
            "source": "rectified-from-event-evidence",
            "normalized": "09:42:15",
            "timezone": "Asia/Shanghai",
            "window": {
                "start": "1990-01-01 09:42:15",
                "end": "1990-01-01 09:42:15",
            },
        },
        "place": {
            "reported": "Shanghai First Maternity Hospital East Campus",
            "resolvedLabel": "Shanghai First Maternity Hospital East Campus",
            "coordinates": {"lat": 31.19174, "lon": 121.54581},
            "timezone": "Asia/Shanghai",
            "accuracy": "poi",
        },
    }
    rectified = BirthInput(
        birthDate="1990-01-01",
        birthTime="09:42:15",
        birthPlace="Shanghai First Maternity Hospital East Campus",
        birthTimePrecision="exact",
        timeSource="rectified-from-event-evidence",
        readingFocus="Career direction",
        lifeEvents="",
    )

    result = json.loads(
        runtime._preserve_reported_input_context(
            json.dumps(original),
            json.dumps(recalculated),
            rectified,
            {
                "selectedCandidateId": "candidate-b",
                "candidates": [
                    {
                        "candidateId": "candidate-b",
                        "interval": {
                            "start": "1990-01-01 09:41:40",
                            "end": "1990-01-01 09:43:05",
                        },
                    }
                ],
            },
        )
    )

    assert result["reportedInput"] == {
        "time": original["time"],
        "place": original["place"],
    }
    assert result["time"]["reported"] == "08:30"
    assert result["time"]["precision"] == "part_of_day"
    assert result["time"]["source"] == "family memory"
    assert result["time"]["window"] == original["time"]["window"]
    assert result["time"]["normalized"] == "09:42:15"
    assert result["time"]["rectifiedNormalized"] == "09:42:15"
    assert result["time"]["rectificationApplied"] is True
    assert result["place"]["reported"] == "Shanghai"
    assert result["place"]["coordinates"] == {"lat": 31.19174, "lon": 121.54581}
    assert result["activeCanonicalInput"] == {
        "localDate": "1990-01-01",
        "localTime": "09:42:15",
        "place": {
            "resolvedLabel": "Shanghai First Maternity Hospital East Campus",
            "coordinates": {"lat": 31.19174, "lon": 121.54581},
            "timezone": "Asia/Shanghai",
        },
        "source": "deterministic_event_selection",
        "precision": "bounded_interval",
        "candidateId": "candidate-b",
        "selectedInterval": {
            "start": "1990-01-01 09:41:40",
            "end": "1990-01-01 09:43:05",
        },
    }
    assert result["readingFocus"] == original["readingFocus"]
    assert result["lifeEvents"] == original["lifeEvents"]
    assert result["constraints"] == original["constraints"]


def test_rectification_rejects_selected_candidate_without_materializable_input() -> None:
    service = ChartRectificationService()
    state = {
        "revision": 3,
        "status": "needs_recalculation",
        "selectedCandidateId": "candidate-b",
        "selectionConfidence": "medium",
        "candidates": [{"candidateId": "candidate-b", "members": []}],
        "searchBounds": {"time": {}, "place": {}},
    }

    updated = service.reject_unmaterializable_selection(state)

    assert updated["revision"] == 4
    assert updated["status"] == "underdetermined"
    assert updated["selectedCandidateId"] is None
    assert updated["selectionConfidence"] == "none"
    assert updated["reportGate"]["fullReportAllowed"] is False
    assert updated["reportGate"]["nextStep"] == "provide_more_precise_or_additional_event_evidence"
    assert updated["rectificationPlan"]["action"] == "rectification_inconclusive"


def test_chart_rectification_sync_preserves_original_time_certainty(tmp_path: Path) -> None:
    class FixedPlaceService:
        @staticmethod
        def resolve(_: str) -> ResolvedPlace:
            return ResolvedPlace(
                label="Shanghai, China",
                lat=31.22222,
                lon=121.45806,
                timezone="Asia/Shanghai",
                source="test-fixture",
                accuracy="city",
                radius_km=20.0,
                confidence="high",
            )

    settings = SimpleNamespace(project_root=tmp_path)
    workspace = SkillWorkspace(settings)  # type: ignore[arg-type]
    calculator = VedicCalculator(settings, FixedPlaceService())  # type: ignore[arg-type]
    runtime = SkillRuntime(
        calculator=calculator,
        workspace=workspace,
        agent_runtime=None,  # type: ignore[arg-type]
    )
    session_id = "preserve-time-certainty"
    workspace.create_session(session_id)
    calculation = calculator.calculate(
        BirthInput(
            birthDate="1990-01-01",
            birthTime="08:30",
            birthPlace="Shanghai, China",
            birthTimePrecision="approximate",
            timeSource="family memory",
            lifeEvents="",
        )
    )
    record = ChartRecord.model_validate_json(calculation.chart_record_json)
    assert record.canonical_moment is not None
    assert record.birth_assertion.time_certainty == "approximate"
    assert record.input_sensitivity is not None
    assert record.input_sensitivity.timing_boundary_scan_status == "complete"
    assert record.input_sensitivity.timing_boundary_sample_count == 3
    assert record.timing_periods
    assert {period.start_boundary.coverage for period in record.timing_periods} == {
        "reported_window_endpoints"
    }
    assert {period.end_boundary.coverage for period in record.timing_periods} == {
        "reported_window_endpoints"
    }
    representative = record.canonical_moment.utc_datetime
    interval = TimeRange(
        start=representative - timedelta(seconds=30),
        end=representative + timedelta(seconds=30),
    )
    record.rectification = RectificationRecord(
        reportedWindow=record.birth_assertion.reported_time_window,
        candidates=[
            CandidateInterval(
                candidateId="candidate-base",
                interval=interval,
                representativeMoment=representative,
                fingerprint="test-fingerprint",
            )
        ],
        decision=RectificationDecision(
            status="comparing_candidates",
            confidence="provisional",
        ),
    )
    record.status = "rectification_required"
    workspace.write_artifact(
        session_id,
        "chart_record.json",
        record.model_dump_json(by_alias=True, indent=2) + "\n",
    )

    runtime._sync_chart_record_rectification(
        session_id,
        {
            "status": "corrected_chart_ready",
            "selectedCandidateId": "candidate-base",
            "selectionConfidence": "medium",
            "holdoutResult": "passed",
            "reportGate": {"fullReportAllowed": True, "reason": "test selection"},
            "candidates": [{"candidateId": "candidate-base"}],
        },
    )

    updated = ChartRecord.model_validate_json(
        workspace.read_artifact_text(session_id, "chart_record.json") or "{}"
    )
    assert updated.status == "rectified"
    assert updated.birth_assertion.time_certainty == "approximate"
    assert updated.birth_assertion.reported_local_time == "08:30"
    assert updated.rectification is not None
    assert updated.rectification.decision.status == "bounded_interval"
    assert updated.rectification.decision.holdout_result == "passed"


@pytest.mark.parametrize("is_base", [False, True])
def test_materialized_chart_revision_keeps_original_candidate_scan(
    tmp_path: Path, is_base: bool
) -> None:
    class FixedPlaceService:
        @staticmethod
        def resolve(_: str) -> ResolvedPlace:
            return ResolvedPlace(
                label="Shanghai, China",
                lat=31.22222,
                lon=121.45806,
                timezone="Asia/Shanghai",
                source="test-fixture",
                accuracy="city",
                radius_km=20.0,
                confidence="high",
            )

    settings = SimpleNamespace(project_root=tmp_path)
    workspace = SkillWorkspace(settings)  # type: ignore[arg-type]
    calculator = VedicCalculator(settings, FixedPlaceService())  # type: ignore[arg-type]
    runtime = SkillRuntime(
        calculator=calculator,
        workspace=workspace,
        agent_runtime=None,  # type: ignore[arg-type]
    )
    session_id = "materialize-selected-interval"
    workspace.create_session(session_id)
    initial = calculator.calculate(
        BirthInput(
            birthDate="1990-01-01",
            birthTime="08:30",
            birthPlace="Shanghai, China",
            birthTimePrecision="approximate",
            timeSource="family memory",
            lifeEvents="2012-06 education: Graduated\n2018-03 career: Changed role\n2021-10 relationship: Married",
        )
    )
    previous = ChartRecord.model_validate_json(initial.chart_record_json)
    assert previous.canonical_moment is not None
    representative = previous.canonical_moment.utc_datetime + timedelta(minutes=10)
    selected_interval = TimeRange(
        start=representative - timedelta(minutes=1),
        end=representative + timedelta(minutes=1),
    )
    selected_candidate = CandidateInterval(
        candidateId="candidate-selected",
        interval=selected_interval,
        representativeMoment=representative,
        fingerprint="selected-fingerprint",
    )
    previous_boundary = SensitivityBoundary(
        boundaryId="boundary.time.original",
        axis="time",
        at=selected_interval.start,
        uncertaintyInterval={
            "start": selected_interval.start - timedelta(minutes=1),
            "end": selected_interval.start,
        },
        resolutionSeconds=60,
        changedFields=["d9Lagna"],
        beforeFingerprint="base-fingerprint",
        afterFingerprint="selected-fingerprint",
    )
    previous.rectification = RectificationRecord(
        reportedWindow=previous.birth_assertion.reported_time_window,
        candidates=[selected_candidate],
        decision=RectificationDecision(
            status="comparing_candidates",
            confidence="provisional",
        ),
    )
    previous.sensitivity_boundaries = [previous_boundary]
    previous.status = "rectification_required"
    original_scan = json.dumps({"marker": "original bounded candidate scan"}, indent=2) + "\n"
    artifacts = {
        "birth_input_context.json": initial.birth_input_context_json,
        "sensitivity_scan.json": original_scan,
        "chart_record.json": previous.model_dump_json(by_alias=True, indent=2) + "\n",
    }
    for path, content in artifacts.items():
        workspace.write_artifact(session_id, path, content)

    local_representative = representative.astimezone(
        previous.canonical_moment.local_datetime.tzinfo
    )
    state = {
        "status": "needs_recalculation",
        "selectedCandidateId": "candidate-selected",
        "selectionConfidence": "medium",
        "holdoutResult": "passed",
        "activeChartRevision": {"revision": 1},
        "candidates": [
            {
                "candidateId": "candidate-selected",
                "isBase": is_base,
                "representativeDatetime": local_representative.strftime("%Y-%m-%d %H:%M:%S"),
                "interval": {
                    "start": (local_representative - timedelta(minutes=1)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "end": (local_representative + timedelta(minutes=1)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                },
                "members": [
                    {
                        "axis": "time",
                        "datetime": local_representative.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                ],
            }
        ],
    }

    updated_state = runtime._materialize_rectification_selection(session_id, state, artifacts)

    assert updated_state["status"] == "corrected_chart_ready"
    assert workspace.read_artifact_text(session_id, "sensitivity_scan.json") == original_scan
    active_scan = json.loads(
        workspace.read_artifact_text(session_id, "active_chart_sensitivity.json") or "{}"
    )
    assert active_scan["schemaVersion"] == "vedic-sensitivity-scan/v1"
    timing_samples = {
        role: sample["birthMomentUtc"]
        for sample in active_scan["timingBoundarySampling"]["samples"]
        for role in sample["roles"]
    }
    assert datetime.fromisoformat(timing_samples["window-start"]) == selected_interval.start
    assert datetime.fromisoformat(timing_samples["window-end"]) == (
        selected_interval.end - timedelta(seconds=1)
    )
    revised = ChartRecord.model_validate_json(
        workspace.read_artifact_text(session_id, "chart_record.json") or "{}"
    )
    assert revised.revision == 2
    assert revised.birth_assertion == previous.birth_assertion
    assert revised.sensitivity_boundaries == [previous_boundary]
    assert revised.input_sensitivity is not None
    assert revised.input_sensitivity.timing_boundary_scan_status == "complete"
    assert {period.start_boundary.coverage for period in revised.timing_periods} == {
        "reported_window_endpoints"
    }
    context = json.loads(
        workspace.read_artifact_text(session_id, "birth_input_context.json") or "{}"
    )
    assert context["time"]["precision"] == "approximate"
    assert context["activeCanonicalInput"]["precision"] == "bounded_interval"
    assert context["activeCanonicalInput"]["candidateId"] == "candidate-selected"


def test_runtime_recalculates_chart_after_collecting_dated_events(tmp_path: Path) -> None:
    class FixedPlaceService:
        @staticmethod
        def resolve(_: str) -> ResolvedPlace:
            return ResolvedPlace(
                label="Shanghai First Maternity Hospital East Campus",
                lat=31.19174,
                lon=121.54581,
                timezone="Asia/Shanghai",
                source="test-fixture",
                accuracy="poi",
                radius_km=0.2,
                confidence="high",
            )

    async def run() -> None:
        settings = SimpleNamespace(project_root=tmp_path)
        workspace = SkillWorkspace(settings)  # type: ignore[arg-type]
        runtime = SkillRuntime(
            calculator=VedicCalculator(settings, FixedPlaceService()),  # type: ignore[arg-type]
            workspace=workspace,
            agent_runtime=None,  # type: ignore[arg-type]
        )
        created = await runtime.create_reader_session(
            BirthInput(
                birthDate="1990-01-01",
                birthTime="08:30",
                birthPlace="Shanghai First Maternity Hospital East Campus",
                birthTimePrecision="part_of_day",
                gender="not provided",
                relationship="not provided",
                timeSource="family memory",
                readingFocus="Career direction",
                lifeEvents="",
                readerRelationship="parent",
                locale="en",
            )
        )
        state = json.loads(
            workspace.read_artifact_text(created.session_id, "chart_rectification_state.json")
            or "{}"
        )
        assert state["status"] == "collecting_evidence"

        await runtime.prepare_rectification_interview(
            RectificationInterviewInput(sessionId=created.session_id, locale="en"),
            use_agent=False,
        )
        interview = json.loads(
            workspace.read_artifact_text(created.session_id, "rectification_interview.json") or "{}"
        )
        question_ids = {
            question["category"]: question["questionId"] for question in interview["questions"]
        }

        for stale_path in [
            "reader_prevalidation.md",
            "prevalidation_result.json",
            "user_context.md",
            "rectification_question_set.json",
            "rectification_answer_batch.json",
        ]:
            workspace.write_artifact(created.session_id, stale_path, "stale\n")

        updated = await runtime.record_rectification_life_events(
            RectificationLifeEventsInput(
                sessionId=created.session_id,
                events=[
                    {
                        "questionId": question_ids["education"],
                        "date": "2012-06",
                        "category": "education",
                        "description": "Graduated from university",
                    },
                    {
                        "questionId": question_ids["career"],
                        "date": "2018-03",
                        "category": "career",
                        "description": "Changed employer and role",
                    },
                    {
                        "questionId": question_ids["relationship"],
                        "date": "2021-10",
                        "category": "relationship",
                        "description": "Registered marriage",
                    },
                ],
            )
        )

        context = json.loads(
            workspace.read_artifact_text(created.session_id, "birth_input_context.json") or "{}"
        )
        record = json.loads(
            workspace.read_artifact_text(created.session_id, "chart_record.json") or "{}"
        )
        reading_session = json.loads(
            workspace.read_artifact_text(created.session_id, "reading_session.json") or "{}"
        )
        next_state = json.loads(
            workspace.read_artifact_text(created.session_id, "chart_rectification_state.json")
            or "{}"
        )
        assert updated.stage == "reader_ready"
        assert context["readingFocus"] == "Career direction"
        assert context["lifeEvents"]["eligibleEventCount"] == 3
        assert record["revision"] == 2
        assert record["subject"]["readerRelationship"] == "parent"
        assert record["subject"]["consultationTopics"] == ["Career direction"]
        assert next_state["status"] != "collecting_evidence"
        expected_contract_status = (
            "underdetermined"
            if next_state["status"] == "underdetermined"
            else "collecting_evidence"
        )
        assert record["rectification"]["decision"]["status"] == expected_contract_status
        assert reading_session["rectificationStatus"] == expected_contract_status
        assert (
            workspace.require_session_dir(created.session_id)
            / ".runtime/chart_revisions/rev_1/chart_record.json"
        ).exists()
        for stale_path in [
            "reader_prevalidation.md",
            "prevalidation_result.json",
            "user_context.md",
            "rectification_question_set.json",
            "rectification_answer_batch.json",
        ]:
            assert workspace.read_artifact_text(created.session_id, stale_path) is None

    asyncio.run(run())


def test_core_readiness_requires_prevalidation_result(tmp_path) -> None:
    runtime = runtime_with_workspace(tmp_path)

    with pytest.raises(ValueError, match="prevalidation_result.json"):
        runtime.assert_core_readiness("session")


def test_core_readiness_accepts_backend_rectification_gate_without_reader_prevalidation(
    tmp_path,
) -> None:
    runtime = runtime_with_workspace(tmp_path)
    session_dir = runtime.workspace.require_session_dir("session")
    (session_dir / "chart_rectification_state.json").write_text(
        json.dumps(
            {
                "status": "corrected_chart_ready",
                "holdoutResult": "passed",
                "reportGate": {"fullReportAllowed": True},
            }
        ),
        encoding="utf-8",
    )

    runtime.assert_core_readiness("session")


def test_core_readiness_blocks_disallowed_report(tmp_path) -> None:
    runtime = runtime_with_workspace(tmp_path)
    session_dir = runtime.workspace.require_session_dir("session")
    (session_dir / "prevalidation_result.json").write_text(
        json.dumps(
            {
                "schemaVersion": "vedic-prevalidation-result/2.0.0",
                "decision": {
                    "reportAllowed": False,
                    "reason": "needs rectification",
                    "nextStep": "review_birth_details_or_stop",
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="完整报告暂不允许生成"):
        runtime.assert_core_readiness("session")


def test_core_readiness_allows_valid_report_gate(tmp_path) -> None:
    runtime = runtime_with_workspace(tmp_path)
    session_dir = runtime.workspace.require_session_dir("session")
    (session_dir / "prevalidation_result.json").write_text(
        json.dumps(
            {
                "schemaVersion": "vedic-prevalidation-result/2.0.0",
                "decision": {
                    "reportAllowed": True,
                    "reportScope": "guarded_full_report",
                },
            }
        ),
        encoding="utf-8",
    )

    runtime.assert_core_readiness("session")


def test_core_readiness_rejects_prevalidation_from_prior_chart_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FixedPlaceService:
        @staticmethod
        def resolve(_: str) -> ResolvedPlace:
            return ResolvedPlace(
                label="Shanghai First Maternity Hospital East Campus",
                lat=31.19174,
                lon=121.54581,
                timezone="Asia/Shanghai",
                source="test-fixture",
                accuracy="poi",
                radius_km=0.2,
                confidence="high",
            )

    async def run() -> None:
        settings = SimpleNamespace(project_root=tmp_path)
        workspace = SkillWorkspace(settings)  # type: ignore[arg-type]
        runtime = SkillRuntime(
            calculator=VedicCalculator(settings, FixedPlaceService()),  # type: ignore[arg-type]
            workspace=workspace,
            agent_runtime=None,  # type: ignore[arg-type]
        )
        created = await runtime.create_reader_session(
            BirthInput(
                birthDate="1990-01-01",
                birthTime="08:30",
                birthPlace="Shanghai First Maternity Hospital East Campus",
                birthTimePrecision="exact",
                gender="not provided",
                relationship="not provided",
                timeSource="hospital birth record",
                readingFocus="Career direction",
                lifeEvents="",
                locale="en",
            )
        )
        prevalidation_markdown = (
            "**1.** Anchor one.\n\n> Derivation: test\n\n**2.** Anchor two.\n\n> Derivation: test\n"
        )
        workspace.write_artifact(
            created.session_id,
            "reader_prevalidation.md",
            prevalidation_markdown,
        )
        result = runtime._write_prevalidation_result(
            created.session_id,
            feedback_markdown="1. 准\n2. 准\n",
        )
        assert result is not None
        assert cast(dict[str, Any], result["decision"])["reportAllowed"] is True

        monkeypatch.setattr(runtime, "_ensure_runtime_contracts", lambda *_args: None)
        monkeypatch.setattr(runtime, "_prepare_judgement_context", lambda *_args: None)
        runtime.assert_core_readiness(created.session_id)

        workspace.write_artifact(
            created.session_id,
            "reader_prevalidation.md",
            prevalidation_markdown + "\nChanged after the quality decision.\n",
        )
        with pytest.raises(ValueError, match="prevalidation_result.json 已过期"):
            runtime.assert_core_readiness(created.session_id)

        workspace.write_artifact(
            created.session_id,
            "reader_prevalidation.md",
            prevalidation_markdown,
        )
        runtime._write_prevalidation_result(
            created.session_id,
            feedback_markdown="1. 准\n2. 准\n",
        )
        runtime.assert_core_readiness(created.session_id)

        record = json.loads(
            workspace.read_artifact_text(created.session_id, "chart_record.json") or "{}"
        )
        record["revision"] = int(record["revision"]) + 1
        workspace.write_artifact(
            created.session_id,
            "chart_record.json",
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        )

        with pytest.raises(ValueError, match="prevalidation_result.json 已过期"):
            runtime.assert_core_readiness(created.session_id)

    asyncio.run(run())


def test_prevalidation_decision_blocks_high_risk_without_rectification() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)

    decision = runtime._prevalidation_decision(
        5,
        5,
        status="scored",
        time_reliability="uncertain",
        input_risk_level="high",
        report_readiness={
            "mode": "rectification_required",
            "scope": "prevalidation_or_d1_only",
            "minimumHitRateForCore": 0.9,
            "coreAllowedWithoutRectification": False,
            "llmContract": {"mustNotUseAsPrimaryEvidence": ["d9Lagna"]},
        },
    )

    assert decision["reportAllowed"] is False
    assert decision["nextStep"] == "complete_deterministic_rectification"
    assert decision["reportScope"] == "prevalidation_or_d1_only"


def test_prevalidation_decision_requires_medium_risk_threshold() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)

    below_threshold = runtime._prevalidation_decision(
        3.5,
        5,
        status="scored",
        time_reliability="uncertain",
        input_risk_level="medium",
        report_readiness={
            "mode": "guarded_after_strong_prevalidation",
            "scope": "guarded_full_report",
            "minimumHitRateForCore": 0.8,
            "coreAllowedWithoutRectification": True,
        },
    )
    at_threshold = runtime._prevalidation_decision(
        4,
        5,
        status="scored",
        time_reliability="uncertain",
        input_risk_level="medium",
        report_readiness={
            "mode": "guarded_after_strong_prevalidation",
            "scope": "guarded_full_report",
            "minimumHitRateForCore": 0.8,
            "coreAllowedWithoutRectification": True,
        },
    )

    assert below_threshold["reportAllowed"] is False
    assert below_threshold["nextStep"] == "review_birth_details_or_stop"
    assert at_threshold["reportAllowed"] is True
    assert at_threshold["nextStep"] == "report_allowed_with_limits"


def test_reliable_exact_time_does_not_bypass_failed_reader_quality_gate() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)

    decision = runtime._prevalidation_decision(
        0,
        5,
        status="scored",
        time_reliability="reliable_exact",
        input_risk_level="low",
        report_readiness={
            "mode": "standard_after_prevalidation",
            "scope": "full_report",
            "minimumHitRateForCore": 0.8,
            "coreAllowedWithoutRectification": True,
        },
    )

    assert decision["reportAllowed"] is False
    assert decision["timeConfidence"] == "high"
    assert decision["nextStep"] == "regenerate_prevalidation_or_review_subject"


def test_reliable_exact_time_does_not_bypass_required_place_rectification() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)

    decision = runtime._prevalidation_decision(
        5,
        5,
        status="scored",
        time_reliability="reliable_exact",
        input_risk_level="high",
        report_readiness={
            "mode": "rectification_required",
            "scope": "prevalidation_or_d1_only",
            "minimumHitRateForCore": 0.9,
            "coreAllowedWithoutRectification": False,
        },
    )

    assert decision["reportAllowed"] is False
    assert decision["nextStep"] == "complete_deterministic_rectification"


def test_reader_quality_attempt_stops_after_two_failed_rounds(tmp_path) -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)
    runtime.workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = "session-quality-attempts"
    runtime.workspace.create_session(session_id)
    runtime.workspace.write_artifact(
        session_id,
        "chart_record.json",
        json.dumps(
            {
                "chartRecordId": "chart-quality-attempts",
                "revision": 0,
                "subject": {"subjectId": "subject-quality-attempts"},
                "birthAssertion": {
                    "localDate": "1990-01-01",
                    "reportedLocalTime": "08:30",
                    "reportedPlace": "Shanghai",
                    "timeCertainty": "exact",
                    "evidence": [{"sourceLabel": "hospital birth record"}],
                },
            }
        ),
    )
    runtime.workspace.write_artifact(
        session_id,
        "sensitivity_scan.json",
        json.dumps(
            {
                "summary": {"riskLevel": "low"},
                "reportReadiness": {
                    "mode": "standard_after_prevalidation",
                    "scope": "full_report",
                    "minimumHitRateForCore": 0.8,
                    "coreAllowedWithoutRectification": True,
                },
            }
        ),
    )
    runtime.workspace.write_artifact(
        session_id,
        "reader_prevalidation.md",
        "**1.** Did this happen?\n\n> Derivation: test\n",
    )

    first = runtime._write_prevalidation_result(session_id, feedback_markdown="1. 不准")
    assert first is not None
    assert first["qualityAttempt"] == 1
    assert cast(dict[str, Any], first["decision"])["nextStep"] == (
        "regenerate_prevalidation_or_review_subject"
    )

    runtime._write_prevalidation_result(session_id, feedback_markdown="")
    second = runtime._write_prevalidation_result(session_id, feedback_markdown="1. 不准")
    assert second is not None
    assert second["qualityAttempt"] == 2
    assert cast(dict[str, Any], second["decision"])["nextStep"] == ("review_birth_details_or_stop")


def test_prevalidation_result_uses_sensitivity_scan_gate() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)
    chart_record_json = json.dumps(
        {
            "chartRecordId": "chart-prevalidation",
            "revision": 3,
            "subject": {
                "subjectId": "subject-1",
            },
            "birthAssertion": {
                "localDate": "1990-01-01",
                "reportedLocalTime": "08:30",
                "reportedPlace": "Shanghai",
                "timeCertainty": "approximate",
                "evidence": [{"sourceLabel": "family memory"}],
            },
        }
    )
    sensitivity_scan_json = json.dumps(
        {
            "summary": {
                "riskLevel": "high",
                "changedFields": ["d9Lagna"],
                "divisionalConfidence": {"D9": {"confidence": "low"}},
            },
            "stability": {"llmRestrictedEvidence": ["d9Lagna", "D9"]},
            "reportReadiness": {
                "mode": "rectification_required",
                "scope": "prevalidation_or_d1_only",
                "minimumHitRateForCore": 0.9,
                "coreAllowedWithoutRectification": False,
                "llmContract": {"mustNotUseAsPrimaryEvidence": ["d9Lagna", "D9"]},
            },
        }
    )

    result = runtime._build_prevalidation_result(
        """
**1.** Anchor one.

> Derivation: test

**2.** Anchor two.

> Derivation: test
        """,
        "1. 准\n2. 准\n",
        chart_record_json,
        sensitivity_scan_json,
    )

    score = cast(dict[str, Any], result["score"])
    decision = cast(dict[str, Any], result["decision"])
    llm_contract = cast(dict[str, Any], decision["llmContract"])

    assert score["hitRate"] == 1.0
    assert result["chartRecordId"] == "chart-prevalidation"
    assert result["chartRevision"] == 3
    assert (
        result["chartRecordSha256"] == hashlib.sha256(chart_record_json.encode("utf-8")).hexdigest()
    )
    assert decision["reportAllowed"] is False
    assert decision["inputRiskLevel"] == "high"
    assert llm_contract["mustNotUseAsPrimaryEvidence"] == [
        "d9Lagna",
        "D9",
    ]


@pytest.mark.parametrize(
    ("locale", "report_allowed", "expected"),
    [
        ("en", True, "full reading can now begin"),
        ("en", False, "instead of forcing a chart"),
        ("zh", True, "可以开始完整解读"),
        ("zh", False, "不要为了生成报告而强行确定盘面"),
        ("ja", False, "無理にチャートを確定しないでください"),
    ],
)
def test_reader_quality_message_matches_gate_semantics(
    locale: str, report_allowed: bool, expected: str
) -> None:
    assert expected in SkillRuntime._reader_quality_message(locale, report_allowed)


def test_lagna_restriction_closes_over_every_house_dependent_fact() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)

    def fact(fact_id: str, fact_type: str, subject_ref: str):
        return SimpleNamespace(fact_id=fact_id, fact_type=fact_type, subject_ref=subject_ref)

    record = SimpleNamespace(
        facts=[
            fact("fact.D1.Lagna.position", "rashi.lagna.position", "D1.Lagna"),
            fact("fact.D1.H10.lord", "rashi.house.lord", "D1.H10"),
            fact(
                "fact.D1.H10.occupant.Sun",
                "rashi.house.occupant",
                "D1.H10.occupant.Sun",
            ),
            fact("fact.D1.Sun.house_ownership", "role.house_ownership", "D1.Sun"),
            fact(
                "fact.D1.relationship.parivartana.H1.H7",
                "relationship.parivartana",
                "D1.Mars~Venus",
            ),
            fact("fact.D1.Sun.digbala", "strength.digbala", "D1.Sun"),
            fact("fact.D1.Sun.shadbala", "strength.shadbala", "D1.Sun"),
            fact("fact.D1.H10.bhava_bala", "strength.bhava_bala", "D1.H10"),
            fact("fact.D1.H10.sav", "ashtakavarga.sav.house", "D1.H10"),
            fact("fact.D1.AL.position", "point.arudha", "D1.AL"),
            fact(
                "fact.D1.aspect.house",
                "aspect.graha_drishti",
                "D1.Saturn->H10",
            ),
            fact(
                "fact.Transit.Saturn.position",
                "timing.transit.position",
                "Transit.Saturn",
            ),
            fact(
                "fact.Transit.Saturn.house",
                "timing.transit.house",
                "Transit.Saturn->D1.H10",
            ),
            fact("fact.D1.Sun.position", "rashi.graha.position", "D1.Sun"),
            fact("fact.D1.Sun.dignity", "strength.dignity", "D1.Sun"),
            fact(
                "fact.D1.aspect.planet",
                "aspect.graha_drishti",
                "D1.Saturn->Sun",
            ),
        ]
    )

    restricted, _ = runtime._restricted_judgement_evidence(
        cast(Any, record),
        {"reportReadiness": {"llmContract": {"mustNotUseAsPrimaryEvidence": ["lagnaSign"]}}},
    )

    assert {
        "fact.D1.Lagna.position",
        "fact.D1.H10.lord",
        "fact.D1.H10.occupant.Sun",
        "fact.D1.Sun.house_ownership",
        "fact.D1.relationship.parivartana.H1.H7",
        "fact.D1.Sun.digbala",
        "fact.D1.Sun.shadbala",
        "fact.D1.H10.bhava_bala",
        "fact.D1.H10.sav",
        "fact.D1.AL.position",
        "fact.D1.aspect.house",
        "fact.Transit.Saturn.house",
    } <= restricted
    assert "fact.D1.Sun.position" not in restricted
    assert "fact.D1.Sun.dignity" not in restricted
    assert "fact.D1.aspect.planet" not in restricted
    assert "fact.Transit.Saturn.position" not in restricted


def test_varga_lagna_restriction_closes_over_the_entire_varga() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)
    record = SimpleNamespace(
        facts=[
            SimpleNamespace(
                fact_id="fact.D9.Lagna.position",
                fact_type="varga.lagna.position",
                subject_ref="D9.Lagna",
            ),
            SimpleNamespace(
                fact_id="fact.D9.Venus.position",
                fact_type="varga.graha.position",
                subject_ref="D9.Venus",
            ),
            SimpleNamespace(
                fact_id="fact.D9.H7.lord",
                fact_type="varga.house.lord",
                subject_ref="D9.H7",
            ),
            SimpleNamespace(
                fact_id="fact.D10.Sun.position",
                fact_type="varga.graha.position",
                subject_ref="D10.Sun",
            ),
        ]
    )

    restricted, _ = runtime._restricted_judgement_evidence(
        cast(Any, record),
        {"reportReadiness": {"llmContract": {"mustNotUseAsPrimaryEvidence": ["d9Lagna"]}}},
    )

    assert restricted == {
        "fact.D9.Lagna.position",
        "fact.D9.Venus.position",
        "fact.D9.H7.lord",
    }


def test_varga_structure_restriction_includes_d9_vargottama() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)
    record = SimpleNamespace(
        facts=[
            SimpleNamespace(
                fact_id="fact.D9.Venus.position",
                fact_type="varga.graha.position",
                subject_ref="D9.Venus",
            ),
            SimpleNamespace(
                fact_id="fact.D1.Venus.vargottama",
                fact_type="varga.vargottama",
                subject_ref="D1.Venus",
            ),
            SimpleNamespace(
                fact_id="fact.D10.Sun.position",
                fact_type="varga.graha.position",
                subject_ref="D10.Sun",
            ),
        ]
    )

    restricted, _ = runtime._restricted_judgement_evidence(
        cast(Any, record),
        {"reportReadiness": {"llmContract": {"mustNotUseAsPrimaryEvidence": ["d9Structure"]}}},
    )

    assert restricted == {
        "fact.D9.Venus.position",
        "fact.D1.Venus.vargottama",
    }


def test_moon_nakshatra_boundary_preserves_stable_sign_structure() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)
    record = SimpleNamespace(
        facts=[
            SimpleNamespace(
                fact_id="fact.D1.Moon.position",
                fact_type="rashi.graha.position",
                subject_ref="D1.Moon",
            ),
            SimpleNamespace(
                fact_id="fact.D1.H4.occupant.Moon",
                fact_type="rashi.house.occupant",
                subject_ref="D1.H4.occupant.Moon",
            ),
            SimpleNamespace(
                fact_id="fact.D1.aspect.moon",
                fact_type="aspect.graha_drishti",
                subject_ref="D1.Moon->Saturn",
            ),
            SimpleNamespace(
                fact_id="fact.D1.same_sign.Moon.Saturn",
                fact_type="relationship.same_sign",
                subject_ref="D1.Moon~Saturn",
            ),
            SimpleNamespace(
                fact_id="fact.D1.yoga.raja_kendra_trikona.Moon.Saturn",
                fact_type="yoga.raja.kendra_trikona",
                subject_ref="D1.Moon~Saturn",
            ),
            SimpleNamespace(
                fact_id="fact.D1.yoga.gaja_kesari",
                fact_type="yoga.gaja_kesari.structure",
                subject_ref="D1.Moon~Jupiter",
            ),
            SimpleNamespace(
                fact_id="fact.D1.relationship.parivartana.H4.H7",
                fact_type="relationship.parivartana",
                subject_ref="D1.Moon~Saturn",
            ),
            SimpleNamespace(
                fact_id="fact.Transit.Saturn.Moon.sade_sati",
                fact_type="timing.transit.sade_sati",
                subject_ref="Transit.Saturn.Moon",
            ),
            SimpleNamespace(
                fact_id="fact.D1.Sun.position",
                fact_type="rashi.graha.position",
                subject_ref="D1.Sun",
            ),
        ]
    )

    restricted, restrict_timing = runtime._restricted_judgement_evidence(
        cast(Any, record),
        {"reportReadiness": {"llmContract": {"mustNotUseAsPrimaryEvidence": ["moonNakshatra"]}}},
    )

    assert restricted == {"fact.D1.Moon.position"}
    assert restrict_timing is True


def test_moon_sign_boundary_restricts_all_moon_sign_dependencies() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)
    record = SimpleNamespace(
        facts=[
            SimpleNamespace(
                fact_id="fact.D1.Moon.position",
                fact_type="rashi.graha.position",
                subject_ref="D1.Moon",
            ),
            SimpleNamespace(
                fact_id="fact.D1.H4.occupant.Moon",
                fact_type="rashi.house.occupant",
                subject_ref="D1.H4.occupant.Moon",
            ),
            SimpleNamespace(
                fact_id="fact.D1.aspect.moon",
                fact_type="aspect.graha_drishti",
                subject_ref="D1.Moon->Saturn",
            ),
            SimpleNamespace(
                fact_id="fact.D1.same_sign.Moon.Saturn",
                fact_type="relationship.same_sign",
                subject_ref="D1.Moon~Saturn",
            ),
            SimpleNamespace(
                fact_id="fact.D1.yoga.raja_kendra_trikona.Moon.Saturn",
                fact_type="yoga.raja.kendra_trikona",
                subject_ref="D1.Moon~Saturn",
            ),
            SimpleNamespace(
                fact_id="fact.D1.yoga.gaja_kesari",
                fact_type="yoga.gaja_kesari.structure",
                subject_ref="D1.Moon~Jupiter",
            ),
            SimpleNamespace(
                fact_id="fact.D1.relationship.parivartana.H4.H7",
                fact_type="relationship.parivartana",
                subject_ref="D1.Moon~Saturn",
            ),
            SimpleNamespace(
                fact_id="fact.Transit.Saturn.Moon.sade_sati",
                fact_type="timing.transit.sade_sati",
                subject_ref="Transit.Saturn.Moon",
            ),
            SimpleNamespace(
                fact_id="fact.D1.Sun.position",
                fact_type="rashi.graha.position",
                subject_ref="D1.Sun",
            ),
        ]
    )

    restricted, restrict_timing = runtime._restricted_judgement_evidence(
        cast(Any, record),
        {"reportReadiness": {"llmContract": {"mustNotUseAsPrimaryEvidence": ["moonSign"]}}},
    )

    assert restricted == {
        "fact.D1.Moon.position",
        "fact.D1.H4.occupant.Moon",
        "fact.D1.aspect.moon",
        "fact.D1.same_sign.Moon.Saturn",
        "fact.D1.relationship.parivartana.H4.H7",
        "fact.D1.yoga.raja_kendra_trikona.Moon.Saturn",
        "fact.D1.yoga.gaja_kesari",
        "fact.Transit.Saturn.Moon.sade_sati",
    }
    assert restrict_timing is False


def test_chara_karaka_boundary_restricts_all_chara_karaka_facts() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)
    record = SimpleNamespace(
        facts=[
            SimpleNamespace(
                fact_id="fact.D1.Sun.chara_karaka",
                fact_type="karaka.chara",
                subject_ref="D1.Sun",
            ),
            SimpleNamespace(
                fact_id="fact.D1.Moon.chara_karaka",
                fact_type="karaka.chara",
                subject_ref="D1.Moon",
            ),
            SimpleNamespace(
                fact_id="fact.D1.Sun.position",
                fact_type="rashi.graha.position",
                subject_ref="D1.Sun",
            ),
        ]
    )

    restricted, restrict_timing = runtime._restricted_judgement_evidence(
        cast(Any, record),
        {"reportReadiness": {"llmContract": {"mustNotUseAsPrimaryEvidence": ["charaKaraka7k"]}}},
    )

    assert restricted == {
        "fact.D1.Sun.chara_karaka",
        "fact.D1.Moon.chara_karaka",
    }
    assert restrict_timing is False


def test_interpretive_state_boundary_restricts_only_dependent_fact_family() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)
    record = SimpleNamespace(
        facts=[
            SimpleNamespace(
                fact_id="fact.D1.Venus.shadbala",
                fact_type="strength.shadbala",
                subject_ref="D1.Venus",
            ),
            SimpleNamespace(
                fact_id="fact.D1.Venus.dignity",
                fact_type="strength.dignity",
                subject_ref="D1.Venus",
            ),
        ]
    )

    restricted, restrict_timing = runtime._restricted_judgement_evidence(
        cast(Any, record),
        {
            "reportReadiness": {
                "llmContract": {"mustNotUseAsPrimaryEvidence": ["shadbalaClassification"]}
            }
        },
    )

    assert restricted == {"fact.D1.Venus.shadbala"}
    assert restrict_timing is False


def test_fact_input_stability_is_the_primary_judgement_restriction_contract() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)
    record = SimpleNamespace(
        facts=[
            SimpleNamespace(
                fact_id="fact.D1.yoga.gaja_kesari",
                fact_type="yoga.gaja_kesari.structure",
                subject_ref="D1.Moon~Jupiter",
                input_stability=ConfidenceGrade.PROVISIONAL,
            ),
            SimpleNamespace(
                fact_id="fact.D1.Sun.position",
                fact_type="rashi.graha.position",
                subject_ref="D1.Sun",
                input_stability=ConfidenceGrade.CORROBORATED,
            ),
        ]
    )

    restricted, restrict_timing = runtime._restricted_judgement_evidence(
        cast(Any, record),
        {"reportReadiness": {"llmContract": {"mustNotUseAsPrimaryEvidence": []}}},
    )

    assert restricted == {"fact.D1.yoga.gaja_kesari"}
    assert restrict_timing is False


def test_rule_evaluation_cannot_match_restricted_evidence() -> None:
    predicate = SimpleNamespace(
        fact_type="rashi.lagna.position",
        subject_selector="D1.Lagna",
        operator="exists",
        expected=None,
    )
    rule = cast(
        Any,
        SimpleNamespace(
            rule_id="judge.test",
            required_evidence_layers=["natal_promise"],
            all_of=[predicate],
            any_of=[],
            none_of=[],
        ),
    )
    record = cast(
        Any,
        SimpleNamespace(
            facts=[
                SimpleNamespace(
                    fact_id="fact.D1.Lagna.position",
                    fact_type="rashi.lagna.position",
                    subject_ref="D1.Lagna",
                    value={"sign": "Aries"},
                )
            ],
            charts=[],
            rectification=None,
        ),
    )

    assert evaluate_method_rule(rule, record)["evaluationStatus"] == "eligible"
    restricted = evaluate_method_rule(
        rule,
        record,
        restricted_fact_ids={"fact.D1.Lagna.position"},
    )
    assert restricted["evaluationStatus"] == "ineligible"
    assert restricted["matchedFactIds"] == []

    excluded_layer = evaluate_method_rule(
        rule,
        record,
        excluded_evidence_layers={"natal_promise"},
    )
    assert excluded_layer["evaluationStatus"] == "ineligible"
    assert "requiredEvidenceLayers:natal_promise" in excluded_layer["failedPredicates"]


def test_rectification_structure_field_resolves_changed_graha_facts() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)
    record = SimpleNamespace(
        facts=[
            SimpleNamespace(fact_id="fact.D9.Venus.position"),
            SimpleNamespace(fact_id="fact.D9.Mars.position"),
            SimpleNamespace(fact_id="fact.D9.Lagna.position"),
        ]
    )
    candidates = [
        {
            "signature": {
                "vargaPlanetSignIndices": {"D9": {"Venus": 4, "Mars": 7}},
            }
        },
        {
            "signature": {
                "vargaPlanetSignIndices": {"D9": {"Venus": 5, "Mars": 7}},
            }
        },
    ]

    fact_ids = runtime._discriminating_fact_ids(
        cast(Any, record),
        "d9Structure",
        candidates,
    )

    assert fact_ids == ["fact.D9.Venus.position"]


def test_rectification_unknown_field_does_not_fall_back_to_lagna() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)
    record = SimpleNamespace(
        facts=[SimpleNamespace(fact_id="fact.D1.Lagna.position")],
    )

    assert runtime._discriminating_fact_ids(cast(Any, record), "unknownField", []) == []


def test_rectification_selects_candidate_and_builds_rectified_birth_input() -> None:
    service = ChartRectificationService()
    birth_context = {
        "time": {
            "date": "1990-01-01",
            "reported": "08:30",
            "precision": "approximate",
            "source": "family memory",
            "window": {"start": "1990-01-01 08:15", "end": "1990-01-01 08:45"},
        },
        "place": {
            "reported": "Shanghai, Shanghai, China",
            "accuracy": "city",
            "radiusKm": 25,
        },
        "constraints": {
            "timeSearchMustStayWithinReportedWindow": True,
            "placeSearchMustStayWithinRadiusKm": True,
            "rejectRectificationOutsideUserFacts": True,
        },
        "lifeEvents": {
            **_rectification_ledger(),
            "raw": "2018-06 career\n2020-09 marriage\n2023-05 relocation",
        },
    }
    sensitivity = {
        "summary": {"riskLevel": "high", "changedFields": ["d9Lagna"]},
        "reportReadiness": {"mode": "rectification_required"},
        "candidateGroups": [
            {
                "candidateId": "A",
                "isBase": True,
                "signature": {"d9Lagna": "Libra"},
                "holdoutScore": 0.2,
                "aggregateScore": 0.1,
                "changedFromBase": [],
                "members": [{"axis": "time", "label": "base", "datetime": "1990-01-01 08:30"}],
            },
            {
                "candidateId": "B",
                "isBase": False,
                "signature": {"d9Lagna": "Scorpio"},
                "holdoutScore": 0.7,
                "aggregateScore": 0.4,
                "changedFromBase": ["d9Lagna"],
                "members": [{"axis": "time", "label": "+15m", "datetime": "1990-01-01 08:45"}],
            },
        ],
    }
    state = service.initial_state(birth_context, sensitivity)
    updated = dict(state)
    updated["status"] = "needs_recalculation"
    updated["selectedCandidateId"] = "B"
    updated["selectionConfidence"] = "medium"
    updated["holdoutResult"] = "passed"

    assert updated["status"] == "needs_recalculation"
    assert updated["selectedCandidateId"] == "B"

    rectified = service.rectified_birth_input(
        updated,
        birth_context,
        {
            "subject": {
                "locale": "ja",
                "genderContext": "女",
                "relationshipStatus": "单身",
            }
        },
    )

    assert rectified is not None
    assert rectified.birth_time == "08:45"
    assert rectified.birth_time_precision == "exact"
    assert rectified.birth_place == "Shanghai, Shanghai, China"
    assert rectified.locale == "ja"
    assert rectified.life_events == "2018-06 career\n2020-09 marriage\n2023-05 relocation"
    assert rectified.gender == "女"
    assert rectified.relationship == "单身"

    ready = service.apply_chart_revision(updated, rectified_input=rectified, chart_revision=1)
    decision = service.apply_prevalidation_decision(
        {"reportAllowed": False, "reportScope": "prevalidation_or_d1_only"},
        ready,
    )

    assert ready["status"] == "corrected_chart_ready"
    assert decision["reportAllowed"] is True
    assert decision["nextStep"] == "report_allowed_after_rectification"


def test_initial_rectification_state_includes_backend_next_round_plan() -> None:
    service = ChartRectificationService()
    state = service.initial_state(
        {
            "time": {"window": {"start": "1990-01-01 08:15", "end": "1990-01-01 08:45"}},
            "place": {"accuracy": "city", "radiusKm": 25},
            "constraints": {
                "placeRectificationAllowed": True,
                "rectificationAxes": ["time", "place"],
            },
        },
        {
            "summary": {"riskLevel": "high", "changedFields": ["d9Lagna"]},
            "reportReadiness": {"mode": "rectification_required"},
            "candidateGroups": [
                {
                    "candidateId": "A",
                    "isBase": True,
                    "changedFromBase": [],
                    "members": [{"axis": "time", "datetime": "1990-01-01 08:30"}],
                },
                {
                    "candidateId": "B",
                    "isBase": False,
                    "changedFromBase": ["d9Lagna"],
                    "members": [{"axis": "time", "datetime": "1990-01-01 08:45"}],
                },
            ],
        },
    )

    plan = state["rectificationPlan"]

    assert plan["schemaVersion"] == "chart-rectification-plan/v1"
    assert plan["action"] == "collect_dated_life_events"
    assert plan["targetCandidateIds"] == ["A", "B"]
    assert plan["discriminatingFields"] == ["d9Lagna"]
    assert plan["focusAxes"] == ["time", "place"]
    assert plan["timeWindow"]["start"] == "1990-01-01 08:25"
    assert plan["timeWindow"]["end"] == "1990-01-01 08:45"


def test_rectification_plan_targets_distinct_equivalence_classes() -> None:
    service = ChartRectificationService()
    state = service.initial_state(
        {
            "time": {"window": {"start": "1990-01-01 08:15", "end": "1990-01-01 08:45"}},
            "place": {"accuracy": "city", "radiusKm": 25},
        },
        {
            "summary": {"riskLevel": "high", "changedFields": ["d9Lagna"]},
            "reportReadiness": {"mode": "rectification_required"},
            "candidateGroups": [
                {
                    "candidateId": "A",
                    "isBase": True,
                    "equivalenceClassId": "equivalence.base",
                    "equivalentCandidateIds": ["A", "B"],
                },
                {
                    "candidateId": "B",
                    "isBase": False,
                    "equivalenceClassId": "equivalence.base",
                    "equivalentCandidateIds": ["A", "B"],
                },
                {
                    "candidateId": "C",
                    "isBase": False,
                    "equivalenceClassId": "equivalence.other",
                    "equivalentCandidateIds": ["C"],
                    "changedFromBase": ["d9Lagna"],
                },
            ],
        },
    )

    targets = state["rectificationPlan"]["targetCandidateIds"]
    assert "C" in targets
    assert len(set(targets) & {"A", "B"}) == 1


def test_rectification_collects_dated_events_before_agent_questions() -> None:
    service = ChartRectificationService()
    state = service.initial_state(
        {
            "time": {"window": {"start": "1990-01-01 08:15", "end": "1990-01-01 08:45"}},
            "place": {"accuracy": "city", "radiusKm": 25},
            "lifeEvents": parse_life_event_ledger(""),
        },
        {
            "summary": {"riskLevel": "high", "changedFields": ["d9Lagna"]},
            "reportReadiness": {"mode": "rectification_required"},
            "candidateGroups": [
                {"candidateId": "A", "isBase": True},
                {"candidateId": "B", "isBase": False, "changedFromBase": ["d9Lagna"]},
            ],
        },
    )

    assert state["status"] == "collecting_evidence"
    assert state["reportGate"]["nextStep"] == "collect_dated_life_events"
    assert state["rectificationPlan"]["action"] == "collect_dated_life_events"


def test_single_stable_candidate_does_not_start_fake_boundary_rectification() -> None:
    service = ChartRectificationService()
    state = service.initial_state(
        {
            "time": {"window": {"start": "1990-01-01 08:15", "end": "1990-01-01 08:45"}},
            "place": {"accuracy": "city", "radiusKm": 25},
            "lifeEvents": _rectification_ledger(),
        },
        {
            "summary": {"riskLevel": "high", "changedFields": []},
            "reportReadiness": {"mode": "rectification_required"},
            "candidateGroups": [
                {
                    "candidateId": "A",
                    "isBase": True,
                    "interval": {
                        "start": "1990-01-01 08:15",
                        "end": "1990-01-01 08:46",
                    },
                }
            ],
        },
    )

    assert state["status"] == "not_required"
    assert state["rectificationPlan"]["action"] == "full_report"
    assert state["reportGate"]["fullReportAllowed"] is True
    assert "one stable chart fingerprint" in state["reportGate"]["reason"]

    decision = service.apply_prevalidation_decision(
        {"reportAllowed": False, "reportScope": "prevalidation_or_d1_only"},
        state,
    )
    assert decision["reportAllowed"] is False
    assert decision["reportScope"] == "prevalidation_or_d1_only"


def test_stable_interval_preserves_successful_reader_quality_gate() -> None:
    service = ChartRectificationService()
    state = {
        "status": "not_required",
        "selectedCandidateId": None,
        "activeCandidateId": "A",
        "selectionConfidence": "stable_interval",
        "reportGate": {
            "fullReportAllowed": True,
            "reason": "One stable chart fingerprint covers the bounded input window.",
        },
    }

    decision = service.apply_prevalidation_decision(
        {
            "reportAllowed": True,
            "reportScope": "guarded_full_report",
            "timeConfidence": "medium",
        },
        state,
    )

    assert decision["reportAllowed"] is True
    assert decision["nextStep"] == "report_allowed_with_stable_interval"
    assert decision["timeConfidence"] == "medium"


def test_tied_dated_events_stop_instead_of_forcing_agent_questions() -> None:
    service = ChartRectificationService()
    event_one = "evt_1_201806_career"
    event_two = "evt_2_202009_marriage"
    state = service.initial_state(
        {
            "time": {"window": {"start": "1990-01-01 08:15", "end": "1990-01-01 08:45"}},
            "place": {"accuracy": "city", "radiusKm": 25},
            "lifeEvents": _rectification_ledger(),
        },
        {
            "summary": {"riskLevel": "high", "changedFields": ["d9Lagna"]},
            "reportReadiness": {"mode": "rectification_required"},
            "candidateGroups": [
                {
                    "candidateId": candidate_id,
                    "isBase": candidate_id == "A",
                    "aggregateScore": 0.2,
                    "evidenceScores": [
                        {"eventId": event_one, "role": "calibration", "score": 0.2},
                        {"eventId": event_two, "role": "calibration", "score": 0.2},
                    ],
                }
                for candidate_id in ("A", "B")
            ],
        },
    )

    assert state["status"] == "underdetermined"
    assert state["rectificationPlan"]["action"] == "rectification_inconclusive"
    assert state["reportGate"]["fullReportAllowed"] is False


def test_deterministic_calibration_selects_candidate_before_any_reader_question() -> None:
    service = ChartRectificationService()
    event_one = "evt_1_201806_career"
    event_two = "evt_2_202009_marriage"
    holdout = "evt_3_202305_relocation"
    state = service.initial_state(
        {
            "time": {"window": {"start": "1990-01-01 08:15", "end": "1990-01-01 08:45"}},
            "place": {"accuracy": "city", "radiusKm": 25},
            "lifeEvents": _rectification_ledger(),
        },
        {
            "summary": {"riskLevel": "high", "changedFields": ["d9Lagna"]},
            "reportReadiness": {"mode": "rectification_required"},
            "candidateGroups": [
                {
                    "candidateId": "A",
                    "isBase": True,
                    "aggregateScore": 0.1,
                    "holdoutScore": 0.2,
                    "evidenceScores": [
                        {"eventId": event_one, "role": "calibration", "score": 0.1},
                        {"eventId": event_two, "role": "calibration", "score": 0.1},
                        {"eventId": holdout, "role": "holdout", "score": 0.2},
                    ],
                },
                {
                    "candidateId": "B",
                    "isBase": False,
                    "aggregateScore": 0.45,
                    "holdoutScore": 0.7,
                    "changedFromBase": ["d9Lagna"],
                    "members": [{"axis": "time", "datetime": "1990-01-01 08:45"}],
                    "evidenceScores": [
                        {"eventId": event_one, "role": "calibration", "score": 0.5},
                        {"eventId": event_two, "role": "calibration", "score": 0.4},
                        {"eventId": holdout, "role": "holdout", "score": 0.7},
                    ],
                },
            ],
        },
    )

    assert state["status"] == "needs_recalculation"
    assert state["selectedCandidateId"] == "B"
    assert state["holdoutResult"] == "passed"


def test_deterministic_selection_requires_calibration_domain_diversity() -> None:
    service = ChartRectificationService()
    ledger = _rectification_ledger()
    ledger["events"][1]["category"] = "career"  # type: ignore[index]
    event_one = str(ledger["events"][0]["eventId"])  # type: ignore[index]
    event_two = str(ledger["events"][1]["eventId"])  # type: ignore[index]
    holdout = str(ledger["events"][2]["eventId"])  # type: ignore[index]
    state = service.initial_state(
        {
            "time": {"window": {"start": "1990-01-01 08:15", "end": "1990-01-01 08:45"}},
            "place": {"accuracy": "city", "radiusKm": 25},
            "lifeEvents": ledger,
        },
        {
            "summary": {"riskLevel": "high", "changedFields": ["d9Lagna"]},
            "reportReadiness": {"mode": "rectification_required"},
            "candidateGroups": [
                {
                    "candidateId": candidate_id,
                    "isBase": candidate_id == "A",
                    "aggregateScore": 0.6 if candidate_id == "B" else 0.1,
                    "holdoutScore": 0.7 if candidate_id == "B" else 0.1,
                    "evidenceScores": [
                        {"eventId": event_one, "role": "calibration", "score": 0.6},
                        {"eventId": event_two, "role": "calibration", "score": 0.6},
                        {"eventId": holdout, "role": "holdout", "score": 0.7},
                    ],
                }
                for candidate_id in ("A", "B")
            ],
        },
    )

    assert state["status"] == "underdetermined"
    assert state["selectionEvidence"]["calibrationCategoryCount"] == 1
    assert "insufficient_calibration_category_diversity" in state["selectionEvidence"]["blockers"]


def test_rectification_state_marks_precise_place_as_time_only() -> None:
    service = ChartRectificationService()

    state = service.initial_state(
        {
            "time": {"window": {"start": "1990-01-01 08:28", "end": "1990-01-01 08:32"}},
            "place": {
                "accuracy": "poi",
                "radiusKm": 0.3,
                "rectificationAllowed": False,
            },
            "constraints": {
                "placeRectificationAllowed": False,
                "rectificationAxes": ["time"],
            },
        },
        {
            "summary": {"riskLevel": "high", "changedFields": ["d9Lagna"]},
            "reportReadiness": {"mode": "rectification_required"},
            "candidateGroups": [
                {"candidateId": "A", "isBase": True, "members": []},
                {
                    "candidateId": "B",
                    "isBase": False,
                    "members": [{"axis": "time", "datetime": "1990-01-01 08:32"}],
                },
            ],
        },
    )

    assert state["searchBounds"]["place"]["rectificationAllowed"] is False
    assert state["guardrails"]["placeRectificationAllowed"] is False
    assert state["guardrails"]["rectificationAxes"] == ["time"]


def test_rectified_place_candidate_uses_coordinate_accuracy() -> None:
    service = ChartRectificationService()
    state = {
        "selectedCandidateId": "B",
        "candidates": [
            {"candidateId": "A", "isBase": True, "members": []},
            {
                "candidateId": "B",
                "isBase": False,
                "members": [
                    {
                        "axis": "place",
                        "coordinates": {"lat": 31.2, "lon": 121.5},
                        "timezone": "Asia/Shanghai",
                    }
                ],
            },
        ],
    }

    rectified = service.rectified_birth_input(
        state,
        {
            "time": {
                "date": "1990-01-01",
                "reported": "08:30",
                "precision": "approximate",
                "utcOffsetSeconds": 28800,
            },
            "place": {
                "reported": "Shanghai, Shanghai, China",
                "accuracy": "city",
                "radiusKm": 25,
            },
        },
        {"subject": {"gender": "女", "relationship": "单身"}},
    )

    assert rectified is not None
    assert "lat=31.2, lon=121.5" in rectified.birth_place
    assert "tz=Asia/Shanghai" in rectified.birth_place
    assert "accuracy=coordinate" in rectified.birth_place
    assert rectified.utc_offset_seconds is None


def test_rectified_ambiguous_time_preserves_selected_candidate_offset() -> None:
    service = ChartRectificationService()
    state = {
        "selectedCandidateId": "B",
        "candidates": [
            {"candidateId": "A", "isBase": True, "members": []},
            {
                "candidateId": "B",
                "isBase": False,
                "representativeDatetime": "2025-11-02 01:30",
                "civilTimeFold": True,
                "utcOffsetSeconds": -18000,
                "members": [
                    {
                        "axis": "time",
                        "datetime": "2025-11-02 01:30",
                    }
                ],
            },
        ],
    }

    rectified = service.rectified_birth_input(
        state,
        {
            "time": {
                "date": "2025-11-02",
                "reported": "01:30",
                "precision": "exact",
                "utcOffsetSeconds": -14400,
            },
            "place": {
                "reported": "New York, New York, United States",
                "accuracy": "coordinate",
                "radiusKm": 0.25,
            },
        },
        {"subject": {"gender": "女", "relationship": "单身"}},
    )

    assert rectified is not None
    assert rectified.utc_offset_seconds == -18000


def test_place_candidate_event_scoring_uses_candidate_coordinates(monkeypatch) -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    observed: list[dict[str, object]] = []

    def fake_score_candidate_events(**kwargs):
        observed.append(kwargs)
        return {"evidenceScores": [], "aggregateScore": 0.1, "holdoutScore": 0.2}

    monkeypatch.setattr(
        "app.services.vedic_calculator.score_candidate_events",
        fake_score_candidate_events,
    )
    candidates = [
        {
            "candidateId": "B",
            "signature": {"lagnaSign": "Aries"},
            "members": [
                {
                    "axis": "place",
                    "coordinates": {"lat": 31.2, "lon": 121.5},
                    "timezone": "Asia/Shanghai",
                }
            ],
        }
    ]

    calculator._score_candidate_groups(
        candidates,
        _rectification_ledger(),
        _birth_payload(),
    )

    assert observed[0]["latitude"] == 31.2
    assert observed[0]["longitude"] == 121.5
    assert observed[0]["timezone_id"] == "Asia/Shanghai"
    assert candidates[0]["scoringLocation"] == {
        "latitude": 31.2,
        "longitude": 121.5,
        "timezoneId": "Asia/Shanghai",
    }


def test_time_scan_splits_equal_chart_signatures_at_event_period_boundary() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    base_signature = calculator._chart_signature(_base_chart())

    def same_signature(*_args, **_kwargs):
        return dict(base_signature)

    def event_period_fingerprint(*, birth_moment, **_kwargs):
        return ("Saturn/Venus/Mercury",) if birth_moment.minute < 30 else ("Saturn/Venus/Ketu",)

    variants = calculator._time_scan_variants(
        lambda *_args: _base_chart(),
        _base_chart(),
        base_signature,
        _birth_payload(),
        "exact",
        "birth certificate",
        calculate_signature=same_signature,
        life_event_ledger={"events": [{"eventId": "evt_1"}]},
        calculate_event_period_fingerprint=event_period_fingerprint,
    )

    assert [{key: item["interval"][key] for key in ("start", "end")} for item in variants] == [
        {"start": "1990-01-01 08:28", "end": "1990-01-01 08:30"},
        {"start": "1990-01-01 08:29", "end": "1990-01-01 08:33"},
    ]
    assert all(item["eventPeriodBoundaryChecked"] for item in variants)


def test_unknown_time_scan_covers_both_folds_of_a_dst_fallback_day() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    payload = {
        **_birth_payload(),
        "year": 2021,
        "month": 11,
        "day": 7,
        "hour": 12,
        "minute": 0,
        "dob": "2021-11-07",
        "time": "12:00",
        "timezone": "America/New_York",
    }
    base_signature = calculator._chart_signature(_base_chart())
    observed: list[tuple[int, int, int | None]] = []

    def signature(_year, _month, _day, hour, minute, _lat, _lon, _timezone, **kwargs):
        observed.append((hour, minute, kwargs.get("utc_offset_seconds")))
        return dict(base_signature)

    window = calculator._time_window(payload, "unknown", "时间未知")
    variants = calculator._time_scan_variants(
        lambda *_args, **_kwargs: _base_chart(),
        _base_chart(),
        base_signature,
        payload,
        "unknown",
        "时间未知",
        calculate_signature=signature,
    )

    assert window["elapsedMinutes"] == 1500
    assert (1, 30, -4 * 3600) in observed
    assert (1, 30, -5 * 3600) in observed
    assert variants[0]["interval"]["startUtc"] == "2021-11-07T04:00:00+00:00"
    assert variants[-1]["interval"]["endUtc"] == "2021-11-08T05:00:00+00:00"
    assert all(item["eventPeriodStableWithinInterval"] for item in variants)


def test_time_scan_splits_at_current_dasha_boundary_without_life_events() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    base_signature = calculator._chart_signature(_base_chart())
    base_signature["currentDasha"] = "Saturn-Sun"

    def same_signature(*_args, **_kwargs):
        return dict(base_signature)

    def period_fingerprint(*, birth_moment, **_kwargs):
        current = "Saturn-Venus" if birth_moment.minute < 30 else "Saturn-Sun"
        return {"eventPeriods": (), "currentDasha": current}

    variants = calculator._time_scan_variants(
        lambda *_args: _base_chart(),
        _base_chart(),
        base_signature,
        _birth_payload(),
        "exact",
        "birth certificate",
        calculate_signature=same_signature,
        life_event_ledger={},
        calculate_event_period_fingerprint=period_fingerprint,
        reference_moment=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )

    assert [variant["signature"]["currentDasha"] for variant in variants] == [
        "Saturn-Venus",
        "Saturn-Sun",
    ]
    assert "currentDasha" in variants[0]["changed"]


def test_rectified_place_candidate_ignored_for_precise_place() -> None:
    service = ChartRectificationService()
    state = {
        "selectedCandidateId": "B",
        "candidates": [
            {"candidateId": "A", "isBase": True, "members": []},
            {
                "candidateId": "B",
                "isBase": False,
                "members": [
                    {
                        "axis": "place",
                        "coordinates": {"lat": 31.2, "lon": 121.5},
                    }
                ],
            },
        ],
    }

    rectified = service.rectified_birth_input(
        state,
        {
            "time": {"date": "1990-01-01", "reported": "08:30", "precision": "exact"},
            "place": {
                "reported": "上海市第一妇婴保健院东院 | lat=31.19174, lon=121.54581, source=agent, accuracy=poi",
                "accuracy": "poi",
                "radiusKm": 0.3,
            },
        },
        {"subject": {"gender": "女", "relationship": "单身"}},
    )

    assert rectified is None


def test_core_batch_prompts_enforce_input_confidence_contract() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)

    batches = runtime._core_batches("开始分析", "zh")
    prompts = [str(batch["prompt"]) for batch in batches]

    assert [batch["id"] for batch in batches] == ["vedicdust_consultation"]
    consultation_prompt = prompts[0]
    assert "judgement_context.json" in consultation_prompt
    assert "claim_graph.json" in consultation_prompt
    assert "consultation_dossier.json" in consultation_prompt
    assert "Use only the listed typed contracts" in consultation_prompt


def test_reader_prompt_cannot_select_birth_time_candidates() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)

    prompt = runtime._reader_prompt("继续验前事", "zh")

    assert "status is not_required" in prompt
    assert (
        "candidate ranking, holdout evaluation, and chart recalculation are backend-owned" in prompt
    )
    assert "Do not emit candidate IDs" in prompt
    assert "cannot select a birth time" in prompt
    assert "user-answerable lived-experience question" in prompt
    assert "Stop analysis as soon as" in prompt
    assert "For a minor" in prompt


def test_reader_readiness_rejects_rectification_candidate_state() -> None:
    runtime = cast(Any, SkillRuntime.__new__(SkillRuntime))
    runtime.workspace = SimpleNamespace(
        read_artifact_text=lambda _session_id, path: (
            json.dumps({"status": "underdetermined"})
            if path == "chart_rectification_state.json"
            else None
        )
    )

    with pytest.raises(ValueError, match="backend-owned"):
        runtime._assert_reader_readiness("session")


def test_reader_readiness_accepts_scan_stable_state() -> None:
    runtime = cast(Any, SkillRuntime.__new__(SkillRuntime))
    runtime.workspace = SimpleNamespace(
        read_artifact_text=lambda _session_id, path: (
            json.dumps({"status": "not_required"})
            if path == "chart_rectification_state.json"
            else None
        )
    )

    runtime._assert_reader_readiness("session")


def test_reader_artifact_validation_rejects_unexpected_artifacts() -> None:
    runtime = cast(Any, SkillRuntime.__new__(SkillRuntime))
    runtime.workspace = SimpleNamespace(read_artifacts=lambda _session_id: [])
    runtime.rectification = ChartRectificationService()

    with pytest.raises(ValueError, match="unexpected artifact"):
        runtime._validate_skill_artifacts(
            "session",
            "vedic-reader",
            {
                "artifacts": [
                    {"path": "reader_prevalidation.md", "content": "**1.** ok"},
                    {"path": "prevalidation_result.json", "content": "{}"},
                ]
            },
        )


def test_reader_artifact_validation_rejects_missing_candidate_field_lines() -> None:
    service = ChartRectificationService()
    state = service.initial_state(
        {"time": {"window": {}}, "place": {"radiusKm": 25, "accuracy": "city"}},
        {
            "summary": {"riskLevel": "high", "changedFields": ["d9Lagna"]},
            "reportReadiness": {"mode": "rectification_required"},
            "candidateGroups": [
                {"candidateId": "A", "isBase": True, "members": []},
                {"candidateId": "B", "isBase": False, "members": []},
            ],
        },
    )
    runtime = cast(Any, SkillRuntime.__new__(SkillRuntime))
    runtime.workspace = SimpleNamespace(
        read_artifacts=lambda _session_id: [
            SimpleNamespace(path="chart_rectification_state.json", content=json.dumps(state))
        ]
    )
    runtime.rectification = service

    with pytest.raises(ValueError, match="output failed validation"):
        runtime._validate_skill_artifacts(
            "session",
            "vedic-reader",
            {
                "artifacts": [
                    {
                        "path": "reader_prevalidation.md",
                        "content": """
**1.** Candidate B timing anchor.

> Derivation: test
> Candidate: B
""",
                    }
                ]
            },
        )


def test_reader_run_retries_once_after_output_contract_rejection() -> None:
    invalid = json.dumps(
        {
            "chatMessage": "retry",
            "artifacts": [
                {
                    "path": "reader_prevalidation.md",
                    "content": "**1.** Saturn in the 7th house indicates pressure.\n\n> Derivation: test",
                }
            ],
        }
    )
    valid_content = """
**1.** Did you move once between 2018 and 2020?

> Derivation: test

**2.** Did your education have one clear interruption?

> Derivation: test

**3.** Did your family make one major financial adjustment before 2015?

> Derivation: test
"""
    valid = json.dumps(
        {
            "chatMessage": "ready",
            "artifacts": [{"path": "reader_prevalidation.md", "content": valid_content}],
        }
    )

    class FakeAgentRuntime:
        def __init__(self) -> None:
            self.prompts: list[str] = []
            self.kwargs: list[dict[str, object]] = []

        async def run_skill_prompt_task(self, _task: str, prompt: str, **kwargs: object):
            self.prompts.append(prompt)
            self.kwargs.append(kwargs)
            if len(self.prompts) == 1:
                raise RuntimeError("API Error: Connection closed mid-response.")
            return SimpleNamespace(raw_text=[invalid, valid][len(self.prompts) - 2])

    class FakeWorkspace:
        def __init__(self) -> None:
            self.artifacts: list[SkillArtifact] = []
            self.files: dict[str, str] = {}

        def require_session_dir(self, _session_id: str) -> None:
            return None

        def read_artifacts(self, _session_id: str) -> list[SkillArtifact]:
            return self.artifacts

        def read_artifact_text(self, _session_id: str, path: str) -> str | None:
            return self.files.get(path)

        def write_artifact(self, _session_id: str, path: str, content: str) -> None:
            self.files[path] = content
            if path.startswith("."):
                return
            self.artifacts = [
                SkillArtifact(
                    path=path,
                    title=path,
                    content=content,
                    updatedAt="2026-07-29T00:00:00Z",
                )
            ]

        def mark_artifact_checkpoint(self, *_args: object, **_kwargs: object) -> None:
            return None

    runtime = cast(Any, SkillRuntime.__new__(SkillRuntime))
    runtime.agent_runtime = FakeAgentRuntime()
    runtime.workspace = FakeWorkspace()
    runtime.rectification = ChartRectificationService()
    runtime._artifact_prompt_for = lambda _input: "base prompt"
    runtime._write_prevalidation_result = lambda *_args, **_kwargs: None

    async def no_sync(*_args: object, **_kwargs: object) -> None:
        return None

    runtime._sync_metadata = no_sync

    response = asyncio.run(
        runtime.run_skill(
            SkillRunInput(
                sessionId="session",
                skill="vedic-reader",
                userMessage="start",
                locale="en",
            )
        )
    )

    assert response.chat_message == "ready"
    assert len(runtime.agent_runtime.prompts) == 3
    assert all(call["allow_file_tools"] is False for call in runtime.agent_runtime.kwargs)
    assert runtime.agent_runtime.prompts[1] == "base prompt"
    assert "previous artifact was rejected" in runtime.agent_runtime.prompts[2]
    assert runtime.workspace.artifacts[0].content.strip() == valid_content.strip()
    trace = json.loads(runtime.workspace.files[".runtime/agent-runs/skill/vedic-reader.json"])
    execution = trace["executions"][0]
    assert execution["attemptCount"] == 3
    assert execution["retryCount"] == 2
    assert execution["finalStatus"] == "accepted"
    assert [attempt["status"] for attempt in execution["attempts"]] == [
        "agent_failed",
        "contract_rejected",
        "accepted",
    ]
    assert execution["attempts"][0]["retryable"] is True
    assert execution["attempts"][0]["willRetry"] is True


def test_life_event_ledger_parses_dated_major_events() -> None:
    ledger = parse_life_event_ledger(
        "2018年10月 结婚\n2021年 搬到上海\n2023 major job change\n2025年 生子"
    )

    events = ledger["events"]

    assert ledger["eventCollectionRequired"] is False
    assert [event["category"] for event in events] == [
        "marriage",
        "relocation",
        "career",
        "child",
    ]
    assert events[0]["date"] == "2018-10"
    assert events[0]["rectificationRules"]["vargas"] == ["D9"]
    assert events[2]["rectificationRules"]["fields"] == [
        "d10Lagna",
        "d10Structure",
        "currentDasha",
    ]
    assert events[3]["rectificationRules"]["fields"][0] == "d7Lagna"


def test_life_event_ledger_preserves_day_precision() -> None:
    ledger = parse_life_event_ledger("2018年10月3日 结婚\n2021-04-12 搬家\n2023/06/08 跳槽")

    assert [event["date"] for event in ledger["events"]] == [
        "2018-10-03",
        "2021-04-12",
        "2023-06-08",
    ]
    assert all(event["datePrecision"] == "day" for event in ledger["events"])


def test_unmapped_event_cannot_become_rectification_holdout() -> None:
    ledger = parse_life_event_ledger(
        "2018年10月 结婚\n2020年6月 跳槽\n2022年3月 搬家\n2024年9月 获得奖项"
    )

    assert ledger["eligibleEventCount"] == 3
    assert ledger["eventCollectionRequired"] is False
    assert ledger["events"][2]["role"] == "holdout"
    assert ledger["events"][3]["category"] == "unknown"
    assert ledger["events"][3]["role"] == "context_only"


def test_rectification_caps_correlated_matches_and_localizes_event_time(monkeypatch) -> None:
    observed_transit_times: list[datetime] = []

    def fake_dasha(*args, **kwargs):
        return [
            {"mahadasha": "Venus", "antardasha": "Mars", "pratyantardasha": "Moon"}
            for _ in args[-1]
        ]

    def fake_transits(lagna_index, moon_index, *, as_of):
        observed_transit_times.append(as_of)
        return {"double_transit_houses": []}

    monkeypatch.setattr("app.calculator.dasha_pyjhora.calculate_dasha_lords_at", fake_dasha)
    monkeypatch.setattr("app.calculator.engine.calc_transits", fake_transits)
    ledger = parse_life_event_ledger("2018年10月 结婚")

    result = score_candidate_events(
        candidate_id="candidate-a",
        signature={
            "lagnaSign": "Aries",
            "planetSignIndices": {"Venus": 6, "Mars": 0, "Moon": 0},
            "d9Lagna": "Taurus",
            "vargaPlanetSignIndices": {"D9": {"Venus": 7, "Mars": 0, "Moon": 0}},
        },
        representative_moment=datetime(1990, 1, 1, 8, 30),
        latitude=31.2304,
        longitude=121.4737,
        timezone_id="Asia/Shanghai",
        ledger=ledger,
    )

    score = result["evidenceScores"][0]
    # Each Dasha level counts once across correlated dimensions. Venus MD,
    # Mars AD, Moon PD, and the D9 domain structure all activate the event map.
    assert score["supportScore"] == 0.46
    assert score["contradictionScore"] == 0.0
    assert score["score"] == 0.46
    md_observation = next(
        item for item in score["observations"] if item["observationId"].endswith("md.activation")
    )
    assert md_observation["details"]["matchedDimensions"] == ["karaka", "occupant", "lord"]
    assert any(
        item["observationId"].endswith("double_transit.activation_not_observed")
        and item["outcome"] == "missing"
        for item in score["observations"]
    )
    assert any(item["outcome"] == "missing" for item in score["observations"])
    assert observed_transit_times == [
        datetime(2018, 10, 1, 4, tzinfo=timezone.utc),
        datetime(2018, 10, 15, 4, tzinfo=timezone.utc),
        datetime(2018, 10, 31, 4, tzinfo=timezone.utc),
    ]
    assert result["scoringPolicy"] == RECTIFICATION_SCORING_POLICY_ID
    assert score["ruleIds"] == [RECTIFICATION_RULE_ID]
    assert score["sourceIds"] == [
        "lineage.pvr-integrated-approach-2000-2010",
        "product.vedicdust-consultation-standard-1",
    ]
    assert score["eventMappingId"] == RECTIFICATION_EVENT_MAPPING_ID


def test_rectification_dasha_activation_includes_declared_graha_drishti(monkeypatch) -> None:
    def fake_dasha(*args, **kwargs):
        return [
            {"mahadasha": "Mars", "antardasha": "Mars", "pratyantardasha": "Mars"} for _ in args[-1]
        ]

    monkeypatch.setattr("app.calculator.dasha_pyjhora.calculate_dasha_lords_at", fake_dasha)
    monkeypatch.setattr(
        "app.calculator.engine.calc_transits",
        lambda lagna_index, moon_index, *, as_of: {"double_transit_houses": []},
    )

    score = score_candidate_events(
        candidate_id="candidate-mars-drishti",
        signature={
            "lagnaSign": "Aries",
            # Mars in H4 casts its seventh graha drishti to career anchor H10.
            "planetSignIndices": {"Mars": 3, "Moon": 0},
            "d10Lagna": "Aries",
            "vargaPlanetSignIndices": {"D10": {"Mars": 0}},
        },
        representative_moment=datetime(1990, 1, 1, 8, 30),
        latitude=31.2304,
        longitude=121.4737,
        timezone_id="Asia/Shanghai",
        ledger=parse_life_event_ledger("2018年10月 跳槽"),
    )["evidenceScores"][0]

    md_observation = next(
        item for item in score["observations"] if item["observationId"].endswith("md.activation")
    )
    assert md_observation["details"]["matchedDimensions"] == ["graha_drishti"]
    assert md_observation["details"]["aspectedRelevantHouses"] == [10, 11]
    assert score["supportScore"] == pytest.approx(
        sum(RECTIFICATION_SCORING_POLICY.dasha_level_weights.values())
    )


def test_rectification_dasha_uses_candidate_local_civil_time(monkeypatch) -> None:
    observed_birth_args: list[tuple[object, ...]] = []

    def fake_dasha(*args, **kwargs):
        observed_birth_args.append(args[:7])
        return [
            {"mahadasha": "Mars", "antardasha": "Moon", "pratyantardasha": "Ketu"} for _ in args[-1]
        ]

    monkeypatch.setattr("app.calculator.dasha_pyjhora.calculate_dasha_lords_at", fake_dasha)
    monkeypatch.setattr(
        "app.calculator.engine.calc_transits",
        lambda lagna_index, moon_index, *, as_of: {"double_transit_houses": []},
    )

    score_candidate_events(
        candidate_id="candidate-new-york",
        signature={
            "lagnaSign": "Aries",
            "planetSignIndices": {"Mars": 2, "Moon": 3, "Ketu": 5},
            "d9Lagna": "Aries",
            "vargaPlanetSignIndices": {"D9": {"Mars": 2, "Moon": 3, "Ketu": 5}},
        },
        representative_moment=datetime(1990, 1, 2, 1, 30, tzinfo=timezone.utc),
        latitude=40.7128,
        longitude=-74.006,
        timezone_id="America/New_York",
        ledger=parse_life_event_ledger("2018年10月 结婚"),
    )

    assert observed_birth_args == [
        (1990, 1, 1, 20, 30, 40.7128, -74.006),
    ]


@pytest.mark.parametrize("event_text", ["2018年10月 结婚", "2018年10月15日 结婚"])
def test_rectification_withholds_dasha_level_that_changes_inside_reported_interval(
    monkeypatch, event_text: str
) -> None:
    def fake_dasha(*args, **kwargs):
        return [
            {"mahadasha": lord, "antardasha": "Jupiter", "pratyantardasha": "Moon"}
            for lord in ("Venus", "Mars", "Venus")
        ]

    def fake_transits(lagna_index, moon_index, *, as_of):
        return {"double_transit_houses": []}

    monkeypatch.setattr("app.calculator.dasha_pyjhora.calculate_dasha_lords_at", fake_dasha)
    monkeypatch.setattr("app.calculator.engine.calc_transits", fake_transits)
    result = score_candidate_events(
        candidate_id="candidate-a",
        signature={
            "lagnaSign": "Aries",
            "planetSignIndices": {
                "Venus": 6,
                "Mars": 0,
                "Jupiter": 0,
                "Moon": 0,
            },
            "d9Lagna": "Taurus",
            "vargaPlanetSignIndices": {"D9": {"Venus": 7, "Mars": 0, "Jupiter": 0, "Moon": 0}},
        },
        representative_moment=datetime(1990, 1, 1, 8, 30),
        latitude=31.2304,
        longitude=121.4737,
        timezone_id="Asia/Shanghai",
        ledger=parse_life_event_ledger(event_text),
    )

    score = result["evidenceScores"][0]
    md_missing = next(
        item for item in score["observations"] if item["observationId"].endswith("md.unavailable")
    )
    assert md_missing["details"] == {
        "level": "md",
        "reason": "period_changes_within_reported_date_range",
        "sampledLords": ["Mars", "Venus"],
    }
    assert not any(
        item["observationId"].endswith(("md.activation", "md.activation_not_observed"))
        for item in score["observations"]
    )


def test_year_precision_cannot_create_transit_evidence(monkeypatch) -> None:
    def fake_dasha(*args, **kwargs):
        return [
            {"mahadasha": "Venus", "antardasha": "Mars", "pratyantardasha": "Moon"}
            for _ in args[-1]
        ]

    def fake_transits(lagna_index, moon_index, *, as_of):
        return {"double_transit_houses": [7]}

    monkeypatch.setattr("app.calculator.dasha_pyjhora.calculate_dasha_lords_at", fake_dasha)
    monkeypatch.setattr("app.calculator.engine.calc_transits", fake_transits)
    result = score_candidate_events(
        candidate_id="candidate-a",
        signature={
            "lagnaSign": "Aries",
            "planetSignIndices": {"Venus": 6, "Mars": 0, "Moon": 0},
            "d9Lagna": "Taurus",
            "vargaPlanetSignIndices": {"D9": {"Venus": 7, "Mars": 0, "Moon": 0}},
        },
        representative_moment=datetime(1990, 1, 1, 8, 30),
        latitude=31.2304,
        longitude=121.4737,
        timezone_id="Asia/Shanghai",
        ledger=parse_life_event_ledger("2018年 结婚"),
    )

    observations = result["evidenceScores"][0]["observations"]
    assert not any(
        item["observationId"].endswith("double_transit.activation") for item in observations
    )
    assert any(
        item["details"].get("reason") == "reported_year_too_broad_for_transit_evidence"
        for item in observations
    )


def test_month_precision_requires_stable_transit_activation(monkeypatch) -> None:
    def fake_dasha(*args, **kwargs):
        return [
            {"mahadasha": "Mars", "antardasha": "Moon", "pratyantardasha": "Ketu"} for _ in args[-1]
        ]

    transit_calls = 0

    def unstable_transits(lagna_index, moon_index, *, as_of):
        nonlocal transit_calls
        transit_calls += 1
        return {"double_transit_houses": [7] if transit_calls != 2 else []}

    monkeypatch.setattr("app.calculator.dasha_pyjhora.calculate_dasha_lords_at", fake_dasha)
    monkeypatch.setattr("app.calculator.engine.calc_transits", unstable_transits)
    kwargs = {
        "candidate_id": "candidate-a",
        "signature": {
            "lagnaSign": "Aries",
            "planetSignIndices": {"Mars": 2, "Moon": 3, "Ketu": 5},
            "d9Lagna": "Aries",
            "vargaPlanetSignIndices": {"D9": {"Mars": 2, "Moon": 3, "Ketu": 5}},
        },
        "representative_moment": datetime(1990, 1, 1, 8, 30),
        "latitude": 31.2304,
        "longitude": 121.4737,
        "timezone_id": "Asia/Shanghai",
        "ledger": parse_life_event_ledger("2018年10月 结婚"),
    }

    unstable = score_candidate_events(**kwargs)["evidenceScores"][0]
    assert unstable["supportScore"] == 0.0
    unstable_observation = next(
        item
        for item in unstable["observations"]
        if item["observationId"].endswith("double_transit.activation_not_observed")
    )
    assert unstable_observation["details"] == {
        "reason": "activation_not_stable_across_reported_interval",
        "observedHouses": [7],
        "stableHouses": [],
    }

    monkeypatch.setattr(
        "app.calculator.engine.calc_transits",
        lambda lagna_index, moon_index, *, as_of: {"double_transit_houses": [7]},
    )
    stable = score_candidate_events(**kwargs)["evidenceScores"][0]
    assert stable["supportScore"] == RECTIFICATION_SCORING_POLICY.double_transit_support_weight
    stable_observation = next(
        item
        for item in stable["observations"]
        if item["observationId"].endswith("double_transit.activation")
    )
    assert stable_observation["details"] == {
        "activatedHouses": [7],
        "stableAcrossReportedInterval": True,
        "sampleCount": 3,
    }


def test_rectification_rejects_incomplete_dasha_hierarchy(monkeypatch) -> None:
    def fake_dasha(*args, **kwargs):
        return [
            {"mahadasha": None, "antardasha": "Venus", "pratyantardasha": None} for _ in args[-1]
        ]

    def fake_transits(lagna_index, moon_index, *, as_of):
        return {"double_transit_houses": []}

    monkeypatch.setattr("app.calculator.dasha_pyjhora.calculate_dasha_lords_at", fake_dasha)
    monkeypatch.setattr("app.calculator.engine.calc_transits", fake_transits)

    with pytest.raises(RuntimeError, match="incomplete hierarchy"):
        score_candidate_events(
            candidate_id="candidate-a",
            signature={
                "lagnaSign": "Aries",
                "planetSignIndices": {"Venus": 6, "Moon": 0},
                "d9Lagna": "Taurus",
                "vargaPlanetSignIndices": {"D9": {"Venus": 7}},
            },
            representative_moment=datetime(1990, 1, 1, 8, 30),
            latitude=31.2304,
            longitude=121.4737,
            timezone_id="Asia/Shanghai",
            ledger=parse_life_event_ledger("2018年10月 结婚"),
        )


@pytest.mark.parametrize(
    ("signature", "message"),
    [
        (
            {
                "lagnaSign": "Unknown",
                "planetSignIndices": {"Venus": 6, "Moon": 0},
                "d9Lagna": "Taurus",
                "vargaPlanetSignIndices": {"D9": {"Venus": 7, "Moon": 0}},
            },
            "valid D1 Lagna",
        ),
        (
            {
                "lagnaSign": "Aries",
                "planetSignIndices": {"Venus": 6},
                "d9Lagna": "Taurus",
                "vargaPlanetSignIndices": {"D9": {"Venus": 7}},
            },
            "D1 sign index for Moon",
        ),
        (
            {
                "lagnaSign": "Aries",
                "planetSignIndices": {"Venus": 6, "Moon": 0},
                "d9Lagna": "Taurus",
                "vargaPlanetSignIndices": {"D9": {"Moon": 0}},
            },
            "D9 sign index for Venus",
        ),
    ],
)
def test_rectification_rejects_incomplete_candidate_signatures(
    monkeypatch, signature: dict[str, object], message: str
) -> None:
    monkeypatch.setattr(
        "app.calculator.dasha_pyjhora.calculate_dasha_lords_at",
        lambda *args, **kwargs: [
            {"mahadasha": "Venus", "antardasha": "Moon", "pratyantardasha": "Moon"}
            for _ in args[-1]
        ],
    )

    with pytest.raises(RuntimeError, match=message):
        score_candidate_events(
            candidate_id="candidate-incomplete",
            signature=signature,
            representative_moment=datetime(1990, 1, 1, 8, 30),
            latitude=31.2304,
            longitude=121.4737,
            timezone_id="Asia/Shanghai",
            ledger=parse_life_event_ledger("2018年10月 结婚"),
        )


def test_rectification_varga_score_uses_domain_house_structure(monkeypatch) -> None:
    def fake_dasha(*args, **kwargs):
        return [
            {"mahadasha": "Mars", "antardasha": "Venus", "pratyantardasha": "Jupiter"}
            for _ in args[-1]
        ]

    def fake_transits(lagna_index, moon_index, *, as_of):
        return {"double_transit_houses": []}

    monkeypatch.setattr("app.calculator.dasha_pyjhora.calculate_dasha_lords_at", fake_dasha)
    monkeypatch.setattr("app.calculator.engine.calc_transits", fake_transits)
    ledger = parse_life_event_ledger("2018年10月 跳槽")
    base_signature = {
        "lagnaSign": "Aries",
        "planetSignIndices": {"Mars": 0, "Venus": 0, "Jupiter": 0, "Moon": 0},
        "d10Lagna": "Aries",
    }

    activated = score_candidate_events(
        candidate_id="candidate-a",
        signature={
            **base_signature,
            "vargaPlanetSignIndices": {"D10": {"Mars": 9, "Venus": 0, "Jupiter": 0}},
        },
        representative_moment=datetime(1990, 1, 1, 8, 30),
        latitude=31.2304,
        longitude=121.4737,
        timezone_id="Asia/Shanghai",
        ledger=ledger,
    )["evidenceScores"][0]
    inactive = score_candidate_events(
        candidate_id="candidate-b",
        signature={
            **base_signature,
            "vargaPlanetSignIndices": {"D10": {"Mars": 0, "Venus": 0, "Jupiter": 0}},
        },
        representative_moment=datetime(1990, 1, 1, 8, 30),
        latitude=31.2304,
        longitude=121.4737,
        timezone_id="Asia/Shanghai",
        ledger=ledger,
    )["evidenceScores"][0]

    assert activated["score"] - inactive["score"] == pytest.approx(0.08)
    assert inactive["contradictionScore"] == 0.0
    assert any(
        item["observationId"].endswith("d10.activation_not_observed")
        and item["outcome"] == "missing"
        for item in inactive["observations"]
    )
    varga_observation = next(
        item
        for item in activated["observations"]
        if item["observationId"].endswith("d10.domain_activation")
    )
    assert varga_observation["details"]["activatedPeriodLords"] == {"Mars": ["occupies_H10"]}


def test_birth_input_context_includes_life_event_ledger() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    place = ResolvedPlace(
        label="Shanghai, Shanghai, China",
        lat=31.2304,
        lon=121.4737,
        timezone="Asia/Shanghai",
        source="geonames-local",
        accuracy="city",
        radius_km=25.0,
        confidence="medium",
    )
    intake = BirthInput(
        birthDate="1990-01-01",
        birthTime="08:30",
        birthPlace="Shanghai, Shanghai, China",
        birthTimePrecision="approximate",
        gender="女",
        relationship="已婚",
        timeSource="family memory",
        lifeEvents="2018-10 结婚\n2023 跳槽",
        locale="zh",
    )
    payload = {**_birth_payload(), "life_events": intake.life_events}

    context = calculator._birth_input_context(payload, intake, place)

    assert context["lifeEvents"]["schemaVersion"] == "life-event-ledger/v1"
    assert context["lifeEvents"]["events"][0]["category"] == "marriage"
    assert context["lifeEvents"]["events"][1]["category"] == "career"


def test_time_source_sets_a_conservative_minimum_radius_without_directional_shift() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    payload = _birth_payload()

    documented = calculator._time_window(payload, "exact", "出生证/医院记录")
    family_clear = calculator._time_window(payload, "exact", "家人明确记忆")
    family_approximate = calculator._time_window(payload, "approximate", "家人大概回忆")

    assert documented["radiusMinutes"] == 2
    assert family_clear["radiusMinutes"] == 10
    assert family_approximate["radiusMinutes"] == 30
    assert family_clear["sourcePolicy"]["directionalBiasApplied"] is False
    assert family_approximate["start"] == "1990-01-01 08:00"
    assert family_approximate["end"] == "1990-01-01 09:00"


def test_rectification_plan_uses_life_event_focus() -> None:
    service = ChartRectificationService()
    ledger = parse_life_event_ledger("2018年10月 结婚\n2021年 搬家\n2023年 跳槽")
    state = service.initial_state(
        {
            "time": {"window": {"start": "1990-01-01 08:15", "end": "1990-01-01 08:45"}},
            "place": {"radiusKm": 25, "accuracy": "city"},
            "lifeEvents": ledger,
        },
        {
            "summary": {"riskLevel": "high", "changedFields": ["d9Lagna", "d10Lagna"]},
            "reportReadiness": {"mode": "rectification_required"},
            "candidateGroups": [
                {
                    "candidateId": "A",
                    "isBase": True,
                    "changedFromBase": [],
                    "members": [{"axis": "time", "datetime": "1990-01-01 08:30"}],
                },
                {
                    "candidateId": "B",
                    "isBase": False,
                    "changedFromBase": ["d9Lagna"],
                    "members": [{"axis": "time", "datetime": "1990-01-01 08:45"}],
                },
                {
                    "candidateId": "C",
                    "isBase": False,
                    "changedFromBase": ["d10Lagna"],
                    "members": [{"axis": "time", "datetime": "1990-01-01 08:15"}],
                },
            ],
        },
    )

    plan = state["rectificationPlan"]

    assert state["lifeEventLedger"]["events"][0]["category"] == "marriage"
    holdout = next(
        event for event in state["lifeEventLedger"]["events"] if event["role"] == "holdout"
    )
    assert holdout["category"] == "marriage"
    assert state["lifeEventLedger"]["holdoutPolicyId"].startswith(
        "vedicdust-rectification-holdout/"
    )
    assert plan["eventCollectionRequired"] is False
    assert [focus["category"] for focus in plan["lifeEventFocus"]] == [
        "relocation",
        "career",
    ]
    assert plan["lifeEventFocus"][1]["fieldOverlap"] == ["d10Lagna"]
    assert all(focus["eventId"] != holdout["eventId"] for focus in plan["lifeEventFocus"])


def test_candidate_partition_fingerprint_excludes_reserved_holdout(monkeypatch) -> None:
    observed_moments: list[list[datetime]] = []

    def fake_dasha(*_args: object, **kwargs: object) -> list[dict[str, str]]:
        moments = list(kwargs.get("moments") or _args[8])
        observed_moments.append(moments)
        return [
            {
                "mahadasha": f"MD-{moment.year}",
                "antardasha": f"AD-{moment.month}",
                "pratyantardasha": f"PD-{moment.day}",
            }
            for moment in moments
        ]

    monkeypatch.setattr("app.calculator.dasha_pyjhora.calculate_dasha_lords_at", fake_dasha)
    ledger = parse_life_event_ledger("2018年10月 结婚\n2021年6月 搬家\n2023年5月 跳槽")
    calibration_only = {
        **ledger,
        "events": [event for event in ledger["events"] if event["role"] == "calibration"],
    }
    kwargs = {
        "birth_moment": datetime(1990, 1, 1, 8, 30),
        "latitude": 31.2304,
        "longitude": 121.4737,
        "timezone_id": "Asia/Shanghai",
    }

    complete_ledger_result = candidate_event_period_fingerprint(ledger=ledger, **kwargs)
    calibration_result = candidate_event_period_fingerprint(ledger=calibration_only, **kwargs)

    assert complete_ledger_result == calibration_result
    assert all(moment.year != 2023 for call in observed_moments for moment in call)


def test_equivalence_classes_ignore_reserved_holdout_scores() -> None:
    signature = {"lagnaSign": "Aries", "moonSign": "Taurus"}
    calibration = {
        "eventId": "evt-calibration",
        "role": "calibration",
        "score": 0.4,
        "supportScore": 0.4,
        "contradictionScore": 0.0,
        "observations": [],
    }
    candidates = [
        {
            "candidateId": "A",
            "signature": signature,
            "evidenceScores": [
                calibration,
                {**calibration, "eventId": "evt-private", "role": "holdout", "score": -1.0},
            ],
        },
        {
            "candidateId": "B",
            "signature": signature,
            "evidenceScores": [
                calibration,
                {**calibration, "eventId": "evt-private", "role": "holdout", "score": 1.0},
            ],
        },
    ]

    VedicCalculator._assign_equivalence_classes(candidates)

    assert candidates[0]["equivalenceClassId"] == candidates[1]["equivalenceClassId"]
    assert candidates[0]["equivalentCandidateIds"] == ["A", "B"]


def test_prevalidation_contract_rejects_visible_astrology_and_non_questions() -> None:
    service = ChartRectificationService()

    errors = service.validate_prevalidation_contract(
        {},
        """
**1.** Saturn in the 7th house indicates relationship pressure.

> Derivation: Saturn=L7

**2.** 木星落入九宫，学业应该不低。

> 推导：Jupiter=L9

**3.** Did you move once between 2018 and 2020?

> Derivation: L4 activated
""",
        enforce_user_facing_quality=True,
    )

    assert any("direct question" in error for error in errors)
    assert any("astrology or candidate terminology" in error for error in errors)
