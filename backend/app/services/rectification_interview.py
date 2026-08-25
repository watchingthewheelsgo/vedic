from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
import hashlib
import json
import re
from typing import Any

from app.schemas import AppLocale
from app.services.life_event_rectification import (
    MAX_RECTIFICATION_EVENTS,
    MIN_RECTIFICATION_EVENTS,
)
from app.vedicdust.rectification_policy import (
    RECTIFICATION_EVENT_RULES,
    RECTIFICATION_EVENT_SUBTYPES,
)


INTERVIEW_SCHEMA_VERSION = "vedicdust-rectification-interview/2.0.0"
_CLARIFICATION_REASON_CODES = frozenset(
    {
        "event_not_confirmed",
        "description_conflicts_with_selection",
        "date_or_occurrence_uncertain",
        "semantic_review_unavailable",
    }
)


class RectificationEvidenceClarificationRequired(ValueError):
    """Tell the client to clarify one answer without accepting or scoring it."""

    def __init__(self, result: dict[str, Any]):
        self.question_id = str(result.get("questionId") or "")
        self.reason_code = str(result.get("clarificationReasonCode") or "event_not_confirmed")
        self.clarification_question = str(result.get("clarificationQuestion") or "").strip()
        message = self.clarification_question or (
            "Please confirm that the selected event occurred and that the date and event type are correct."
        )
        super().__init__(message)

    def api_detail(self) -> dict[str, str]:
        return {
            "code": "rectification_evidence_clarification_required",
            "message": str(self),
            "questionId": self.question_id,
            "reasonCode": self.reason_code,
        }


_FIELD_CATEGORY_PRIORITY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("d24", ("education",)),
    ("d10", ("career",)),
    ("d4", ("relocation", "property")),
    ("d9", ("relationship",)),
    ("d7", ("child",)),
    ("d12", ("family",)),
    ("d2", ("finance",)),
    ("d30", ("health",)),
    ("d20", ("spiritual",)),
    ("lagnasign", ("relocation", "family")),
)

_DEFAULT_PRIORITY = (
    "education",
    "career",
    "relocation",
    "relationship",
    "family",
    "property",
    "finance",
    "child",
    "health",
    "spiritual",
    "legal",
    "loss",
)

