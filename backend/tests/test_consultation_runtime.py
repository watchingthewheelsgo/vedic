from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.services import skill_runtime as runtime_module
from app.services.skill_runtime import SkillRuntime
from app.services.skill_workspace import SkillWorkspace
from app.schemas import ConsultationAnswerResponse, ConsultationQuestionInput
from app.vedicdust.models import (
    AstronomySnapshot,
    BirthAssertion,
    CanonicalBirthMoment,
    ChartRecord,
    ClaimGraph,
    ConsultationConfidence,
    ConsultationDossier,
    ConsultationScope,
    EvidenceItem,
    GeoPoint,
    GroundedNarrative,
    InputSensitivityAssessment,
    JyotishFact,
    PlaceResolution,
    RuleProvenance,
    ReportSection,
    SubjectContext,
    ZodiacPosition,
)
from app.vedicdust.profiles import parashari_lahiri_profile


class ConsultationClock(datetime):
    instant = datetime(2026, 9, 6, 23, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.instant.astimezone(tz)


@pytest.fixture
def consultation_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(runtime_module, "datetime", ConsultationClock)
    monkeypatch.setattr(ConsultationClock, "instant", datetime(2026, 9, 6, 23, tzinfo=timezone.utc))
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    profile = parashari_lahiri_profile()
    evidence = EvidenceItem(
        evidenceId="birth-input",
        evidenceClass="user_testimony",
        sourceLabel="synthetic runtime fixture",
        observedValue="1990-01-01 08:00",
        confidence="corroborated",
    )
    record = ChartRecord(
        chartRecordId="chart-consultation-resume",
        readingSessionId=session_id,
        revision=1,
        createdAt=ConsultationClock.instant,
        subject=SubjectContext(subjectId="subject-consultation-resume"),
        birthAssertion=BirthAssertion(
            localDate="1990-01-01",
            reportedLocalTime="08:00",
            reportedPlace="Shanghai, China",
            timeCertainty="reported_exact",
            evidence=[evidence],
        ),
        canonicalMoment=CanonicalBirthMoment(
            localDatetime=datetime.fromisoformat("1990-01-01T08:00:00+08:00"),
            utcDatetime=datetime(1990, 1, 1, tzinfo=timezone.utc),
            timezoneId="Asia/Shanghai",
            utcOffsetSeconds=28800,
            historicalOffsetStatus="resolved",
            place=PlaceResolution(
                label="Shanghai, China",
                point=GeoPoint(latitudeDeg=31.23, longitudeDeg=121.47),
                precision="city",
                timezoneId="Asia/Shanghai",
                evidence=[evidence],
            ),
            resolutionConfidence="corroborated",
        ),
        astronomy=AstronomySnapshot(
            snapshotId="synthetic-snapshot",
            calculatedAt=ConsultationClock.instant,
            julianDayUt=2447892.5,
            calculationProvider="test",
            calculationAdapterVersion="test",
            ephemerisVersion="test",
            providerVersions={},
            timezoneDatabaseVersion="test",
            ephemerisDataFingerprint="sha256:" + "0" * 64,
            ayanamsaValueDeg=23.7,
            ascendant=ZodiacPosition(longitudeDeg=10, sign="Aries", signIndex=0, degreeInSign=10),
            grahas=[],
            status="partial",
        ),
        inputSensitivity=InputSensitivityAssessment(scanStatus="complete"),
        calculationProfile=profile,
        facts=[
            JyotishFact(
                factId="fact.D1.Lagna.position",
                factType="rashi.lagna.position",
                subjectRef="D1.Lagna",
                value=ZodiacPosition(
                    longitudeDeg=10, sign="Aries", signIndex=0, degreeInSign=10
                ).model_dump(by_alias=True),
                provenance=RuleProvenance(
                    ruleId="derive.astronomy.sidereal-position",
                    ruleVersion="1.0.0",
                    methodProfileId=profile.profile_id,
                    evidenceClass="astronomical_authority",
                    sourceIds=["astro.swisseph.programmer-manual"],
                    confidence="verified",
                ),
            ),
            JyotishFact(
                factId="fact.D1.H1.sav",
                factType="ashtakavarga.sav.house",
                subjectRef="D1.H1",
                value=30,
                unit="bindu",
                provenance=RuleProvenance(
                    ruleId="derive.ashtakavarga.pyjhora",
                    ruleVersion="1.0.0",
                    methodProfileId=profile.profile_id,
                    evidenceClass="software_reference",
                    sourceIds=["software.pyjhora.compatibility"],
                    confidence="corroborated",
                ),
            ),
        ],
        status="ready_for_judgement",
    )
    workspace.write_artifact(session_id, "chart_record.json", record.model_dump_json(by_alias=True))
    workspace.write_artifact(session_id, "chart_audit.json", '{"permittedNextSteps":["judge"]}')
    workspace.write_artifact(session_id, "reading_session.json", "{}")
    workspace.write_artifact(
        session_id,
        "chart_rectification_state.json",
        '{"status":"not_required","reportGate":{"fullReportAllowed":true}}',
    )
    runtime = cast(Any, SkillRuntime.__new__(SkillRuntime))
    runtime.workspace = workspace
    runtime.agent_runtime = None
    return runtime, session_id


def evidence_snapshot(runtime: Any, session_id: str) -> dict[str, str]:
    return {
        path: runtime.workspace.read_artifact_text(session_id, path)
        for path in (
            ".runtime/consultation-subject-context.json",
            "judgement_context.json",
            "claim_graph.json",
        )
    }


def test_judgement_retry_preserves_evidence_and_checkpoints(consultation_runtime) -> None:
    runtime, session_id = consultation_runtime
    runtime._prepare_judgement_context(session_id)
    before = evidence_snapshot(runtime, session_id)
    workspace = runtime.workspace
    workspace.write_artifact(session_id, "consultation_report.md", "Previous report")
    workspace.mark_artifact_checkpoint(
        session_id,
        "consultation_report.md",
        producer="test-consultation",
        dependency_paths=list(before),
    )

    ConsultationClock.instant = datetime(2026, 9, 7, 10, tzinfo=timezone.utc)
    runtime._prepare_judgement_context(session_id)

    assert evidence_snapshot(runtime, session_id) == before
    assert workspace.artifact_checkpoint_valid(
        session_id,
        "consultation_report.md",
        producer="test-consultation",
        dependency_paths=list(before),
    )


@pytest.mark.parametrize("change", ["date", "topic", "subject", "chart", "fact"])
def test_judgement_refreshes_changed_inputs(consultation_runtime, change: str) -> None:
    runtime, session_id = consultation_runtime
    runtime._prepare_judgement_context(session_id)
    before = evidence_snapshot(runtime, session_id)
    workspace = runtime.workspace
    workspace.write_artifact(session_id, "consultation_report.md", "Previous report")
    workspace.mark_artifact_checkpoint(
        session_id,
        "consultation_report.md",
        producer="test-consultation",
        dependency_paths=list(before),
    )
    if change == "date":
        ConsultationClock.instant = datetime(2026, 9, 7, 16, tzinfo=timezone.utc)
    elif change == "topic":
        workspace.write_artifact(
            session_id,
            ".runtime/consultation-topic-selection.json",
            '{"selectedTopicIds":["career"]}',
        )
    else:
        record = ChartRecord.model_validate_json(
            workspace.read_artifact_text(session_id, "chart_record.json")
        )
        if change == "subject":
            record.subject.display_name = "Updated name"
        elif change == "chart":
            record.revision += 1
        else:
            record.facts[1].value = 25
        workspace.write_artifact(
            session_id, "chart_record.json", record.model_dump_json(by_alias=True)
        )
    runtime._prepare_judgement_context(session_id)

    if change != "fact":
        assert evidence_snapshot(runtime, session_id) != before
    assert not workspace.artifact_checkpoint_valid(
        session_id,
        "consultation_report.md",
        producer="test-consultation",
        dependency_paths=list(before),
    )


def test_finalization_does_not_rebuild_evidence_even_when_dossier_is_invalid(
    consultation_runtime,
) -> None:
    runtime, session_id = consultation_runtime
    runtime._prepare_judgement_context(session_id)
    before = evidence_snapshot(runtime, session_id)
    runtime.workspace.write_artifact(session_id, "consultation_dossier.json", "{}")
    ConsultationClock.instant = datetime(2026, 9, 8, 1, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="ConsultationDossier"):
        asyncio.run(runtime._finalize_consultation_artifacts(session_id))

    assert evidence_snapshot(runtime, session_id) == before
    assert runtime.workspace.read_artifact_text(session_id, "consultation_report.md") is None


def test_finalization_rechecks_pending_confirmation(consultation_runtime) -> None:
    runtime, session_id = consultation_runtime
    runtime._prepare_judgement_context(session_id)
    before = evidence_snapshot(runtime, session_id)
    runtime.workspace.write_artifact(session_id, "consultation_dossier.json", "{}")
    runtime.workspace.write_artifact(
        session_id,
        "chart_rectification_state.json",
        '{"status":"rectification_confirmation_required"}',
    )

    with pytest.raises(ValueError, match="阶段性的生时校正结论"):
        asyncio.run(runtime._finalize_consultation_artifacts(session_id))

    assert evidence_snapshot(runtime, session_id) == before


def test_new_question_with_same_topic_invalidates_report_checkpoint(consultation_runtime) -> None:
    runtime, session_id = consultation_runtime

    class TopicAgent:
        def is_configured(self):
            return True

        async def run_structured_reasoning_task(self, *_args, **_kwargs):
            return SimpleNamespace(raw_text='{"topicIds":["career"],"rationale":"Career question"}')

    runtime.agent_runtime = TopicAgent()
    dependencies = runtime._core_batch_dependency_paths("vedicdust_consultation")
    asyncio.run(runtime._ensure_consultation_topic_selection(session_id, "Should I change jobs?"))
    runtime._prepare_judgement_context(session_id)
    before = evidence_snapshot(runtime, session_id)
    runtime.workspace.write_artifact(session_id, "consultation_dossier.json", "Previous dossier")
    runtime.workspace.mark_artifact_checkpoint(
        session_id,
        "consultation_dossier.json",
        producer="vedic-core:vedicdust_consultation",
        dependency_paths=dependencies,
    )
    asyncio.run(runtime._ensure_consultation_topic_selection(session_id, "Should I change jobs?"))
    assert runtime.workspace.artifact_checkpoint_valid(
        session_id,
        "consultation_dossier.json",
        producer="vedic-core:vedicdust_consultation",
        dependency_paths=dependencies,
    )

    asyncio.run(
        runtime._ensure_consultation_topic_selection(
            session_id, "How should I approach starting a business?"
        )
    )
    runtime._prepare_judgement_context(session_id)

    assert evidence_snapshot(runtime, session_id) == before
    assert not runtime.workspace.artifact_checkpoint_valid(
        session_id,
        "consultation_dossier.json",
        producer="vedic-core:vedicdust_consultation",
        dependency_paths=dependencies,
    )


@pytest.fixture
def narrative_audit(consultation_runtime):
    runtime, session_id = consultation_runtime
    runtime._prepare_judgement_context(session_id)
    graph = ClaimGraph.model_validate_json(
        runtime.workspace.read_artifact_text(session_id, "claim_graph.json")
    )
    claim_id = graph.claims[0].claim_id
    dossier = ConsultationDossier(
        dossierId="dossier-audit",
        chartRecordId=graph.chart_record_id,
        chartRevision=graph.chart_revision,
        methodProfileId=graph.method_profile_id,
        claimGraphVersion=graph.schema_version,
        generatedAt=graph.generated_at,
        locale="en",
        audience="self",
        scope=ConsultationScope(),
        confidence=ConsultationConfidence(
            overall="low",
            inputConfidence="provisional",
            rectificationConfidence="provisional",
            judgementConfidence="low",
            rationale=["Synthetic lifecycle fixture"],
        ),
        sections=[
            ReportSection(
                sectionId="foundation",
                sectionKind="chart_foundation",
                title="Foundation",
                purpose="Explain foundation",
                claimIds=[claim_id],
                narratives=[
                    GroundedNarrative(
                        narrativeId="narrative-foundation",
                        kind="integration",
                        claimIds=[claim_id],
                        text="These chart patterns should be considered together with the stated limitations.",
                    )
                ],
            )
        ],
        releaseStatus="draft",
    )
    runtime.workspace.write_artifact(
        session_id, "consultation_dossier.json", dossier.model_dump_json(by_alias=True)
    )

    class AuditAgent:
        def __init__(self):
            self.calls = 0
            self.verdict = {
                "supported": True,
                "unsafeCertainty": False,
                "unsupportedStatements": [],
            }

        def is_configured(self):
            return True

        async def run_skill_prompt_task(self, *_args, **_kwargs):
            self.calls += 1
            return SimpleNamespace(raw_text=json.dumps(self.verdict))

    agent = AuditAgent()
    runtime.agent_runtime = agent

    async def audit_prompt(*_args, **_kwargs):
        agent.calls += 1
        return SimpleNamespace(
            raw_text=json.dumps(
                {"results": [{"narrativeId": "narrative-foundation", **agent.verdict}]}
            )
        )

    runtime._run_bounded_audit_prompt = audit_prompt
    return runtime, session_id, dossier, graph, agent


@pytest.mark.parametrize("change", ["graph", "dossier"])
def test_narrative_audit_cache_tracks_all_audited_evidence(narrative_audit, change: str) -> None:
    runtime, session_id, dossier, graph, agent = narrative_audit
    asyncio.run(runtime._audit_consultation_narratives(session_id, dossier, graph))
    asyncio.run(runtime._audit_consultation_narratives(session_id, dossier, graph))
    assert agent.calls == 1
    if change == "graph":
        graph.claims[0].plain_statement = "The available evidence is now more limited."
        runtime.workspace.write_artifact(
            session_id, "claim_graph.json", graph.model_dump_json(by_alias=True)
        )
    else:
        dossier.sections[0].narratives[
            0
        ].text = "This revised paragraph requires its own grounding review."
        runtime.workspace.write_artifact(
            session_id, "consultation_dossier.json", dossier.model_dump_json(by_alias=True)
        )
    asyncio.run(runtime._audit_consultation_narratives(session_id, dossier, graph))
    assert agent.calls == 2


def test_missing_auditor_cannot_approve_unaudited_prose(narrative_audit) -> None:
    runtime, session_id, dossier, graph, _agent = narrative_audit
    runtime.agent_runtime = None
    with pytest.raises(ValueError, match="audit"):
        asyncio.run(runtime._audit_consultation_narratives(session_id, dossier, graph))


@pytest.mark.parametrize("evidence_changed", [False, True])
def test_only_current_audit_can_be_reused_without_a_configured_agent(
    narrative_audit, evidence_changed: bool
) -> None:
    runtime, session_id, dossier, graph, agent = narrative_audit
    asyncio.run(runtime._audit_consultation_narratives(session_id, dossier, graph))
    runtime.agent_runtime = None
    if evidence_changed:
        graph.claims[0].plain_statement = "The supporting evidence has changed."
        runtime.workspace.write_artifact(
            session_id, "claim_graph.json", graph.model_dump_json(by_alias=True)
        )
        with pytest.raises(ValueError, match="audit"):
            asyncio.run(runtime._audit_consultation_narratives(session_id, dossier, graph))
    else:
        asyncio.run(runtime._audit_consultation_narratives(session_id, dossier, graph))
    assert agent.calls == 1


@pytest.mark.parametrize("target", ["narrative", "answer"])
@pytest.mark.parametrize(
    "verdict",
    [
        {"supported": True},
        {"supported": True, "unsafeCertainty": "true", "unsupportedStatements": []},
        {
            "supported": True,
            "unsafeCertainty": False,
            "unsupportedStatements": ["Invented prediction"],
        },
        {"supported": True, "unsafeCertainty": False, "unsupportedStatements": "none"},
    ],
)
def test_grounding_rejects_incomplete_or_contradictory_verdicts(
    narrative_audit, target: str, verdict: dict
) -> None:
    runtime, session_id, dossier, graph, agent = narrative_audit
    agent.verdict = verdict
    with pytest.raises(ValueError):
        if target == "narrative":
            asyncio.run(runtime._audit_consultation_narratives(session_id, dossier, graph))
        else:
            asyncio.run(
                runtime._audit_consultation_answer(
                    question="What does this pattern mean?",
                    response=ConsultationAnswerResponse(
                        answerability="answered",
                        answer=dossier.sections[0].narratives[0].text,
                        supportingClaimIds=[graph.claims[0].claim_id],
                        limitations=[],
                        followUpQuestions=[],
                    ),
                    context={"approvedClaims": [graph.claims[0].model_dump(by_alias=True)]},
                    locale="en",
                )
            )
    assert agent.calls == (
        1 if verdict.get("unsupportedStatements") == ["Invented prediction"] else 2
    )


@pytest.mark.parametrize("target", ["narrative", "answer"])
def test_grounding_can_recover_from_incomplete_verdict(narrative_audit, target: str) -> None:
    runtime, session_id, dossier, graph, agent = narrative_audit

    async def audit_prompt(*_args, **_kwargs):
        agent.calls += 1
        verdict = {"supported": True} if agent.calls == 1 else agent.verdict
        payload = (
            {"results": [{"narrativeId": "narrative-foundation", **verdict}]}
            if target == "narrative"
            else verdict
        )
        return SimpleNamespace(raw_text=json.dumps(payload))

    runtime._run_bounded_audit_prompt = audit_prompt
    agent.run_skill_prompt_task = audit_prompt
    if target == "narrative":
        asyncio.run(runtime._audit_consultation_narratives(session_id, dossier, graph))
    else:
        asyncio.run(
            runtime._audit_consultation_answer(
                question="What does this pattern mean?",
                response=ConsultationAnswerResponse(
                    answerability="answered",
                    answer=dossier.sections[0].narratives[0].text,
                    supportingClaimIds=[graph.claims[0].claim_id],
                    limitations=[],
                    followUpQuestions=[],
                ),
                context={"approvedClaims": [graph.claims[0].model_dump(by_alias=True)]},
                locale="en",
            )
        )
    assert agent.calls == 2


@pytest.mark.parametrize(
    "stale_dependency",
    [
        None,
        "claim_graph.json",
        "consultation_dossier.json",
        "chart_record.json",
        "pending_confirmation",
        "current",
    ],
)
def test_followup_requires_current_rendered_artifacts(
    narrative_audit, stale_dependency: str | None
) -> None:
    runtime, session_id, dossier, graph, agent = narrative_audit
    # Schema approval alone must not substitute for verified publication receipts.
    payload = dossier.model_dump(by_alias=True, mode="json")
    payload["releaseStatus"] = "approved"
    payload["executiveClaimIds"] = ["claim-a", "claim-b", "claim-c"]
    payload["sections"] = [
        ReportSection(
            sectionId=kind,
            sectionKind=kind,
            title=kind,
            purpose=kind,
            claimIds=["claim-a", "claim-b", "claim-c"]
            if kind in {"executive_synthesis", "chart_foundation", "decision_support"}
            else [],
        ).model_dump(by_alias=True, mode="json")
        for kind in [
            "scope",
            "executive_synthesis",
            "chart_foundation",
            "timing_outlook",
            "decision_support",
            "follow_up",
            "technical_evidence",
        ]
    ]
    approved = ConsultationDossier.model_validate(payload)
    workspace = runtime.workspace
    workspace.write_artifact(
        session_id, "consultation_dossier.json", approved.model_dump_json(by_alias=True)
    )
    workspace.write_artifact(session_id, "agent_context.json", '{"approvedClaims":[]}')
    if stale_dependency is not None:
        for path in [
            "consultation_report.md",
            "consultation_report_manifest.json",
            "agent_context.json",
        ]:
            if path != "agent_context.json":
                workspace.write_artifact(session_id, path, "Old published content")
            workspace.mark_artifact_checkpoint(
                session_id,
                path,
                producer="vedicdust-consultation-renderer",
                dependency_paths=[
                    "judgement_context.json",
                    "claim_graph.json",
                    "consultation_dossier.json",
                ],
            )
        assert runtime._consultation_artifacts_complete(session_id)
        if stale_dependency == "pending_confirmation":
            workspace.write_artifact(
                session_id,
                "chart_rectification_state.json",
                '{"status":"rectification_confirmation_required"}',
            )
        elif stale_dependency != "current":
            content = workspace.read_artifact_text(session_id, stale_dependency)
            workspace.write_artifact(session_id, stale_dependency, content + "\n")
    question = ConsultationQuestionInput(
        sessionId=session_id, question="How should I interpret this report?"
    )
    if stale_dependency == "current":
        agent.verdict = {
            "answerability": "insufficient_evidence",
            "answer": "The report does not contain enough evidence to answer this question.",
            "supportingClaimIds": [],
            "limitations": ["The published report contains no claims addressing this question."],
            "followUpQuestions": [],
        }
        response = asyncio.run(runtime.answer_consultation_question(question))
        assert response.answerability == "insufficient_evidence"
        assert agent.calls == 1
        return
    expected_error = (
        "阶段性的生时校正结论"
        if stale_dependency == "pending_confirmation"
        else "approved consultation must be completed"
    )
    with pytest.raises(ValueError, match=expected_error):
        asyncio.run(runtime.answer_consultation_question(question))
    assert agent.calls == 0


def test_narrative_audit_serializes_timing_claims(narrative_audit) -> None:
    from app.vedicdust.models import TimeRange

    runtime, session_id, dossier, graph, agent = narrative_audit
    graph.claims[0].time_scope = TimeRange(
        start=datetime(2027, 1, 1, tzinfo=timezone.utc),
        end=datetime(2028, 1, 1, tzinfo=timezone.utc),
    )
    asyncio.run(runtime._audit_consultation_narratives(session_id, dossier, graph))
    assert agent.calls == 1
