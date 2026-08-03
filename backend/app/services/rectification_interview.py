from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from typing import Any

from app.schemas import AppLocale
from app.vedicdust.rectification_policy import RECTIFICATION_EVENT_RULES


INTERVIEW_SCHEMA_VERSION = "vedicdust-rectification-interview/1.0.0"
MAX_RECTIFICATION_EVENTS = 5


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
    ("currentdasha", ("career", "education", "relocation")),
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
) -> dict[str, Any]:
    plan = (
        state.get("rectificationPlan") if isinstance(state.get("rectificationPlan"), dict) else {}
    )
    ledger = state.get("lifeEventLedger") if isinstance(state.get("lifeEventLedger"), dict) else {}
    existing = [item for item in ledger.get("events", []) if isinstance(item, dict)]
    existing_categories = {str(item.get("category") or "") for item in existing}
    remaining = max(0, MAX_RECTIFICATION_EVENTS - len(existing))
    categories = _rank_categories(
        plan.get("discriminatingFields"),
        existing_categories,
        life_stage=life_stage,
    )
    # Offer every remaining independent category. The evidence target remains
    # bounded separately, so a skipped or inapplicable question does not trap
    # the user before the minimum evidence set is reached.
    question_count = remaining
    selected_categories = categories[:question_count]
    copy = _COPY.get(locale, _COPY["en"])
    target = min(MAX_RECTIFICATION_EVENTS, max(3, len(existing) + 1))
    questions = []
    for index, category in enumerate(selected_categories, start=1):
        title, prompt = copy["category"][category]
        questions.append(
            {
                "questionId": f"rectify.r{len(existing) + 1}.q{index}.{category}",
                "category": category,
                "title": title,
                "prompt": prompt,
                "whyWeAsk": copy["why"],
                "dateLabel": copy["date"],
                "detailsLabel": copy["details"],
                "detailsPlaceholder": copy["placeholder"],
                "answerType": "dated_event",
                "allowSkip": True,
            }
        )

    status = "collecting" if questions else "exhausted"
    return {
        "schemaVersion": INTERVIEW_SCHEMA_VERSION,
        "sessionId": session_id,
        "generatedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "round": max(1, len(existing) + 1),
        "status": status,
        "title": copy["title"],
        "intro": copy["intro"],
        "progress": {
            "answered": len(existing),
            "minimumRequired": 3,
            "maximumAccepted": MAX_RECTIFICATION_EVENTS,
            "target": target,
            "label": copy["progress"].format(answered=len(existing), target=target),
        },
        "questions": questions,
        "source": "deterministic_brief",
        "stopReason": (
            "The maximum evidence set has been reached. Preserve an underdetermined result."
            if not questions
            else None
        ),
    }


def validate_agent_question_wording(
    brief: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    proposed = payload.get("questions")
    if not isinstance(proposed, list):
        raise ValueError("rectification interview response must contain questions")
    expected = {item["questionId"]: item for item in brief["questions"]}
    if {item.get("questionId") for item in proposed if isinstance(item, dict)} != set(expected):
        raise ValueError("rectification interview changed the backend question set")
    result = {**brief, "source": "agent_wording"}
    questions = []
    forbidden = ("candidate", "候选盘", "得分", "d1", "d9", "d10", "d60", "星盘显示")
    for item in proposed:
        if not isinstance(item, dict):
            raise ValueError("rectification interview question must be an object")
        original = expected[str(item["questionId"])]
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
        parts = value.split("-")
        try:
            year = int(parts[0])
            month = int(parts[1]) if len(parts) >= 2 else None
            day = int(parts[2]) if len(parts) == 3 else None
            if month is None:
                start, end = date(year, 1, 1), date(year, 12, 31)
            elif day is None:
                start = date(year, month, 1)
                end = date(year, month, monthrange(year, month)[1])
            else:
                start = end = date(year, month, day)
        except (TypeError, ValueError, IndexError) as exc:
            raise ValueError(f"life event has an invalid calendar date: {value}") from exc
        if end < born:
            raise ValueError(f"life event cannot be before the birth date: {value}")
        if start > current:
            raise ValueError(f"life event cannot be in the future: {value}")


def validate_rectification_event_bindings(
    events: list[dict[str, Any]],
    *,
    state: dict[str, Any],
    interview: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return newly answered events after enforcing backend-issued question identity."""

    ledger = state.get("lifeEventLedger") if isinstance(state.get("lifeEventLedger"), dict) else {}
    existing = {
        (str(item.get("date") or ""), str(item.get("category") or ""))
        for item in ledger.get("events", [])
        if isinstance(item, dict)
    }
    questions = {
        str(item.get("questionId")): str(item.get("category"))
        for item in interview.get("questions", [])
        if isinstance(item, dict) and item.get("questionId") and item.get("category")
    }
    used_question_ids: set[str] = set()
    new_events: list[dict[str, Any]] = []
    for event in events:
        question_id = str(event.get("questionId") or "")
        category = str(event.get("category") or "")
        date_value = str(event.get("date") or "")
        if not question_id:
            if (date_value, category) not in existing:
                raise ValueError("new life events must answer a current verification question")
            continue
        if question_id in used_question_ids:
            raise ValueError("a verification question can only provide one life event")
        expected_category = questions.get(question_id)
        if expected_category is None:
            raise ValueError("life event references an expired verification question")
        if category != expected_category:
            raise ValueError("life event category does not match its verification question")
        used_question_ids.add(question_id)
        new_events.append(event)
    if not new_events:
        raise ValueError("at least one current verification question must be answered")
    return new_events


def validate_agent_event_evidence(
    expected_events: list[dict[str, Any]],
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Accept an Agent audit only when it accounts for every submitted event exactly once."""

    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("life event evidence audit must contain results")
    expected = {str(item.get("questionId")): str(item.get("category")) for item in expected_events}
    observed: dict[str, dict[str, Any]] = {}
    for item in raw_results:
        if not isinstance(item, dict):
            raise ValueError("life event evidence audit result must be an object")
        question_id = str(item.get("questionId") or "")
        if question_id in observed or question_id not in expected:
            raise ValueError("life event evidence audit changed the submitted question set")
        if str(item.get("category") or "") != expected[question_id]:
            raise ValueError("life event evidence audit changed an event category")
        observed[question_id] = item
    if set(observed) != set(expected):
        raise ValueError("life event evidence audit omitted a submitted event")
    rejected = [
        str(item.get("reason") or "event description does not match the requested event type")
        for item in observed.values()
        if item.get("accepted") is not True
    ]
    if rejected:
        raise ValueError("Please revise the life event: " + "; ".join(rejected[:2]))
    return list(observed.values())


def _rank_categories(
    raw_fields: Any,
    excluded: set[str],
    *,
    life_stage: str | None,
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
    return result
