from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import json
import pytest

from app.schemas import BirthInput
from app.services.place_service import ResolvedPlace
from app.services.chart_rectification import ChartRectificationService
from app.services.life_event_rectification import parse_life_event_ledger
from app.services.skill_runtime import SkillRuntime
from app.services.vedic_calculator import VedicCalculator


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
        "d9": {"Lagna": ("Libra", 0)},
        "d10": {"Lagna": ("Capricorn", 0)},
        "d4": {"Lagna": ("Cancer", 0)},
        "d5": {"Lagna": ("Leo", 0)},
        "divisional_charts": divisional_charts,
    }


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
    assert summary["divisionalConfidence"]["D60"]["recommendedUse"] == "final_confirmation_only"
    assert summary["advancedVargaPolicy"]["finalConfirmationOnly"] == ["D60"]
    assert summary["rectificationAxes"] == ["time"]
    assert summary["placeRectificationAllowed"] is False


def test_chart_signature_tracks_all_standard_divisional_lagnas() -> None:
    calculator = VedicCalculator(SimpleNamespace(), SimpleNamespace())
    signature = calculator._chart_signature(_base_chart())

    for factor in [2, 3, 4, 5, 7, 9, 10, 12, 16, 20, 24, 27, 30, 60]:
        assert signature[f"d{factor}Lagna"]
    assert signature["d7Lagna"] == "Virgo"
    assert signature["d60Lagna"] == "Leo"


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
        lambda *_args: chart,
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
        lambda *_args: chart,
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
    assert "City/district coordinates are approximate" in scan["rectificationGuardrails"]["place"]
    assert "place" in member_axes


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


def test_core_readiness_requires_prevalidation_result(tmp_path) -> None:
    runtime = runtime_with_workspace(tmp_path)

    with pytest.raises(ValueError, match="prevalidation_result.json"):
        runtime.assert_core_readiness("session")


def test_core_readiness_blocks_disallowed_report(tmp_path) -> None:
    runtime = runtime_with_workspace(tmp_path)
    session_dir = runtime.workspace.require_session_dir("session")
    (session_dir / "prevalidation_result.json").write_text(
        json.dumps(
            {
                "decision": {
                    "reportAllowed": False,
                    "reason": "needs rectification",
                    "nextStep": "candidate_confirmation_or_rectifier",
                }
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
                "decision": {
                    "reportAllowed": True,
                    "reportScope": "guarded_full_report",
                }
            }
        ),
        encoding="utf-8",
    )

    runtime.assert_core_readiness("session")


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
    assert decision["nextStep"] == "candidate_confirmation_or_rectifier"
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
    assert at_threshold["reportAllowed"] is True
    assert at_threshold["nextStep"] == "report_allowed_with_limits"


