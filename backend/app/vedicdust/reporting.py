from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    AgentClaimContext,
    AgentContext,
    AgentFactContext,
    ChartRecord,
    Claim,
    ClaimGraph,
    ConsultationDossier,
    ConsultationReportManifest,
    ReportSection,
    TimingWindow,
)


COPY = {
    "en": {
        "report_title": "VedicDust Consultation",
        "scope": "Reading scope",
        "birth_basis": "Birth basis",
        "method": "Method",
        "confidence": "Confidence",
        "requested_topics": "Requested topics",
        "included_topics": "Included topics",
        "omitted_topics": "Not included",
        "report_depth": "Report depth",
        "chart_revision": "Chart revision",
        "rule_pack": "Rule pack",
        "residual_uncertainty": "Residual uncertainty",
        "meaning": "What this may mean",
        "expressions": "How it may show up",
        "counterweight": "Limits and counterweights",
        "conditions": "Conditions",
        "implications": "Practical implications",
        "technical_basis": "Technical basis",
        "timing": "Timing",
        "opportunities": "Constructive expression",
        "pressures": "Pressure expression",
        "questions": "Questions to carry forward",
        "no_timing": "No timing window passed the current evidence and confidence gate.",
        "no_questions": "No unresolved consultation question is currently recorded.",
        "evidence": "Technical evidence",
        "claim": "Claim",
        "facts": "Facts",
        "rules": "Rules",
        "counter_facts": "Counter-evidence",
        "certainty": "Certainty",
    },
    "zh": {
        "report_title": "VedicDust 专业咨询档案",
        "scope": "本次解读范围",
        "birth_basis": "出生依据",
        "method": "计算与解读方法",
        "confidence": "整体可信度",
        "requested_topics": "本次关注",
        "included_topics": "纳入解读",
        "omitted_topics": "本次未纳入",
        "report_depth": "报告深度",
        "chart_revision": "盘面版本",
        "rule_pack": "判断规则包",
        "residual_uncertainty": "仍需保留的不确定性",
        "meaning": "这对你可能意味着什么",
        "expressions": "现实中可能如何表现",
        "counterweight": "限制与相反力量",
        "conditions": "成立条件",
        "implications": "现实启示",
        "technical_basis": "技术依据",
        "timing": "时间范围",
        "opportunities": "有利表达",
        "pressures": "压力表达",
        "questions": "值得继续讨论的问题",
        "no_timing": "当前没有通过证据与可信度门槛的时间窗口。",
        "no_questions": "当前没有尚待确认的咨询问题。",
        "evidence": "专业证据附录",
        "claim": "判断",
        "facts": "盘面事实",
        "rules": "方法规则",
        "counter_facts": "相反证据",
        "certainty": "可信度",
    },
    "ja": {
        "report_title": "VedicDust コンサルテーション記録",
        "scope": "今回のリーディング範囲",
        "birth_basis": "出生情報の根拠",
        "method": "計算と判断方法",
        "confidence": "総合的な確度",
        "requested_topics": "相談テーマ",
        "included_topics": "今回扱うテーマ",
        "omitted_topics": "今回扱わないテーマ",
        "report_depth": "レポートの深さ",
        "chart_revision": "チャート版",
        "rule_pack": "判断ルールパック",
        "residual_uncertainty": "残る不確実性",
        "meaning": "この配置が示しうること",
        "expressions": "現実での現れ方",
        "counterweight": "制約と反対要因",
        "conditions": "成立条件",
        "implications": "実践上の示唆",
        "technical_basis": "技術的根拠",
        "timing": "期間",
        "opportunities": "建設的な現れ方",
        "pressures": "負荷としての現れ方",
        "questions": "今後の相談テーマ",
        "no_timing": "現在の証拠と確度の基準を満たす時期判断はありません。",
        "no_questions": "現在、未解決の相談テーマは記録されていません。",
        "evidence": "専門的根拠",
        "claim": "判断",
        "facts": "チャート事実",
        "rules": "判断ルール",
        "counter_facts": "反証",
        "certainty": "確度",
    },
}


def build_report_manifest(dossier: ConsultationDossier) -> ConsultationReportManifest:
    return ConsultationReportManifest(
        dossier_id=dossier.dossier_id,
        chart_record_id=dossier.chart_record_id,
        chart_revision=dossier.chart_revision,
        claim_graph_version=dossier.claim_graph_version,
        generated_at=dossier.generated_at,
        locale=dossier.locale,
        audience=dossier.audience,
        sections=dossier.sections,
        omitted_claim_ids=dossier.omitted_claim_ids,
        release_status=dossier.release_status,
    )


