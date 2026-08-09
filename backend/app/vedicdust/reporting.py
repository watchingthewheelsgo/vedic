from __future__ import annotations

from datetime import date, datetime

from .models import (
    AgentClaimContext,
    AgentContext,
    AgentFactContext,
    ChartRecord,
    Claim,
    ClaimGraph,
    ConfidenceGrade,
    ConsultationConfidence,
    ConsultationDossier,
    ConsultationReportManifest,
    JudgementContext,
    QualityCheck,
    ReportSection,
    TimeRange,
    TimingWindow,
)
from .confidence import effective_fact_confidence


COPY = {
    "en": {
        "report_title": "VedicDust Consultation",
        "scope": "Reading scope",
        "reported_birth": "Reported birth details",
        "calculation_basis": "Chart calculation basis",
        "calculation_assurance": "Calculation assurance",
        "method": "Method",
        "confidence": "Confidence",
        "requested_topics": "Requested topics",
        "included_topics": "Included topics",
        "omitted_topics": "Not included",
        "report_depth": "Report depth",
        "reading_frame": "Reading frame",
        "age_during_window": "Age during this window",
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
        "context_facts": "Context facts",
        "rules": "Rules",
        "counter_facts": "Counter-evidence",
        "certainty": "Certainty",
        "assurance_note": (
            "Stable findings are presented first. Method details and traceable evidence are kept "
            "in the professional appendix."
        ),
    },
    "zh": {
        "report_title": "VedicDust 专业咨询档案",
        "scope": "本次解读范围",
        "reported_birth": "用户报告的出生信息",
        "calculation_basis": "本次盘面采用的计算依据",
        "calculation_assurance": "计算验证范围",
        "method": "计算与解读方法",
        "confidence": "整体可信度",
        "requested_topics": "本次关注",
        "included_topics": "纳入解读",
        "omitted_topics": "本次未纳入",
        "report_depth": "报告深度",
        "reading_frame": "解读对象",
        "age_during_window": "该阶段年龄",
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
        "context_facts": "结构背景",
        "rules": "方法规则",
        "counter_facts": "相反证据",
        "certainty": "可信度",
        "assurance_note": "正文优先呈现稳定且与你有关的结论；计算方法和可追溯依据集中放在专业附录。",
    },
    "ja": {
        "report_title": "VedicDust コンサルテーション記録",
        "scope": "今回のリーディング範囲",
        "reported_birth": "申告された出生情報",
        "calculation_basis": "今回のチャート計算基準",
        "calculation_assurance": "計算検証の範囲",
        "method": "計算と判断方法",
        "confidence": "総合的な確度",
        "requested_topics": "相談テーマ",
        "included_topics": "今回扱うテーマ",
        "omitted_topics": "今回扱わないテーマ",
        "report_depth": "レポートの深さ",
        "reading_frame": "リーディング対象",
        "age_during_window": "この期間の年齢",
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
        "context_facts": "構造的背景",
        "rules": "判断ルール",
        "counter_facts": "反証",
        "certainty": "確度",
        "assurance_note": "本文では安定した要点を優先し、計算方法と追跡可能な根拠は専門付録にまとめます。",
    },
}


_CONFIDENCE_LEVEL = {
    ConfidenceGrade.VERIFIED: "high",
    ConfidenceGrade.CORROBORATED: "moderate",
    ConfidenceGrade.PROVISIONAL: "low",
    ConfidenceGrade.DISPUTED: "low",
    ConfidenceGrade.UNAVAILABLE: "low",
}
_CERTAINTY_RANK = {"low": 0, "moderate": 1, "high": 2}


