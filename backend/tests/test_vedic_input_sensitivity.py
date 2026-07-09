from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import json
import pytest

from app.services.place_service import ResolvedPlace
from app.services.chart_rectification import ChartRectificationService
from app.services.skill_runtime import SkillRuntime
from app.services.vedic_calculator import VedicCalculator


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
    structured_data_json = json.dumps(
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
        structured_data_json,
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