def test_prevalidation_result_uses_sensitivity_scan_gate() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)
    birth_chart_facts_json = json.dumps(
        {
            "subject": {
                "birthDate": "1990-01-01",
                "birthTime": "08:30",
                "birthPlace": "Shanghai",
                "timePrecision": "约略时间",
                "timeSource": "family memory",
            },
            "sensitivityScan": {
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
        birth_chart_facts_json,
    )

    score = cast(dict[str, Any], result["score"])
    decision = cast(dict[str, Any], result["decision"])
    llm_contract = cast(dict[str, Any], decision["llmContract"])

    assert score["hitRate"] == 1.0
    assert decision["reportAllowed"] is False
    assert decision["inputRiskLevel"] == "high"
    assert llm_contract["mustNotUseAsPrimaryEvidence"] == [
        "d9Lagna",
        "D9",
    ]


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
    }
    sensitivity = {
        "summary": {"riskLevel": "high", "changedFields": ["d9Lagna"]},
        "reportReadiness": {"mode": "rectification_required"},
        "candidateGroups": [
            {
                "candidateId": "A",
                "isBase": True,
                "signature": {"d9Lagna": "Libra"},
                "changedFromBase": [],
                "members": [{"axis": "time", "label": "base", "datetime": "1990-01-01 08:30"}],
            },
            {
                "candidateId": "B",
                "isBase": False,
                "signature": {"d9Lagna": "Scorpio"},
                "changedFromBase": ["d9Lagna"],
                "members": [{"axis": "time", "label": "+15m", "datetime": "1990-01-01 08:45"}],
            },
        ],
    }
    state = service.initial_state(birth_context, sensitivity)

    updated = service.update_from_feedback(
        state,
        """
**1.** Candidate B timing anchor.

> Derivation: test
> Candidate: B
> Field: d9Lagna

**2.** Another B timing anchor.

> Derivation: test
> Candidate: B
> Field: d9Lagna
""",
        """
#### Anchor 1
- User answer: 准 (accurate)
- Anchor text: Candidate B timing anchor.

#### Anchor 2
- User answer: 准 (accurate)
- Anchor text: Another B timing anchor.
""",
        {"score": {"hitRate": 1.0}},
    )

    assert updated["status"] == "needs_recalculation"
    assert updated["selectedCandidateId"] == "B"
    assert updated["candidateBoundAnchorCount"] == 2

    rectified = service.rectified_birth_input(
        updated,
        birth_context,
        {
            "subject": {
                "birthDate": "1990-01-01",
                "birthTime": "08:30",
                "birthPlace": "Shanghai",
                "gender": "女",
                "relationship": "单身",
            }
        },
    )

    assert rectified is not None
    assert rectified.birth_time == "08:45"
    assert rectified.birth_time_precision == "approximate"
    assert rectified.birth_place == "Shanghai, Shanghai, China"

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
    assert plan["action"] == "first_rectification_round"
    assert plan["targetCandidateIds"] == ["A", "B"]
    assert plan["discriminatingFields"] == ["d9Lagna"]
    assert plan["focusAxes"] == ["time", "place"]
    assert plan["timeWindow"]["start"] == "1990-01-01 08:25"
    assert plan["timeWindow"]["end"] == "1990-01-01 08:45"
    assert plan["requiredAnchorCount"] == 3


def test_rectification_accumulates_scores_and_narrows_next_round_window() -> None:
    service = ChartRectificationService()
    state = service.initial_state(
        {
            "time": {"window": {"start": "1990-01-01 08:15", "end": "1990-01-01 08:45"}},
            "place": {"accuracy": "city", "radiusKm": 25},
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
                    "members": [{"axis": "time", "datetime": "1990-01-01 08:40"}],
                },
                {
                    "candidateId": "C",
                    "isBase": False,
                    "changedFromBase": ["d10Lagna"],
                    "members": [{"axis": "time", "datetime": "1990-01-01 08:45"}],
                },
            ],
        },
    )

    round_one = service.update_from_feedback(
        state,
        """
**1.** Base candidate anchor.

> Derivation: test
> Candidate: A
> Field: d9Lagna

**2.** Candidate B anchor.

> Derivation: test
> Candidate: B
> Field: d9Lagna
""",
        """
#### Anchor 1
- User answer: 不准 (inaccurate)

#### Anchor 2
- User answer: 准 (accurate)
""",
        {"score": {"hitRate": 0.5}},
    )

    assert round_one["status"] == "needs_more_feedback"
    assert round_one["rectificationRound"] == 1
    assert round_one["candidateBoundAnchorCount"] == 2
    assert round_one["rectificationPlan"]["action"] == "next_rectification_round"
    assert round_one["rectificationPlan"]["targetCandidateIds"] == ["B", "C"]
    assert round_one["rectificationPlan"]["timeWindow"]["start"] == "1990-01-01 08:35"
    assert round_one["rectificationPlan"]["timeWindow"]["end"] == "1990-01-01 08:45"

    round_two = service.update_from_feedback(
        round_one,
        """
**1.** Narrow B timing anchor.

> Derivation: test
> Candidate: B
> Field: d9Lagna
""",
        """
#### Anchor 1
- User answer: 准 (accurate)
""",
        {"score": {"hitRate": 1.0}},
    )

    scores = {candidate["candidateId"]: candidate["score"] for candidate in round_two["candidates"]}

    assert scores["B"] == 2.0
    assert round_two["candidateBoundAnchorCount"] == 3
    assert round_two["feedbackAnchorCount"] == 3
    assert round_two["status"] == "needs_recalculation"
    assert round_two["selectedCandidateId"] == "B"
    assert round_two["rectificationPlan"]["action"] == "apply_candidate_recalculation"


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