def materialize_consultation_dossier(
    record: ChartRecord,
    graph: ClaimGraph,
    context: JudgementContext,
    draft: ConsultationDossier,
) -> ConsultationDossier:
    """Replace model-authored release semantics with backend-owned projections."""

    dossier = draft.model_copy(deep=True)
    dossier.dossier_id = f"dossier.{record.chart_record_id}.r{record.revision}"
    dossier.generated_at = graph.generated_at
    dossier.locale = record.subject.locale
    dossier.audience = record.subject.reader_relationship
    dossier.sections = _materialize_report_sections(record, graph, dossier.sections)
    dossier.omitted_claim_ids = {
        claim_id: _omitted_claim_reason(record.subject.locale)
        for claim_id in sorted(dossier.omitted_claim_ids)
    }
    dossier.unresolved_questions = (
        list(record.rectification.decision.unresolved_questions)
        if record.rectification is not None
        else []
    )

    claims_by_id = {claim.claim_id: claim for claim in graph.claims}
    assigned_claim_ids = {
        claim_id
        for section in dossier.sections
        for claim_id in section.claim_ids
        if claim_id in claims_by_id
    }
    included_claims = [
        claims_by_id[claim_id]
        for claim_id in sorted(assigned_claim_ids)
        if claims_by_id[claim_id].status != "withheld"
    ]
    omitted_topics = dict(graph.omitted_topics)
    for claim_id, reason in sorted(dossier.omitted_claim_ids.items()):
        claim = claims_by_id.get(claim_id)
        if claim is not None:
            omitted_topics.setdefault(claim.topic, reason)

    dossier.scope.requested_topics = list(context.requested_topics)
    dossier.scope.user_questions = list(record.subject.consultation_topics)
    dossier.scope.included_topics = sorted({claim.topic for claim in included_claims})
    dossier.scope.omitted_topics = omitted_topics
    dossier.scope.residual_uncertainties = _residual_uncertainties(record)
    dossier.confidence = _consultation_confidence(record, included_claims)

    timing_section = next(
        (section for section in dossier.sections if section.section_kind == "timing_outlook"),
        None,
    )
    timing_claims = (
        [
            claims_by_id[claim_id]
            for claim_id in timing_section.claim_ids
            if claim_id in claims_by_id
            and claims_by_id[claim_id].scope == "timing"
            and claims_by_id[claim_id].status != "withheld"
        ]
        if timing_section is not None
        else []
    )
    dossier.timing_windows = [
        _timing_window_from_claim(claim, graph.generated_at) for claim in timing_claims
    ]
    if timing_section is not None:
        timing_section.timing_window_ids = [
            window.timing_window_id for window in dossier.timing_windows
        ]
    dossier.quality_checks = _dossier_release_checks(record, graph, context, dossier)
    dossier.release_status = (
        "approved"
        if all(check.status == "passed" for check in dossier.quality_checks)
        else "blocked"
    )
    return dossier


