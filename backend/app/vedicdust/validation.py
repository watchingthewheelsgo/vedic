from __future__ import annotations

from .fact_catalog import fact_definition
from .claims import bounded_claim_certainty, build_claim_graph
from .confidence import effective_fact_confidence, effective_timing_confidence, minimum_confidence
from .judgement import build_judgement_context
from .presentation_policy import ACTIVE_PRESENTATION_POLICY
from .models import (
    AgentContext,
    ChartRecord,
    ClaimGraph,
    ConfidenceGrade,
    ConsultationDossier,
    JudgementContext,
    RuleCatalog,
)
from .rule_engine import evaluate_method_rule
from .rectification_policy import (
    RECTIFICATION_EVENT_MAPPING_ID,
    RECTIFICATION_HOLDOUT_POLICY_ID,
    RECTIFICATION_SCORING_POLICY_ID,
    RECTIFICATION_SOURCE_IDS,
)
from .source_registry import load_validation_fixture_registry, validate_profile_source_ids
from .sensitivity import (
    TIMING_SENSITIVITY_DEPENDENCIES,
    expected_fact_input_stability,
    expected_timing_input_stability,
    fact_sensitivity_dependencies,
)


def validate_chart_record_provenance(record: ChartRecord, catalog: RuleCatalog) -> None:
    """Reject facts or timing periods whose declared provenance drifted from the catalog."""

    rules_by_id = {rule.rule_id: rule for rule in catalog.rules if rule.status != "retired"}
    errors: list[str] = []
    expected_rule_pack = f"vedicdust-rules-{catalog.catalog_version}"
    if record.calculation_profile.rule_pack_version != expected_rule_pack:
        errors.append("calculation profile rule pack does not match the active catalog")
    try:
        validate_profile_source_ids(record.calculation_profile.source_ids)
    except ValueError as error:
        errors.append(str(error))
    provenance_items = [
        *(fact.provenance for fact in record.facts),
        *(period.provenance for period in record.timing_periods),
    ]
    for fact in record.facts:
        if record.input_sensitivity is None:
            continue
        expected_dependencies = fact_sensitivity_dependencies(fact.fact_type, fact.subject_ref)
        if fact.sensitivity_dependencies != expected_dependencies:
            errors.append(f"sensitivity dependency drift for {fact.fact_id}")
        if fact.input_stability != expected_fact_input_stability(
            fact,
            record.charts,
            record.input_sensitivity,
        ):
            errors.append(f"input stability drift for {fact.fact_id}")
    if record.input_sensitivity is not None and record.canonical_moment is not None:
        for period in record.timing_periods:
            if period.sensitivity_dependencies != TIMING_SENSITIVITY_DEPENDENCIES:
                errors.append(f"timing sensitivity dependency drift for {period.period_id}")
            expected_stability = expected_timing_input_stability(
                record.input_sensitivity,
                record.canonical_moment.resolution_confidence,
            )
            if period.input_stability != expected_stability:
                errors.append(f"timing input stability drift for {period.period_id}")
            timing_status = record.input_sensitivity.timing_boundary_scan_status
            expected_sample_count = record.input_sensitivity.timing_boundary_sample_count
            for label, boundary in (
                ("start", period.start_boundary),
                ("end", period.end_boundary),
            ):
                if timing_status == "complete" and (
                    boundary.coverage != "reported_window_endpoints"
                    or boundary.sampled_hypotheses != expected_sample_count
                ):
                    errors.append(f"timing {label} boundary coverage drift for {period.period_id}")
                if timing_status == "not_run" and boundary.coverage != "canonical_only":
                    errors.append(
                        f"timing {label} boundary must be canonical-only for {period.period_id}"
                    )
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
        if rule.status == "draft":
            errors.append(f"draft rule {provenance.rule_id} cannot emit runtime evidence")
        if rule.status == "provisional" and provenance.confidence not in {
            ConfidenceGrade.UNAVAILABLE,
            ConfidenceGrade.DISPUTED,
            ConfidenceGrade.PROVISIONAL,
        }:
            errors.append(f"provisional rule {provenance.rule_id} overstates evidence confidence")
    if record.rectification is not None:
        fixture_registry = load_validation_fixture_registry()
        for fixture_id in record.rectification.professional_review_fixture_ids:
            fixture = fixture_registry.get(fixture_id)
            if fixture is None:
                errors.append(f"unknown rectification professional review fixture {fixture_id}")
            elif fixture.fixture_kind != "professional_review":
                errors.append(
                    f"rectification fixture {fixture_id} is not a professional review fixture"
                )
        for candidate in record.rectification.candidates:
            for score in candidate.evidence_scores:
                unknown_rules = sorted(set(score.rule_ids) - set(rules_by_id))
                if unknown_rules:
                    errors.append("unknown rectification rule " + ", ".join(unknown_rules))
                for rule_id in score.rule_ids:
                    rule = rules_by_id.get(rule_id)
                    if rule is None:
                        continue
                    if record.calculation_profile.profile_id not in rule.method_profile_ids:
                        errors.append(f"rectification method profile mismatch for rule {rule_id}")
                    if rule.topic != "rectification":
                        errors.append(f"non-rectification rule {rule_id} used for event scoring")
                expected_sources = sorted(
                    {
                        source_id
                        for rule_id in score.rule_ids
                        if (rule := rules_by_id.get(rule_id)) is not None
                        for source_id in rule.source_ids
                    }
                )
                if sorted(score.source_ids) != expected_sources:
                    errors.append(f"rectification source drift for event {score.event_id}")
                if sorted(score.source_ids) != sorted(RECTIFICATION_SOURCE_IDS):
                    errors.append(f"rectification policy source drift for event {score.event_id}")
                if score.scoring_policy_id != RECTIFICATION_SCORING_POLICY_ID:
                    errors.append(f"rectification scoring policy drift for event {score.event_id}")
                if score.event_mapping_id != RECTIFICATION_EVENT_MAPPING_ID:
                    errors.append(f"rectification event mapping drift for event {score.event_id}")
        if len(record.rectification.life_events) >= 3:
            holdout_count = sum(
                1 for event in record.rectification.life_events if event.role == "holdout"
            )
            if holdout_count != 1:
                errors.append(
                    "rectification evidence must retain exactly one holdout event under "
                    f"{RECTIFICATION_HOLDOUT_POLICY_ID}"
                )
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
    if record.status not in {"ready_for_judgement", "rectified"}:
        errors.append(f"chart record status {record.status} cannot publish claims")
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
    context_rule_ids = (
        {rule.rule_id for rule in context.rules if rule.evaluation_status == "eligible"}
        if context
        else set()
    )
    context_topics = {topic.topic_id: topic for topic in context.topics} if context else {}
    context_units = {unit.unit_id: unit for unit in context.units} if context else {}
    released_claims = [claim for claim in graph.claims if claim.status != "withheld"]
    if context is not None:
        required_claim_count = min(
            context.presentation_policy.minimum_structural_coverage,
            len(context.units),
        )
        if len(released_claims) < required_claim_count:
            errors.append(
                "claim graph requires at least "
                f"{required_claim_count} released synthesis claims for the available context"
            )
    if any(check.status == "failed" for check in graph.quality_checks):
        errors.append("claim graph contains failed quality checks")
    for claim in graph.claims:
        conclusion = None
        unit = context_units.get(claim.judgement_unit_id) if context is not None else None
        if context is not None and unit is None:
            errors.append(
                f"claim {claim.claim_id} references unknown judgement unit "
                f"{claim.judgement_unit_id}"
            )
        elif unit is not None:
            conclusions_by_id = {
                conclusion.conclusion_id: conclusion for conclusion in unit.conclusions
            }
            conclusion = conclusions_by_id.get(claim.conclusion_id)
            if claim.topic != unit.topic_id:
                errors.append(
                    f"claim {claim.claim_id} topic {claim.topic} does not match "
                    f"judgement unit {unit.topic_id}"
                )
            if conclusion is None:
                errors.append(
                    f"claim {claim.claim_id} references unknown conclusion {claim.conclusion_id}"
                )
            elif claim.judgement_code != conclusion.conclusion_code:
                errors.append(
                    f"claim {claim.claim_id} changes conclusion code {conclusion.conclusion_code}"
                )
            if claim.judgement_code not in unit.allowed_output_codes:
                errors.append(
                    f"claim {claim.claim_id} uses output code {claim.judgement_code} "
                    f"outside judgement unit"
                )
            if conclusion is not None:
                semantic_drift = {
                    "title": claim.title != conclusion.title,
                    "scope": claim.scope != conclusion.scope,
                    "plain statement": claim.plain_statement != conclusion.plain_statement,
                    "technical statement": (
                        claim.technical_statement != conclusion.technical_statement
                    ),
                    "real-world expressions": (
                        claim.real_world_expressions != conclusion.real_world_expressions
                    ),
                    "conditions": claim.conditions != conclusion.conditions,
                    "user relevance": claim.user_relevance != conclusion.user_relevance,
                    "supporting facts": (
                        set(claim.supporting_fact_ids) != set(conclusion.supporting_fact_ids)
                    ),
                    "context facts": (
                        set(claim.context_fact_ids) != set(conclusion.context_fact_ids)
                    ),
                    "counter facts": (
                        set(claim.counter_fact_ids) != set(conclusion.counter_fact_ids)
                    ),
                    "counter statements": (
                        claim.counter_statements != conclusion.counter_statements
                    ),
                    "timing facts": (set(claim.timing_fact_ids) != set(conclusion.timing_fact_ids)),
                    "timing periods": (
                        set(claim.timing_period_ids) != set(conclusion.timing_period_ids)
                    ),
                    "rules": set(claim.rule_ids) != set(conclusion.rule_ids),
                    "time scope": claim.time_scope != conclusion.time_scope,
                    "practical implications": (
                        claim.practical_implications != conclusion.practical_implications
                    ),
                    "limitations": set(claim.limitations) != set(conclusion.limitations),
                }
                changed_fields = [label for label, changed in semantic_drift.items() if changed]
                if changed_fields:
                    errors.append(
                        f"claim {claim.claim_id} rewrites backend conclusion fields: "
                        + ", ".join(changed_fields)
                    )
            if claim.scope not in unit.allowed_scopes:
                errors.append(
                    f"claim {claim.claim_id} uses scope {claim.scope} outside judgement unit"
                )
            invalid_rules = sorted(set(claim.rule_ids) - set(unit.permitted_rule_ids))
            if invalid_rules:
                errors.append(
                    f"claim {claim.claim_id} uses rules outside judgement unit: "
                    + ", ".join(invalid_rules)
                )
            if unit.primary_rule_id not in claim.rule_ids:
                errors.append(
                    f"claim {claim.claim_id} must cite primary rule {unit.primary_rule_id}"
                )
            allowed_domain_facts = set(
                unit.natal_fact_ids + unit.capacity_fact_ids + unit.varga_fact_ids
            )
            invalid_domain_facts = sorted(
                set(claim.supporting_fact_ids + claim.context_fact_ids + claim.counter_fact_ids)
                - allowed_domain_facts
            )
            if invalid_domain_facts:
                errors.append(
                    f"claim {claim.claim_id} uses facts outside judgement unit: "
                    + ", ".join(invalid_domain_facts)
                )
            invalid_timing_facts = sorted(set(claim.timing_fact_ids) - set(unit.timing_fact_ids))
            if invalid_timing_facts:
                errors.append(
                    f"claim {claim.claim_id} uses timing facts outside judgement unit: "
                    + ", ".join(invalid_timing_facts)
                )
            invalid_periods = sorted(set(claim.timing_period_ids) - set(unit.timing_period_ids))
            if invalid_periods:
                errors.append(
                    f"claim {claim.claim_id} uses timing periods outside judgement unit: "
                    + ", ".join(invalid_periods)
                )
            certainty_rank = {"withheld": -1, "low": 0, "moderate": 1, "high": 2}
            certainty_cap = (
                conclusion.certainty_cap if conclusion is not None else unit.certainty_cap
            )
            if certainty_rank[claim.certainty] > certainty_rank[certainty_cap]:
                errors.append(
                    f"claim {claim.claim_id} exceeds judgement unit certainty cap {certainty_cap}"
                )
            missing_limitations = sorted(set(unit.limitations) - set(claim.limitations))
            if claim.status != "withheld" and missing_limitations:
                errors.append(
                    f"claim {claim.claim_id} omits judgement unit limitations: "
                    + " | ".join(missing_limitations)
                )
        referenced_facts = [
            facts_by_id[fact_id]
            for fact_id in claim.supporting_fact_ids
            + claim.context_fact_ids
            + claim.counter_fact_ids
            + claim.timing_fact_ids
            if fact_id in facts_by_id
        ]
        referenced_periods = [
            timing_periods_by_id[period_id]
            for period_id in claim.timing_period_ids
            if period_id in timing_periods_by_id
        ]
        expected_evidence_confidence = minimum_confidence(
            *(effective_fact_confidence(fact) for fact in referenced_facts),
            *(effective_timing_confidence(period) for period in referenced_periods),
        )
        if claim.evidence_confidence != expected_evidence_confidence:
            errors.append(
                f"claim {claim.claim_id} evidence confidence does not match its referenced evidence"
            )
        if context is not None and unit is not None and conclusion is not None:
            expected_certainty = bounded_claim_certainty(
                record,
                conclusion.certainty_cap,
                evidence_confidence=expected_evidence_confidence,
            )
            if claim.certainty != "withheld" and claim.certainty != expected_certainty:
                errors.append(
                    f"claim {claim.claim_id} certainty does not match its evidence and input caps"
                )
        evidence_layers = {
            fact_definition(fact.fact_type).evidence_layer for fact in referenced_facts
        }
        if claim.timing_period_ids:
            evidence_layers.add("timing")
        claim_rules = [rules_by_id[rule_id] for rule_id in claim.rule_ids if rule_id in rules_by_id]
        judgement_rules = [rule for rule in claim_rules if rule.rule_kind == "judgement"]
        if not judgement_rules:
            errors.append(f"claim {claim.claim_id} requires at least one judgement rule")
        for fact_id in (
            claim.supporting_fact_ids
            + claim.context_fact_ids
            + claim.counter_fact_ids
            + claim.timing_fact_ids
        ):
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
        evidence_sets = (
            set(claim.supporting_fact_ids),
            set(claim.context_fact_ids),
            set(claim.counter_fact_ids),
        )
        if any(
            left & right
            for index, left in enumerate(evidence_sets)
            for right in evidence_sets[index + 1 :]
        ):
            errors.append(f"claim {claim.claim_id} assigns more than one role to one fact")
        if context is not None:
            if set(
                claim.supporting_fact_ids
                + claim.context_fact_ids
                + claim.counter_fact_ids
                + claim.timing_fact_ids
            ) & set(context.restricted_fact_ids):
                errors.append(f"claim {claim.claim_id} uses restricted facts as evidence")
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
                permitted_facts = set(
                    topic.natal_fact_ids
                    + topic.capacity_fact_ids
                    + topic.varga_fact_ids
                    + topic.timing_fact_ids
                )
                invalid_facts = sorted(
                    set(
                        claim.supporting_fact_ids
                        + claim.context_fact_ids
                        + claim.counter_fact_ids
                        + claim.timing_fact_ids
                    )
                    - permitted_facts
                )
                if invalid_facts:
                    errors.append(
                        f"claim {claim.claim_id} uses facts outside topic {claim.topic}: "
                        + ", ".join(invalid_facts)
                    )
                invalid_periods = sorted(
                    set(claim.timing_period_ids) - set(topic.timing_period_ids)
                )
                if invalid_periods:
                    errors.append(
                        f"claim {claim.claim_id} uses timing periods outside topic "
                        f"{claim.topic}: " + ", ".join(invalid_periods)
                    )
        evidence_vargas = {
            facts_by_id[fact_id].subject_ref.split(".", 1)[0]
            for fact_id in claim.supporting_fact_ids + claim.context_fact_ids
            if fact_id in facts_by_id
            and fact_definition(facts_by_id[fact_id].fact_type).evidence_layer
            == "varga_confirmation"
        }
        if "D60" in evidence_vargas and "D60" not in eligible_vargas:
            errors.append(f"claim {claim.claim_id} uses ineligible D60 as evidence")
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
        if any(_contains_assertive_phrase(user_facing_text, term) for term in prohibited):
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

    if context is not None and record.status in {"ready_for_judgement", "rectified"}:
        expected_graph = build_claim_graph(record, context, generated_at=graph.generated_at)
        if [claim.model_dump() for claim in graph.claims] != [
            claim.model_dump() for claim in expected_graph.claims
        ]:
            errors.append("claim graph selection or ordering drifted from presentation policy")
        if graph.omitted_topics != expected_graph.omitted_topics:
            errors.append("claim graph omitted-topic accounting drifted")
        if [check.model_dump() for check in graph.quality_checks] != [
            check.model_dump() for check in expected_graph.quality_checks
        ]:
            errors.append("claim graph quality checks drifted")

    if errors:
        raise ValueError("; ".join(errors))