_COPY: dict[str, dict[str, Any]] = {
    "en": {
        "title": "A few dates can narrow the birth window",
        "intro": (
            "Answer one card at a time. Choose events you remember independently; "
            "an approximate year or month is enough."
        ),
        "progress": "Confirmed {answered} of {target}",
        "why": "This event type helps compare the chart areas that change inside your reported time window.",
        "date": "When did this happen?",
        "details": "What changed?",
        "placeholder": "A short factual description is enough.",
        "category": {
            "education": (
                "Education milestone",
                "Think of admission, graduation, a major exam, or study abroad.",
            ),
            "career": (
                "Career turning point",
                "Think of a first job, promotion, job loss, career switch, or starting a business.",
            ),
            "relationship": (
                "Relationship milestone",
                "Think of a committed relationship, marriage, separation, or divorce.",
            ),
            "relocation": (
                "Major move",
                "Think of moving to another city or country, not a routine local move.",
            ),
            "child": (
                "Child or pregnancy milestone",
                "Think of a birth, pregnancy, adoption, or a major event involving a child.",
            ),
            "health": (
                "Major health event",
                "Think of surgery, hospitalization, a serious accident, or a clear diagnosis.",
            ),
            "family": (
                "Family turning point",
                "Think of a major event involving a parent or the structure of your household.",
            ),
            "finance": (
                "Financial turning point",
                "Think of a large gain, loss, debt, or a lasting income change.",
            ),
            "property": (
                "Home or property milestone",
                "Think of buying, selling, or losing a home or property.",
            ),
            "legal": (
                "Legal or dispute milestone",
                "Think of a lawsuit, formal dispute, or legal resolution.",
            ),
            "loss": (
                "Major bereavement",
                "Only answer if you are comfortable sharing a clearly dated major loss.",
            ),
            "spiritual": (
                "Spiritual turning point",
                "Think of a lasting change in practice, faith, or worldview.",
            ),
        },
    },
    "zh": {
        "title": "几个真实日期，可以帮助缩小出生时间范围",
        "intro": "每次只回答一张卡片。请选择你能独立确认的真实事件，记得年份或月份就可以。",
        "progress": "已确认 {answered}/{target}",
        "why": "这类事件可以区分你所报告时间范围内发生变化的盘面部分。",
        "date": "大约发生在什么时候？",
        "details": "当时发生了什么变化？",
        "placeholder": "用一句事实描述即可，不需要解释原因。",
        "category": {
            "education": (
                "一次重要的学习节点",
                "例如入学、毕业、重要考试、留学或明显改变学习方向。",
            ),
            "career": (
                "一次职业转折",
                "例如第一份工作、升职、失业、转行、创业或工作性质明显改变。",
            ),
            "relationship": ("一次明确的关系节点", "例如确定长期关系、结婚、分居或离婚。"),
            "relocation": ("一次重要迁移", "例如跨城市或跨国家搬迁，不包括日常短距离搬家。"),
            "child": ("一次子女相关节点", "例如怀孕、生育、收养或孩子发生的重要事件。"),
            "health": ("一次重大的健康事件", "例如手术、住院、严重意外或明确诊断。"),
            "family": ("一次家庭结构变化", "例如父母或家庭关系发生可以明确定位时间的重大变化。"),
            "finance": ("一次明显的财务转折", "例如大额收益、损失、负债或收入结构长期改变。"),
            "property": ("一次住房或房产节点", "例如买房、卖房、失去住房或重要房产安排。"),
            "legal": ("一次法律或纠纷节点", "例如诉讼、正式纠纷或法律结果。"),
            "loss": ("一次重大的离别", "只在你愿意分享时回答，并请选择时间较明确的重大离别。"),
            "spiritual": ("一次长期的观念转变", "例如修行、信仰或人生观发生持续性的改变。"),
        },
    },
    "ja": {
        "title": "いくつかの実際の日付から出生時刻の範囲を絞ります",
        "intro": "一度に一枚ずつ答えてください。年または月までの記憶で構いません。",
        "progress": "確認済み {answered}/{target}",
        "why": "この種類の出来事は、申告された時間帯で変化するチャート要素の比較に役立ちます。",
        "date": "いつ頃でしたか？",
        "details": "何が変わりましたか？",
        "placeholder": "短い事実の説明で十分です。",
        "category": {
            "education": ("学業上の節目", "入学、卒業、重要な試験、留学など。"),
            "career": ("仕事上の転機", "就職、昇進、失職、転職、起業など。"),
            "relationship": ("関係上の節目", "交際、結婚、別居、離婚など。"),
            "relocation": ("大きな転居", "別の都市や国への移動など。"),
            "child": ("子どもに関する節目", "妊娠、出産、養子、子どもの重要な出来事など。"),
            "health": ("大きな健康上の出来事", "手術、入院、重大な事故、明確な診断など。"),
            "family": ("家族構成の転機", "親や世帯構成に関わる重要な変化など。"),
            "finance": ("経済上の転機", "大きな利益、損失、負債、収入構造の変化など。"),
            "property": ("住居や不動産の節目", "購入、売却、住居を失う出来事など。"),
            "legal": ("法的な節目", "訴訟、正式な紛争、法的決着など。"),
            "loss": ("大きな死別", "共有してもよい、時期の明確な出来事だけを選んでください。"),
            "spiritual": ("価値観の転機", "実践、信仰、世界観の持続的な変化など。"),
        },
    },
}