def _materialize_report_sections(
    record: ChartRecord,
    graph: ClaimGraph,
    sections: list[ReportSection],
) -> list[ReportSection]:
    claims_by_id = {claim.claim_id: claim for claim in graph.claims}
    titles = {
        "en": {
            "scope": "Reading scope",
            "executive_synthesis": "Executive synthesis",
            "chart_foundation": "Chart foundation",
            "core_architecture": "Core chart architecture",
            "priority_domain": "Priority domain",
            "timing_outlook": "Timing outlook",
            "decision_support": "Decision support",
            "follow_up": "Questions to carry forward",
            "technical_evidence": "Technical evidence",
        },
        "zh": {
            "scope": "本次解读范围",
            "executive_synthesis": "核心结论",
            "chart_foundation": "盘面基础",
            "core_architecture": "核心结构",
            "priority_domain": "重点领域",
            "timing_outlook": "时间窗口",
            "decision_support": "现实决策参考",
            "follow_up": "值得继续讨论的问题",
            "technical_evidence": "专业证据附录",
        },
        "ja": {
            "scope": "今回のリーディング範囲",
            "executive_synthesis": "主要な結論",
            "chart_foundation": "チャートの基礎",
            "core_architecture": "チャートの中核構造",
            "priority_domain": "優先テーマ",
            "timing_outlook": "時期の見通し",
            "decision_support": "意思決定の参考",
            "follow_up": "今後の相談テーマ",
            "technical_evidence": "専門的根拠",
        },
    }
    priorities = {
        "scope": 10,
        "executive_synthesis": 20,
        "chart_foundation": 30,
        "core_architecture": 40,
        "priority_domain": 50,
        "timing_outlook": 70,
        "decision_support": 80,
        "follow_up": 90,
        "technical_evidence": 100,
    }
    localized_titles = titles.get(record.subject.locale, titles["en"])
    materialized: list[ReportSection] = []
    priority_domain_index = 0
    for source in sections:
        section = source.model_copy(deep=True)
        title = localized_titles[section.section_kind]
        if section.section_kind == "priority_domain":
            priority_domain_index += 1
            first_claim = next(
                (
                    claims_by_id[claim_id]
                    for claim_id in section.claim_ids
                    if claim_id in claims_by_id
                ),
                None,
            )
            if first_claim is not None:
                title = first_claim.title
            section.priority = priorities[section.section_kind] + priority_domain_index
        else:
            section.priority = priorities[section.section_kind]
        section.title = title
        section.purpose = f"Render approved {section.section_kind} content."
        section.visual_refs = []
        section.confidence_disclosure_required = any(
            claims_by_id[claim_id].certainty == "low"
            for claim_id in section.claim_ids
            if claim_id in claims_by_id
        )
        materialized.append(section)
    return materialized


def _omitted_claim_reason(locale: str) -> str:
    if locale == "zh":
        return "为保持报告聚焦，本条已从正文省略；后端批准的判断仍保留在咨询上下文中。"
    if locale == "ja":
        return "レポートを焦点化するため本文から省略しました。承認済みの判断は相談コンテキストに保持されています。"
    return (
        "Omitted from the main narrative to keep the report focused; the approved "
        "judgement remains available in the consultation context."
    )


