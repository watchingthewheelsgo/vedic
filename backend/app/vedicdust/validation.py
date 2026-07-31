from __future__ import annotations

from .fact_catalog import fact_definition
from .models import (
    AgentContext,
    ChartRecord,
    ClaimGraph,
    ConsultationDossier,
    JudgementContext,
    RuleCatalog,
)


def validate_chart_record_provenance(record: ChartRecord, catalog: RuleCatalog) -> None:
    """Reject facts or timing periods whose declared provenance drifted from the catalog."""

    rules_by_id = {rule.rule_id: rule for rule in catalog.rules if rule.status != "retired"}
    errors: list[str] = []
    provenance_items = [
        *(fact.provenance for fact in record.facts),
        *(period.provenance for period in record.timing_periods),
    ]
    for provenance in provenance_items:
        rule = rules_by_id.get(provenance.rule_id)
        if rule is None:
            errors.append(f"unknown provenance rule {provenance.rule_id}")
            continue
        if provenance.rule_version != rule.rule_version:
            errors.append(f"provenance version drift for {provenance.rule_id}")
        if provenance.method_profile_id not in rule.method_profile_ids:
            errors.append(f"method profile mismatch for {provenance.rule_id}")
        if provenance.evidence_class != rule.evidence_class:
            errors.append(f"evidence class drift for {provenance.rule_id}")
        if provenance.source_ids != rule.source_ids:
            errors.append(f"source drift for {provenance.rule_id}")
    if errors:
        raise ValueError("; ".join(sorted(set(errors))))


def validate_claim_graph(
    record: ChartRecord,
    graph: ClaimGraph,
    catalog: RuleCatalog,
    context: JudgementContext | None = None,
) -> None:
    """Validate cross-artifact references at the judgement seam."""

    errors: list[str] = []
    if graph.chart_record_id != record.chart_record_id:
        errors.append("claim graph chart record id does not match the active chart record")
    if graph.chart_revision != record.revision:
        errors.append("claim graph chart revision does not match the active chart record")
    if graph.method_profile_id != record.calculation_profile.profile_id:
        errors.append("claim graph method profile does not match the active chart record")
    if context is not None and graph.rule_pack_version != context.rule_pack_version:
        errors.append("claim graph rule pack version does not match judgement context")

    facts_by_id = {fact.fact_id: fact for fact in record.facts}
    timing_periods_by_id = {period.period_id: period for period in record.timing_periods}
    rules_by_id = {rule.rule_id: rule for rule in catalog.rules if rule.status != "retired"}
    eligible_vargas = {
        chart.varga_id for chart in record.charts if chart.eligible_as_primary_evidence
    }
    context_rule_ids = {rule.rule_id for rule in context.rules} if context else set()
    context_topics = {topic.topic_id: topic for topic in context.topics} if context else {}
    released_claims = [claim for claim in graph.claims if claim.status != "withheld"]
    if context is not None and len(released_claims) < 5:
        errors.append("claim graph requires at least five released synthesis claims")
    if any(check.status == "failed" for check in graph.quality_checks):
        errors.append("claim graph contains failed quality checks")
    for claim in graph.claims:
        referenced_facts = [
            facts_by_id[fact_id]
            for fact_id in claim.supporting_fact_ids
            + claim.counter_fact_ids
            + claim.timing_fact_ids
            if fact_id in facts_by_id
        ]
        evidence_layers = {
            fact_definition(fact.fact_type).evidence_layer for fact in referenced_facts
        }
        if claim.timing_period_ids:
            evidence_layers.add("timing")
        claim_rules = [rules_by_id[rule_id] for rule_id in claim.rule_ids if rule_id in rules_by_id]
        judgement_rules = [rule for rule in claim_rules if rule.rule_kind == "judgement"]
        if not judgement_rules:
            errors.append(f"claim {claim.claim_id} requires at least one judgement rule")
        for fact_id in claim.supporting_fact_ids + claim.counter_fact_ids + claim.timing_fact_ids:
            if fact_id not in facts_by_id:
                errors.append(f"claim {claim.claim_id} references unknown fact {fact_id}")
        for rule_id in claim.rule_ids:
            rule = rules_by_id.get(rule_id)
            if rule is None:
                errors.append(f"claim {claim.claim_id} references unknown rule {rule_id}")
            elif record.calculation_profile.profile_id not in rule.method_profile_ids:
                errors.append(
                    f"claim {claim.claim_id} uses rule {rule_id} from another method profile"
                )
            elif context is not None and rule_id not in context_rule_ids:
                errors.append(
                    f"claim {claim.claim_id} uses rule {rule_id} outside judgement context"
                )
            else:
                missing_layers = sorted(set(rule.required_evidence_layers) - evidence_layers)
                if missing_layers:
                    errors.append(
                        f"claim {claim.claim_id} lacks evidence layers for {rule_id}: "
                        + ", ".join(missing_layers)
                    )
        for period_id in claim.timing_period_ids:
            if period_id not in timing_periods_by_id:
                errors.append(
                    f"claim {claim.claim_id} references unknown timing period {period_id}"
                )
        if set(claim.supporting_fact_ids) & set(claim.counter_fact_ids):
            errors.append(
                f"claim {claim.claim_id} uses the same fact as support and counter-evidence"
            )
        if context is not None:
            if set(claim.supporting_fact_ids) & set(context.restricted_fact_ids):
                errors.append(f"claim {claim.claim_id} uses restricted facts as support")
            if set(claim.timing_period_ids) & set(context.restricted_timing_period_ids):
                errors.append(f"claim {claim.claim_id} uses restricted timing periods")
            topic = context_topics.get(claim.topic)
            if topic is None:
                errors.append(f"claim {claim.claim_id} uses unknown topic {claim.topic}")
            else:
                permitted_rules = set(topic.rule_ids) | set(context.global_gate_rule_ids)
                invalid_rules = sorted(set(claim.rule_ids) - permitted_rules)
                if invalid_rules:
                    errors.append(
                        f"claim {claim.claim_id} uses rules outside topic {claim.topic}: "
                        + ", ".join(invalid_rules)
                    )
        supporting_vargas = {
            facts_by_id[fact_id].subject_ref.split(".", 1)[0]
            for fact_id in claim.supporting_fact_ids
            if fact_id in facts_by_id
            and fact_definition(facts_by_id[fact_id].fact_type).evidence_layer
            == "varga_confirmation"
        }
        if "D60" in supporting_vargas and "D60" not in eligible_vargas:
            errors.append(f"claim {claim.claim_id} uses ineligible D60 as supporting evidence")
        if claim.scope == "timing" and "judge.timing.vimshottari-activation" not in claim.rule_ids:
            errors.append(
                f"timing claim {claim.claim_id} requires judge.timing.vimshottari-activation"
            )
        user_facing_text = " ".join(
            [
                claim.plain_statement,
                claim.user_relevance or "",
                *claim.real_world_expressions,
                *claim.practical_implications,
            ]
        ).lower()
        prohibited = {
            "guaranteed event",
            "will definitely",
            "scientifically proven",
            "注定会",
            "必然发生",
            "保证发生",
            "必ず起こる",
        }
        if any(term in user_facing_text for term in prohibited):
            errors.append(f"claim {claim.claim_id} uses prohibited certainty language")
        if claim.topic == "health" and any(
            term in user_facing_text
            for term in {"diagnosed with", "you have the disease", "确诊", "患有此病", "診断される"}
        ):
            errors.append(f"health claim {claim.claim_id} crosses the diagnosis boundary")
        if claim.topic == "finance" and any(
            term in user_facing_text
            for term in {"guaranteed return", "risk-free profit", "稳赚", "必赚", "確実な利益"}
        ):
            errors.append(f"finance claim {claim.claim_id} promises an outcome")

    if errors:
        raise ValueError("; ".join(errors))


