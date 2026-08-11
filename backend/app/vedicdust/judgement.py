from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .fact_catalog import fact_definition
from .judgement_kernel import INTERPRETATION_RULE_IDS, compile_topic_judgement
from .models import (
    ChartRecord,
    JyotishFact,
    JudgementContext,
    JudgementRuleContext,
    JudgementTopicContext,
    JudgementUnit,
    MethodRule,
    QualityCheck,
    RuleCatalog,
    TimingPeriod,
)
from .rule_engine import evaluate_method_rule
from .presentation_policy import (
    ACTIVE_PRESENTATION_POLICY,
    build_topic_presentation_priority,
)


@dataclass(frozen=True)
class TopicDefinition:
    topic_id: str
    title: str
    purpose: str
    houses: tuple[int, ...]
    anchor_houses: tuple[int, ...]
    karakas: tuple[str, ...]
    vargas: tuple[str, ...]
    rule_id: str


TOPICS = (
    TopicDefinition(
        "foundation",
        "Chart foundation",
        "Establish the chart's organizing structure before domain conclusions.",
        (1,),
        (1,),
        ("Sun", "Moon"),
        ("D9",),
        "judge.foundation.integrated",
    ),
    TopicDefinition(
        "identity",
        "Identity and agency",
        "Assess temperament, agency, and the conditions under which potential is expressed.",
        (1, 5, 9),
        (1,),
        ("Sun", "Moon", "Jupiter"),
        ("D9",),
        "judge.identity.integrated",
    ),
    TopicDefinition(
        "career",
        "Career and contribution",
        "Assess work direction, responsibility, authority, and sustainable contribution.",
        (2, 6, 10, 11),
        (10,),
        ("Sun", "Mercury", "Jupiter", "Saturn"),
        ("D10",),
        "judge.career.d1-d10",
    ),
    TopicDefinition(
        "finance",
        "Resources and finance",
        "Assess resource formation, retention, material support, and financial pressure.",
        (2, 4, 8, 11),
        (2, 11),
        ("Jupiter", "Venus", "Mercury"),
        ("D2", "D4"),
        "judge.finance.d1-d2-d4",
    ),
    TopicDefinition(
        "relationship",
        "Relationships and partnership",
        "Assess partnership promise, reciprocity, maturity, and relationship conditions.",
        (2, 7, 8, 11),
        (7,),
        ("Venus", "Jupiter", "Mars"),
        ("D9",),
        "judge.relationship.d1-d9",
    ),
    TopicDefinition(
        "home",
        "Home and rootedness",
        "Assess home, property, mobility, emotional rootedness, and domestic stability.",
        (4, 8, 12),
        (4,),
        ("Moon", "Venus", "Mars"),
        ("D4",),
        "judge.home.d1-d4",
    ),
    TopicDefinition(
        "learning",
        "Learning and vocation",
        "Assess learning style, formal study, mastery, and knowledge transmission.",
        (2, 4, 5, 9),
        (5, 9),
        ("Mercury", "Jupiter"),
        ("D24",),
        "judge.learning.d1-d24",
    ),
    TopicDefinition(
        "children",
        "Children and stewardship",
        "Assess the promise and responsibilities connected with children and mentorship.",
        (5, 9),
        (5,),
        ("Jupiter", "Moon"),
        ("D7",),
        "judge.children.d1-d7",
    ),
    TopicDefinition(
        "health",
        "Vitality and health patterns",
        "Assess vitality, strain patterns, recovery conditions, and preventive attention.",
        (1, 6, 8, 12),
        (1, 6),
        ("Sun", "Moon", "Mars", "Saturn"),
        ("D30",),
        "judge.health.d1-d30",
    ),
    TopicDefinition(
        "dharma",
        "Meaning and inner practice",
        "Assess values, meaning, spiritual practice, and the maturation of worldview.",
        (5, 9, 12),
        (9,),
        ("Jupiter", "Ketu", "Sun"),
        ("D9", "D20"),
        "judge.dharma.d1-d9-d20",
    ),
    TopicDefinition(
        "family",
        "Family and lineage",
        "Assess family roles, parental inheritance, lineage obligations, and support.",
        (2, 4, 9, 10),
        (2, 4),
        ("Sun", "Moon", "Jupiter"),
        ("D12",),
        "judge.family.d1-d12",
    ),
)

GLOBAL_GATE_RULE_IDS = (
    "sop.promise-before-varga",
    "sop.promise-capacity-before-timing",
    "sop.d60-eligibility-gate",
    "judge.timing.vimshottari-activation",
)