def _dossier_release_checks(
    record: ChartRecord,
    graph: ClaimGraph,
    context: JudgementContext,
    dossier: ConsultationDossier,
) -> list[QualityCheck]:
    prerequisite_failures = [
        check.check_id
        for check in [*record.quality_checks, *context.quality_checks, *graph.quality_checks]
        if check.status == "failed"
    ]
    if record.status not in {"ready_for_judgement", "rectified"}:
        prerequisite_failures.append(f"chart-status:{record.status}")

    claims_by_id = {claim.claim_id: claim for claim in graph.claims}
    released_claim_ids = {claim.claim_id for claim in graph.claims if claim.status != "withheld"}
    assigned_claim_ids = [
        claim_id for section in dossier.sections for claim_id in section.claim_ids
    ]
    omitted_claim_ids = set(dossier.omitted_claim_ids)
    assignment_failures: list[str] = []
    unknown_or_withheld = sorted(
        {
            claim_id
            for claim_id in assigned_claim_ids
            if claim_id not in claims_by_id or claims_by_id[claim_id].status == "withheld"
        }
    )
    if unknown_or_withheld:
        assignment_failures.append("unknown-or-withheld:" + ",".join(unknown_or_withheld))
    duplicate_claim_ids = sorted(
        {claim_id for claim_id in assigned_claim_ids if assigned_claim_ids.count(claim_id) > 1}
    )
    if duplicate_claim_ids:
        assignment_failures.append("duplicate:" + ",".join(duplicate_claim_ids))
    unaccounted = sorted(released_claim_ids - set(assigned_claim_ids) - omitted_claim_ids)
    if unaccounted:
        assignment_failures.append("unaccounted:" + ",".join(unaccounted))
    assigned_and_omitted = sorted(set(assigned_claim_ids) & omitted_claim_ids)
    if assigned_and_omitted:
        assignment_failures.append("assigned-and-omitted:" + ",".join(assigned_and_omitted))
    unknown_omitted = sorted(omitted_claim_ids - set(claims_by_id))
    if unknown_omitted:
        assignment_failures.append("unknown-omitted:" + ",".join(unknown_omitted))

    required_kinds = {
        "scope",
        "executive_synthesis",
        "chart_foundation",
        "timing_outlook",
        "decision_support",
        "follow_up",
        "technical_evidence",
    }
    sections_by_kind = {section.section_kind: section for section in dossier.sections}
    structure_failures = [
        f"missing-section:{kind}" for kind in sorted(required_kinds - set(sections_by_kind))
    ]
    narrative_section_kinds = {
        "executive_synthesis",
        "chart_foundation",
        "core_architecture",
        "priority_domain",
        "timing_outlook",
        "decision_support",
    }
    for section in dossier.sections:
        if (
            section.section_kind in narrative_section_kinds
            and section.claim_ids
            and not section.narratives
        ):
            structure_failures.append(f"missing-grounded-narrative:{section.section_kind}")
    executive_claim_ids = set(dossier.executive_claim_ids)
    executive_section = sections_by_kind.get("executive_synthesis")
    executive_section_ids = set(executive_section.claim_ids if executive_section else [])
    if not 3 <= len(dossier.executive_claim_ids) <= 5:
        structure_failures.append("executive-claim-count")
    if executive_claim_ids != executive_section_ids:
        structure_failures.append("executive-section-mismatch")
    if executive_claim_ids - released_claim_ids:
        structure_failures.append("executive-claim-not-released")
    for kind in ("chart_foundation", "decision_support"):
        section = sections_by_kind.get(kind)
        if section is None or not section.claim_ids:
            structure_failures.append(f"empty-section:{kind}")

    return [
        QualityCheck(
            checkId="consultation.release-prerequisites",
            status="passed" if not prerequisite_failures else "failed",
            expected="ready chart and no failed deterministic quality checks",
            observed=prerequisite_failures,
            message=(
                "The deterministic chart, judgement, and claim prerequisites permit release."
                if not prerequisite_failures
                else "Deterministic prerequisites do not permit consultation release."
            ),
        ),
        QualityCheck(
            checkId="consultation.claim-accounting",
            status="passed" if not assignment_failures else "failed",
            expected="every released claim assigned once or explicitly omitted",
            observed=assignment_failures,
            message=(
                "Every released claim is accounted for exactly once."
                if not assignment_failures
                else "The consultation arrangement does not account for every released claim."
            ),
        ),
        QualityCheck(
            checkId="consultation.report-structure",
            status="passed" if not structure_failures else "failed",
            expected="required sections and three to five released executive claims",
            observed=structure_failures,
            message=(
                "The report structure satisfies the deterministic release contract."
                if not structure_failures
                else "The report structure does not satisfy the release contract."
            ),
        ),
    ]


def _consultation_confidence(
    record: ChartRecord,
    claims: list[Claim],
) -> ConsultationConfidence:
    input_grade = (
        record.canonical_moment.resolution_confidence
        if record.canonical_moment is not None
        else ConfidenceGrade.UNAVAILABLE
    )
    rectification_grade = (
        record.rectification.decision.confidence
        if record.rectification is not None
        else input_grade
    )
    claim_certainties = [claim.certainty for claim in claims if claim.certainty in _CERTAINTY_RANK]
    judgement = (
        min(claim_certainties, key=lambda value: _CERTAINTY_RANK[value])
        if claim_certainties
        else "low"
    )
    overall = min(
        (_CONFIDENCE_LEVEL[input_grade], _CONFIDENCE_LEVEL[rectification_grade], judgement),
        key=lambda value: _CERTAINTY_RANK[value],
    )
    rationale = _confidence_rationale(
        record.subject.locale,
        input_grade.value,
        rectification_grade.value,
        judgement,
    )
    return ConsultationConfidence(
        overall=overall,
        input_confidence=input_grade,
        rectification_confidence=rectification_grade,
        judgement_confidence=judgement,
        rationale=rationale,
    )