def build_rectification_interview(
    state: dict[str, Any],
    *,
    session_id: str,
    locale: AppLocale,
    life_stage: str | None = None,
    skipped_categories: set[str] | None = None,
    available_categories: set[str] | None = None,
) -> dict[str, Any]:
    plan = (
        state.get("rectificationPlan") if isinstance(state.get("rectificationPlan"), dict) else {}
    )
    ledger = state.get("lifeEventLedger") if isinstance(state.get("lifeEventLedger"), dict) else {}
    existing = [
        item
        for item in ledger.get("events", [])
        if isinstance(item, dict) and item.get("role") in {"calibration", "holdout"}
    ]
    existing_categories = {str(item.get("category") or "") for item in existing}
    round_history = [
        item for item in state.get("rectificationRounds", []) if isinstance(item, dict)
    ]
    recorded_question_rounds = []
    for item in ledger.get("events", []):
        if not isinstance(item, dict):
            continue
        match = re.match(r"^rectify\.r(\d+)\.q\d+\.[a-z]+$", str(item.get("questionId") or ""))
        if match:
            recorded_question_rounds.append(int(match.group(1)))
    interaction_round = (
        max(
            len(existing),
            max((int(item.get("round") or 0) for item in round_history), default=0),
            max(recorded_question_rounds, default=0),
        )
        + 1
    )
    # Prefer a third distinct domain for the reserved event. If the user only has
    # two reliably dated domains, permit a repeat rather than invent an event.
    excluded_categories = existing_categories if len(existing) < 3 else set()
    remaining = max(0, MAX_RECTIFICATION_EVENTS - len(existing))
    categories = _rank_categories(
        plan.get("discriminatingFields"),
        excluded_categories,
        life_stage=life_stage,
        candidate_summaries=(
            plan.get("candidateSummaries")
            if isinstance(plan.get("candidateSummaries"), list)
            else []
        ),
        question_discrimination=(
            plan.get("questionDiscrimination")
            if isinstance(plan.get("questionDiscrimination"), dict)
            else {}
        ),
    )
    skipped = skipped_categories or set()
    categories = [category for category in categories if category not in skipped]
    if available_categories is not None:
        categories = [category for category in categories if category in available_categories]
    # Domain breadth is preferred, but it must not replace actual information
    # gain. If every new domain is non-discriminating, permit a genuinely new
    # dated episode in a previously used domain after the new domains have been
    # considered.
    repeat_categories = _rank_categories(
        plan.get("discriminatingFields"),
        set(),
        life_stage=life_stage,
        candidate_summaries=(
            plan.get("candidateSummaries")
            if isinstance(plan.get("candidateSummaries"), list)
            else []
        ),
        question_discrimination=(
            plan.get("questionDiscrimination")
            if isinstance(plan.get("questionDiscrimination"), dict)
            else {}
        ),
    )
    repeat_categories = [category for category in repeat_categories if category not in skipped]
    if available_categories is not None:
        repeat_categories = [
            category for category in repeat_categories if category in available_categories
        ]
    categories.extend(category for category in repeat_categories if category not in categories)
    # One question is a complete interaction round. The answer is recalculated
    # before the next question is selected from the updated candidate state. The
    # backend owns the bounded pool; the Agent may choose one item from that pool
    # after the answer state has been recalculated, but it cannot invent a new
    # category or question identity.
    copy = _COPY.get(locale, _COPY["en"])
    target = min(MAX_RECTIFICATION_EVENTS, max(MIN_RECTIFICATION_EVENTS, len(existing) + 1))
    candidate_set_fingerprint = _candidate_set_fingerprint(plan)
    candidate_count = len(_target_candidate_ids(plan))
    question_pool = []
    for category in categories:
        if len(question_pool) >= min(3, remaining):
            break
        title, prompt = copy["category"][category]
        selection_contract = _selection_contract_for_category(plan, category)
        if selection_contract is None:
            continue
        index = len(question_pool) + 1
        question_pool.append(
            {
                "questionId": f"rectify.r{interaction_round}.q{index}.{category}",
                "category": category,
                "title": title,
                "prompt": prompt,
                "whyWeAsk": copy["why"],
                "dateLabel": copy["date"],
                "detailsLabel": copy["details"],
                "detailsPlaceholder": copy["placeholder"],
                "answerType": "dated_event",
                "allowedSubtypes": list(RECTIFICATION_EVENT_SUBTYPES.get(category, ())),
                "allowSkip": True,
                "selectionContract": selection_contract,
            }
        )
    questions = question_pool[:1]

    status = "collecting" if questions else "exhausted"
    if questions:
        stop_reason = None
    elif remaining <= 0:
        stop_reason = (
            "The maximum evidence set has been reached. Preserve an underdetermined result."
        )
    else:
        stop_reason = (
            "No remaining event domain has backend-proven information gain for the current "
            "candidate set. Preserve an underdetermined result or request a narrower reported "
            "time window; do not ask a generic coverage question."
        )
    return {
        "schemaVersion": INTERVIEW_SCHEMA_VERSION,
        "sessionId": session_id,
        "generatedAt": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "round": interaction_round,
        "stateRevision": int(state.get("revision") or 0),
        "chartRevision": int(
            (
                state.get("activeChartRevision")
                if isinstance(state.get("activeChartRevision"), dict)
                else {}
            ).get("revision")
            or 0
        ),
        "candidateSetFingerprint": candidate_set_fingerprint,
        "candidateCount": candidate_count,
        "status": status,
        "title": copy["title"],
        "intro": copy["intro"],
        "progress": {
            "answered": len(existing),
            "maximumAccepted": MAX_RECTIFICATION_EVENTS,
            "minimumRequired": MIN_RECTIFICATION_EVENTS,
            "target": target,
            "label": copy["progress"].format(answered=len(existing), target=target),
        },
        "questions": questions,
        "questionPool": question_pool,
        "source": "deterministic_brief",
        "availableCategories": sorted(available_categories or []),
        "stopReason": stop_reason,
    }