def build_judgement_context(
    record: ChartRecord,
    catalog: RuleCatalog,
    *,
    restricted_fact_ids: set[str] | None = None,
    restrict_timing: bool = False,
    requested_topics: list[str] | None = None,
    now: datetime | None = None,
) -> JudgementContext:
    """Build the deterministic evidence and conclusion menu used to publish Claims."""

    restricted = restricted_fact_ids or set()
    facts_by_id = {fact.fact_id: fact for fact in record.facts}
    eligible_vargas = {
        chart.varga_id for chart in record.charts if chart.eligible_as_primary_evidence
    }
    requested = _validate_requested_topic_ids(requested_topics or [])
    reference_time = now or datetime.now(timezone.utc)
    relevant_period_ids = _relevant_period_ids(record, reference_time)
    periods_by_id = {period.period_id: period for period in record.timing_periods}
    period_ids = [] if restrict_timing else relevant_period_ids
    active_rules = {
        rule.rule_id: rule
        for rule in catalog.rules
        if rule.status not in {"draft", "retired"}
        and record.calculation_profile.profile_id in rule.method_profile_ids
    }
    rule_evaluations = {
        rule.rule_id: evaluate_method_rule(
            rule,
            record,
            restricted_fact_ids=restricted,
            excluded_evidence_layers={"timing"} if restrict_timing else set(),
        )
        for rule in active_rules.values()
        if rule.rule_kind in {"judgement", "workflow_gate"}
    }
    rule_contexts = [
        JudgementRuleContext(
            rule_id=rule.rule_id,
            title=rule.title,
            topic=rule.topic,
            output_code=rule.output_code,
            evidence_class=rule.evidence_class,
            source_ids=rule.source_ids,
            required_evidence_layers=rule.required_evidence_layers,
            status=rule.status,
            judgement_use=rule.judgement_use,
            evaluation_status=rule_evaluations[rule.rule_id]["evaluationStatus"],
            matched_fact_ids=rule_evaluations[rule.rule_id]["matchedFactIds"],
            failed_predicates=rule_evaluations[rule.rule_id]["failedPredicates"],
            limitations=rule.limitations,
        )
        for rule in active_rules.values()
        if rule.rule_kind in {"judgement", "workflow_gate"}
    ]

    topics = [
        _build_topic(
            definition,
            facts_by_id,
            eligible_vargas,
            period_ids,
            requested,
            restricted,
        )
        for definition in TOPICS
        if definition.rule_id in active_rules
        and rule_evaluations[definition.rule_id]["evaluationStatus"] == "eligible"
    ]
    eligible_interpretation_rule_ids = [
        rule_id
        for rule_id in INTERPRETATION_RULE_IDS.values()
        if rule_id in active_rules and rule_evaluations[rule_id]["evaluationStatus"] == "eligible"
    ]
    for topic in topics:
        topic.rule_ids = list(dict.fromkeys([*topic.rule_ids, *eligible_interpretation_rule_ids]))
    topics.sort(key=lambda item: (-item.priority_score, item.topic_id))
    definitions_by_id = {definition.topic_id: definition for definition in TOPICS}
    units = [
        _build_judgement_unit(
            topic,
            definitions_by_id[topic.topic_id],
            active_rules,
            rule_evaluations,
            facts_by_id,
            periods_by_id,
            record.subject.locale,
            reference_time,
        )
        for topic in topics
    ]
    permitted_by_topic = {unit.topic_id: unit.permitted_rule_ids for unit in units}
    for topic in topics:
        topic.rule_ids = permitted_by_topic[topic.topic_id]

    checks = [
        QualityCheck(
            check_id="judgement-context.rules",
            status="passed" if rule_contexts else "failed",
            expected="active judgement rules",
            observed=len(rule_contexts),
            message="Judgement rules were resolved for the active Calculation Profile.",
        ),
        QualityCheck(
            check_id="judgement-context.topic-evidence",
            status="passed" if topics else "failed",
            expected="at least one topic evidence bundle",
            observed=len(topics),
            message="Topic evidence was selected from the active Chart Record.",
        ),
        QualityCheck(
            check_id="judgement-context.timing-horizon",
            status="passed" if period_ids else "warning",
            expected="Vimshottari periods covering the current to five-year horizon",
            observed=len(period_ids),
            message=(
                "Timing periods cover the consultation horizon."
                if period_ids
                else "No declared Vimshottari period covers the consultation horizon; "
                "timing conclusions are withheld."
            ),
        ),
    ]
    return JudgementContext(
        chart_record_id=record.chart_record_id,
        chart_revision=record.revision,
        method_profile_id=record.calculation_profile.profile_id,
        generated_at=reference_time,
        requested_topics=sorted(requested),
        rule_pack_version=f"vedicdust-rules-{catalog.catalog_version}",
        presentation_policy=ACTIVE_PRESENTATION_POLICY,
        rules=rule_contexts,
        global_gate_rule_ids=[
            rule_id
            for rule_id in GLOBAL_GATE_RULE_IDS
            if rule_id in active_rules
            and rule_evaluations[rule_id]["evaluationStatus"] == "eligible"
        ],
        topics=topics,
        units=units,
        restricted_fact_ids=sorted(restricted & facts_by_id.keys()),
        restricted_timing_period_ids=relevant_period_ids if restrict_timing else [],
        quality_checks=checks,
    )