def validate_judgement_context(
    record: ChartRecord,
    context: JudgementContext,
    catalog: RuleCatalog,
) -> None:
    """Validate the deterministic evidence menu before it reaches the Agent."""

    errors: list[str] = []
    if context.chart_record_id != record.chart_record_id:
        errors.append("judgement context chart record id does not match")
    if context.chart_revision != record.revision:
        errors.append("judgement context chart revision does not match")
    if context.method_profile_id != record.calculation_profile.profile_id:
        errors.append("judgement context method profile does not match")
    if context.rule_pack_version != f"vedicdust-rules-{catalog.catalog_version}":
        errors.append("judgement context rule pack version does not match the active catalog")

    fact_ids = {fact.fact_id for fact in record.facts}
    period_ids = {period.period_id for period in record.timing_periods}
    catalog_rules = {
        rule.rule_id: rule
        for rule in catalog.rules
        if rule.status != "retired"
        and record.calculation_profile.profile_id in rule.method_profile_ids
    }
    for rule in context.rules:
        source = catalog_rules.get(rule.rule_id)
        if source is None:
            errors.append(f"judgement context contains unknown rule {rule.rule_id}")
        elif (
            rule.title != source.title
            or rule.topic != source.topic
            or rule.required_evidence_layers != source.required_evidence_layers
            or rule.status != source.status
            or rule.limitations != source.limitations
        ):
            errors.append(f"judgement context rule drift for {rule.rule_id}")
    for topic in context.topics:
        for fact_id in topic.natal_fact_ids + topic.capacity_fact_ids + topic.varga_fact_ids:
            if fact_id not in fact_ids:
                errors.append(f"topic {topic.topic_id} references unknown fact {fact_id}")
        for period_id in topic.timing_period_ids:
            if period_id not in period_ids:
                errors.append(
                    f"topic {topic.topic_id} references unknown timing period {period_id}"
                )
    if set(context.restricted_fact_ids) - fact_ids:
        errors.append("judgement context contains unknown restricted facts")
    if set(context.restricted_timing_period_ids) - period_ids:
        errors.append("judgement context contains unknown restricted timing periods")

    if errors:
        raise ValueError("; ".join(errors))