def validate_agent_question_wording(
    brief: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    proposed = payload.get("questions")
    if not isinstance(proposed, list):
        raise ValueError("rectification interview response must contain questions")
    raw_pool_items = brief.get("questionPool")
    pool_items = raw_pool_items if isinstance(raw_pool_items, list) else []
    raw_expected_items = brief.get("questions")
    expected_items = pool_items or (
        raw_expected_items if isinstance(raw_expected_items, list) else []
    )
    expected = {
        str(item["questionId"]): item
        for item in expected_items
        if isinstance(item, dict) and item.get("questionId")
    }
    proposed_ids = {
        str(item.get("questionId"))
        for item in proposed
        if isinstance(item, dict) and item.get("questionId")
    }
    if len(proposed) != 1 or len(proposed_ids) != 1:
        raise ValueError("rectification interview must return exactly one approved question")
    if not proposed_ids.issubset(set(expected)):
        raise ValueError("rectification interview selected an unapproved question pool item")
    result = {
        **brief,
        "source": "agent_wording",
    }
    result.pop("questionPool", None)
    result.pop("lifeEventFocus", None)
    questions = []
    forbidden = ("candidate", "候选盘", "得分", "d1", "d9", "d10", "d60", "星盘显示")
    for item in proposed:
        if not isinstance(item, dict):
            raise ValueError("rectification interview question must be an object")
        question_id = str(item.get("questionId") or "")
        if question_id not in expected:
            raise ValueError("rectification interview selected an unapproved question pool item")
        original = expected[question_id]
        if not _valid_selection_contract(
            original.get("selectionContract"),
            candidate_set_fingerprint=str(brief.get("candidateSetFingerprint") or ""),
            expected_candidate_count=int(brief.get("candidateCount") or 0),
        ):
            raise ValueError("rectification interview selected a non-discriminating question")
        if item.get("category") != original["category"]:
            raise ValueError("rectification interview changed a question category")
        merged = dict(original)
        for field in ("title", "prompt", "whyWeAsk", "detailsPlaceholder"):
            value = str(item.get(field) or "").strip()
            if not value or len(value) > 240:
                raise ValueError(f"rectification interview has invalid {field}")
            if any(token in value.casefold() for token in forbidden):
                raise ValueError("rectification wording leaks candidate or chart-leading language")
            merged[field] = value
        questions.append(merged)
    result["questions"] = questions
    return result


def validate_rectification_event_dates(
    events: list[dict[str, Any]],
    *,
    birth_date: str,
    today: date | None = None,
) -> None:
    """Validate partial event dates without inventing missing month/day values."""

    try:
        born = date.fromisoformat(birth_date)
    except ValueError as exc:
        raise ValueError("the session has an invalid birth date") from exc
    current = today or date.today()
    for event in events:
        value = str(event.get("date") or "")
        try:
            start, end = _rectification_event_date_bounds(value)
        except (TypeError, ValueError, IndexError) as exc:
            raise ValueError(f"life event has an invalid calendar date: {value}") from exc
        if end < born:
            raise ValueError(f"life event cannot be before the birth date: {value}")
        if start > current:
            raise ValueError(f"life event cannot be in the future: {value}")
        if end > current:
            raise ValueError(
                "A partial life-event date cannot include future days. Add the remembered "
                "month or exact date."
            )


def validate_rectification_episode_independence(
    events: list[dict[str, Any]],
    *,
    existing_events: list[dict[str, Any]],
) -> None:
    """Require each adaptive answer to add a genuinely new dated episode.

    A partial year or month represents its complete civil interval. If that
    interval overlaps an existing scored episode, accepting it would advance an
    interaction round without adding independent evidence. Ask for a narrower
    date or a different period instead of creating a no-progress loop.
    """

    existing_intervals: list[tuple[date, date, str]] = []
    for existing in existing_events:
        if not isinstance(existing, dict):
            continue
        if str(existing.get("category") or "") == "unknown":
            continue
        if str(existing.get("role") or "") == "context_only":
            continue
        value = str(existing.get("date") or "")
        try:
            start, end = _rectification_event_date_bounds(value)
        except ValueError as exc:
            raise ValueError("stored rectification evidence has an invalid date") from exc
        existing_intervals.append((start, end, value))

    for event in events:
        value = str(event.get("date") or "")
        start, end = _rectification_event_date_bounds(value)
        overlap = next(
            (
                existing_value
                for existing_start, existing_end, existing_value in existing_intervals
                if start <= existing_end and end >= existing_start
            ),
            None,
        )
        if overlap is not None:
            raise ValueError(
                "This event overlaps a previously submitted life period "
                f"({overlap}). Add a more precise month or day, or choose an event "
                "from a different period."
            )


def _rectification_event_date_bounds(value: str) -> tuple[date, date]:
    if re.fullmatch(r"(?:19|20)\d{2}", value):
        year = int(value)
        return date(year, 1, 1), date(year, 12, 31)
    if re.fullmatch(r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])", value):
        year, month = (int(part) for part in value.split("-"))
        return date(year, month, 1), date(year, month, monthrange(year, month)[1])
    if re.fullmatch(
        r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])",
        value,
    ):
        exact = date.fromisoformat(value)
        return exact, exact
    raise ValueError("unsupported partial event date")