def _confidence_rationale(
    locale: str,
    input_grade: str,
    rectification_grade: str,
    judgement_grade: str,
) -> list[str]:
    if locale == "zh":
        return [
            f"出生输入可信度：{input_grade}。",
            f"生时校正可信度：{rectification_grade}。",
            f"本报告纳入判断的最低可信度：{judgement_grade}。",
        ]
    if locale == "ja":
        return [
            f"出生入力の確度: {input_grade}。",
            f"出生時刻補正の確度: {rectification_grade}。",
            f"採用した判断の最低確度: {judgement_grade}。",
        ]
    return [
        f"Birth input confidence: {input_grade}.",
        f"Birth-time rectification confidence: {rectification_grade}.",
        f"Lowest certainty among included judgements: {judgement_grade}.",
    ]


def _residual_uncertainties(record: ChartRecord) -> list[str]:
    values = [
        check.message for check in record.quality_checks if check.status in {"warning", "not_run"}
    ]
    if record.rectification is not None:
        values.extend(record.rectification.decision.unresolved_questions)
        if (
            record.rectification.decision.status in {"bounded_interval", "multiple_equivalent"}
            and record.rectification.validation_status == "internal_regression_only"
        ):
            values.append(_rectification_validation_limitation(record.subject.locale))
    return list(dict.fromkeys(values))


def _rectification_validation_limitation(locale: str) -> str:
    if locale == "zh":
        return "生时校正方法目前仅通过内部回归测试，尚未完成独立专业盲审。"
    if locale == "ja":
        return "出生時刻補正手法は現在、内部回帰テストのみを通過しており、独立した専門家の盲検レビューは未完了です。"
    return (
        "The birth-time rectification method has passed internal regression tests only; "
        "independent professional blind review is still pending."
    )


def _timing_window_from_claim(claim: Claim, reference_time: datetime) -> TimingWindow:
    if claim.scope != "timing" or claim.time_scope is None:
        raise ValueError(f"claim {claim.claim_id} is not eligible for a timing window")
    if claim.time_scope.end <= reference_time:
        horizon = "historical"
    elif claim.time_scope.start <= reference_time < claim.time_scope.end:
        horizon = "current"
    elif (claim.time_scope.start - reference_time).days <= 730:
        horizon = "near_term"
    else:
        horizon = "strategic"
    return TimingWindow(
        timing_window_id=f"window.{claim.claim_id.removeprefix('claim.')}",
        title=claim.title,
        horizon=horizon,
        interval=claim.time_scope,
        claim_ids=[claim.claim_id],
        activation_fact_ids=claim.timing_fact_ids,
        activation_period_ids=claim.timing_period_ids,
        opportunities=claim.real_world_expressions,
        pressures=[],
        conditions=claim.conditions,
        confidence=claim.certainty,
        limitations=claim.limitations,
    )