def _build_judgement_unit(
    topic: JudgementTopicContext,
    definition: TopicDefinition,
    active_rules: dict[str, MethodRule],
    rule_evaluations: dict[str, dict[str, object]],
    facts_by_id: dict[str, JyotishFact],
    periods_by_id: dict[str, TimingPeriod],
    locale: str,
    reference_time: datetime,
) -> JudgementUnit:
    """Compile one topic into the exact semantic allowance exposed to the model."""

    primary_rule = active_rules[topic.rule_ids[0]]
    permitted_rules = [primary_rule.rule_id]
    output_codes = [primary_rule.output_code]
    allowed_scopes = ["natal_promise", "capacity"]

    eligible_varga_facts = [
        fact_id
        for fact_id in topic.varga_fact_ids
        if any(fact_id.startswith(f"fact.{varga_id}.") for varga_id in topic.eligible_vargas)
    ]
    promise_gate = active_rules.get("sop.promise-before-varga")
    if (
        eligible_varga_facts
        and promise_gate is not None
        and rule_evaluations[promise_gate.rule_id]["evaluationStatus"] == "eligible"
    ):
        permitted_rules.append(promise_gate.rule_id)

    interpretation_rules: dict[str, str] = {}
    for interpretation_key, rule_id in INTERPRETATION_RULE_IDS.items():
        rule = active_rules.get(rule_id)
        if rule is not None and rule_evaluations[rule.rule_id]["evaluationStatus"] == "eligible":
            interpretation_rules[interpretation_key] = rule.rule_id
            permitted_rules.append(rule.rule_id)
            output_codes.append(rule.output_code)

    timing_rule = active_rules.get("judge.timing.vimshottari-activation")
    timing_gate = active_rules.get("sop.promise-capacity-before-timing")
    timing_is_eligible = all(
        rule is not None and rule_evaluations[rule.rule_id]["evaluationStatus"] == "eligible"
        for rule in (timing_rule, timing_gate)
    )
    if timing_is_eligible and topic.timing_period_ids:
        assert timing_rule is not None and timing_gate is not None
        permitted_rules.extend([timing_rule.rule_id, timing_gate.rule_id])
        output_codes.append(timing_rule.output_code)
        allowed_scopes.append("timing")

    certainty_cap = "moderate" if primary_rule.status == "provisional" else "high"
    limitations = list(dict.fromkeys([*primary_rule.limitations, *topic.limitations]))
    if primary_rule.status == "provisional":
        limitations.append(
            "This domain synthesis is a provisional VedicDust product rule and cannot be high certainty."
        )
        limitations.append(
            "Calculation rules establish facts; separate VedicDust structural-bands 1.2.0 "
            "interpretation rules determine whether those facts may carry direction. Dignity "
            "and Shadbala may contribute only a source-grounded traditional tendency; SAV and "
            "combustion remain descriptive."
        )
        limitations.append(
            "A supportive or challenging domain direction requires convergence from at least "
            "two separately registered methods agreeing on that direction. Any conclusion that "
            "depends on an unreviewed traditional tendency is capped at low certainty; one method "
            "or opposing methods remain descriptive."
        )

    findings, conclusions = compile_topic_judgement(
        topic_id=topic.topic_id,
        topic_title=topic.title,
        anchor_houses=definition.anchor_houses,
        karakas=definition.karakas,
        primary_rule_id=primary_rule.rule_id,
        natal_fact_ids=topic.natal_fact_ids,
        capacity_fact_ids=topic.capacity_fact_ids,
        varga_fact_ids=eligible_varga_facts,
        facts_by_id=facts_by_id,
        locale=locale,
        requested=topic.requested,
        certainty_cap=certainty_cap,
        limitations=list(dict.fromkeys(limitations)),
        interpretation_rule_ids=interpretation_rules,
        directional_judgement_rule_ids={
            rule.rule_id
            for rule in active_rules.values()
            if rule.rule_kind == "judgement"
            and rule.status == "validated"
            and rule.judgement_use == "directional"
        },
        traditional_tendency_rule_ids={
            rule.rule_id
            for rule in active_rules.values()
            if rule.rule_kind == "judgement"
            and rule.status in {"provisional", "validated"}
            and rule.judgement_use == "traditional_tendency"
        },
        validated_derivation_rule_ids={
            rule.rule_id
            for rule in active_rules.values()
            if rule.rule_kind == "derivation" and rule.status == "validated"
        },
        direction_eligible_derivation_rule_ids={
            rule.rule_id
            for rule in active_rules.values()
            if rule.rule_kind == "derivation" and rule.status in {"provisional", "validated"}
        },
        timing_rule_id=(timing_rule.rule_id if timing_is_eligible and timing_rule else None),
        timing_gate_rule_id=(timing_gate.rule_id if timing_is_eligible and timing_gate else None),
        timing_periods=[
            periods_by_id[period_id]
            for period_id in topic.timing_period_ids
            if period_id in periods_by_id
        ],
        reference_time=reference_time,
    )
    used_rule_ids = {
        primary_rule.rule_id,
        *(finding.rule_id for finding in findings),
        *(rule_id for conclusion in conclusions for rule_id in conclusion.rule_ids),
    }
    permitted_rules = [rule_id for rule_id in permitted_rules if rule_id in used_rule_ids]
    output_codes = [active_rules[rule_id].output_code for rule_id in permitted_rules]
    output_codes.extend(conclusion.conclusion_code for conclusion in conclusions)

    return JudgementUnit(
        unit_id=f"unit.{topic.topic_id}.{primary_rule.rule_id}",
        topic_id=topic.topic_id,
        primary_rule_id=primary_rule.rule_id,
        permitted_rule_ids=list(dict.fromkeys(permitted_rules)),
        allowed_output_codes=list(dict.fromkeys(output_codes)),
        allowed_scopes=allowed_scopes,
        natal_fact_ids=topic.natal_fact_ids,
        capacity_fact_ids=topic.capacity_fact_ids,
        varga_fact_ids=eligible_varga_facts,
        timing_fact_ids=topic.timing_fact_ids if "timing" in allowed_scopes else [],
        timing_period_ids=topic.timing_period_ids if "timing" in allowed_scopes else [],
        findings=findings,
        conclusions=conclusions,
        certainty_cap=certainty_cap,
        limitations=list(dict.fromkeys(limitations)),
    )