def validate_rectification_event_bindings(
    events: list[dict[str, Any]],
    *,
    state: dict[str, Any],
    interview: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return newly answered events after enforcing backend-issued question identity."""

    expected_fingerprint = _candidate_set_fingerprint(
        state.get("rectificationPlan") if isinstance(state.get("rectificationPlan"), dict) else {}
    )
    interview_fingerprint = str(interview.get("candidateSetFingerprint") or "")
    if not expected_fingerprint or interview_fingerprint != expected_fingerprint:
        raise ValueError("the verification question belongs to an outdated candidate set")
    if int(interview.get("stateRevision") or 0) != int(state.get("revision") or 0):
        raise ValueError("the verification question belongs to an outdated rectification state")
    active_revision = state.get("activeChartRevision")
    active_revision = active_revision if isinstance(active_revision, dict) else {}
    if int(interview.get("chartRevision") or 0) != int(active_revision.get("revision") or 0):
        raise ValueError("the verification question belongs to an outdated chart revision")

    questions = {
        str(item.get("questionId")): {
            "category": str(item.get("category")),
            "allowedSubtypes": {str(value) for value in item.get("allowedSubtypes") or [] if value},
            "selectionContract": item.get("selectionContract"),
        }
        for item in interview.get("questions", [])
        if isinstance(item, dict) and item.get("questionId") and item.get("category")
    }
    if len(events) != 1:
        raise ValueError("answer exactly one current verification question at a time")
    event = events[0]
    question_id = str(event.get("questionId") or "")
    category = str(event.get("category") or "")
    if not question_id:
        raise ValueError("new life events must answer a current verification question")
    expected_question = questions.get(question_id)
    if expected_question is None:
        raise ValueError("life event references an expired verification question")
    expected_category = str(expected_question["category"])
    if category != expected_category:
        raise ValueError("life event category does not match its verification question")
    event_subtype = str(event.get("eventSubtype") or "")
    allowed_subtypes = expected_question["allowedSubtypes"]
    if not event_subtype or event_subtype not in allowed_subtypes:
        raise ValueError("life event subtype does not match its verification question")
    plan = (
        state.get("rectificationPlan") if isinstance(state.get("rectificationPlan"), dict) else {}
    )
    current_contract = _selection_contract_for_category(plan, expected_category)
    if current_contract is None or expected_question.get("selectionContract") != current_contract:
        raise ValueError("life event does not answer a discriminating verification question")
    return [event]


def validate_agent_event_evidence(
    expected_events: list[dict[str, Any]],
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Apply bounded Agent semantics and surface ambiguity before event acceptance."""

    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("life event evidence audit must contain results")
    expected_by_question = {str(item.get("questionId")): item for item in expected_events}
    expected = {
        question_id: {
            "category": str(item.get("category")),
            "eventSubtype": str(item.get("eventSubtype") or ""),
        }
        for question_id, item in expected_by_question.items()
    }
    observed: dict[str, dict[str, Any]] = {}
    for item in raw_results:
        if not isinstance(item, dict):
            raise ValueError("life event evidence audit result must be an object")
        question_id = str(item.get("questionId") or "")
        if question_id in observed or question_id not in expected:
            raise ValueError("life event evidence audit changed the submitted question set")
        if str(item.get("category") or "") != expected[question_id]["category"]:
            raise ValueError("life event evidence audit changed an event category")
        if str(item.get("eventSubtype") or "") != expected[question_id]["eventSubtype"]:
            raise ValueError("life event evidence audit changed an event subtype")
        observed[question_id] = item
    if set(observed) != set(expected):
        raise ValueError("life event evidence audit omitted a submitted event")
    normalized: list[dict[str, Any]] = []
    for question_id, item in observed.items():
        expected_event = expected_by_question[question_id]
        assessment = str(item.get("assessment") or "").strip().casefold()
        if not assessment:
            assessment = "needs_clarification" if item.get("accepted") is False else "clear"
        if assessment not in {"clear", "needs_clarification"}:
            raise ValueError("life event evidence audit has an invalid assessment")
        clarification_required = assessment == "needs_clarification"
        reason_code = str(item.get("clarificationReasonCode") or "").strip()
        clarification_question = str(item.get("clarificationQuestion") or "").strip()
        if clarification_required:
            if reason_code not in _CLARIFICATION_REASON_CODES:
                raise ValueError("life event evidence audit has an invalid clarification reason")
            if not clarification_question or len(clarification_question) > 240:
                raise ValueError("life event evidence audit has an invalid clarification question")
        facts = _normalize_event_facts(item.get("eventFacts"))
        if facts["occurrence"] == "uncertain" and not clarification_required:
            raise ValueError("uncertain event occurrence requires clarification")
        normalized.append(
            {
                "questionId": question_id,
                "category": expected[question_id]["category"],
                "eventSubtype": expected[question_id]["eventSubtype"],
                "date": str(expected_event.get("date") or ""),
                "description": str(expected_event.get("description") or ""),
                "accepted": not clarification_required,
                "reason": (
                    "Agent found a bounded ambiguity that requires user clarification."
                    if clarification_required
                    else "Backend binding and Agent semantic review passed."
                ),
                "eventFacts": facts,
                "semanticAssessment": assessment,
                "clarificationRequired": clarification_required,
                "clarificationReasonCode": reason_code if clarification_required else None,
                "clarificationQuestion": clarification_question if clarification_required else None,
                "agentReason": str(item.get("reason") or "")[:500],
            }
        )
    return normalized


def _normalize_event_facts(value: Any) -> dict[str, str]:
    """Keep Agent semantics bounded before they enter deterministic evidence context."""

    raw = value if isinstance(value, dict) else {}
    allowed = {
        "occurrence": {"occurred", "ongoing", "uncertain"},
        "agency": {"active", "passive", "mixed", "unknown"},
        "impact": {"major", "moderate", "minor", "unknown"},
        "dateConfidence": {"year", "month", "day", "unknown"},
    }
    defaults = {
        "occurrence": "occurred",
        "agency": "unknown",
        "impact": "unknown",
        "dateConfidence": "unknown",
    }
    return {
        field: (
            str(raw.get(field) or defaults[field])
            if str(raw.get(field) or defaults[field]) in values
            else defaults[field]
        )
        for field, values in allowed.items()
    }


def _rank_categories(
    raw_fields: Any,
    excluded: set[str],
    *,
    life_stage: str | None,
    candidate_summaries: list[dict[str, Any]],
    question_discrimination: dict[str, Any],
) -> list[str]:
    fields = [str(value).casefold() for value in raw_fields or []]
    ranked: list[str] = []
    for needle, categories in _FIELD_CATEGORY_PRIORITY:
        if any(needle in field for field in fields):
            ranked.extend(categories)
    ranked.extend(_DEFAULT_PRIORITY)
    if life_stage in {"child", "teen"}:
        age_priority = ["education", "relocation", "family", "health"]
        ranked = [*age_priority, *ranked]
        excluded = excluded | {
            "career",
            "relationship",
            "child",
            "finance",
            "property",
            "legal",
            "spiritual",
        }
    result: list[str] = []
    for category in ranked:
        if category in excluded or category in result or category not in RECTIFICATION_EVENT_RULES:
            continue
        result.append(category)
    priority = {category: index for index, category in enumerate(result)}
    return sorted(
        result,
        key=lambda category: (
            -_category_information_score(
                category,
                fields,
                candidate_summaries,
                question_discrimination,
            ),
            priority[category],
        ),
    )


def _category_information_score(
    category: str,
    discriminating_fields: list[str],
    candidate_summaries: list[dict[str, Any]],
    question_discrimination: dict[str, Any],
) -> int:
    normalized_discrimination = {
        str(field).casefold(): value for field, value in question_discrimination.items()
    }
    rules = RECTIFICATION_EVENT_RULES.get(category, RECTIFICATION_EVENT_RULES["unknown"])
    preferred = {str(value).casefold() for value in rules.get("fields") or []}
    matched = [field for field in discriminating_fields if field.casefold() in preferred]
    score = len(matched) * 100
    for field in matched:
        partition = normalized_discrimination.get(field.casefold())
        if not isinstance(partition, dict):
            continue
        candidate_count = int(partition.get("candidateCount") or 0)
        partition_count = int(partition.get("partitionCount") or 0)
        largest = int(partition.get("largestPartitionSize") or candidate_count)
        if candidate_count > 1 and partition_count > 1:
            balance = candidate_count - largest
            score += (partition_count - 1) * 40 + balance * 10
    if not candidate_summaries:
        return score
    for field in matched:
        changed_count = sum(
            field in {str(value).casefold() for value in candidate.get("changedFromBase") or []}
            for candidate in candidate_summaries
            if isinstance(candidate, dict)
        )
        if 0 < changed_count < len(candidate_summaries):
            score += 20 + min(changed_count, len(candidate_summaries) - changed_count)
    return score


def _question_selection_contract(
    category: str,
    question_discrimination: dict[str, Any],
    *,
    matched_fields: list[str],
    candidate_set_fingerprint: str,
    expected_candidate_count: int,
) -> dict[str, Any] | None:
    rules = RECTIFICATION_EVENT_RULES.get(category, RECTIFICATION_EVENT_RULES["unknown"])
    normalized_discrimination = {
        str(field).casefold(): value for field, value in question_discrimination.items()
    }
    preferred = {str(field).casefold() for field in rules.get("fields") or []}
    eligible: list[tuple[str, dict[str, Any]]] = []
    for field in matched_fields:
        if field.casefold() not in preferred:
            continue
        summary = normalized_discrimination.get(field.casefold())
        if not isinstance(summary, dict):
            continue
        candidate_count = int(summary.get("candidateCount") or 0)
        partition_count = int(summary.get("partitionCount") or 0)
        largest_partition = int(summary.get("largestPartitionSize") or candidate_count)
        if (
            candidate_count >= 2
            and candidate_count == expected_candidate_count
            and partition_count >= 2
            and 0 < largest_partition < candidate_count
        ):
            eligible.append((field, summary))
    if not eligible or not candidate_set_fingerprint:
        return None
    eligible.sort(
        key=lambda item: (
            int(item[1].get("candidateCount") or 0) - int(item[1].get("largestPartitionSize") or 0),
            int(item[1].get("partitionCount") or 0),
        ),
        reverse=True,
    )
    best_field, best = eligible[0]
    candidate_count = int(best.get("candidateCount") or 0)
    largest_partition = int(best.get("largestPartitionSize") or 0)
    return {
        "tier": "discriminating",
        "eligible": True,
        "matchedFieldCount": len(eligible),
        "matchedFields": [field for field, _summary in eligible],
        "primaryField": best_field,
        "partitionCount": int(best.get("partitionCount") or 0),
        "candidateCount": candidate_count,
        "largestPartitionSize": largest_partition,
        "maximumElimination": candidate_count - largest_partition,
        "candidateSetFingerprint": candidate_set_fingerprint,
    }


def _selection_contract_for_category(
    plan: dict[str, Any],
    category: str,
) -> dict[str, Any] | None:
    discriminating_fields = [str(value) for value in plan.get("discriminatingFields") or []]
    return _question_selection_contract(
        category,
        plan.get("questionDiscrimination")
        if isinstance(plan.get("questionDiscrimination"), dict)
        else {},
        matched_fields=_category_discriminating_fields(category, discriminating_fields),
        candidate_set_fingerprint=_candidate_set_fingerprint(plan),
        expected_candidate_count=len(_target_candidate_ids(plan)),
    )


def _target_candidate_ids(plan: dict[str, Any]) -> list[str]:
    return sorted({str(value) for value in plan.get("targetCandidateIds") or [] if value})


def _candidate_set_fingerprint(plan: dict[str, Any]) -> str:
    target_ids = _target_candidate_ids(plan)
    discrimination = (
        plan.get("questionDiscrimination")
        if isinstance(plan.get("questionDiscrimination"), dict)
        else {}
    )
    if len(target_ids) < 2 or not discrimination:
        return ""
    payload = {
        "schemaVersion": plan.get("schemaVersion"),
        "selectionPolicyId": plan.get("selectionPolicyId"),
        "eventMappingId": plan.get("eventMappingId"),
        "holdoutPolicyId": plan.get("holdoutPolicyId"),
        "status": plan.get("status"),
        "action": plan.get("action"),
        "targetCandidateIds": target_ids,
        "questionDiscrimination": discrimination,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _valid_selection_contract(
    value: Any,
    *,
    candidate_set_fingerprint: str,
    expected_candidate_count: int,
) -> bool:
    if not isinstance(value, dict):
        return False
    candidate_count = int(value.get("candidateCount") or 0)
    partition_count = int(value.get("partitionCount") or 0)
    largest_partition = int(value.get("largestPartitionSize") or candidate_count)
    matched_fields = [str(field) for field in value.get("matchedFields") or [] if field]
    primary_field = str(value.get("primaryField") or "")
    return (
        bool(candidate_set_fingerprint)
        and value.get("tier") == "discriminating"
        and value.get("eligible") is True
        and int(value.get("matchedFieldCount") or 0) == len(matched_fields)
        and len(matched_fields) > 0
        and primary_field in matched_fields
        and candidate_count >= 2
        and candidate_count == expected_candidate_count
        and 2 <= partition_count <= candidate_count
        and 0 < largest_partition < candidate_count
        and int(value.get("maximumElimination") or 0) == candidate_count - largest_partition
        and str(value.get("candidateSetFingerprint") or "") == candidate_set_fingerprint
    )


def _category_discriminating_fields(
    category: str,
    discriminating_fields: list[str],
) -> list[str]:
    rules = RECTIFICATION_EVENT_RULES.get(category, RECTIFICATION_EVENT_RULES["unknown"])
    preferred = {str(value).casefold() for value in rules.get("fields") or []}
    return [field for field in discriminating_fields if field.casefold() in preferred]
