from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.services.skill_runtime import SkillRuntime
from app.schemas import BirthInput, RectificationLifeEventsInput, SkillBirthInput, SkillRunInput
from app.vedicdust.models import (
    AstronomySnapshot,
    AuditFinding,
    BirthAssertion,
    CandidateEvidenceScore,
    CandidateInterval,
    ChartAudit,
    ChartRecord,
    ClaimGraph,
    ConfidenceGrade,
    ConsultationConfidence,
    ConsultationDossier,
    ConsultationScope,
    EvidenceClass,
    EvidenceItem,
    GrahaPosition,
    InputSensitivityAssessment,
    JyotishFact,
    JudgementContext,
    JudgementFinding,
    LifeEvent,
    ReportSection,
    RectificationDecision,
    RectificationRecord,
    ReadingSession,
    RuleProvenance,
    SourceReference,
    SubjectContext,
    TimeRange,
    ValidationFixtureReference,
    ZodiacPosition,
)
from app.vedicdust.profiles import parashari_lahiri_profile
from app.vedicdust.professional_review import (
    ProfessionalReviewArtifact,
    validate_professional_review_fixture,
)
from app.vedicdust.chart_record_builder import _candidate_evidence_score, _rectification
from app.vedicdust.claims import build_claim_graph
from app.vedicdust.judgement import TOPICS, _validate_requested_topic_ids, build_judgement_context
from app.vedicdust.orchestrator import audit_chart_record
from app.vedicdust.rectification_policy import RECTIFICATION_EVENT_RULES
from app.vedicdust.reporting import (
    _rectification_validation_limitation,
    _residual_uncertainties,
    build_agent_context,
    materialize_consultation_dossier,
    render_consultation_report,
)
from app.vedicdust.source_registry import (
    load_rule_catalog,
    load_source_registry,
    load_validation_fixture_registry,
    validate_profile_source_ids,
    validate_rule_catalog_sources,
)
from app.vedicdust.sensitivity import (
    build_input_sensitivity_assessment,
    expected_fact_input_stability,
    expected_timing_input_stability,
    fact_sensitivity_dependencies,
)


def test_requested_topics_accept_only_agent_selected_ontology_ids() -> None:
    assert _validate_requested_topic_ids(["family", "home", "family"]) == {
        "family",
        "home",
    }
    assert _validate_requested_topic_ids(["原生家庭", "career and finance", "homework"]) == set()


from app.vedicdust.validation import (
    _contains_assertive_phrase,
    validate_agent_context,
    validate_chart_record_provenance,
    validate_claim_graph,
    validate_consultation_dossier,
    validate_judgement_context,
)
from app.vedicdust.varga_policy import SUPPORTED_VARGA_FACTORS, VARGA_DOMAIN_POLICIES


UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]


def test_fact_sensitivity_preserves_stable_d1_graha_when_only_lagna_changes() -> None:
    assessment = InputSensitivityAssessment(
        scanStatus="complete",
        changedFields=["lagnaSign"],
    )
    charts = cast(
        Any,
        [SimpleNamespace(varga_id="D1", input_stability=ConfidenceGrade.PROVISIONAL)],
    )
    lagna_fact = cast(
        Any,
        SimpleNamespace(fact_type="rashi.lagna.position", subject_ref="D1.Lagna"),
    )
    sun_fact = cast(
        Any,
        SimpleNamespace(fact_type="rashi.graha.position", subject_ref="D1.Sun"),
    )

    assert fact_sensitivity_dependencies(
        lagna_fact.fact_type,
        lagna_fact.subject_ref,
    ) == ["lagnaSign"]
    assert fact_sensitivity_dependencies(
        sun_fact.fact_type,
        sun_fact.subject_ref,
    ) == ["d1Structure"]
    assert (
        expected_fact_input_stability(lagna_fact, charts, assessment) == ConfidenceGrade.PROVISIONAL
    )
    assert (
        expected_fact_input_stability(sun_fact, charts, assessment) == ConfidenceGrade.CORROBORATED
    )


def test_fact_sensitivity_fails_closed_when_scan_is_incomplete() -> None:
    assessment = build_input_sensitivity_assessment(
        {
            "summary": {
                "changedFields": [],
                "scanErrors": [{"candidate": "08:31"}],
            }
        }
    )
    fact = cast(
        Any,
        SimpleNamespace(fact_type="rashi.graha.position", subject_ref="D1.Sun"),
    )
    charts = cast(
        Any,
        [SimpleNamespace(varga_id="D1", input_stability=ConfidenceGrade.VERIFIED)],
    )

    assert assessment.scan_status == "partial"
    assert assessment.scan_error_count == 1
    assert expected_fact_input_stability(fact, charts, assessment) == ConfidenceGrade.PROVISIONAL


def test_timing_input_stability_tracks_moon_and_dasha_boundaries() -> None:
    stable = InputSensitivityAssessment(
        scanStatus="complete",
        changedFields=[],
        timingBoundaryScanStatus="complete",
        timingBoundarySampleCount=3,
    )
    changed = InputSensitivityAssessment(
        scanStatus="complete",
        changedFields=["moonPada"],
        timingBoundaryScanStatus="complete",
        timingBoundarySampleCount=3,
    )

    assert (
        expected_timing_input_stability(stable, ConfidenceGrade.CORROBORATED)
        == ConfidenceGrade.CORROBORATED
    )
    assert (
        expected_timing_input_stability(changed, ConfidenceGrade.CORROBORATED)
        == ConfidenceGrade.PROVISIONAL
    )
    not_sampled = InputSensitivityAssessment(scanStatus="complete", changedFields=[])
    assert (
        expected_timing_input_stability(not_sampled, ConfidenceGrade.CORROBORATED)
        == ConfidenceGrade.PROVISIONAL
    )


def test_rectification_life_event_submission_builds_a_parseable_ledger() -> None:
    submission = RectificationLifeEventsInput(
        sessionId="session-1",
        expectedChartRevision=1,
        events=[
            {
                "date": "2012-06",
                "category": "education",
                "eventSubtype": "graduation",
                "description": "Graduated",
            },
            {
                "date": "2018-03",
                "category": "career",
                "eventSubtype": "job_change",
                "description": "Changed employer",
            },
            {
                "date": "2021-10",
                "category": "relationship",
                "eventSubtype": "marriage",
                "description": "Registered marriage",
            },
        ],
    )

    from app.services.life_event_rectification import parse_life_event_ledger

    ledger = parse_life_event_ledger(submission.ledger_text())
    assert ledger["eligibleEventCount"] == 3
    assert [event["role"] for event in ledger["events"]] == [
        "calibration",
        "calibration",
        "holdout",
    ]


def test_reading_focus_is_not_rectification_evidence() -> None:
    input_data = BirthInput(
        birthDate="1990-01-01",
        birthTime="08:30",
        birthPlace="Shanghai, China",
        birthTimePrecision="approximate",
        gender="not provided",
        relationship="not provided",
        timeSource="family memory",
        readingFocus="Career direction and relationship timing",
        lifeEvents="",
        readerRelationship="parent",
    )

    assert input_data.reading_focus == "Career direction and relationship timing"
    assert input_data.life_events == ""
    assert input_data.reader_relationship == "parent"


@pytest.mark.parametrize("field", ["displayName", "gender", "relationship"])
def test_vedic_session_requires_basic_profile(field: str) -> None:
    payload = {
        "displayName": "Asha",
        "birthDate": "1990-01-01",
        "birthTime": "08:30",
        "birthPlace": "Shanghai, China",
        "birthTimePrecision": "approximate",
        "gender": "女",
        "relationship": "单身",
    }
    payload[field] = "   "

    with pytest.raises(ValidationError, match="required profile field cannot be blank"):
        SkillBirthInput.model_validate(payload)


def test_vedic_session_uses_internal_time_source_when_user_does_not_supply_one() -> None:
    input_data = SkillBirthInput(
        displayName="Asha",
        birthDate="1990-01-01",
        birthTime="08:30",
        birthPlace="Shanghai, China",
        birthTimePrecision="approximate",
        gender="女",
        relationship="单身",
    )

    assert input_data.time_source == "user_reported_time"