def _contains_assertive_phrase(text: str, phrase: str) -> bool:
    """Ignore a prohibited phrase when it is explicitly negated in nearby text."""

    start = 0
    negations = (
        "not ",
        "never ",
        "cannot ",
        "does not ",
        "不",
        "并非",
        "不能",
        "不是",
        "ない",
        "ません",
    )
    while (index := text.find(phrase, start)) >= 0:
        prefix = text[max(0, index - 18) : index]
        if not any(negation in prefix for negation in negations):
            return True
        start = index + len(phrase)
    return False


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
    if context.presentation_policy != ACTIVE_PRESENTATION_POLICY:
        errors.append("judgement context presentation policy does not match the active policy")

    fact_ids = {fact.fact_id for fact in record.facts}
    period_ids = {period.period_id for period in record.timing_periods}
    catalog_rules = {
        rule.rule_id: rule
        for rule in catalog.rules
        if rule.status != "retired"
        and record.calculation_profile.profile_id in rule.method_profile_ids
    }
    directional_judgement_rule_ids = {
        rule.rule_id
        for rule in catalog_rules.values()
        if rule.rule_kind == "judgement"
        and rule.status == "validated"
        and rule.judgement_use == "directional"
    }
    traditional_tendency_rule_ids = {
        rule.rule_id
        for rule in catalog_rules.values()
        if rule.rule_kind == "judgement"
        and rule.status in {"provisional", "validated"}
        and rule.judgement_use == "traditional_tendency"
    }
    direction_permitted_rule_ids = directional_judgement_rule_ids | traditional_tendency_rule_ids
    for rule in context.rules:
        source = catalog_rules.get(rule.rule_id)
        if source is None:
            errors.append(f"judgement context contains unknown rule {rule.rule_id}")
        elif (
            rule.title != source.title
            or rule.topic != source.topic
            or rule.output_code != source.output_code
            or rule.evidence_class != source.evidence_class
            or rule.source_ids != source.source_ids
            or rule.required_evidence_layers != source.required_evidence_layers
            or rule.status != source.status
            or rule.judgement_use != source.judgement_use
            or rule.limitations != source.limitations
        ):
            errors.append(f"judgement context rule drift for {rule.rule_id}")
        if rule.evaluation_status == "eligible" and rule.failed_predicates:
            errors.append(f"eligible rule {rule.rule_id} contains failed predicates")
        if rule.evaluation_status == "ineligible" and not rule.failed_predicates:
            errors.append(f"ineligible rule {rule.rule_id} lacks a failed predicate")
        if source is not None:
            expected_evaluation = evaluate_method_rule(
                source,
                record,
                restricted_fact_ids=set(context.restricted_fact_ids),
                excluded_evidence_layers=(
                    {"timing"} if context.restricted_timing_period_ids else set()
                ),
            )
            if (
                rule.evaluation_status != expected_evaluation["evaluationStatus"]
                or rule.matched_fact_ids != expected_evaluation["matchedFactIds"]
                or rule.failed_predicates != expected_evaluation["failedPredicates"]
            ):
                errors.append(f"judgement context rule evaluation drift for {rule.rule_id}")
    for topic in context.topics:
        for fact_id in (
            topic.natal_fact_ids
            + topic.capacity_fact_ids
            + topic.varga_fact_ids
            + topic.timing_fact_ids
        ):
            if fact_id not in fact_ids:
                errors.append(f"topic {topic.topic_id} references unknown fact {fact_id}")
        for period_id in topic.timing_period_ids:
            if period_id not in period_ids:
                errors.append(
                    f"topic {topic.topic_id} references unknown timing period {period_id}"
                )
    topics_by_id = {topic.topic_id: topic for topic in context.topics}
    for unit in context.units:
        topic = topics_by_id.get(unit.topic_id)
        if topic is None:
            errors.append(f"judgement unit {unit.unit_id} references unknown topic")
            continue
        primary_rule = catalog_rules.get(unit.primary_rule_id)
        if primary_rule is None or primary_rule.rule_kind != "judgement":
            errors.append(f"judgement unit {unit.unit_id} has an invalid primary rule")
        elif primary_rule.output_code not in unit.allowed_output_codes:
            errors.append(f"judgement unit {unit.unit_id} omits its primary output code")
        topic_fact_ids = set(
            topic.natal_fact_ids
            + topic.capacity_fact_ids
            + topic.varga_fact_ids
            + topic.timing_fact_ids
        )
        unit_fact_ids = set(
            unit.natal_fact_ids
            + unit.capacity_fact_ids
            + unit.varga_fact_ids
            + unit.timing_fact_ids
        )
        if unit_fact_ids - topic_fact_ids:
            errors.append(f"judgement unit {unit.unit_id} contains facts outside its topic")
        if set(unit.timing_period_ids) - set(topic.timing_period_ids):
            errors.append(f"judgement unit {unit.unit_id} contains periods outside its topic")
        for rule_id in unit.permitted_rule_ids:
            rule = catalog_rules.get(rule_id)
            context_rule = next((item for item in context.rules if item.rule_id == rule_id), None)
            if rule is None or context_rule is None or context_rule.evaluation_status != "eligible":
                errors.append(f"judgement unit {unit.unit_id} permits an ineligible rule {rule_id}")
        for finding in unit.findings:
            if (
                finding.polarity != "context"
                and finding.rule_id not in direction_permitted_rule_ids
            ):
                errors.append(
                    f"judgement unit {unit.unit_id} releases direction from "
                    f"non-directional rule {finding.rule_id}"
                )
        findings_by_id = {finding.finding_id: finding for finding in unit.findings}
        for conclusion in unit.conclusions:
            if conclusion.direction == "descriptive":
                continue
            directional_findings = [
                findings_by_id[finding_id]
                for finding_id in conclusion.finding_ids
                if finding_id in findings_by_id and findings_by_id[finding_id].polarity != "context"
            ]
            if not directional_findings:
                errors.append(
                    f"judgement conclusion {conclusion.conclusion_id} has direction without "
                    "directional findings"
                )
            invalid_directional_rules = sorted(
                {
                    finding.rule_id
                    for finding in directional_findings
                    if finding.rule_id not in direction_permitted_rule_ids
                }
            )
            if invalid_directional_rules:
                errors.append(
                    f"judgement conclusion {conclusion.conclusion_id} uses non-directional rules: "
                    + ", ".join(invalid_directional_rules)
                )
            if (
                any(
                    finding.rule_id in traditional_tendency_rule_ids
                    for finding in directional_findings
                )
                and conclusion.certainty_cap != "low"
            ):
                errors.append(
                    f"judgement conclusion {conclusion.conclusion_id} must cap a traditional "
                    "tendency at low certainty"
                )
    expected_context = build_judgement_context(
        record,
        catalog,
        restricted_fact_ids=set(context.restricted_fact_ids),
        restrict_timing=bool(context.restricted_timing_period_ids),
        requested_topics=context.requested_topics,
        now=context.generated_at,
    )
    if [unit.model_dump() for unit in context.units] != [
        unit.model_dump() for unit in expected_context.units
    ]:
        errors.append("judgement context deterministic findings or conclusions drifted")
    if [topic.model_dump() for topic in context.topics] != [
        topic.model_dump() for topic in expected_context.topics
    ]:
        errors.append("judgement context topic selection drifted")
    if [check.model_dump() for check in context.quality_checks] != [
        check.model_dump() for check in expected_context.quality_checks
    ]:
        errors.append("judgement context quality checks drifted")
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
    context: JudgementContext | None = None,
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
    if context is not None:
        from .reporting import materialize_consultation_dossier

        expected = materialize_consultation_dossier(record, graph, context, dossier)
        if dossier.dossier_id != expected.dossier_id:
            errors.append("consultation dossier id drifted from backend projection")
        if dossier.generated_at != expected.generated_at:
            errors.append("consultation dossier generated time is not backend-owned")
        if dossier.locale != expected.locale or dossier.audience != expected.audience:
            errors.append("consultation dossier audience or locale drifted from the Chart Record")
        if dossier.scope != expected.scope:
            errors.append(
                "consultation dossier scope drifted from backend-owned consultation scope"
            )
        if dossier.confidence != expected.confidence:
            errors.append("consultation dossier confidence drifted from backend-owned confidence")
        if dossier.timing_windows != expected.timing_windows:
            errors.append("consultation dossier timing windows drifted from approved timing Claims")
        if dossier.release_status != expected.release_status:
            errors.append("consultation dossier release status drifted from backend decision")
        if dossier.quality_checks != expected.quality_checks:
            errors.append("consultation dossier quality checks drifted from backend decision")
        if dossier.sections != expected.sections:
            errors.append("consultation dossier section presentation drifted from backend layout")
        if dossier.omitted_claim_ids != expected.omitted_claim_ids:
            errors.append("consultation dossier omission reasons drifted from backend language")
        if dossier.unresolved_questions != expected.unresolved_questions:
            errors.append("consultation dossier unresolved questions drifted from backend evidence")
        expected_window_ids = {
            section.section_id: section.timing_window_ids for section in expected.sections
        }
        if any(
            section.timing_window_ids != expected_window_ids.get(section.section_id, [])
            for section in dossier.sections
        ):
            errors.append("consultation section timing-window assignments drifted")

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
            elif (
                section.section_kind == "timing_outlook"
                and claims_by_id[claim_id].scope != "timing"
            ):
                errors.append(f"timing outlook contains non-timing claim {claim_id}")
            elif (
                section.section_kind != "timing_outlook"
                and claims_by_id[claim_id].scope == "timing"
            ):
                errors.append(f"timing claim {claim_id} is assigned outside timing outlook")
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
    if dossier.release_status != "approved" or any(
        check.status != "passed" for check in dossier.quality_checks
    ):
        errors.append("agent context cannot be validated against an unapproved dossier")
    if context.dossier_id != dossier.dossier_id:
        errors.append("agent context dossier id does not match")
    if context.chart_record_id != record.chart_record_id:
        errors.append("agent context chart record id does not match")
    if context.chart_revision != record.revision:
        errors.append("agent context chart revision does not match")
    if context.locale != dossier.locale:
        errors.append("agent context locale does not match the consultation dossier")
    if context.subject != record.subject:
        errors.append("agent context subject framing does not match the Chart Record")
    if context.reported_birth_date != record.birth_assertion.local_date:
        errors.append("agent context reported birth date does not match the Chart Record")

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
            or fact.confidence != effective_fact_confidence(source)
            or fact.calculation_confidence != source.provenance.confidence
            or fact.input_stability != source.input_stability
        ):
            errors.append(f"agent context fact drift for {fact.fact_id}")
    for claim in context.approved_claims:
        source = claims_by_id.get(claim.claim_id)
        if source is None:
            errors.append(f"agent context references unknown claim {claim.claim_id}")
        elif source.status == "withheld":
            errors.append(f"agent context exposes withheld claim {claim.claim_id}")
        elif (
            claim.topic != source.topic
            or claim.statement != source.plain_statement
            or claim.user_relevance != source.user_relevance
            or claim.certainty != source.certainty
            or claim.supporting_fact_ids != source.supporting_fact_ids
            or claim.context_fact_ids != source.context_fact_ids
            or claim.counter_fact_ids != source.counter_fact_ids
            or claim.counter_statements != source.counter_statements
            or claim.rule_ids != source.rule_ids
            or claim.conditions != source.conditions
            or claim.practical_implications != source.practical_implications
            or claim.limitations != source.limitations
            or claim.time_scope != source.time_scope
        ):
            errors.append(f"agent context claim drift for {claim.claim_id}")
        for window_id in claim.timing_window_ids:
            if window_id not in timing_windows_by_id:
                errors.append(
                    f"agent context claim {claim.claim_id} references unknown timing window "
                    f"{window_id}"
                )

    from .reporting import build_agent_context

    if not errors:
        expected = build_agent_context(record, graph, dossier)
        if context.model_dump() != expected.model_dump():
            errors.append("agent context deterministic projection drifted")

    if errors:
        raise ValueError("; ".join(errors))
