from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .fact_catalog import fact_definition
from .models import (
    ChartRecord,
    JyotishFact,
    JudgementContext,
    JudgementRuleContext,
    JudgementTopicContext,
    QualityCheck,
    RuleCatalog,
)


@dataclass(frozen=True)
class TopicDefinition:
    topic_id: str
    title: str
    purpose: str
    houses: tuple[int, ...]
    karakas: tuple[str, ...]
    vargas: tuple[str, ...]
    rule_id: str
    aliases: tuple[str, ...] = ()


TOPICS = (
    TopicDefinition(
        "foundation",
        "Chart foundation",
        "Establish the chart's organizing structure before domain conclusions.",
        (1,),
        ("Sun", "Moon"),
        ("D9",),
        "judge.foundation.integrated",
        ("core", "overview", "基础", "整体"),
    ),
    TopicDefinition(
        "identity",
        "Identity and agency",
        "Assess temperament, agency, and the conditions under which potential is expressed.",
        (1, 5, 9),
        ("Sun", "Moon", "Jupiter"),
        ("D9",),
        "judge.identity.integrated",
        ("self", "personality", "性格", "自我", "人生"),
    ),
    TopicDefinition(
        "career",
        "Career and contribution",
        "Assess work direction, responsibility, authority, and sustainable contribution.",
        (2, 6, 10, 11),
        ("Sun", "Mercury", "Jupiter", "Saturn"),
        ("D10",),
        "judge.career.d1-d10",
        ("work", "job", "事业", "职业", "工作"),
    ),
    TopicDefinition(
        "finance",
        "Resources and finance",
        "Assess resource formation, retention, material support, and financial pressure.",
        (2, 4, 8, 11),
        ("Jupiter", "Venus", "Mercury"),
        ("D2", "D4"),
        "judge.finance.d1-d2-d4",
        ("money", "wealth", "财务", "财富", "收入"),
    ),
    TopicDefinition(
        "relationship",
        "Relationships and partnership",
        "Assess partnership promise, reciprocity, maturity, and relationship conditions.",
        (2, 7, 8, 11),
        ("Venus", "Jupiter", "Mars"),
        ("D9",),
        "judge.relationship.d1-d9",
        ("love", "marriage", "感情", "婚姻", "关系"),
    ),
    TopicDefinition(
        "home",
        "Home and rootedness",
        "Assess home, property, mobility, emotional rootedness, and domestic stability.",
        (4, 8, 12),
        ("Moon", "Venus", "Mars"),
        ("D4",),
        "judge.home.d1-d4",
        ("property", "relocation", "家庭", "房产", "搬迁", "居住"),
    ),
    TopicDefinition(
        "learning",
        "Learning and vocation",
        "Assess learning style, formal study, mastery, and knowledge transmission.",
        (2, 4, 5, 9),
        ("Mercury", "Jupiter"),
        ("D5", "D24"),
        "judge.learning.d1-d5-d24",
        ("education", "study", "学习", "教育", "学业"),
    ),
    TopicDefinition(
        "children",
        "Children and stewardship",
        "Assess the promise and responsibilities connected with children and mentorship.",
        (5, 9),
        ("Jupiter", "Moon"),
        ("D7",),
        "judge.children.d1-d7",
        ("child", "kids", "子女", "孩子", "生育"),
    ),
    TopicDefinition(
        "health",
        "Vitality and health patterns",
        "Assess vitality, strain patterns, recovery conditions, and preventive attention.",
        (1, 6, 8, 12),
        ("Sun", "Moon", "Mars", "Saturn"),
        ("D30",),
        "judge.health.d1-d30",
        ("wellbeing", "身体", "健康", "疾病"),
    ),
    TopicDefinition(
        "dharma",
        "Meaning and inner practice",
        "Assess values, meaning, spiritual practice, and the maturation of worldview.",
        (5, 9, 12),
        ("Jupiter", "Ketu", "Sun"),
        ("D9", "D20"),
        "judge.dharma.d1-d9-d20",
        ("spirituality", "purpose", "精神", "灵性", "意义"),
    ),
    TopicDefinition(
        "family",
        "Family and lineage",
        "Assess family roles, parental inheritance, lineage obligations, and support.",
        (2, 4, 9, 10),
        ("Sun", "Moon", "Jupiter"),
        ("D12",),
        "judge.family.d1-d12",
        ("parents", "parent", "父母", "原生家庭", "家族"),
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
    """Build the deterministic evidence menu consumed by the judgement Agent."""

    restricted = restricted_fact_ids or set()
    facts_by_id = {fact.fact_id: fact for fact in record.facts}
    eligible_vargas = {
        chart.varga_id for chart in record.charts if chart.eligible_as_primary_evidence
    }
    requested = _normalize_requested_topics(
        [*record.subject.consultation_topics, *(requested_topics or [])]
    )
    reference_time = now or datetime.now(timezone.utc)
    relevant_period_ids = _relevant_period_ids(record, reference_time)
    period_ids = [] if restrict_timing else relevant_period_ids
    active_rules = {
        rule.rule_id: rule
        for rule in catalog.rules
        if rule.status not in {"draft", "retired"}
        and record.calculation_profile.profile_id in rule.method_profile_ids
    }
    rule_contexts = [
        JudgementRuleContext(
            rule_id=rule.rule_id,
            title=rule.title,
            topic=rule.topic,
            required_evidence_layers=rule.required_evidence_layers,
            status=rule.status,
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
    ]
    topics.sort(key=lambda item: (-item.priority_score, item.topic_id))

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
    ]
    return JudgementContext(
        chart_record_id=record.chart_record_id,
        chart_revision=record.revision,
        method_profile_id=record.calculation_profile.profile_id,
        generated_at=reference_time,
        requested_topics=sorted(requested),
        rule_pack_version=f"vedicdust-rules-{catalog.catalog_version}",
        rules=rule_contexts,
        global_gate_rule_ids=[
            rule_id for rule_id in GLOBAL_GATE_RULE_IDS if rule_id in active_rules
        ],
        topics=topics,
        restricted_fact_ids=sorted(restricted & facts_by_id.keys()),
        restricted_timing_period_ids=relevant_period_ids if restrict_timing else [],
        quality_checks=checks,
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
    natal: list[str] = []
    capacity: list[str] = []
    varga: list[str] = []

    for fact_id, raw_fact in facts_by_id.items():
        fact = raw_fact
        if fact_id in restricted:
            continue
        layer = fact_definition(fact.fact_type).evidence_layer
        subject_ref = fact.subject_ref
        if layer == "natal_promise" and (
            subject_ref in house_refs
            or subject_ref in graha_refs
            or any(subject_ref.endswith(f"->{house}") for house in house_refs)
            or (definition.topic_id == "foundation" and subject_ref == "D1.Lagna")
        ):
            natal.append(fact_id)
        elif layer == "capacity" and (subject_ref in house_refs or subject_ref in graha_refs):
            capacity.append(fact_id)
        elif layer == "varga_confirmation" and any(
            subject_ref.startswith(f"{varga_id}.") for varga_id in definition.vargas
        ):
            varga.append(fact_id)

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
            ("timing", period_ids),
        )
        if values
    ]
    sav_values = [
        float(facts_by_id[fact_id].value)
        for fact_id in capacity
        if facts_by_id[fact_id].fact_type == "ashtakavarga.sav.house"
    ]
    average_sav_deviation = (
        sum(abs(value - 28.0) for value in sav_values) / len(sav_values) if sav_values else 0.0
    )
    aspect_count = sum(
        1 for fact_id in natal if facts_by_id[fact_id].fact_type == "aspect.graha_drishti"
    )
    score = 95 if definition.topic_id == "foundation" else 45
    if requested:
        score = 100
    elif definition.topic_id != "foundation":
        score = min(
            92,
            score + min(24, round(average_sav_deviation * 3)) + min(12, aspect_count * 2),
        )
    if primary_vargas:
        score = min(100, score + 8)
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
        rule_ids=[definition.rule_id],
        natal_fact_ids=sorted(natal),
        capacity_fact_ids=sorted(capacity),
        varga_fact_ids=sorted(varga),
        timing_period_ids=period_ids,
        eligible_vargas=primary_vargas,
        evidence_layers=evidence_layers,
        limitations=limitations,
    )


def _normalize_requested_topics(values: list[str]) -> set[str]:
    normalized: set[str] = set()
    for raw in values:
        value = raw.strip().lower()
        for topic in TOPICS:
            if value == topic.topic_id or any(alias in value for alias in topic.aliases):
                normalized.add(topic.topic_id)
    return normalized


def _relevant_period_ids(record: ChartRecord, now: datetime) -> list[str]:
    start = now - timedelta(days=366)
    end = now + timedelta(days=365 * 5)
    return [
        period.period_id
        for period in record.timing_periods
        if period.interval.end > start and period.interval.start < end
    ]