def test_rectification_decision_requires_reproducible_bounded_result() -> None:
    with pytest.raises(ValidationError, match="requires a resulting interval"):
        RectificationDecision(
            status="bounded_interval",
            selectedCandidateIds=["candidate-1"],
            confidence=ConfidenceGrade.CORROBORATED,
        )

    interval = TimeRange(
        start=datetime(1990, 1, 1, 8, 30, tzinfo=UTC),
        end=datetime(1990, 1, 1, 8, 31, tzinfo=UTC),
    )
    decision = RectificationDecision(
        status="bounded_interval",
        selectedCandidateIds=["candidate-1"],
        resultingInterval=interval,
        confidence=ConfidenceGrade.CORROBORATED,
        holdoutResult="passed",
    )
    assert decision.resulting_interval == interval

    with pytest.raises(ValidationError, match="requires a passed holdout"):
        RectificationDecision(
            status="bounded_interval",
            selectedCandidateIds=["candidate-1"],
            resultingInterval=interval,
            confidence=ConfidenceGrade.CORROBORATED,
        )


def test_rectification_record_caps_internal_method_assurance() -> None:
    interval = TimeRange(
        start=datetime(1990, 1, 1, 8, 30, tzinfo=UTC),
        end=datetime(1990, 1, 1, 8, 31, tzinfo=UTC),
    )
    decision = RectificationDecision(
        status="bounded_interval",
        selectedCandidateIds=["candidate-1"],
        resultingInterval=interval,
        confidence=ConfidenceGrade.CORROBORATED,
        holdoutResult="passed",
    )
    candidate = CandidateInterval(
        candidateId="candidate-1",
        interval=interval,
        representativeMoment=interval.start,
        fingerprint="candidate-1-fingerprint",
    )

    with pytest.raises(
        ValidationError,
        match="rectification decision references unknown candidate",
    ):
        RectificationRecord(decision=decision)

    with pytest.raises(
        ValidationError,
        match="internally validated rectification cannot exceed provisional confidence",
    ):
        RectificationRecord(candidates=[candidate], decision=decision)

    with pytest.raises(
        ValidationError,
        match="professional rectification maturity requires independent professional review",
    ):
        RectificationRecord(
            methodMaturity="professionally_validated",
            candidates=[candidate],
            decision=decision,
        )

    reviewed = RectificationRecord(
        methodMaturity="professionally_validated",
        validationStatus="independent_professional_review",
        professionalReviewFixtureIds=["professional-review.fixture"],
        rectificationBenchmarkFixtureIds=["rectification-benchmark.fixture"],
        candidates=[candidate],
        decision=decision,
    )
    assert reviewed.decision.confidence == ConfidenceGrade.CORROBORATED

    with pytest.raises(
        ValidationError,
        match="requires professional review and source-blind benchmark fixtures",
    ):
        RectificationRecord(
            methodMaturity="professionally_validated",
            validationStatus="independent_professional_review",
            candidates=[candidate],
            decision=decision,
        )


def test_chart_record_migrates_supported_rectification_contract_versions() -> None:
    testimony = EvidenceItem(
        evidenceId="event-source",
        evidenceClass="user_testimony",
        sourceLabel="user",
        observedValue="2018 career change",
        confidence="corroborated",
    )
    event = LifeEvent(
        eventId="event-1",
        episodeId="episode-1",
        category="career",
        eventSubtype="job_change",
        interval=TimeRange(
            start=datetime(2018, 1, 1, tzinfo=UTC),
            end=datetime(2019, 1, 1, tzinfo=UTC),
        ),
        datePrecision="year",
        eventTimezoneBasis="unknown_event_location_utc_offset_envelope",
        description="Changed jobs",
        role="calibration",
        evidence=testimony,
    )
    record = ChartRecord(
        chartRecordId="chart-legacy",
        readingSessionId="session-legacy",
        revision=1,
        createdAt=datetime(2026, 8, 9, tzinfo=UTC),
        subject=SubjectContext(subjectId="subject-legacy"),
        birthAssertion=BirthAssertion(
            localDate="1990-01-01",
            reportedLocalTime="08:00",
            reportedPlace="Test City",
            timeCertainty="approximate",
            evidence=[testimony],
        ),
        calculationProfile=parashari_lahiri_profile(),
        rectification=RectificationRecord(
            lifeEvents=[event],
            decision=RectificationDecision(
                status="underdetermined",
                confidence=ConfidenceGrade.UNAVAILABLE,
            ),
        ),
        status="intake",
    )
    payload = record.model_dump(by_alias=True, mode="json")
    payload["schemaVersion"] = "vedicdust-chart-record/1.3.0"
    payload["rectification"]["schemaVersion"] = "vedicdust-rectification/1.4.0"
    payload["rectification"]["lifeEvents"][0].pop("episodeId")
    payload["rectification"]["lifeEvents"][0].pop("eventTimezoneBasis")

    migrated = ChartRecord.model_validate(payload)

    assert migrated.schema_version == "vedicdust-chart-record/1.6.0"
    assert migrated.rectification is not None
    assert migrated.rectification.schema_version == "vedicdust-rectification/1.7.0"
    assert migrated.rectification.life_events[0].episode_id == "event-1"


def test_unresolved_sensitivity_scan_is_a_blocking_chart_state() -> None:
    source = SimpleNamespace(
        input_context={
            "time": {
                "window": {
                    "start": "2021-11-07 01:00",
                    "end": "2021-11-07 02:00",
                }
            }
        },
        timezone_id="America/New_York",
        sensitivity_scan={
            "reportReadiness": {
                "mode": "rectification_required",
                "blockingFactors": ["scan_incomplete:resolve_civil_time_or_place_input"],
            },
            "candidateGroups": [],
        },
    )
    rectification = _rectification(source, ConfidenceGrade.PROVISIONAL)

    assert rectification is not None
    assert rectification.decision.status == "input_resolution_required"
    assert rectification.decision.confidence == ConfidenceGrade.UNAVAILABLE
    assert rectification.selection_policy_id == "vedicdust-rectification-event-ranking/1.26.0"
    assert rectification.event_mapping_id == "vedicdust-rectification-event-map/1.8.0"
    assert rectification.holdout_policy_id == "vedicdust-rectification-holdout/1.5.0"
    assert rectification.method_maturity == "product_hypothesis"
    assert rectification.validation_status == "internal_regression_only"
    assert rectification.source_ids == [
        "lineage.pvr-integrated-approach-2000-2010",
        "product.vedicdust-consultation-standard-1",
    ]
    assert "独立专业盲审" in _rectification_validation_limitation("zh")

    record = SimpleNamespace(
        chart_record_id="chart-input-resolution",
        quality_checks=[],
        canonical_moment=SimpleNamespace(place=SimpleNamespace(precision="coordinate")),
        rectification=rectification,
    )
    audit = audit_chart_record(record)

    assert audit.status == "blocked"
    assert audit.permitted_next_steps == ["collect_input"]
    assert any(
        finding.finding_id == "rectification.input-resolution-required"
        and finding.severity == "blocking"
        for finding in audit.findings
    )


def test_multiple_equivalent_intervals_permit_only_scoped_judgement() -> None:
    intervals = [
        TimeRange(
            start=datetime(1990, 1, 1, 8, minute, tzinfo=UTC),
            end=datetime(1990, 1, 1, 8, minute + 5, tzinfo=UTC),
        )
        for minute in (10, 30)
    ]
    rectification = RectificationRecord(
        candidates=[
            CandidateInterval(
                candidateId=candidate_id,
                interval=interval,
                representativeMoment=interval.start,
                fingerprint=f"{candidate_id}-fingerprint",
            )
            for candidate_id, interval in zip(
                ["candidate-a", "candidate-b"], intervals, strict=True
            )
        ],
        decision=RectificationDecision(
            status="multiple_equivalent",
            selectedCandidateIds=["candidate-a", "candidate-b"],
            resultingIntervals=intervals,
            confidence=ConfidenceGrade.PROVISIONAL,
            holdoutResult="passed",
            unresolvedQuestions=["The exact time remains unresolved."],
        ),
    )
    record = SimpleNamespace(
        chart_record_id="chart-equivalent",
        status="ready_for_judgement",
        quality_checks=[],
        canonical_moment=SimpleNamespace(place=SimpleNamespace(precision="coordinate")),
        rectification=rectification,
    )

    audit = audit_chart_record(record)

    assert audit.status == "passed_with_limits"
    assert audit.permitted_next_steps == ["judge"]
    assert any(
        finding.finding_id == "rectification.unresolved"
        and "stable across the retained intervals" in str(finding.required_action)
        for finding in audit.findings
    )