def _build_topic(
    definition: TopicDefinition,
    facts_by_id: dict[str, JyotishFact],
    eligible_vargas: set[str],
    period_ids: list[str],
    requested_topics: set[str],
    restricted: set[str],
) -> JudgementTopicContext:
    house_refs = {f"D1.H{house}" for house in definition.houses}
    graha_refs = {f"D1.{graha}" for graha in definition.karakas}
    relevant_graha_refs = set(graha_refs)
    for fact in facts_by_id.values():
        if fact.fact_type == "rashi.house.occupant" and any(
            fact.subject_ref.startswith(f"{house_ref}.occupant.") for house_ref in house_refs
        ):
            relevant_graha_refs.add(f"D1.{fact.subject_ref.rsplit('.', 1)[-1]}")
        elif fact.fact_type == "rashi.house.lord" and fact.subject_ref in house_refs:
            value = fact.value if isinstance(fact.value, dict) else {}
            lord = value.get("lord")
            if lord:
                relevant_graha_refs.add(f"D1.{lord}")
    natal: list[str] = []
    capacity: list[str] = []
    varga: list[str] = []
    timing: list[str] = []

    for fact_id, raw_fact in facts_by_id.items():
        fact = raw_fact
        if fact_id in restricted:
            continue
        layer = fact_definition(fact.fact_type).evidence_layer
        subject_ref = fact.subject_ref
        if layer == "natal_promise" and (
            subject_ref in house_refs
            or subject_ref in relevant_graha_refs
            or any(subject_ref.startswith(f"{house}.occupant.") for house in house_refs)
            or any(subject_ref.endswith(f"->{house}") for house in house_refs)
            or _relationship_mentions_any(subject_ref, relevant_graha_refs)
            or (definition.topic_id == "foundation" and subject_ref == "D1.Lagna")
        ):
            natal.append(fact_id)
        elif layer == "capacity" and (
            subject_ref in house_refs or subject_ref in relevant_graha_refs
        ):
            capacity.append(fact_id)
        elif layer == "varga_confirmation" and _varga_fact_matches_topic(
            fact, definition, house_refs, relevant_graha_refs
        ):
            varga.append(fact_id)
        elif layer == "timing":
            timing.append(fact_id)

    available_vargas = sorted(
        varga_id
        for varga_id in definition.vargas
        if any(facts_by_id[fact_id].subject_ref.startswith(f"{varga_id}.") for fact_id in varga)
    )
    primary_vargas = sorted(set(available_vargas) & eligible_vargas)
    requested = definition.topic_id in requested_topics
    evidence_layers = [
        layer
        for layer, values in (
            ("natal_promise", natal),
            ("capacity", capacity),
            ("varga_confirmation", varga),
            ("timing", [*timing, *period_ids]),
        )
        if values
    ]
    sav_evidence = [
        (fact_id, float(facts_by_id[fact_id].value))
        for fact_id in capacity
        if facts_by_id[fact_id].fact_type == "ashtakavarga.sav.house"
    ]
    aspect_fact_ids = [
        fact_id for fact_id in natal if facts_by_id[fact_id].fact_type == "aspect.graha_drishti"
    ]
    eligible_varga_fact_ids = [
        fact_id
        for fact_id in varga
        if any(fact_id.startswith(f"fact.{varga_id}.") for varga_id in primary_vargas)
    ]
    score, priority_reasons = build_topic_presentation_priority(
        topic_id=definition.topic_id,
        requested=requested,
        sav_evidence=sav_evidence,
        aspect_fact_ids=aspect_fact_ids,
        eligible_varga_fact_ids=eligible_varga_fact_ids,
    )
    limitations: list[str] = []
    missing_primary = sorted(set(available_vargas) - set(primary_vargas))
    if missing_primary:
        limitations.append(
            "These vargas are corroboration-only for the current birth-time confidence: "
            + ", ".join(missing_primary)
        )
    if not natal:
        limitations.append("No topic-specific D1 evidence bundle is available.")
    if not capacity:
        limitations.append("Capacity evidence is incomplete; certainty must be low or withheld.")

    return JudgementTopicContext(
        topic_id=definition.topic_id,
        title=definition.title,
        purpose=definition.purpose,
        requested=requested,
        priority_score=score,
        priority_reasons=priority_reasons,
        rule_ids=[definition.rule_id],
        natal_fact_ids=sorted(natal),
        capacity_fact_ids=sorted(capacity),
        varga_fact_ids=sorted(varga),
        timing_fact_ids=sorted(timing),
        timing_period_ids=period_ids,
        eligible_vargas=primary_vargas,
        evidence_layers=evidence_layers,
        limitations=limitations,
    )


