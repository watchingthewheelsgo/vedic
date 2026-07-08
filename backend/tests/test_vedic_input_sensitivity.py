from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import json
import pytest

from app.services.place_service import ResolvedPlace
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