def test_report_discloses_method_maturity_only_after_rectification_selection() -> None:
    def record(status: str) -> SimpleNamespace:
        return SimpleNamespace(
            quality_checks=[],
            subject=SimpleNamespace(locale="zh"),
            rectification=SimpleNamespace(
                validation_status="internal_regression_only",
                decision=SimpleNamespace(status=status, unresolved_questions=[]),
            ),
        )

    assert _residual_uncertainties(record("not_required")) == []
    assert _residual_uncertainties(record("bounded_interval")) == [
        "生时校正方法目前仅通过内部回归测试，尚未完成独立专业盲审。"
    ]


def test_candidate_scoring_failure_is_a_blocking_runtime_state() -> None:
    source = SimpleNamespace(
        input_context={
            "time": {
                "window": {
                    "start": "1990-01-01 08:15",
                    "end": "1990-01-01 08:45",
                }
            }
        },
        timezone_id="Asia/Shanghai",
        sensitivity_scan={
            "reportReadiness": {
                "mode": "rectification_required",
                "blockingFactors": ["candidate_scoring_incomplete:retry_deterministic_calculation"],
            },
            "candidateGroups": [],
        },
    )
    rectification = _rectification(source, ConfidenceGrade.PROVISIONAL)

    assert rectification is not None
    assert rectification.decision.status == "calculation_failed"
    assert rectification.decision.confidence == ConfidenceGrade.UNAVAILABLE

    reading = ReadingSession(
        readingSessionId="reading-failed",
        subjectId="subject-failed",
        chartRecordId="chart-failed",
        activeChartRevision=1,
        createdAt=datetime.now(UTC),
        updatedAt=datetime.now(UTC),
        stage="blocked",
        rectificationStatus="calculation_failed",
        reportStatus="blocked",
    )
    assert reading.rectification_status == "calculation_failed"

    record = SimpleNamespace(
        chart_record_id="chart-failed",
        quality_checks=[],
        canonical_moment=SimpleNamespace(place=SimpleNamespace(precision="coordinate")),
        rectification=rectification,
    )
    audit = audit_chart_record(record)
    assert audit.status == "blocked"
    assert any(
        finding.finding_id == "rectification.calculation-failed" and finding.severity == "blocking"
        for finding in audit.findings
    )


def _position(longitude: float = 10.0) -> ZodiacPosition:
    return ZodiacPosition(
        longitude_deg=longitude,
        sign="Aries",
        sign_index=0,
        degree_in_sign=longitude,
    )