def _relationship_mentions_any(subject_ref: str, graha_refs: set[str]) -> bool:
    if "->" in subject_ref:
        source, target = subject_ref.split("->", 1)
        return source in graha_refs or f"D1.{target}" in graha_refs
    if "~" in subject_ref:
        left, right = subject_ref.split("~", 1)
        return left in graha_refs or f"D1.{right}" in graha_refs
    return False


def _varga_fact_matches_topic(
    fact: JyotishFact,
    definition: TopicDefinition,
    house_refs: set[str],
    graha_refs: set[str],
) -> bool:
    varga_id, separator, subject = fact.subject_ref.partition(".")
    if not separator or varga_id not in definition.vargas:
        return False
    if subject == "Lagna":
        return True
    if subject.startswith("H"):
        return f"D1.{subject}" in house_refs
    return f"D1.{subject}" in graha_refs


def _validate_requested_topic_ids(values: list[str]) -> set[str]:
    """Accept canonical ontology IDs; natural-language classification is Agent-owned."""

    allowed = {topic.topic_id for topic in TOPICS}
    return {value.strip() for value in values if value.strip() in allowed}


def _relevant_period_ids(record: ChartRecord, now: datetime) -> list[str]:
    start = now - timedelta(days=366)
    end = now + timedelta(days=365 * 5)
    return [
        period.period_id
        for period in record.timing_periods
        if period.end_boundary.latest > start and period.start_boundary.earliest < end
    ]