def validate_consultation_dossier(
    record: ChartRecord,
    graph: ClaimGraph,
    dossier: ConsultationDossier,
) -> None:
    """Validate that the released consultation is only an arrangement of approved claims."""

    errors: list[str] = []
    if dossier.chart_record_id != record.chart_record_id:
        errors.append("consultation dossier chart record id does not match the active chart record")
    if dossier.chart_revision != record.revision:
        errors.append("consultation dossier chart revision does not match the active chart record")
    if dossier.method_profile_id != record.calculation_profile.profile_id:
        errors.append("consultation dossier method profile does not match the active chart record")
    if dossier.claim_graph_version != graph.schema_version:
        errors.append("consultation dossier claim graph version does not match")

    claims_by_id = {claim.claim_id: claim for claim in graph.claims}
    facts_by_id = {fact.fact_id: fact for fact in record.facts}
    timing_periods_by_id = {period.period_id: period for period in record.timing_periods}
    assigned_claim_ids: list[str] = []
    assigned_timing_window_ids: list[str] = []
    timing_windows_by_id = {window.timing_window_id: window for window in dossier.timing_windows}

    for claim_id in dossier.executive_claim_ids:
        if claim_id not in claims_by_id:
            errors.append(f"executive synthesis references unknown claim {claim_id}")
        elif claims_by_id[claim_id].status == "withheld":
            errors.append(f"executive synthesis includes withheld claim {claim_id}")

    for section in dossier.sections:
        assigned_claim_ids.extend(section.claim_ids)
        assigned_timing_window_ids.extend(section.timing_window_ids)
        for claim_id in section.claim_ids:
            if claim_id not in claims_by_id:
                errors.append(f"section {section.section_id} references unknown claim {claim_id}")
            elif claims_by_id[claim_id].status == "withheld":
                errors.append(f"section {section.section_id} includes withheld claim {claim_id}")
        for window_id in section.timing_window_ids:
            if window_id not in timing_windows_by_id:
                errors.append(
                    f"section {section.section_id} references unknown timing window {window_id}"
                )

    executive_section_claim_ids = {
        claim_id
        for section in dossier.sections
        if section.section_kind == "executive_synthesis"
        for claim_id in section.claim_ids
    }
    missing_executive_assignments = sorted(
        set(dossier.executive_claim_ids) - executive_section_claim_ids
    )
    if missing_executive_assignments:
        errors.append(
            "executive claims are not assigned to executive synthesis: "
            + ", ".join(missing_executive_assignments)
        )
    extra_executive_assignments = sorted(
        executive_section_claim_ids - set(dossier.executive_claim_ids)
    )
    if extra_executive_assignments:
        errors.append(
            "executive synthesis contains non-executive claims: "
            + ", ".join(extra_executive_assignments)
        )

    duplicate_assignments = sorted(
        {claim_id for claim_id in assigned_claim_ids if assigned_claim_ids.count(claim_id) > 1}
    )
    if duplicate_assignments:
        errors.append(
            "claims must belong to one report section: " + ", ".join(duplicate_assignments)
        )
    duplicate_window_assignments = sorted(
        {
            window_id
            for window_id in assigned_timing_window_ids
            if assigned_timing_window_ids.count(window_id) > 1
        }
    )
    if duplicate_window_assignments:
        errors.append(
            "timing windows must belong to one report section: "
            + ", ".join(duplicate_window_assignments)
        )
    unassigned_timing_windows = sorted(set(timing_windows_by_id) - set(assigned_timing_window_ids))
    if unassigned_timing_windows:
        errors.append(
            "dossier does not assign timing windows: " + ", ".join(unassigned_timing_windows)
        )

    omitted_claim_ids = set(dossier.omitted_claim_ids)
    unknown_omitted = sorted(omitted_claim_ids - set(claims_by_id))
    if unknown_omitted:
        errors.append("dossier omits unknown claims: " + ", ".join(unknown_omitted))
    assigned_and_omitted = sorted(set(assigned_claim_ids) & omitted_claim_ids)
    if assigned_and_omitted:
        errors.append("dossier both assigns and omits claims: " + ", ".join(assigned_and_omitted))

    released_claim_ids = {claim.claim_id for claim in graph.claims if claim.status != "withheld"}
    unaccounted = sorted(released_claim_ids - set(assigned_claim_ids) - omitted_claim_ids)
    if unaccounted:
        errors.append("dossier does not account for claims: " + ", ".join(unaccounted))

    for window in dossier.timing_windows:
        for claim_id in window.claim_ids:
            claim = claims_by_id.get(claim_id)
            if claim is None:
                errors.append(
                    f"timing window {window.timing_window_id} references unknown claim {claim_id}"
                )
            elif claim.scope != "timing":
                errors.append(
                    f"timing window {window.timing_window_id} uses non-timing claim {claim_id}"
                )
        for fact_id in window.activation_fact_ids:
            if fact_id not in facts_by_id:
                errors.append(
                    f"timing window {window.timing_window_id} references unknown fact {fact_id}"
                )
        for period_id in window.activation_period_ids:
            if period_id not in timing_periods_by_id:
                errors.append(
                    f"timing window {window.timing_window_id} references unknown timing period "
                    f"{period_id}"
                )

    timing_sections = [
        section for section in dossier.sections if section.section_kind == "timing_outlook"
    ]
    if timing_sections:
        timing_section = timing_sections[0]
        timing_claim_ids = {
            claim_id
            for window_id in timing_section.timing_window_ids
            if window_id in timing_windows_by_id
            for claim_id in timing_windows_by_id[window_id].claim_ids
        }
        missing_timing_claim_assignments = sorted(timing_claim_ids - set(timing_section.claim_ids))
        if missing_timing_claim_assignments:
            errors.append(
                "timing window claims must be assigned to timing outlook: "
                + ", ".join(missing_timing_claim_assignments)
            )
        windows_outside_timing = sorted(
            set(assigned_timing_window_ids) - set(timing_section.timing_window_ids)
        )
        if windows_outside_timing:
            errors.append(
                "timing windows must be assigned to timing outlook: "
                + ", ".join(windows_outside_timing)
            )

    if dossier.release_status == "approved" and any(
        check.status == "failed" for check in dossier.quality_checks
    ):
        errors.append("approved consultation dossier contains failed quality checks")

    if errors:
        raise ValueError("; ".join(errors))