def build_agent_context(
    record: ChartRecord,
    graph: ClaimGraph,
    dossier: ConsultationDossier,
) -> AgentContext:
    window_ids_by_claim: dict[str, list[str]] = {}
    for window in dossier.timing_windows:
        for claim_id in window.claim_ids:
            window_ids_by_claim.setdefault(claim_id, []).append(window.timing_window_id)

    approved_claims = [
        AgentClaimContext(
            claim_id=claim.claim_id,
            topic=claim.topic,
            statement=claim.plain_statement,
            user_relevance=claim.user_relevance,
            certainty=claim.certainty,
            supporting_fact_ids=claim.supporting_fact_ids,
            counter_fact_ids=claim.counter_fact_ids,
            rule_ids=claim.rule_ids,
            conditions=claim.conditions,
            practical_implications=claim.practical_implications,
            limitations=claim.limitations,
            time_scope=claim.time_scope,
            timing_window_ids=window_ids_by_claim.get(claim.claim_id, []),
        )
        for claim in graph.claims
        if claim.status != "withheld" and claim.certainty != "withheld"
    ]
    topic_index: dict[str, list[str]] = {}
    for claim in approved_claims:
        topic_index.setdefault(claim.topic, []).append(claim.claim_id)

    stable_fact_ids = sorted(
        {
            fact_id
            for claim in graph.claims
            if claim.status != "withheld"
            for fact_id in (
                claim.supporting_fact_ids + claim.counter_fact_ids + claim.timing_fact_ids
            )
        }
    )
    user_confirmed_event_ids = (
        [event.event_id for event in record.rectification.life_events]
        if record.rectification
        else []
    )
    facts_by_id = {fact.fact_id: fact for fact in record.facts}
    stable_facts = [
        AgentFactContext(
            fact_id=fact.fact_id,
            fact_type=fact.fact_type,
            subject_ref=fact.subject_ref,
            value=fact.value,
            unit=fact.unit,
            confidence=fact.provenance.confidence,
        )
        for fact_id in stable_fact_ids
        if (fact := facts_by_id.get(fact_id)) is not None
    ]

    return AgentContext(
        dossier_id=dossier.dossier_id,
        chart_record_id=record.chart_record_id,
        chart_revision=record.revision,
        generated_at=datetime.now(timezone.utc),
        locale=dossier.locale,
        stable_fact_ids=stable_fact_ids,
        stable_facts=stable_facts,
        approved_claims=approved_claims,
        withheld_claim_ids=[claim.claim_id for claim in graph.claims if claim.status == "withheld"],
        timing_windows=dossier.timing_windows,
        user_confirmed_event_ids=user_confirmed_event_ids,
        rejected_hypotheses=[
            f"{claim_id}: {reason}" for claim_id, reason in dossier.omitted_claim_ids.items()
        ],
        open_questions=dossier.unresolved_questions,
        uncertainties=[
            *dossier.scope.residual_uncertainties,
            *[
                limitation
                for claim in graph.claims
                if claim.status != "withheld"
                for limitation in claim.limitations
            ],
        ],
        topic_index=topic_index,
    )


def render_consultation_report(
    record: ChartRecord,
    graph: ClaimGraph,
    dossier: ConsultationDossier,
) -> str:
    copy = COPY.get(dossier.locale, COPY["en"])
    claims_by_id = {claim.claim_id: claim for claim in graph.claims}
    windows_by_id = {window.timing_window_id: window for window in dossier.timing_windows}
    lines = [
        f"# {copy['report_title']}",
        "",
        f"> {copy['confidence']}: **{_grade(dossier.confidence.overall, dossier.locale)}**",
        f"> {copy['method']}: `{dossier.method_profile_id}`",
        f"> {copy['rule_pack']}: `{graph.rule_pack_version}`",
        f"> {copy['chart_revision']}: `{dossier.chart_revision}`",
        "",
    ]

    for section in sorted(dossier.sections, key=lambda item: (item.priority, item.section_id)):
        lines.extend([f"## {section.title}", ""])
        if section.section_kind == "scope":
            lines.extend(_render_scope(record, dossier, copy))
        elif section.section_kind == "timing_outlook":
            rendered_window = False
            for window_id in section.timing_window_ids:
                window = windows_by_id.get(window_id)
                if window:
                    lines.extend(_render_timing_window(window, copy, dossier.locale))
                    rendered_window = True
            if not rendered_window:
                lines.extend([copy["no_timing"], ""])
        elif section.section_kind == "follow_up":
            if dossier.unresolved_questions:
                lines.extend([f"- {question}" for question in dossier.unresolved_questions])
                lines.append("")
            else:
                lines.extend([copy["no_questions"], ""])
        elif section.section_kind == "technical_evidence":
            lines.extend(_render_evidence(graph, section, copy))
        else:
            for claim_id in section.claim_ids:
                claim = claims_by_id.get(claim_id)
                if claim and claim.status != "withheld":
                    lines.extend(_render_claim(claim, copy, dossier.locale))

    return "\n".join(lines).rstrip() + "\n"