def test_rectification_does_not_confirm_base_from_tied_candidate_support() -> None:
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

    updated = service.update_from_feedback(
        state,
        """
**1.** Base chart timing anchor.

> Derivation: test
> Candidate: A
> Field: d9Lagna

**2.** Candidate B timing anchor.

> Derivation: test
> Candidate: B
> Field: d9Lagna
""",
        """
#### Anchor 1
- User answer: 准 (accurate)

#### Anchor 2
- User answer: 准 (accurate)
""",
        {"score": {"hitRate": 1.0}},
    )

    decision = service.apply_prevalidation_decision(
        {"reportAllowed": False, "reportScope": "prevalidation_or_d1_only"},
        updated,
    )

    assert updated["selectedCandidateId"] is None
    assert updated["status"] == "needs_more_feedback"
    assert decision["reportAllowed"] is False


def test_rectification_does_not_confirm_base_from_one_supported_anchor() -> None:
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

    updated = service.update_from_feedback(
        state,
        """
**1.** Base chart timing anchor.

> Derivation: test
> Candidate: A
> Field: d9Lagna
""",
        """
#### Anchor 1
- User answer: 准 (accurate)
""",
        {"score": {"hitRate": 1.0}},
    )

    assert updated["selectedCandidateId"] is None
    assert updated["status"] == "needs_more_feedback"