def build_report_manifest(dossier: ConsultationDossier) -> ConsultationReportManifest:
    _require_approved_dossier(dossier, "build a public report manifest")
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
    _require_approved_dossier(dossier, "build future consultation context")
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
            evidence_confidence=claim.evidence_confidence,
            certainty=claim.certainty,
            supporting_fact_ids=claim.supporting_fact_ids,
            context_fact_ids=claim.context_fact_ids,
            counter_fact_ids=claim.counter_fact_ids,
            counter_statements=claim.counter_statements,
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
                claim.supporting_fact_ids
                + claim.context_fact_ids
                + claim.counter_fact_ids
                + claim.timing_fact_ids
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
            confidence=effective_fact_confidence(fact),
            calculationConfidence=fact.provenance.confidence,
            inputStability=fact.input_stability,
        )
        for fact_id in stable_fact_ids
        if (fact := facts_by_id.get(fact_id)) is not None
    ]

    return AgentContext(
        dossier_id=dossier.dossier_id,
        chart_record_id=record.chart_record_id,
        chart_revision=record.revision,
        generated_at=dossier.generated_at,
        locale=dossier.locale,
        subject=record.subject,
        reported_birth_date=record.birth_assertion.local_date,
        stable_fact_ids=stable_fact_ids,
        stable_facts=stable_facts,
        approved_claims=approved_claims,
        withheld_claim_ids=[claim.claim_id for claim in graph.claims if claim.status == "withheld"],
        timing_windows=dossier.timing_windows,
        user_confirmed_event_ids=user_confirmed_event_ids,
        rejected_hypotheses=[],
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
    _require_approved_dossier(dossier, "render a public consultation report")
    copy = _audience_copy(COPY.get(dossier.locale, COPY["en"]), dossier.locale, dossier.audience)
    claims_by_id = {claim.claim_id: claim for claim in graph.claims}
    windows_by_id = {window.timing_window_id: window for window in dossier.timing_windows}
    lines = [
        f"# {copy['report_title']}",
        "",
        f"> {copy['confidence']}: **{_grade(dossier.confidence.overall, dossier.locale)}**",
        f"> {copy['assurance_note']}",
        "",
    ]

    for section in sorted(dossier.sections, key=lambda item: (item.priority, item.section_id)):
        lines.extend([f"## {section.title}", ""])
        for narrative in section.narratives:
            lines.extend([narrative.text, ""])
        if section.section_kind == "scope":
            lines.extend(_render_scope(record, dossier, copy))
        elif section.section_kind == "timing_outlook":
            rendered_window = False
            for window_id in section.timing_window_ids:
                window = windows_by_id.get(window_id)
                if window:
                    lines.extend(_render_timing_window(window, copy, dossier.locale, record))
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
            visible_claims = [
                claim
                for claim_id in section.claim_ids
                if (claim := claims_by_id.get(claim_id)) is not None and claim.status != "withheld"
            ]
            if section.narratives:
                lines.extend(_render_claim_takeaways(visible_claims, copy, dossier.locale))
            else:
                for claim in visible_claims:
                    lines.extend(_render_claim(claim, copy, dossier.locale))

    return "\n".join(lines).rstrip() + "\n"


def _require_approved_dossier(dossier: ConsultationDossier, action: str) -> None:
    if dossier.release_status != "approved" or any(
        check.status != "passed" for check in dossier.quality_checks
    ):
        raise ValueError(f"cannot {action} from an unapproved consultation dossier")


def _render_scope(
    record: ChartRecord,
    dossier: ConsultationDossier,
    copy: dict[str, str],
) -> list[str]:
    assertion = record.birth_assertion
    reported_time = assertion.reported_local_time or "unknown"
    reported_birth = (
        f"{assertion.local_date} {reported_time} · {assertion.reported_place} · "
        f"{_time_certainty_label(assertion.time_certainty, dossier.locale)}"
    )
    canonical = record.canonical_moment
    calculation_basis = "unresolved"
    if canonical:
        calculation_basis = (
            f"{canonical.local_datetime.isoformat()} · {canonical.place.label} · "
            f"{canonical.timezone_id}"
        )
        decision = record.rectification.decision if record.rectification else None
        if decision and decision.resulting_interval is not None:
            calculation_basis += (
                f" · {_selected_interval_label(dossier.locale)} "
                f"{decision.resulting_interval.start.isoformat()} to "
                f"{decision.resulting_interval.end.isoformat()}"
            )
        elif decision and decision.resulting_intervals:
            retained = "; ".join(
                f"{interval.start.isoformat()} to {interval.end.isoformat()}"
                for interval in decision.resulting_intervals
            )
            calculation_basis += f" · {_equivalent_intervals_label(dossier.locale)} {retained}"
    lines = [
        f"- **{copy['reported_birth']}**: {reported_birth}",
        f"- **{copy['calculation_basis']}**: {calculation_basis}",
        f"- **{copy['calculation_assurance']}**: {_calculation_assurance_label(record, dossier.locale)}",
        f"- **{copy['confidence']}**: {_grade(dossier.confidence.overall, dossier.locale)}",
        f"- **{copy['report_depth']}**: {_report_depth_label(dossier.scope.report_depth, dossier.locale)}",
        f"- **{copy['reading_frame']}**: {_reading_frame(record)}",
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
    if claim.counter_statements or claim.limitations:
        lines.extend(["", f"**{copy['counterweight']}**", ""])
        lines.extend(f"- {item}" for item in claim.counter_statements)
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
    lines.append("")
    return lines


def _render_claim_takeaways(claims: list[Claim], copy: dict[str, str], locale: str) -> list[str]:
    if not claims:
        return []
    heading = {
        "zh": "### 关键观察",
        "ja": "### 主なポイント",
        "en": "### Key observations",
    }.get(locale, "### Key observations")
    lines = [heading, ""]
    for claim in claims:
        title = claim.title or claim.topic
        lines.append(f"- **{title}** ({_grade(claim.certainty, locale)}): {claim.plain_statement}")
        if claim.user_relevance:
            lines.append(f"  - **{copy['meaning']}**: {claim.user_relevance}")
    lines.append("")
    return lines


def _render_timing_window(
    window: TimingWindow,
    copy: dict[str, str],
    locale: str,
    record: ChartRecord,
) -> list[str]:
    lines = [
        f"### {window.title}",
        "",
        f"**{copy['timing']}**: {window.interval.start.date().isoformat()} – "
        f"{window.interval.end.date().isoformat()}",
        "",
        f"**{copy['confidence']}**: {_grade(window.confidence, locale)}",
    ]
    age_range = _age_range_for_interval(record.birth_assertion.local_date, window.interval)
    if age_range is not None:
        start_age, end_age = age_range
        label = str(start_age) if start_age == end_age else f"{start_age}-{end_age}"
        lines.extend(["", f"**{copy['age_during_window']}**: {label}"])
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
    lines = [f"### {copy['evidence']}", ""]
    for claim in claims:
        title = claim.title or claim.topic
        supporting_ids = claim.supporting_fact_ids + claim.timing_fact_ids + claim.timing_period_ids
        lines.extend(
            [
                f"#### {title}",
                "",
                claim.technical_statement,
                "",
                f"- **{copy['certainty']}**: {claim.certainty}",
                f"- **{copy['facts']}**: {', '.join(supporting_ids)}",
                f"- **{copy['context_facts']}**: {', '.join(claim.context_fact_ids) or '-'}",
                f"- **{copy['counter_facts']}**: {', '.join(claim.counter_fact_ids) or '-'}",
                f"- **{copy['rules']}**: {', '.join(claim.rule_ids)}",
                "",
            ]
        )
    return lines


def _time_certainty_label(value: str, locale: str) -> str:
    labels = {
        "en": {
            "exact_minute": "recorded to the minute",
            "bounded_window": "reported as an approximate time",
            "part_of_day": "only the part of day is known",
            "unknown": "birth time is uncertain",
        },
        "zh": {
            "exact_minute": "时间记录到分钟",
            "bounded_window": "时间为大致范围",
            "part_of_day": "仅知道大致时段",
            "unknown": "出生时间不确定",
        },
        "ja": {
            "exact_minute": "分単位の記録あり",
            "bounded_window": "おおよその時間帯",
            "part_of_day": "時間帯のみ判明",
            "unknown": "出生時刻は不明確",
        },
    }
    return labels.get(locale, labels["en"]).get(value, value.replace("_", " "))


def _report_depth_label(value: str, locale: str) -> str:
    labels = {
        "en": {"standard": "focused consultation", "professional": "professional consultation"},
        "zh": {"standard": "重点咨询版", "professional": "专业完整解读"},
        "ja": {"standard": "重点相談版", "professional": "専門的な完全版"},
    }
    return labels.get(locale, labels["en"]).get(value, value)


def _calculation_assurance_label(record: ChartRecord, locale: str) -> str:
    non_d1 = [chart for chart in record.charts if chart.factor != 1]
    independently_matched = bool(non_d1) and all(
        chart.calculation_assurance == "independent_external_match" for chart in non_d1
    )
    labels = {
        "en": (
            "D1 uses Swiss Ephemeris; divisional charts match an independent external reference set."
            if independently_matched
            else "D1 uses Swiss Ephemeris; divisional charts have internal provider regression coverage, not a complete independent desktop-software match."
        ),
        "zh": (
            "D1 采用 Swiss Ephemeris；分盘已通过独立外部参考样本核对。"
            if independently_matched
            else "D1 采用 Swiss Ephemeris；分盘已通过内部提供方回归，但尚不等同于完整的独立桌面软件交叉验证。"
        ),
        "ja": (
            "D1 は Swiss Ephemeris を使用し、分割図は独立した外部参照と照合済みです。"
            if independently_matched
            else "D1 は Swiss Ephemeris を使用し、分割図は内部プロバイダー回帰済みですが、独立したデスクトップソフトとの完全照合ではありません。"
        ),
    }
    return labels.get(locale, labels["en"])


def _selected_interval_label(locale: str) -> str:
    return {"zh": "校正后采用范围", "ja": "補正後の採用範囲"}.get(
        locale, "rectified working interval"
    )


def _equivalent_intervals_label(locale: str) -> str:
    return {"zh": "保留的等价范围", "ja": "保持された同等範囲"}.get(
        locale, "retained equivalent intervals"
    )


def _audience_copy(
    base: dict[str, str],
    locale: str,
    audience: str,
) -> dict[str, str]:
    copy = dict(base)
    if audience == "self":
        return copy
    if locale == "zh":
        copy["meaning"] = "这对当事人可能意味着什么"
    elif locale == "ja":
        copy["meaning"] = "本人にとって何を意味しうるか"
    else:
        copy["meaning"] = "What this may mean for the subject"
    return copy


def _reading_frame(record: ChartRecord) -> str:
    subject = record.subject
    labels = {
        "zh": {
            "child": "儿童",
            "teen": "青少年",
            "young_adult": "青年",
            "adult": "成年人",
            "elder": "长者",
            "self": "本人阅读",
            "parent": "由父母阅读",
            "partner": "由伴侣阅读",
            "family": "由家人阅读",
            "professional": "专业咨询",
            "age": "岁",
        },
        "ja": {
            "child": "子ども",
            "teen": "青少年",
            "young_adult": "若年成人",
            "adult": "成人",
            "elder": "高齢期",
            "self": "本人向け",
            "parent": "保護者向け",
            "partner": "パートナー向け",
            "family": "家族向け",
            "professional": "専門相談",
            "age": "歳",
        },
    }
    locale = subject.locale
    localized = labels.get(locale)
    stage = subject.life_stage or "unspecified"
    relationship = subject.reader_relationship
    if localized is None:
        parts = [stage.replace("_", " "), relationship.replace("_", " ")]
        if subject.current_age is not None:
            parts.insert(0, f"age {subject.current_age}")
        return " · ".join(parts)
    parts = [localized.get(stage, stage), localized.get(relationship, relationship)]
    if subject.current_age is not None:
        parts.insert(0, f"{subject.current_age}{localized['age']}")
    return " · ".join(parts)


def _age_range_for_interval(
    birth_date: str,
    interval: TimeRange,
) -> tuple[int, int] | None:
    try:
        born = date.fromisoformat(birth_date)
        start = interval.start.date()
        end = interval.end.date()
    except (AttributeError, TypeError, ValueError):
        return None
    return _age_on_date(born, start), _age_on_date(born, end)


def _age_on_date(born: date, target: date) -> int:
    return target.year - born.year - ((target.month, target.day) < (born.month, born.day))


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
