from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from .confidence import effective_fact_confidence, effective_timing_confidence, minimum_confidence
from .models import (
    ChartRecord,
    Claim,
    ClaimGraph,
    ConfidenceGrade,
    JudgementConclusion,
    JudgementContext,
    JudgementUnit,
    QualityCheck,
)
from .presentation_policy import selected_topic_ids


Certainty = Literal["high", "moderate", "low"]
_CERTAINTY_RANK: dict[Certainty, int] = {"low": 0, "moderate": 1, "high": 2}
_CONFIDENCE_CAP: dict[ConfidenceGrade, Certainty] = {
    ConfidenceGrade.VERIFIED: "high",
    ConfidenceGrade.CORROBORATED: "moderate",
    ConfidenceGrade.PROVISIONAL: "low",
    ConfidenceGrade.DISPUTED: "low",
    ConfidenceGrade.UNAVAILABLE: "low",
}


def build_claim_graph(
    record: ChartRecord,
    context: JudgementContext,
    *,
    generated_at: datetime | None = None,
) -> ClaimGraph:
    """Publish backend conclusions without asking a model to reproduce their semantics."""

    if record.status not in {"ready_for_judgement", "rectified"}:
        raise ValueError(f"chart record status {record.status} cannot publish claims")
    if any(check.status == "failed" for check in context.quality_checks):
        raise ValueError("judgement context contains failed quality checks")

    topics_by_id = {topic.topic_id: topic for topic in context.topics}
    units_by_topic = {unit.topic_id: unit for unit in context.units}
    ordered_topic_ids = selected_topic_ids(context)
    policy = context.presentation_policy
    claims: list[Claim] = []
    for topic_id in ordered_topic_ids:
        unit = units_by_topic[topic_id]
        structural = next(
            (conclusion for conclusion in unit.conclusions if conclusion.scope != "timing"),
            None,
        )
        if structural is not None:
            claims.append(_claim(record, unit, structural))

    for topic_id in ordered_topic_ids:
        topic = topics_by_id[topic_id]
        if (policy.timing_claims_for_requested_topics_only and not topic.requested) or len(
            claims
        ) >= policy.total_claim_limit:
            continue
        unit = units_by_topic[topic_id]
        timing = next(
            (conclusion for conclusion in unit.conclusions if conclusion.scope == "timing"),
            None,
        )
        if timing is not None:
            claims.append(_claim(record, unit, timing))

    selected_topics = {claim.topic for claim in claims}
    omitted_topics = {
        topic_id: "No eligible backend judgement conclusion passed the current evidence gate."
        for topic_id in context.requested_topics
        if topic_id not in selected_topics
    }
    required_count = min(policy.minimum_structural_coverage, len(context.units))
    coverage_ok = len(claims) >= required_count
    request_coverage_ok = not omitted_topics
    return ClaimGraph(
        chart_record_id=record.chart_record_id,
        chart_revision=record.revision,
        method_profile_id=record.calculation_profile.profile_id,
        rule_pack_version=context.rule_pack_version,
        generated_at=generated_at or context.generated_at,
        claims=claims,
        omitted_topics=omitted_topics,
        quality_checks=[
            QualityCheck(
                check_id="claim-graph.synthesis-coverage",
                status="passed" if coverage_ok else "failed",
                expected=required_count,
                observed=len(claims),
                message=(
                    "The deterministic claim graph covers the available synthesis scope."
                    if coverage_ok
                    else "The deterministic claim graph has insufficient synthesis coverage."
                ),
            ),
            QualityCheck(
                check_id="claim-graph.requested-topic-coverage",
                status="passed" if request_coverage_ok else "warning",
                expected=context.requested_topics,
                observed=sorted(selected_topics & set(context.requested_topics)),
                message=(
                    "All recognized requested topics have eligible conclusions."
                    if request_coverage_ok
                    else "One or more requested topics remain omitted with an explicit reason."
                ),
            ),
        ],
    )


def _claim(
    record: ChartRecord,
    unit: JudgementUnit,
    conclusion: JudgementConclusion,
) -> Claim:
    evidence_confidence = _claim_evidence_confidence(record, conclusion)
    certainty = bounded_claim_certainty(
        record,
        conclusion.certainty_cap,
        evidence_confidence=evidence_confidence,
    )
    suffix = "timing" if conclusion.scope == "timing" else "structure"
    return Claim(
        claim_id=f"claim.{unit.topic_id}.{suffix}",
        topic=unit.topic_id,
        judgement_unit_id=unit.unit_id,
        conclusion_id=conclusion.conclusion_id,
        judgement_code=conclusion.conclusion_code,
        title=conclusion.title,
        plain_statement=conclusion.plain_statement,
        technical_statement=conclusion.technical_statement,
        real_world_expressions=conclusion.real_world_expressions,
        user_relevance=conclusion.user_relevance,
        conditions=conclusion.conditions,
        supporting_fact_ids=conclusion.supporting_fact_ids,
        context_fact_ids=conclusion.context_fact_ids,
        counter_fact_ids=conclusion.counter_fact_ids,
        counter_statements=conclusion.counter_statements,
        timing_fact_ids=conclusion.timing_fact_ids,
        timing_period_ids=conclusion.timing_period_ids,
        rule_ids=conclusion.rule_ids,
        evidence_confidence=evidence_confidence,
        certainty=certainty,
        scope=conclusion.scope,
        status="tentative" if certainty == "low" else "supported",
        time_scope=conclusion.time_scope,
        practical_implications=conclusion.practical_implications,
        limitations=conclusion.limitations,
    )


def _claim_evidence_confidence(
    record: ChartRecord,
    conclusion: JudgementConclusion,
) -> ConfidenceGrade:
    facts_by_id = {fact.fact_id: fact for fact in record.facts}
    periods_by_id = {period.period_id: period for period in record.timing_periods}
    referenced_fact_ids = list(
        dict.fromkeys(
            conclusion.supporting_fact_ids
            + conclusion.context_fact_ids
            + conclusion.counter_fact_ids
            + conclusion.timing_fact_ids
        )
    )
    grades = [
        effective_fact_confidence(facts_by_id[fact_id])
        if fact_id in facts_by_id
        else ConfidenceGrade.UNAVAILABLE
        for fact_id in referenced_fact_ids
    ]
    grades.extend(
        effective_timing_confidence(periods_by_id[period_id])
        if period_id in periods_by_id
        else ConfidenceGrade.UNAVAILABLE
        for period_id in conclusion.timing_period_ids
    )
    return minimum_confidence(*grades)


def bounded_claim_certainty(
    record: ChartRecord,
    conclusion_cap: Certainty,
    *,
    evidence_confidence: ConfidenceGrade,
) -> Certainty:
    confidence_grades = [
        record.canonical_moment.resolution_confidence
        if record.canonical_moment is not None
        else ConfidenceGrade.UNAVAILABLE,
        evidence_confidence,
    ]
    if record.rectification is not None:
        confidence_grades.append(record.rectification.decision.confidence)
    input_cap = min(
        (_CONFIDENCE_CAP[grade] for grade in confidence_grades),
        key=lambda certainty: _CERTAINTY_RANK[certainty],
    )
    return cast(
        Certainty,
        min(
            (conclusion_cap, input_cap),
            key=lambda certainty: _CERTAINTY_RANK[certainty],
        ),
    )