def test_rectification_allows_single_supported_candidate_when_alternatives_are_rejected() -> None:
    service = ChartRectificationService()
    state = service.initial_state(
        {"time": {"window": {}}, "place": {"radiusKm": 25, "accuracy": "city"}},
        {
            "summary": {"riskLevel": "high", "changedFields": ["d9Lagna"]},
            "reportReadiness": {"mode": "rectification_required"},
            "candidateGroups": [
                {"candidateId": "A", "isBase": True, "members": []},
                {
                    "candidateId": "B",
                    "isBase": False,
                    "members": [{"axis": "time", "datetime": "1990-01-01 08:45"}],
                },
            ],
        },
    )

    updated = service.update_from_feedback(
        state,
        """
**1.** Base chart timing anchor.

> Derivation: test
> Candidate: A
> Field: d9Lagna

**2.** Candidate B timing anchor.

> Derivation: test
> Candidate: B
> Field: d9Lagna
""",
        """
#### Anchor 1
- User answer: 不准 (inaccurate)

#### Anchor 2
- User answer: 准 (accurate)
""",
        {"score": {"hitRate": 0.5}},
    )

    assert updated["selectedCandidateId"] == "B"
    assert updated["status"] == "needs_recalculation"


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
                    }
                ],
            },
        ],
    }

    rectified = service.rectified_birth_input(
        state,
        {
            "time": {"date": "1990-01-01", "reported": "08:30", "precision": "approximate"},
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
    assert "accuracy=coordinate" in rectified.birth_place


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


def test_rectification_requires_machine_candidate_line_for_candidate_bound_anchor() -> None:
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

    updated = service.update_from_feedback(
        state,
        """
**1.** Candidate B timing anchor.

> Derivation: test
""",
        """
#### Anchor 1
- User answer: 准 (accurate)
""",
        {"score": {"hitRate": 1.0}},
    )

    decision = service.apply_prevalidation_decision(
        {"reportAllowed": False, "reportScope": "prevalidation_or_d1_only"},
        updated,
    )

    assert updated["candidateBoundAnchorCount"] == 0
    assert updated["status"] == "needs_candidate_bound_checks"
    assert decision["reportAllowed"] is False


def test_rectification_does_not_confirm_base_from_generic_hit_rate_and_non_base_anchor() -> None:
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

    updated = service.update_from_feedback(
        state,
        """
**1.** Generic accurate anchor.

> Derivation: test

**2.** Generic accurate anchor.

> Derivation: test

**3.** Generic accurate anchor.

> Derivation: test

**4.** Generic accurate anchor.

> Derivation: test

**5.** B-specific timing anchor.

> Derivation: test
> Candidate: B
> Field: d9Lagna
""",
        """
#### Anchor 1
- User answer: 准 (accurate)
#### Anchor 2
- User answer: 准 (accurate)
#### Anchor 3
- User answer: 准 (accurate)
#### Anchor 4
- User answer: 准 (accurate)
#### Anchor 5
- User answer: 准 (accurate)
""",
        {"score": {"hitRate": 1.0}},
    )

    decision = service.apply_prevalidation_decision(
        {"reportAllowed": False, "reportScope": "prevalidation_or_d1_only"},
        updated,
    )

    candidate_scores = {
        candidate["candidateId"]: candidate["score"] for candidate in updated["candidates"]
    }

    assert updated["candidateBoundAnchorCount"] == 1
    assert updated["selectedCandidateId"] is None
    assert updated["status"] == "needs_candidate_bound_checks"
    assert candidate_scores == {"A": 0.0, "B": 1.0}
    assert decision["reportAllowed"] is False


def test_rectification_blocks_high_risk_feedback_without_candidate_bound_anchors() -> None:
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

    updated = service.update_from_feedback(
        state,
        """
**1.** Generic personality anchor.

> Derivation: test
""",
        """
#### Anchor 1
- User answer: 准 (accurate)
""",
        {"score": {"hitRate": 1.0}},
    )

    decision = service.apply_prevalidation_decision(
        {"reportAllowed": False, "reportScope": "prevalidation_or_d1_only"},
        updated,
    )

    assert updated["status"] == "needs_candidate_bound_checks"
    assert decision["reportAllowed"] is False
    assert decision["nextStep"] == "needs_candidate_bound_checks"


def test_core_batch_prompts_enforce_input_confidence_contract() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)

    batches = runtime._core_batches("开始分析", "zh")
    prompts = [str(batch["prompt"]) for batch in batches]
    audit_prompt = next(
        str(batch["prompt"]) for batch in batches if batch["id"] == "report_quality_audit"
    )

    assert prompts
    assert all("sensitivity_scan.reportReadiness.llmContract" in prompt for prompt in prompts)
    assert all("mustNotUseAsPrimaryEvidence" in prompt for prompt in prompts)
    assert all("rectification_required" in prompt for prompt in prompts)
    assert "prevalidation_result.decision.reportAllowed is false" in audit_prompt
    assert "primary conclusion anchor" in audit_prompt


def test_reader_prompt_uses_backend_rectification_plan() -> None:
    runtime = SkillRuntime.__new__(SkillRuntime)

    prompt = runtime._reader_prompt("继续验前事", "zh")

    assert "chart_rectification_state.rectificationPlan" in prompt
    assert "targetCandidateIds" in prompt
    assert "discriminatingFields" in prompt
    assert "timeWindow" in prompt
    assert "Do not invent candidate IDs" in prompt


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

    with pytest.raises(ValueError, match="candidate-bound validation"):
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
    assert events[2]["rectificationRules"]["fields"] == ["d10Lagna", "currentDasha"]
    assert events[3]["rectificationRules"]["fields"][0] == "d7Lagna"


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


def test_rectification_plan_uses_life_event_focus() -> None:
    service = ChartRectificationService()
    ledger = parse_life_event_ledger("2018年10月 结婚\n2023年 跳槽")
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
    assert plan["eventCollectionRequired"] is False
    assert [focus["category"] for focus in plan["lifeEventFocus"]] == ["marriage", "career"]
    assert plan["lifeEventFocus"][0]["fieldOverlap"] == ["d9Lagna"]


def test_reader_contract_requires_event_line_when_life_event_focus_exists() -> None:
    service = ChartRectificationService()
    ledger = parse_life_event_ledger("2018年10月 结婚\n2023年 跳槽")
    state = service.initial_state(
        {
            "time": {"window": {}},
            "place": {"radiusKm": 25, "accuracy": "city"},
            "lifeEvents": ledger,
        },
        {
            "summary": {"riskLevel": "high", "changedFields": ["d9Lagna"]},
            "reportReadiness": {"mode": "rectification_required"},
            "candidateGroups": [
                {"candidateId": "A", "isBase": True, "members": []},
                {
                    "candidateId": "B",
                    "isBase": False,
                    "changedFromBase": ["d9Lagna"],
                    "members": [],
                },
            ],
        },
    )

    errors = service.validate_prevalidation_contract(
        state,
        """
**1.** Candidate B marriage timing anchor.

> Derivation: test
> Candidate: B
> Field: d9Lagna
""",
    )

    event_id = ledger["events"][0]["eventId"]
    valid_errors = service.validate_prevalidation_contract(
        state,
        f"""
**1.** Candidate B marriage timing anchor.

> Derivation: test
> Candidate: B
> Field: d9Lagna
> Event: {event_id}
""",
    )

    assert any("Event line" in error for error in errors)
    assert valid_errors == []