def test_agent_workspace_boundary_restores_authoritative_inputs(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    chart_path = session_dir / "chart_record.json"
    chart_path.write_text('{"chartRecordId":"original"}\n', encoding="utf-8")
    snapshot = SkillRuntime._snapshot_agent_workspace(session_dir, {"claim_graph.json"})

    chart_path.write_text('{"chartRecordId":"tampered"}\n', encoding="utf-8")
    (session_dir / "unauthorized.json").write_text("{}\n", encoding="utf-8")
    (session_dir / "claim_graph.json").write_text('{"claims":[]}\n', encoding="utf-8")

    errors = SkillRuntime._restore_agent_workspace_boundary(
        session_dir,
        {"claim_graph.json"},
        snapshot,
    )

    assert errors == ["created:unauthorized.json", "modified:chart_record.json"]
    assert chart_path.read_text(encoding="utf-8") == '{"chartRecordId":"original"}\n'
    assert not (session_dir / "unauthorized.json").exists()
    assert (session_dir / "claim_graph.json").exists()


def test_product_profile_has_no_unregistered_sources() -> None:
    from app.services.vedic_calculator import CALCULATION_VERSION

    profile = parashari_lahiri_profile()
    validate_profile_source_ids(profile.source_ids)

    assert profile.profile_id == "parashari-lahiri-1.1.0"
    assert CALCULATION_VERSION == f"vedicdust-{profile.profile_id}"
    assert profile.planet_position_model == "geocentric_apparent"
    assert profile.ephemeris_flags == ["FLG_SWIEPH", "FLG_SIDEREAL", "FLG_SPEED"]
    assert profile.ayanamsa.model == "lahiri"
    assert profile.node_model == "mean"
    assert profile.rashi_house_model == "whole_sign"
    assert profile.dasha_year_days == pytest.approx(365.256364)
    assert tuple(profile.supported_vargas) == SUPPORTED_VARGA_FACTORS
    methods = {setting.factor: setting for setting in profile.varga_methods}
    assert methods[1].provider_method is None
    assert methods[2].algorithm_id == "traditional-parashara-hora-leo-cancer"
    assert methods[2].provider_method == 2
    assert {setting.provider_method for factor, setting in methods.items() if factor > 2} == {1}


def test_directional_convergence_requires_permitted_same_polarity_methods() -> None:
    from app.vedicdust.judgement_kernel import _require_directional_method_convergence

    first = JudgementFinding(
        findingId="finding.test.first",
        findingCode="test.first",
        ruleId="judge.capacity.dignity-condition",
        polarity="supportive",
        weight=0.8,
        factIds=["fact.D1.H10.lord", "fact.D1.Saturn.dignity"],
        technicalStatement="One dignity interpretation with two dependent facts.",
    )
    same_method = first.model_copy(
        update={
            "finding_id": "finding.test.second",
            "finding_code": "test.second",
            "fact_ids": ["fact.D1.H1.lord", "fact.D1.Mars.dignity"],
        }
    )
    context_only = _require_directional_method_convergence(
        [first, same_method],
        directional_judgement_rule_ids=set(),
    )
    assert {finding.polarity for finding in context_only} == {"context"}
    assert {finding.parameters["directionWithheldReason"] for finding in context_only} == {
        "interpretation_rule_not_directional"
    }

    withheld = _require_directional_method_convergence(
        [first, same_method],
        directional_judgement_rule_ids={"judge.capacity.dignity-condition"},
    )
    assert {finding.polarity for finding in withheld} == {"context"}
    assert withheld[0].parameters["directionalJudgementRuleIds"] == [
        "judge.capacity.dignity-condition"
    ]

    independent_method = same_method.model_copy(
        update={"rule_id": "judge.capacity.sav-structural-band"}
    )
    allowed_methods = {
        "judge.capacity.dignity-condition",
        "judge.capacity.sav-structural-band",
    }
    released = _require_directional_method_convergence(
        [first, independent_method],
        directional_judgement_rule_ids=allowed_methods,
    )
    assert [finding.polarity for finding in released] == ["supportive", "supportive"]

    opposing_method = independent_method.model_copy(update={"polarity": "challenging"})
    opposing = _require_directional_method_convergence(
        [first, opposing_method],
        directional_judgement_rule_ids=allowed_methods,
    )
    assert {finding.polarity for finding in opposing} == {"context"}
    assert {finding.parameters["directionWithheldReason"] for finding in opposing} == {
        "insufficient_directional_method_convergence"
    }


def test_candidate_evidence_migrates_legacy_family_contract_without_changing_observations() -> None:
    legacy_payload = {
        "eventId": "event-1",
        "episodeId": "episode-1",
        "role": "calibration",
        "score": 0.57,
        "supportScore": 0.57,
        "contradictionScore": 0.0,
        "methodConvergenceComponents": ["dasha", "varga"],
        "methodConvergenceFamilies": ["period_domain"],
        "methodConvergenceCount": 1,
        "methodConvergenceMet": False,
        "observations": [
            {
                "observationId": "event-1.dasha",
                "component": "dasha",
                "outcome": "support",
                "weight": 0.28,
            },
            {
                "observationId": "event-1.varga",
                "component": "varga",
                "outcome": "support",
                "weight": 0.19,
            },
            {
                "observationId": "event-1.kp",
                "component": "kp_sub_lord",
                "outcome": "support",
                "weight": 0.1,
            },
        ],
        "ruleIds": ["rectification.test"],
        "sourceIds": ["source.test"],
        "scoringPolicyId": "vedicdust-rectification-event-ranking/1.19.0",
        "eventMappingId": "vedicdust-rectification-event-map/1.7.0",
        "eventTimezoneBasis": "unknown_event_location_utc_offset_envelope",
        "explanation": "Legacy evidence record.",
    }
    score = CandidateEvidenceScore.model_validate(legacy_payload)
    rebuilt_score = _candidate_evidence_score(legacy_payload)

    assert score.selection_score == pytest.approx(0.47)
    assert score.selection_support_score == pytest.approx(0.47)
    assert score.selection_contradiction_score == 0
    assert score.method_convergence_layers == [
        "d1_period_activation",
        "domain_varga_activation",
    ]
    assert score.method_convergence_count == 2
    assert score.method_convergence_met is True
    assert score.support_score == pytest.approx(0.57)
    assert rebuilt_score == score


def test_candidate_evidence_never_treats_d1_capacity_as_method_convergence() -> None:
    payload = {
        "eventId": "event-1",
        "episodeId": "episode-1",
        "role": "calibration",
        "score": 0.38,
        "supportScore": 0.38,
        "contradictionScore": 0.0,
        "methodConvergenceComponents": ["natal_promise", "dasha"],
        "methodConvergenceLayers": ["d1_directional_capacity", "d1_period_activation"],
        "methodConvergenceCount": 2,
        "methodConvergenceMet": True,
        "observations": [
            {
                "observationId": "event-1.natal",
                "component": "natal_promise",
                "outcome": "support",
                "weight": 0.1,
            },
            {
                "observationId": "event-1.dasha",
                "component": "dasha",
                "outcome": "support",
                "weight": 0.28,
            },
        ],
        "ruleIds": ["rectification.test"],
        "sourceIds": ["source.test"],
        "scoringPolicyId": "vedicdust-rectification-event-ranking/1.23.0",
        "eventMappingId": "vedicdust-rectification-event-map/1.7.0",
        "eventTimezoneBasis": "unknown_event_location_utc_offset_envelope",
        "explanation": "Legacy evidence with an over-authoritative D1 convergence flag.",
    }

    score = CandidateEvidenceScore.model_validate(payload)

    assert score.method_convergence_components == ["dasha"]
    assert score.method_convergence_layers == ["d1_period_activation"]
    assert score.method_convergence_count == 1
    assert score.method_convergence_met is False
    assert score.selection_support_score == pytest.approx(0.28)
    assert score.selection_score == pytest.approx(0.28)


def test_candidate_evidence_rebuilds_declared_convergence_from_observations() -> None:
    payload = {
        "eventId": "event-1",
        "episodeId": "episode-1",
        "role": "calibration",
        "score": 0.28,
        "supportScore": 0.28,
        "contradictionScore": 0.0,
        "selectionScore": 0.28,
        "selectionSupportScore": 0.28,
        "selectionContradictionScore": 0.0,
        "methodConvergenceComponents": ["dasha", "varga"],
        "methodConvergenceLayers": ["d1_period_activation", "domain_varga_activation"],
        "methodConvergenceCount": 2,
        "methodConvergenceMet": True,
        "observations": [
            {
                "observationId": "event-1.dasha",
                "component": "dasha",
                "outcome": "support",
                "weight": 0.28,
            },
            {
                "observationId": "event-1.varga",
                "component": "varga",
                "outcome": "missing",
                "weight": 0.0,
            },
        ],
        "ruleIds": ["rectification.test"],
        "sourceIds": ["source.test"],
        "scoringPolicyId": "vedicdust-rectification-event-ranking/1.23.0",
        "eventMappingId": "vedicdust-rectification-event-map/1.7.0",
        "eventTimezoneBasis": "unknown_event_location_utc_offset_envelope",
        "explanation": "Legacy evidence with a stale declared Varga component.",
    }

    score = CandidateEvidenceScore.model_validate(payload)

    assert score.method_convergence_components == ["dasha"]
    assert score.method_convergence_layers == ["d1_period_activation"]
    assert score.method_convergence_count == 1
    assert score.method_convergence_met is False


def test_public_vedic_skill_api_has_one_report_pipeline() -> None:
    skill_schema = SkillRunInput.model_json_schema()["properties"]["skill"]
    public_skills = set(skill_schema["enum"])

    assert {"vedic-reader", "vedic-core", "vedic-rectifier", "vedic-synastry"} <= public_skills
    assert {"vedic-career", "vedic-love"}.isdisjoint(public_skills)


def test_source_registry_distinguishes_authority_from_pending_classics() -> None:
    registry = load_source_registry()

    assert registry["astro.swisseph.programmer-manual"].citation_status == "pinned"
    assert registry["classic.bphs.pending-edition"].citation_status == "pending-edition-pin"
    assert registry["lineage.pvr-integrated-approach-2000-2010"].citation_status == "pinned"
    assert registry["software.pyjhora.compatibility"].citation_status == "informational"


def test_validation_fixture_registry_points_to_real_pytest_nodes() -> None:
    registry = load_validation_fixture_registry()

    assert registry
    for fixture in registry.values():
        for node in fixture.test_nodes:
            relative_path, test_name = node.split("::", maxsplit=1)
            test_path = ROOT / relative_path
            assert test_path.is_file(), f"missing fixture test file: {node}"
            module = ast.parse(test_path.read_text(encoding="utf-8"), filename=str(test_path))
            test_functions = {
                item.name
                for item in module.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            assert test_name in test_functions, f"missing fixture test function: {node}"


def test_professional_review_fixture_requires_auditable_evidence() -> None:
    with pytest.raises(ValidationError, match="evidence artifact path and SHA-256"):
        ValidationFixtureReference(
            fixtureId="professional.example",
            fixtureKind="professional_review",
            testNodes=[
                "backend/tests/test_vedicdust_contracts.py::"
                "test_professional_review_fixture_requires_auditable_evidence"
            ],
            description="A label alone must not certify a directional judgement rule.",
        )

    with pytest.raises(ValidationError, match="protocol, reviewer, timestamp"):
        ValidationFixtureReference(
            fixtureId="professional.example",
            fixtureKind="professional_review",
            testNodes=[
                "backend/tests/test_vedicdust_contracts.py::"
                "test_professional_review_fixture_requires_auditable_evidence"
            ],
            description="Evidence without a recorded review is still not professional review.",
            evidenceArtifactPath="reviews/example.json",
            evidenceArtifactSha256="sha256:" + "0" * 64,
        )


def test_professional_review_fixture_validates_blind_case_evidence(tmp_path: Path) -> None:
    retained: dict[str, dict[str, str]] = {}
    for name in ("chart-record", "claim-graph", "consultation-dossier"):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps({"artifact": name}) + "\n", encoding="utf-8")
        retained[name] = {
            "path": path.name,
            "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    review_payload = {
        "schemaVersion": "vedicdust-professional-review/1.1.0",
        "protocolId": "blind-output-review/1.0.0",
        "reviewScope": "calculation_and_judgement",
        "reviewerId": "external-jyotishi-01",
        "reviewerCredentials": ["Recorded lineage and practice credential"],
        "reviewedAt": "2026-08-02T00:00:00Z",
        "blindedToSubjectIdentity": True,
        "blindedToSystemAuthorship": True,
        "reviewerIndependentOfImplementation": True,
        "cases": [
            {
                "caseId": "review-case-001",
                "chartRecord": retained["chart-record"],
                "claimGraph": retained["claim-graph"],
                "consultationDossier": retained["consultation-dossier"],
                "expectedDisposition": "withhold",
                "observedDisposition": "withhold",
                "decision": "accepted_with_reservations",
                "assessment": {
                    "methodFidelity": "reservation",
                    "evidenceTraceability": "accepted",
                    "uncertaintyCalibration": "accepted",
                    "readerComprehensibility": "accepted",
                },
                "disagreements": ["Varga emphasis should remain withheld."],
                "rationale": "The system withheld direction when the available methods diverged.",
            }
        ],
    }
    review_path = tmp_path / "professional-review.json"
    review_path.write_text(json.dumps(review_payload) + "\n", encoding="utf-8")
    fixture = ValidationFixtureReference(
        fixtureId="professional.example",
        fixtureKind="professional_review",
        testNodes=[
            "backend/tests/test_vedicdust_contracts.py::"
            "test_professional_review_fixture_validates_blind_case_evidence"
        ],
        description="Retains a blind review of complete consultation artifacts.",
        evidenceArtifactPath=review_path.name,
        evidenceArtifactSha256=("sha256:" + hashlib.sha256(review_path.read_bytes()).hexdigest()),
        reviewProtocolId="blind-output-review/1.0.0",
        reviewedBy="external-jyotishi-01",
        reviewedAt="2026-08-02T00:00:00Z",
        reviewedCaseIds=["review-case-001"],
        reviewScope="calculation_and_judgement",
    )

    artifact = validate_professional_review_fixture(fixture, review_path)
    assert artifact.cases[0].decision == "accepted_with_reservations"

    registry_path = tmp_path / "validation-fixtures.json"
    registry_path.write_text(
        json.dumps(
            {
                "schemaVersion": "vedicdust-validation-fixtures/1.0.0",
                "fixtures": [fixture.model_dump(by_alias=True, mode="json")],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert load_validation_fixture_registry(registry_path)[fixture.fixture_id] == fixture

    review_payload["cases"][0]["observedDisposition"] = "publish"
    review_path.write_text(json.dumps(review_payload) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="disposition mismatch"):
        validate_professional_review_fixture(fixture, review_path)


def test_rectification_professional_review_requires_specific_workflow_assessment(
    tmp_path: Path,
) -> None:
    retained: dict[str, dict[str, str]] = {}
    for name, payload in {
        "chart-record": {"artifact": "chart-record"},
        "claim-graph": {"artifact": "claim-graph"},
        "consultation-dossier": {"artifact": "consultation-dossier"},
        "rectification-state": {
            "status": "corrected_chart_ready",
            "selectionPolicyId": "selection-policy",
            "eventMappingId": "event-map",
            "holdoutPolicyId": "holdout-policy",
        },
    }.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        retained[name] = {
            "path": path.name,
            "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def review_case(index: int) -> dict[str, object]:
        disposition = "withhold" if index == 0 else "publish"
        return {
            "caseId": f"rectification-review-{index}",
            "chartRecord": retained["chart-record"],
            "claimGraph": retained["claim-graph"],
            "consultationDossier": retained["consultation-dossier"],
            "rectificationState": retained["rectification-state"],
            "expectedDisposition": disposition,
            "observedDisposition": disposition,
            "decision": "accepted",
            "assessment": {
                "methodFidelity": "accepted",
                "evidenceTraceability": "accepted",
                "uncertaintyCalibration": "accepted",
                "readerComprehensibility": "accepted",
            },
            "rectificationAssessment": {
                "candidateConstruction": "accepted",
                "eventMethodFidelity": "accepted",
                "holdoutIndependence": "accepted",
                "stoppingAndAbstention": "accepted",
                "uncertaintyCommunication": "accepted",
            },
            "rationale": "The reviewer accepted the source-blind workflow and its stopping rule.",
        }

    cases = [review_case(index) for index in range(5)]
    payload = {
        "schemaVersion": "vedicdust-professional-review/1.1.0",
        "protocolId": "blind-rectification-review/1.0.0",
        "reviewScope": "rectification",
        "reviewerId": "external-jyotishi-02",
        "reviewerCredentials": ["Documented professional Jyotish practice"],
        "reviewedAt": "2026-08-03T00:00:00Z",
        "blindedToSubjectIdentity": True,
        "blindedToSystemAuthorship": True,
        "reviewerIndependentOfImplementation": True,
        "cases": cases,
    }
    with pytest.raises(ValidationError, match="at least 5 blind cases"):
        ProfessionalReviewArtifact.model_validate({**payload, "cases": cases[:1]})

    review_path = tmp_path / "rectification-professional-review.json"
    review_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    fixture = ValidationFixtureReference(
        fixtureId="professional.rectification",
        fixtureKind="professional_review",
        testNodes=[
            "backend/tests/test_vedicdust_contracts.py::"
            "test_rectification_professional_review_requires_specific_workflow_assessment"
        ],
        description="Independent blind review of the complete rectification workflow.",
        evidenceArtifactPath=review_path.name,
        evidenceArtifactSha256=("sha256:" + hashlib.sha256(review_path.read_bytes()).hexdigest()),
        reviewProtocolId="blind-rectification-review/1.0.0",
        reviewedBy="external-jyotishi-02",
        reviewedAt="2026-08-03T00:00:00Z",
        reviewedCaseIds=[f"rectification-review-{index}" for index in range(5)],
        reviewScope="rectification",
    )

    artifact = validate_professional_review_fixture(fixture, review_path)

    assert artifact.review_scope == "rectification"
    assert artifact.cases[0].rectification_assessment is not None


def test_pinned_source_contract_requires_locator_url_and_textual_edition() -> None:
    with pytest.raises(ValidationError, match="reproducible locator"):
        SourceReference(
            sourceId="lineage.test",
            evidenceClass="lineage_commentary",
            title="Test lineage source",
            edition="First edition",
            url="https://example.com/source.pdf",
            citationStatus="pinned",
        )
    with pytest.raises(ValidationError, match="retrievable URL"):
        SourceReference(
            sourceId="lineage.test",
            evidenceClass="lineage_commentary",
            title="Test lineage source",
            locator="PDF p. 10",
            edition="First edition",
            citationStatus="pinned",
        )
    with pytest.raises(ValidationError, match="requires an edition"):
        SourceReference(
            sourceId="lineage.test",
            evidenceClass="lineage_commentary",
            title="Test lineage source",
            locator="PDF p. 10",
            url="https://example.com/source.pdf",
            citationStatus="pinned",
        )


def test_rule_catalog_is_unique_and_uses_registered_sources() -> None:
    catalog = load_rule_catalog()
    validate_rule_catalog_sources(catalog)

    assert catalog.catalog_version == "1.37.0"
    rule_ids = {rule.rule_id for rule in catalog.rules}
    assert {
        "sop.promise-before-varga",
        "sop.promise-capacity-before-timing",
        "sop.d60-eligibility-gate",
    } <= rule_ids
    assert {
        "judge.foundation.integrated",
        "judge.identity.integrated",
        "judge.career.d1-d10",
        "judge.finance.d1-d2-d4",
        "judge.relationship.d1-d9",
        "judge.home.d1-d4",
        "judge.learning.d1-d24",
        "judge.children.d1-d7",
        "judge.health.d1-d30",
        "judge.dharma.d1-d9-d20",
        "judge.family.d1-d12",
        "judge.timing.vimshottari-activation",
        "judge.capacity.sav-structural-band",
        "judge.capacity.dignity-condition",
        "judge.capacity.shadbala-band",
        "judge.capacity.combustion-condition",
        "judge.structure.lagna-sun-moon-reference-points",
        "judge.structure.house-lord-placement",
        "judge.structure.house-occupancy",
        "judge.structure.graha-drishti",
        "judge.structure.varga-confirmation",
        "judge.structure.same-sign-association",
        "judge.structure.natural-karaka",
        "judge.structure.dispositor-path",
    } <= rule_ids
    assert {
        "derive.astronomy.sidereal-position",
        "derive.rashi.whole-sign-house",
        "derive.varga.profile-pinned",
        "derive.strength.dignity",
        "derive.strength.shadbala-pyjhora",
        "derive.ashtakavarga.pyjhora",
        "derive.aspect.parashari-graha-drishti",
        "derive.yoga.kendra-trikona-association",
        "derive.capacity.combustion-threshold",
        "derive.capacity.directional-strength-house",
        "derive.varga.d1-d9-vargottama",
        "derive.role.chara-karaka-7k",
        "derive.point.arudha-al-ul",
        "derive.state.lunar-phase-hemicycle",
        "derive.strength.bhava-bala-pyjhora",
        "derive.point.special-lagna-pyjhora",
        "derive.strength.vargeeya-bala-pyjhora",
        "derive.timing.transit-position-swisseph",
        "derive.timing.transit-whole-sign-house",
        "derive.timing.sade-sati-phase",
        "derive.timing.saturn-jupiter-double-transit",
        "derive.timing.vimshottari-pyjhora",
        "rectify.event-evidence-ranking",
    } <= rule_ids
    workflow_rules = [rule for rule in catalog.rules if rule.rule_id.startswith("sop.")]
    assert all(rule.evidence_class == EvidenceClass.PRODUCT_HYPOTHESIS for rule in workflow_rules)
    rules_by_id = {rule.rule_id: rule for rule in catalog.rules}
    assert rules_by_id["derive.strength.dignity"].status == "validated"
    assert rules_by_id["derive.strength.dignity"].judgement_use == "context_only"
    assert rules_by_id["derive.ashtakavarga.pyjhora"].judgement_use == "context_only"
    assert all(
        rules_by_id[rule_id].status == "provisional"
        and rules_by_id[rule_id].judgement_use == "context_only"
        for rule_id in {
            "judge.capacity.sav-structural-band",
            "judge.capacity.combustion-condition",
            "judge.structure.lagna-sun-moon-reference-points",
            "judge.structure.house-lord-placement",
            "judge.structure.house-occupancy",
            "judge.structure.graha-drishti",
            "judge.structure.varga-confirmation",
            "judge.structure.same-sign-association",
            "judge.structure.natural-karaka",
            "judge.structure.dispositor-path",
        }
    )
    assert all(
        rules_by_id[rule_id].status == "provisional"
        and rules_by_id[rule_id].judgement_use == "traditional_tendency"
        for rule_id in {
            "judge.capacity.dignity-condition",
            "judge.capacity.shadbala-band",
        }
    )
    assert rules_by_id["judge.capacity.dignity-condition"].evidence_class == (
        EvidenceClass.LINEAGE_COMMENTARY
    )
    assert set(rules_by_id["judge.capacity.dignity-condition"].source_ids) == {
        "lineage.pvr-lessons-volume-1-2005",
        "lineage.pvr-integrated-approach-2000-2010",
    }
    assert rules_by_id["judge.capacity.shadbala-band"].evidence_class == (
        EvidenceClass.LINEAGE_COMMENTARY
    )
    expected_rectification_sources = {
        "lineage.pvr-integrated-approach-2000-2010",
        "product.vedicdust-consultation-standard-1",
    }
    assert set(rules_by_id["rectify.event-evidence-ranking"].source_ids) == (
        expected_rectification_sources
    )
    assert set(rules_by_id["sop.d60-eligibility-gate"].source_ids) == (
        expected_rectification_sources
    )
    varga_domain_rules = {
        "judge.foundation.integrated",
        "judge.identity.integrated",
        "judge.career.d1-d10",
        "judge.finance.d1-d2-d4",
        "judge.relationship.d1-d9",
        "judge.home.d1-d4",
        "judge.learning.d1-d24",
        "judge.children.d1-d7",
        "judge.health.d1-d30",
        "judge.dharma.d1-d9-d20",
        "judge.family.d1-d12",
    }
    assert all(
        "lineage.pvr-integrated-approach-2000-2010" in rules_by_id[rule_id].source_ids
        for rule_id in varga_domain_rules
    )
    assert all(
        rule.validation_fixture_ids
        for rule in catalog.rules
        if rule.rule_kind == "judgement" and rule.status != "draft"
    )


def test_rule_source_gate_rejects_pending_mismatched_and_unreviewed_directional_rules() -> None:
    catalog = load_rule_catalog()

    pending = catalog.model_copy(deep=True)
    pending_rule = next(
        rule for rule in pending.rules if rule.rule_id == "derive.rashi.whole-sign-house"
    )
    pending_rule.source_ids = ["classic.bphs.pending-edition"]
    with pytest.raises(ValueError, match="pending-edition source"):
        validate_rule_catalog_sources(pending)

    mismatched = catalog.model_copy(deep=True)
    mismatched_rule = next(
        rule for rule in mismatched.rules if rule.rule_id == "derive.role.house-ownership"
    )
    mismatched_rule.source_ids = ["product.vedicdust-consultation-standard-1"]
    with pytest.raises(ValueError, match="no source matching evidence class lineage_commentary"):
        validate_rule_catalog_sources(mismatched)

    directional = catalog.model_copy(deep=True)
    directional_rule = next(
        rule for rule in directional.rules if rule.rule_id == "judge.foundation.integrated"
    )
    directional_rule.judgement_use = "directional"
    with pytest.raises(ValueError, match="must be validated"):
        validate_rule_catalog_sources(directional)

    untested_judgement = catalog.model_copy(deep=True)
    untested_rule = next(
        rule for rule in untested_judgement.rules if rule.rule_id == "judge.foundation.integrated"
    )
    untested_rule.validation_fixture_ids = []
    with pytest.raises(ValueError, match="requires an executable contract fixture"):
        validate_rule_catalog_sources(untested_judgement)

    wrong_fixture_kind = catalog.model_copy(deep=True)
    wrong_fixture_rule = next(
        rule for rule in wrong_fixture_kind.rules if rule.rule_id == "judge.foundation.integrated"
    )
    wrong_fixture_rule.validation_fixture_ids = ["invariant.sav-total-337"]
    with pytest.raises(ValueError, match="requires an executable contract fixture"):
        validate_rule_catalog_sources(wrong_fixture_kind)

    fixtureless = catalog.model_copy(deep=True)
    fixtureless_rule = next(
        rule for rule in fixtureless.rules if rule.rule_id == "derive.rashi.whole-sign-house"
    )
    fixtureless_rule.validation_fixture_ids = []
    with pytest.raises(ValueError, match="validated rule .* requires validation fixtures"):
        validate_rule_catalog_sources(fixtureless)

    unknown_fixture = catalog.model_copy(deep=True)
    unknown_fixture_rule = next(
        rule for rule in unknown_fixture.rules if rule.rule_id == "derive.rashi.whole-sign-house"
    )
    unknown_fixture_rule.validation_fixture_ids = ["contract.this-does-not-exist"]
    with pytest.raises(ValueError, match="unknown validation fixture id"):
        validate_rule_catalog_sources(unknown_fixture)

    unreviewed_direction = catalog.model_copy(deep=True)
    unreviewed_direction_rule = next(
        rule for rule in unreviewed_direction.rules if rule.rule_id == "judge.foundation.integrated"
    )
    unreviewed_direction_rule.status = "validated"
    unreviewed_direction_rule.judgement_use = "directional"
    unreviewed_direction_rule.validation_fixture_ids = [
        "contract.judgement.capacity-rule-separation"
    ]
    with pytest.raises(ValueError, match="requires a professional review fixture"):
        validate_rule_catalog_sources(unreviewed_direction)

    ungrounded_tendency = catalog.model_copy(deep=True)
    ungrounded_tendency_rule = next(
        rule
        for rule in ungrounded_tendency.rules
        if rule.rule_id == "judge.capacity.dignity-condition"
    )
    ungrounded_tendency_rule.source_ids = ["product.vedicdust-consultation-standard-1"]
    ungrounded_tendency_rule.evidence_class = EvidenceClass.PRODUCT_HYPOTHESIS
    with pytest.raises(ValueError, match="requires a pinned classical or lineage source"):
        validate_rule_catalog_sources(ungrounded_tendency)


def test_rectification_event_vargas_follow_the_declared_domain_policy() -> None:
    supported_vargas = {f"D{factor}" for factor in VARGA_DOMAIN_POLICIES}
    for event_rule in RECTIFICATION_EVENT_RULES.values():
        assert set(event_rule["vargas"]) <= supported_vargas
        assert "D60" not in event_rule["vargas"]
        declared_varga_fields = {
            field.removesuffix("Lagna").removesuffix("Structure").upper()
            for field in event_rule["fields"]
            if field.startswith("d") and (field.endswith("Lagna") or field.endswith("Structure"))
        }
        assert declared_varga_fields <= set(event_rule["vargas"])

    assert RECTIFICATION_EVENT_RULES["education"]["vargas"] == ["D24"]
    assert "d5Lagna" not in RECTIFICATION_EVENT_RULES["education"]["fields"]
    assert "d5Structure" not in RECTIFICATION_EVENT_RULES["education"]["fields"]

    learning = next(topic for topic in TOPICS if topic.topic_id == "learning")
    assert learning.vargas == ("D24",)
    assert learning.rule_id == "judge.learning.d1-d24"


def test_time_range_rejects_empty_or_reversed_interval() -> None:
    moment = datetime(1990, 1, 1, 8, 0, tzinfo=UTC)

    with pytest.raises(ValidationError, match="end must be after start"):
        TimeRange(start=moment, end=moment)


def test_candidate_representative_moment_must_be_inside_interval() -> None:
    start = datetime(1990, 1, 1, 8, 0, tzinfo=UTC)
    end = datetime(1990, 1, 1, 8, 10, tzinfo=UTC)

    with pytest.raises(ValidationError, match="inside the candidate interval"):
        CandidateInterval(
            candidate_id="candidate-1",
            interval=TimeRange(start=start, end=end),
            representative_moment=end,
            fingerprint="lagna-aries:d9-cancer",
        )


def test_complete_astronomy_snapshot_requires_unique_nine_grahas() -> None:
    graha_names = [
        "Sun",
        "Moon",
        "Mars",
        "Mercury",
        "Jupiter",
        "Venus",
        "Saturn",
        "Rahu",
        "Ketu",
    ]
    grahas = [
        GrahaPosition(
            graha=name,
            position=_position(10.0 + index),
            motion="not_applicable" if name == "Ketu" else "direct",
        )
        for index, name in enumerate(graha_names)
    ]

    snapshot = AstronomySnapshot(
        snapshot_id="astro-1",
        calculated_at=datetime.now(UTC),
        julian_day_ut=2447892.5,
        calculation_provider="Swiss Ephemeris + PyJHora",
        calculation_adapter_version="test-adapter",
        ephemeris_version="test",
        provider_versions={"PyJHora": "test", "pysweph": "test"},
        timezone_database_version="test",
        ephemeris_data_fingerprint="sha256:" + "0" * 64,
        ayanamsa_value_deg=23.7,
        ascendant=_position(),
        grahas=grahas,
        status="complete",
    )
    assert len(snapshot.grahas) == 9

    with pytest.raises(ValidationError, match="duplicate grahas"):
        AstronomySnapshot(
            snapshot_id="astro-2",
            calculated_at=datetime.now(UTC),
            julian_day_ut=2447892.5,
            calculation_provider="Swiss Ephemeris + PyJHora",
            calculation_adapter_version="test-adapter",
            ephemeris_version="test",
            provider_versions={"PyJHora": "test", "pysweph": "test"},
            timezone_database_version="test",
            ephemeris_data_fingerprint="sha256:" + "0" * 64,
            ayanamsa_value_deg=23.7,
            ascendant=_position(),
            grahas=[grahas[0], grahas[0]],
            status="partial",
        )


def test_chart_audit_status_must_match_blocking_findings() -> None:
    finding = AuditFinding(
        finding_id="missing-timezone",
        severity="blocking",
        category="civil_time",
        field_refs=["canonicalMoment.timezoneId"],
        message="Historical time zone is unresolved.",
        required_action="Resolve the IANA time zone before calculation.",
    )

    with pytest.raises(ValidationError, match="must agree with blocking findings"):
        ChartAudit(
            chart_record_id="chart-1",
            audited_at=datetime.now(UTC),
            status="passed_with_limits",
            findings=[finding],
            permitted_next_steps=["collect_input"],
        )


def test_schema_uses_canonical_camel_case_language() -> None:
    schema = ChartAudit.model_json_schema(by_alias=True)
    assert "schemaVersion" in schema["properties"]
    assert "permittedNextSteps" in schema["properties"]
    assert "permitted_next_steps" not in schema["properties"]


def test_certainty_language_guard_allows_explicit_negation_only() -> None:
    assert not _contains_assertive_phrase("不等同于事件必然发生", "必然发生")
    assert _contains_assertive_phrase("这件事必然发生", "必然发生")
    assert not _contains_assertive_phrase("This is not a guaranteed event.", "guaranteed event")
    assert _contains_assertive_phrase("This is a guaranteed event.", "guaranteed event")


def test_claim_graph_references_chart_facts_and_registered_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = parashari_lahiri_profile()
    testimony = EvidenceItem(
        evidence_id="birth-record",
        evidence_class="user_testimony",
        source_label="user",
        observed_value="1990-01-01 around 08:00",
        confidence="corroborated",
    )
    fact = JyotishFact(
        fact_id="fact.D1.Lagna.position",
        fact_type="rashi.lagna.position",
        subject_ref="D1.Lagna",
        value=_position().model_dump(by_alias=True),
        provenance=RuleProvenance(
            rule_id="derive.astronomy.sidereal-position",
            rule_version="1.0.0",
            method_profile_id=profile.profile_id,
            evidence_class="astronomical_authority",
            source_ids=["astro.swisseph.programmer-manual"],
            confidence=ConfidenceGrade.VERIFIED,
        ),
    )
    capacity_fact = JyotishFact(
        fact_id="fact.D1.H1.sav",
        fact_type="ashtakavarga.sav.house",
        subject_ref="D1.H1",
        value=30,
        unit="bindu",
        provenance=RuleProvenance(
            rule_id="derive.ashtakavarga.pyjhora",
            rule_version="1.0.0",
            method_profile_id=profile.profile_id,
            evidence_class="software_reference",
            source_ids=["software.pyjhora.compatibility"],
            confidence=ConfidenceGrade.CORROBORATED,
        ),
    )
    record = ChartRecord(
        chart_record_id="chart-claim",
        reading_session_id="session-claim",
        revision=1,
        created_at=datetime.now(UTC),
        subject=SubjectContext(subject_id="subject-1"),
        birth_assertion=BirthAssertion(
            local_date="1990-01-01",
            reported_local_time="08:00",
            reported_place="Test City",
            time_certainty="approximate",
            reported_time_window=TimeRange(
                start=datetime(1990, 1, 1, 7, 45, tzinfo=UTC),
                end=datetime(1990, 1, 1, 8, 15, tzinfo=UTC),
            ),
            evidence=[testimony],
        ),
        calculation_profile=profile,
        facts=[fact, capacity_fact],
        status="intake",
    )
    catalog = load_rule_catalog()
    judgement_context = build_judgement_context(
        record,
        catalog,
        now=datetime(2026, 7, 31, tzinfo=UTC),
    )
    assert judgement_context.presentation_policy.policy_id == (
        "vedicdust-presentation-selection/1.0.0"
    )
    assert judgement_context.presentation_policy.score_semantics == (
        "presentation_salience_not_astrological_strength"
    )
    foundation_topic = next(
        topic for topic in judgement_context.topics if topic.topic_id == "foundation"
    )
    assert foundation_topic.priority_score == sum(
        reason.applied_points for reason in foundation_topic.priority_reasons
    )
    assert [reason.reason_code for reason in foundation_topic.priority_reasons] == ["baseline"]
    validate_judgement_context(record, judgement_context, catalog)
    presentation_policy_drift = judgement_context.model_copy(deep=True)
    presentation_policy_drift.presentation_policy.structural_topic_limit = 7  # type: ignore[assignment]
    with pytest.raises(ValueError, match="presentation policy does not match"):
        validate_judgement_context(record, presentation_policy_drift, catalog)
    directional_drift = judgement_context.model_copy(deep=True)
    directional_drift.units[0].findings[0].polarity = "supportive"
    with pytest.raises(ValueError, match="releases direction from non-directional rule"):
        validate_judgement_context(record, directional_drift, catalog)
    record.status = "ready_for_judgement"
    graph = build_claim_graph(record, judgement_context, generated_at=datetime.now(UTC))

    foundation_context = next(
        topic for topic in judgement_context.topics if topic.topic_id == "foundation"
    )
    assert fact.fact_id in foundation_context.natal_fact_ids
    assert capacity_fact.fact_id in foundation_context.capacity_fact_ids
    assert foundation_context.rule_ids == ["judge.foundation.integrated"]
    foundation_rule = next(
        rule for rule in judgement_context.rules if rule.rule_id == "judge.foundation.integrated"
    )
    assert foundation_rule.evaluation_status == "eligible"
    assert set(foundation_rule.matched_fact_ids) == {fact.fact_id, capacity_fact.fact_id}
    career_rule = next(
        rule for rule in judgement_context.rules if rule.rule_id == "judge.career.d1-d10"
    )
    assert career_rule.evaluation_status == "ineligible"
    assert career_rule.failed_predicates

    validate_claim_graph(record, graph, catalog, judgement_context)
    unready_record = record.model_copy(deep=True)
    unready_record.status = "intake"
    with pytest.raises(ValueError, match="status intake cannot publish claims"):
        validate_claim_graph(unready_record, graph, catalog, judgement_context)
    selection_drift = graph.model_copy(deep=True)
    selection_drift.claims[0].claim_id = "claim-arbitrary"
    with pytest.raises(ValueError, match="selection or ordering drifted"):
        validate_claim_graph(record, selection_drift, catalog, judgement_context)
    inflated_evidence = graph.model_copy(deep=True)
    inflated_evidence.claims[0].evidence_confidence = ConfidenceGrade.VERIFIED
    with pytest.raises(ValueError, match="evidence confidence does not match"):
        validate_claim_graph(record, inflated_evidence, catalog, judgement_context)
    inflated_certainty = graph.model_copy(deep=True)
    inflated_certainty.claims[0].certainty = "moderate"
    inflated_certainty.claims[0].status = "supported"
    with pytest.raises(ValueError, match="certainty does not match"):
        validate_claim_graph(record, inflated_certainty, catalog, judgement_context)
    duplicate_payload = graph.model_dump(by_alias=True)
    duplicate_claim = dict(duplicate_payload["claims"][0])
    duplicate_claim["claimId"] = "claim-duplicate"
    duplicate_payload["claims"].append(duplicate_claim)
    with pytest.raises(ValueError, match="cannot publish one conclusion more than once"):
        ClaimGraph.model_validate(duplicate_payload)
    rewritten = graph.model_copy(deep=True)
    rewritten.claims[0].technical_statement = "The model invented a stronger conclusion."
    with pytest.raises(ValueError, match="rewrites backend conclusion fields"):
        validate_claim_graph(record, rewritten, catalog, judgement_context)
    validate_chart_record_provenance(record, catalog)

    primary_claim_id = graph.claims[0].claim_id
    sections = [
        ReportSection(
            section_id=kind,
            section_kind=kind,
            title=kind.replace("_", " ").title(),
            purpose=f"Render {kind}",
            claim_ids=[primary_claim_id] if kind == "executive_synthesis" else [],
            priority=index,
        )
        for index, kind in enumerate(
            [
                "scope",
                "executive_synthesis",
                "chart_foundation",
                "timing_outlook",
                "decision_support",
                "follow_up",
                "technical_evidence",
            ]
        )
    ]
    dossier = ConsultationDossier(
        dossier_id="dossier-1",
        chart_record_id=record.chart_record_id,
        chart_revision=record.revision,
        method_profile_id=profile.profile_id,
        claim_graph_version=graph.schema_version,
        generated_at=datetime.now(UTC),
        locale="en",
        audience="self",
        scope=ConsultationScope(
            requested_topics=["foundation"],
            included_topics=["foundation"],
        ),
        confidence=ConsultationConfidence(
            overall="low",
            input_confidence=ConfidenceGrade.PROVISIONAL,
            rectification_confidence=ConfidenceGrade.PROVISIONAL,
            judgement_confidence="low",
            rationale=["The birth time remains approximate."],
        ),
        executive_claim_ids=[primary_claim_id],
        sections=sections,
        unresolved_questions=["What additional evidence would strengthen this claim?"],
        release_status="draft",
    )
    dossier = materialize_consultation_dossier(record, graph, judgement_context, dossier)
    assert dossier.release_status == "blocked"
    assert {check.check_id: check.status for check in dossier.quality_checks} == {
        "consultation.release-prerequisites": "passed",
        "consultation.claim-accounting": "passed",
        "consultation.report-structure": "failed",
    }
    validate_consultation_dossier(record, graph, dossier, judgement_context)
    confidence_drift = dossier.model_copy(deep=True)
    confidence_drift.confidence.overall = "high"
    with pytest.raises(ValueError, match="backend-owned confidence"):
        validate_consultation_dossier(record, graph, confidence_drift, judgement_context)
    release_drift = dossier.model_copy(deep=True)
    release_drift.release_status = "approved"
    with pytest.raises(ValueError, match="release status drifted"):
        validate_consultation_dossier(record, graph, release_drift, judgement_context)
    quality_drift = dossier.model_copy(deep=True)
    quality_drift.quality_checks = []
    with pytest.raises(ValueError, match="quality checks drifted"):
        validate_consultation_dossier(record, graph, quality_drift, judgement_context)
    with pytest.raises(ValueError, match="unapproved consultation dossier"):
        build_agent_context(record, graph, dossier)
    with pytest.raises(ValueError, match="unapproved consultation dossier"):
        render_consultation_report(record, graph, dossier)

    invalid = graph.model_copy(deep=True)
    invalid.claims[0].supporting_fact_ids = ["fact.missing"]
    with pytest.raises(ValueError, match="unknown fact"):
        validate_claim_graph(record, invalid, load_rule_catalog())

    context_drift = graph.model_copy(deep=True)
    context_drift.claims[0].context_fact_ids = []
    with pytest.raises(ValueError, match="rewrites backend conclusion fields: context facts"):
        validate_claim_graph(record, context_drift, catalog, judgement_context)

    invalid_semantics = graph.model_copy(deep=True)
    invalid_semantics.claims[0].judgement_code = "synthesize_relationship_d1_capacity_d9"
    with pytest.raises(ValueError, match="output code .* outside judgement unit"):
        validate_claim_graph(record, invalid_semantics, catalog, judgement_context)

    invalid_record = record.model_copy(deep=True)
    invalid_record.facts[0].provenance.source_ids = ["product.vedicdust-consultation-standard-1"]
    with pytest.raises(ValueError, match="source drift"):
        validate_chart_record_provenance(invalid_record, load_rule_catalog())

    overclaimed_record = record.model_copy(deep=True)
    overclaimed_record.facts[1].provenance = RuleProvenance(
        rule_id="derive.strength.shadbala-pyjhora",
        rule_version="1.1.0",
        method_profile_id=profile.profile_id,
        evidence_class="software_reference",
        source_ids=[
            "software.pyjhora.compatibility",
            "product.vedicdust-consultation-standard-1",
        ],
        confidence=ConfidenceGrade.CORROBORATED,
    )
    with pytest.raises(ValueError, match="overstates evidence confidence"):
        validate_chart_record_provenance(overclaimed_record, catalog)

    false_professional_review = record.model_copy(deep=True)
    review_interval = TimeRange(
        start=datetime(1990, 1, 1, 7, 55, tzinfo=UTC),
        end=datetime(1990, 1, 1, 8, 5, tzinfo=UTC),
    )
    false_professional_review.rectification = RectificationRecord(
        methodMaturity="professionally_validated",
        validationStatus="independent_professional_review",
        professionalReviewFixtureIds=["contract.rashi.whole-sign-house"],
        rectificationBenchmarkFixtureIds=["contract.workflow.d60-eligibility"],
        candidates=[
            CandidateInterval(
                candidateId="candidate-1",
                interval=review_interval,
                representativeMoment=review_interval.start,
                fingerprint="candidate-1-review-fingerprint",
            )
        ],
        decision=RectificationDecision(
            status="bounded_interval",
            selectedCandidateIds=["candidate-1"],
            resultingInterval=review_interval,
            confidence=ConfidenceGrade.CORROBORATED,
            holdoutResult="passed",
        ),
    )
    with pytest.raises(ValueError, match="is not a professional review fixture"):
        validate_chart_record_provenance(false_professional_review, catalog)

    generic_professional_review = ValidationFixtureReference(
        fixtureId="professional.generic-output-review",
        fixtureKind="professional_review",
        testNodes=[
            "backend/tests/test_vedicdust_contracts.py::"
            "test_claim_graph_references_chart_facts_and_registered_rules"
        ],
        description="Blind review of calculation and report judgement outputs only.",
        evidenceArtifactPath="reviews/generic-output-review.json",
        evidenceArtifactSha256="sha256:" + "0" * 64,
        reviewProtocolId="blind-output-review/1.0.0",
        reviewedBy="external-jyotishi-generic",
        reviewedAt="2026-08-03T00:00:00Z",
        reviewedCaseIds=["generic-review-1"],
        reviewScope="calculation_and_judgement",
    )
    monkeypatch.setattr(
        "app.vedicdust.validation.load_validation_fixture_registry",
        lambda: {generic_professional_review.fixture_id: generic_professional_review},
    )
    wrong_scope_review = false_professional_review.model_copy(deep=True)
    assert wrong_scope_review.rectification is not None
    wrong_scope_review.rectification.professional_review_fixture_ids = [
        generic_professional_review.fixture_id
    ]
    with pytest.raises(ValueError, match="does not review the rectification workflow"):
        validate_chart_record_provenance(wrong_scope_review, catalog)


def test_generated_json_schemas_are_current() -> None:
    from app.vedicdust.models import (
        AgentContext,
        ConsultationReportManifest,
        ConsultationDossier,
        ReadingSession,
        RuleCatalog,
        SynastryContext,
        ValidationFixtureRegistry,
    )
    from app.vedicdust.rectification_benchmark import (
        RectificationBenchmarkArtifact,
        RectificationBenchmarkBlindInput,
        RectificationBenchmarkReport,
        RectificationBenchmarkRunReceipt,
    )

    models = {
        "vedicdust-chart-record.schema.json": ChartRecord,
        "vedicdust-reading-session.schema.json": ReadingSession,
        "vedicdust-chart-audit.schema.json": ChartAudit,
        "vedicdust-claim-graph.schema.json": ClaimGraph,
        "vedicdust-judgement-context.schema.json": JudgementContext,
        "vedicdust-consultation-dossier.schema.json": ConsultationDossier,
        "vedicdust-agent-context.schema.json": AgentContext,
        "vedicdust-report-manifest.schema.json": ConsultationReportManifest,
        "vedicdust-rule-catalog.schema.json": RuleCatalog,
        "vedicdust-validation-fixtures.schema.json": ValidationFixtureRegistry,
        "vedicdust-rectification-benchmark.schema.json": RectificationBenchmarkArtifact,
        "vedicdust-rectification-benchmark-report.schema.json": RectificationBenchmarkReport,
        "vedicdust-rectification-blind-input.schema.json": RectificationBenchmarkBlindInput,
        "vedicdust-rectification-run-receipt.schema.json": RectificationBenchmarkRunReceipt,
        "vedicdust-synastry-context.schema.json": SynastryContext,
    }
    schema_root = ROOT / "docs" / "vedicdust" / "schemas"
    for filename, model in models.items():
        committed = json.loads((schema_root / filename).read_text(encoding="utf-8"))
        assert committed == model.model_json_schema(by_alias=True, mode="serialization")