def _render_scope(
    record: ChartRecord,
    dossier: ConsultationDossier,
    copy: dict[str, str],
) -> list[str]:
    canonical = record.canonical_moment
    birth_basis = record.birth_assertion.reported_place
    if canonical:
        birth_basis = (
            f"{canonical.local_datetime.isoformat()} · {canonical.place.label} · "
            f"{canonical.timezone_id}"
        )
    lines = [
        f"- **{copy['birth_basis']}**: {birth_basis}",
        f"- **{copy['confidence']}**: {_grade(dossier.confidence.overall, dossier.locale)}",
        f"- **{copy['report_depth']}**: {dossier.scope.report_depth}",
    ]
    if dossier.scope.requested_topics:
        lines.append(
            f"- **{copy['requested_topics']}**: " + ", ".join(dossier.scope.requested_topics)
        )
    if dossier.scope.included_topics:
        lines.append(
            f"- **{copy['included_topics']}**: " + ", ".join(dossier.scope.included_topics)
        )
    if dossier.scope.omitted_topics:
        lines.append(f"- **{copy['omitted_topics']}**:")
        lines.extend(
            f"  - {topic}: {reason}" for topic, reason in dossier.scope.omitted_topics.items()
        )
    if dossier.scope.residual_uncertainties:
        lines.append(f"- **{copy['residual_uncertainty']}**:")
        lines.extend(f"  - {uncertainty}" for uncertainty in dossier.scope.residual_uncertainties)
    lines.extend(f"- {rationale}" for rationale in dossier.confidence.rationale)
    lines.append("")
    return lines


def _render_claim(claim: Claim, copy: dict[str, str], locale: str) -> list[str]:
    title = claim.title or claim.topic
    lines = [
        f"### {title}",
        "",
        claim.plain_statement,
        "",
        f"**{copy['confidence']}**: {_grade(claim.certainty, locale)}",
    ]
    if claim.user_relevance:
        lines.extend(["", f"**{copy['meaning']}**", "", claim.user_relevance])
    if claim.real_world_expressions:
        lines.extend(["", f"**{copy['expressions']}**", ""])
        lines.extend(f"- {item}" for item in claim.real_world_expressions)
    if claim.conditions:
        lines.extend(["", f"**{copy['conditions']}**", ""])
        lines.extend(f"- {item}" for item in claim.conditions)
    if claim.practical_implications:
        lines.extend(["", f"**{copy['implications']}**", ""])
        lines.extend(f"- {item}" for item in claim.practical_implications)
    if claim.limitations:
        lines.extend(["", f"**{copy['counterweight']}**", ""])
        lines.extend(f"- {item}" for item in claim.limitations)
    if claim.time_scope:
        lines.extend(
            [
                "",
                f"**{copy['timing']}**: "
                f"{claim.time_scope.start.date().isoformat()} – "
                f"{claim.time_scope.end.date().isoformat()}",
            ]
        )
    lines.extend(["", f"_{copy['technical_basis']}: {claim.technical_statement}_", ""])
    return lines


def _render_timing_window(window: TimingWindow, copy: dict[str, str], locale: str) -> list[str]:
    lines = [
        f"### {window.title}",
        "",
        f"**{copy['timing']}**: {window.interval.start.date().isoformat()} – "
        f"{window.interval.end.date().isoformat()}",
        "",
        f"**{copy['confidence']}**: {_grade(window.confidence, locale)}",
    ]
    for label, values in (
        (copy["opportunities"], window.opportunities),
        (copy["pressures"], window.pressures),
        (copy["conditions"], window.conditions),
        (copy["counterweight"], window.limitations),
    ):
        if values:
            lines.extend(["", f"**{label}**", ""])
            lines.extend(f"- {value}" for value in values)
    lines.append("")
    return lines


def _render_evidence(
    graph: ClaimGraph,
    section: ReportSection,
    copy: dict[str, str],
) -> list[str]:
    allowed = set(section.claim_ids)
    claims = [
        claim
        for claim in graph.claims
        if claim.status != "withheld" and (not allowed or claim.claim_id in allowed)
    ]
    lines = [
        f"### {copy['evidence']}",
        "",
        f"| {copy['claim']} | {copy['certainty']} | {copy['facts']} | "
        f"{copy['counter_facts']} | {copy['rules']} |",
        "|---|---|---|---|---|",
    ]
    for claim in claims:
        title = claim.title or claim.topic
        supporting_ids = claim.supporting_fact_ids + claim.timing_fact_ids + claim.timing_period_ids
        lines.append(
            f"| {title} | {claim.certainty} | {', '.join(supporting_ids)} | "
            f"{', '.join(claim.counter_fact_ids) or '-'} | {', '.join(claim.rule_ids)} |"
        )
    lines.append("")
    return lines


def _grade(value: str, locale: str) -> str:
    labels = {
        "en": {
            "high": "High",
            "moderate": "Moderate",
            "low": "Low",
            "blocked": "Blocked",
        },
        "zh": {
            "high": "高",
            "moderate": "中等",
            "low": "低",
            "blocked": "暂不可发布",
        },
        "ja": {
            "high": "高",
            "moderate": "中",
            "low": "低",
            "blocked": "公開不可",
        },
    }
    return labels.get(locale, labels["en"]).get(value, value)
