from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.vedicdust.models import (
    AstronomySnapshot,
    AuditFinding,
    BirthAssertion,
    CandidateInterval,
    ChartAudit,
    ChartRecord,
    Claim,
    ClaimGraph,
    ConfidenceGrade,
    ConsultationConfidence,
    ConsultationDossier,
    ConsultationScope,
    EvidenceClass,
    EvidenceItem,
    GrahaPosition,
    JyotishFact,
    JudgementContext,
    ReportSection,
    RuleProvenance,
    SubjectContext,
    TimeRange,
    ZodiacPosition,
)
from app.vedicdust.profiles import parashari_lahiri_profile
from app.vedicdust.judgement import build_judgement_context
from app.vedicdust.reporting import build_agent_context, render_consultation_report
from app.vedicdust.source_registry import (
    load_rule_catalog,
    load_source_registry,
    validate_profile_source_ids,
    validate_rule_catalog_sources,
)
from app.vedicdust.validation import (
    validate_agent_context,
    validate_chart_record_provenance,
    validate_claim_graph,
    validate_consultation_dossier,
    validate_judgement_context,
)


UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]


def _position(longitude: float = 10.0) -> ZodiacPosition:
    return ZodiacPosition(
        longitude_deg=longitude,
        sign="Aries",
        sign_index=0,
        degree_in_sign=longitude,
    )


def test_product_profile_has_no_unregistered_sources() -> None:
    profile = parashari_lahiri_profile()
    validate_profile_source_ids(profile.source_ids)

    assert profile.profile_id == "parashari-lahiri-1.0.0"
    assert profile.ayanamsa.model == "lahiri"
    assert profile.node_model == "mean"
    assert profile.rashi_house_model == "whole_sign"
    assert profile.dasha_year_days == pytest.approx(365.256364)
    assert set(profile.supported_vargas) == {1, 2, 3, 4, 5, 7, 9, 10, 12, 16, 20, 24, 27, 30, 60}


def test_source_registry_distinguishes_authority_from_pending_classics() -> None:
    registry = load_source_registry()

    assert registry["astro.swisseph.programmer-manual"].citation_status == "pinned"
    assert registry["classic.bphs.pending-edition"].citation_status == "pending-edition-pin"
    assert registry["software.pyjhora.compatibility"].citation_status == "informational"


def test_rule_catalog_is_unique_and_uses_registered_sources() -> None:
    catalog = load_rule_catalog()
    validate_rule_catalog_sources(catalog)

    assert catalog.catalog_version == "1.1.0"
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
        "judge.learning.d1-d5-d24",
        "judge.children.d1-d7",
        "judge.health.d1-d30",
        "judge.dharma.d1-d9-d20",
        "judge.family.d1-d12",
        "judge.timing.vimshottari-activation",
    } <= rule_ids
    assert {
        "derive.astronomy.sidereal-position",
        "derive.rashi.whole-sign-house",
        "derive.varga.parashara-method-1",
        "derive.strength.dignity",
        "derive.strength.shadbala-pyjhora",
        "derive.ashtakavarga.pyjhora",
        "derive.aspect.parashari-graha-drishti",
        "derive.timing.vimshottari-pyjhora",
    } <= rule_ids
    workflow_rules = [rule for rule in catalog.rules if rule.rule_id.startswith("sop.")]
    assert all(rule.evidence_class == EvidenceClass.PRODUCT_HYPOTHESIS for rule in workflow_rules)


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


