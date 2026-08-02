from __future__ import annotations

from .models import (
    JudgementContext,
    JudgementPresentationPolicy,
    PresentationPriorityReason,
)


ACTIVE_PRESENTATION_POLICY = JudgementPresentationPolicy()


def build_topic_presentation_priority(
    *,
    topic_id: str,
    requested: bool,
    sav_evidence: list[tuple[str, float]],
    aspect_fact_ids: list[str],
    eligible_varga_fact_ids: list[str],
) -> tuple[int, list[PresentationPriorityReason]]:
    """Return deterministic report salience; this is not a Jyotish strength measure."""

    policy = ACTIVE_PRESENTATION_POLICY
    score = policy.foundation_baseline if topic_id == "foundation" else policy.domain_baseline
    reasons = [
        PresentationPriorityReason(
            reason_code="baseline",
            applied_points=score,
            detail=(
                "The chart foundation receives near-mandatory report prominence."
                if topic_id == "foundation"
                else "Every eligible consultation domain starts with neutral presentation salience."
            ),
        )
    ]
    if requested:
        boost = policy.requested_topic_target - score
        if boost:
            reasons.append(
                PresentationPriorityReason(
                    reason_code="requested_topic",
                    applied_points=boost,
                    detail="The user explicitly requested this consultation domain.",
                )
            )
        return policy.requested_topic_target, reasons

    if topic_id != "foundation":
        sav_points = min(
            policy.sav_deviation_cap,
            round(
                (
                    sum(abs(value - policy.sav_neutral_reference) for _, value in sav_evidence)
                    / len(sav_evidence)
                    if sav_evidence
                    else 0.0
                )
                * policy.sav_deviation_multiplier
            ),
        )
        if sav_points:
            reasons.append(
                PresentationPriorityReason(
                    reason_code="sav_deviation_salience",
                    applied_points=sav_points,
                    evidence_fact_ids=sorted(fact_id for fact_id, _ in sav_evidence),
                    detail=(
                        "House-capacity values are unusually far from the neutral SAV reference; "
                        "this raises report salience without assigning a favourable direction."
                    ),
                )
            )
            score += sav_points
        aspect_points = min(
            policy.aspect_points_cap,
            len(aspect_fact_ids) * policy.aspect_points_per_fact,
        )
        if aspect_points:
            reasons.append(
                PresentationPriorityReason(
                    reason_code="natal_aspect_salience",
                    applied_points=aspect_points,
                    evidence_fact_ids=sorted(aspect_fact_ids),
                    detail=(
                        "The domain has multiple D1 graha-drishti links; this raises report "
                        "salience without treating aspect count as strength."
                    ),
                )
            )
            score += aspect_points

    varga_points = (
        min(policy.eligible_varga_boost, policy.requested_topic_target - score)
        if eligible_varga_fact_ids
        else 0
    )
    if varga_points:
        reasons.append(
            PresentationPriorityReason(
                reason_code="eligible_varga",
                applied_points=varga_points,
                evidence_fact_ids=sorted(eligible_varga_fact_ids),
                detail=(
                    "A birth-time-eligible domain varga is available for corroboration, so the "
                    "domain can support a more complete explanation."
                ),
            )
        )
        score += varga_points
    return score, reasons


def selected_topic_ids(context: JudgementContext) -> list[str]:
    """Apply the serialized presentation policy to eligible judgement topics."""

    policy = context.presentation_policy
    topics_by_id = {topic.topic_id: topic for topic in context.topics}
    available = {unit.topic_id for unit in context.units}
    ordered: list[str] = []

    def add(topic_id: str) -> None:
        if topic_id in available and topic_id not in ordered:
            ordered.append(topic_id)

    if policy.foundation_always_included:
        add("foundation")
    if policy.requested_topics_first:
        for topic in sorted(
            (topic for topic in context.topics if topic.requested),
            key=lambda item: (-item.priority_score, item.topic_id),
        ):
            add(topic.topic_id)
    target_count = min(policy.structural_topic_limit, len(available))
    for topic in sorted(
        topics_by_id.values(), key=lambda item: (-item.priority_score, item.topic_id)
    ):
        if len(ordered) >= target_count:
            break
        add(topic.topic_id)
    return ordered[: policy.total_claim_limit]