def validate_agent_context(
    record: ChartRecord,
    graph: ClaimGraph,
    dossier: ConsultationDossier,
    context: AgentContext,
) -> None:
    """Validate the compact future-Q&A context against its source artifacts."""

    errors: list[str] = []
    if context.dossier_id != dossier.dossier_id:
        errors.append("agent context dossier id does not match")
    if context.chart_record_id != record.chart_record_id:
        errors.append("agent context chart record id does not match")
    if context.chart_revision != record.revision:
        errors.append("agent context chart revision does not match")

    facts_by_id = {fact.fact_id for fact in record.facts}
    claims_by_id = {claim.claim_id: claim for claim in graph.claims}
    timing_windows_by_id = {window.timing_window_id for window in dossier.timing_windows}
    for fact_id in context.stable_fact_ids:
        if fact_id not in facts_by_id:
            errors.append(f"agent context references unknown fact {fact_id}")
    projected_fact_ids = [fact.fact_id for fact in context.stable_facts]
    if len(projected_fact_ids) != len(set(projected_fact_ids)):
        errors.append("agent context contains duplicate stable fact projections")
    if set(projected_fact_ids) != set(context.stable_fact_ids):
        errors.append("agent context stable fact projections do not match stable fact ids")
    record_facts = {fact.fact_id: fact for fact in record.facts}
    for fact in context.stable_facts:
        source = record_facts.get(fact.fact_id)
        if source is None:
            continue
        if (
            fact.fact_type != source.fact_type
            or fact.subject_ref != source.subject_ref
            or fact.value != source.value
            or fact.unit != source.unit
            or fact.confidence != source.provenance.confidence
        ):
            errors.append(f"agent context fact drift for {fact.fact_id}")
    for claim in context.approved_claims:
        source = claims_by_id.get(claim.claim_id)
        if source is None:
            errors.append(f"agent context references unknown claim {claim.claim_id}")
        elif source.status == "withheld":
            errors.append(f"agent context exposes withheld claim {claim.claim_id}")
        elif (
            claim.supporting_fact_ids != source.supporting_fact_ids
            or claim.counter_fact_ids != source.counter_fact_ids
            or claim.rule_ids != source.rule_ids
            or claim.conditions != source.conditions
            or claim.practical_implications != source.practical_implications
            or claim.time_scope != source.time_scope
        ):
            errors.append(f"agent context claim drift for {claim.claim_id}")
        for window_id in claim.timing_window_ids:
            if window_id not in timing_windows_by_id:
                errors.append(
                    f"agent context claim {claim.claim_id} references unknown timing window "
                    f"{window_id}"
                )

    if errors:
        raise ValueError("; ".join(errors))