def test_claim_graph_references_chart_facts_and_registered_rules() -> None:
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
    graph = ClaimGraph(
        chart_record_id=record.chart_record_id,
        method_profile_id=profile.profile_id,
        rule_pack_version="vedicdust-rules-1.1.0",
        generated_at=datetime.now(UTC),
        claims=[
            Claim(
                claim_id=f"claim-{index}",
                topic="foundation",
                plain_statement=(
                    "The chart contains a provisional relationship promise."
                    if index == 1
                    else f"Relationship synthesis {index} remains provisional."
                ),
                technical_statement="D1 promise is present; confirmation is still required.",
                supporting_fact_ids=[fact.fact_id, capacity_fact.fact_id],
                rule_ids=["judge.foundation.integrated"],
                certainty="low",
                scope="natal_promise",
            )
            for index in range(1, 6)
        ],
    )

    catalog = load_rule_catalog()
    judgement_context = build_judgement_context(
        record,
        catalog,
        now=datetime(2026, 7, 31, tzinfo=UTC),
    )
    validate_judgement_context(record, judgement_context, catalog)
    foundation_context = next(
        topic for topic in judgement_context.topics if topic.topic_id == "foundation"
    )
    assert fact.fact_id in foundation_context.natal_fact_ids
    assert capacity_fact.fact_id in foundation_context.capacity_fact_ids
    assert foundation_context.rule_ids == ["judge.foundation.integrated"]

    validate_claim_graph(record, graph, catalog, judgement_context)
    validate_chart_record_provenance(record, catalog)

    sections = [
        ReportSection(
            section_id=kind,
            section_kind=kind,
            title=kind.replace("_", " ").title(),
            purpose=f"Render {kind}",
            claim_ids=(
                ["claim-1", "claim-2", "claim-3"]
                if kind == "executive_synthesis"
                else ["claim-4"]
                if kind == "chart_foundation"
                else ["claim-5"]
                if kind == "decision_support"
                else []
            ),
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
        executive_claim_ids=["claim-1", "claim-2", "claim-3"],
        sections=sections,
        unresolved_questions=["What additional evidence would strengthen this claim?"],
        release_status="approved",
    )
    validate_consultation_dossier(record, graph, dossier)
    context = build_agent_context(record, graph, dossier)
    validate_agent_context(record, graph, dossier, context)
    report = render_consultation_report(record, graph, dossier)
    assert "# VedicDust Consultation" in report
    assert "The chart contains a provisional relationship promise." in report
    assert context.topic_index == {
        "foundation": [
            "claim-1",
            "claim-2",
            "claim-3",
            "claim-4",
            "claim-5",
        ]
    }

    invalid = graph.model_copy(deep=True)
    invalid.claims[0].supporting_fact_ids = ["fact.missing"]
    with pytest.raises(ValueError, match="unknown fact"):
        validate_claim_graph(record, invalid, load_rule_catalog())

    invalid_record = record.model_copy(deep=True)
    invalid_record.facts[0].provenance.source_ids = ["product.vedicdust-consultation-standard-1"]
    with pytest.raises(ValueError, match="source drift"):
        validate_chart_record_provenance(invalid_record, load_rule_catalog())


def test_generated_json_schemas_are_current() -> None:
    from app.vedicdust.models import (
        AgentContext,
        ConsultationReportManifest,
        ConsultationDossier,
        ReadingSession,
        RectificationAnswerBatch,
        RectificationQuestionSet,
        RuleCatalog,
    )

    models = {
        "vedicdust-chart-record.schema.json": ChartRecord,
        "vedicdust-reading-session.schema.json": ReadingSession,
        "vedicdust-chart-audit.schema.json": ChartAudit,
        "vedicdust-question-set.schema.json": RectificationQuestionSet,
        "vedicdust-answer-batch.schema.json": RectificationAnswerBatch,
        "vedicdust-claim-graph.schema.json": ClaimGraph,
        "vedicdust-judgement-context.schema.json": JudgementContext,
        "vedicdust-consultation-dossier.schema.json": ConsultationDossier,
        "vedicdust-agent-context.schema.json": AgentContext,
        "vedicdust-report-manifest.schema.json": ConsultationReportManifest,
        "vedicdust-rule-catalog.schema.json": RuleCatalog,
    }
    schema_root = ROOT / "docs" / "vedicdust" / "schemas"
    for filename, model in models.items():
        committed = json.loads((schema_root / filename).read_text(encoding="utf-8"))
        assert committed == model.model_json_schema(by_alias=True, mode="serialization")
