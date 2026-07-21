from __future__ import annotations

import re
from collections import Counter
from typing import Any


EVENT_RULES: dict[str, dict[str, Any]] = {
    "marriage": {
        "label": "marriage / committed relationship",
        "houses": [7, 2, 11],
        "vargas": ["D9"],
        "karakas": ["Venus", "Jupiter"],
        "fields": ["d9Lagna", "currentDasha"],
    },
    "relationship": {
        "label": "relationship change",
        "houses": [5, 7, 12],
        "vargas": ["D9"],
        "karakas": ["Venus", "Mars"],
        "fields": ["d9Lagna", "currentDasha"],
    },
    "career": {
        "label": "career change",
        "houses": [10, 6, 11],
        "vargas": ["D10"],
        "karakas": ["Sun", "Saturn", "Mercury"],
        "fields": ["d10Lagna", "currentDasha"],
    },
    "education": {
        "label": "education / examination",
        "houses": [4, 5, 9],
        "vargas": ["D5", "D24"],
        "karakas": ["Mercury", "Jupiter"],
        "fields": ["d24Lagna", "d5Lagna", "currentDasha"],
    },
    "relocation": {
        "label": "relocation / migration",
        "houses": [4, 9, 12],
        "vargas": ["D4"],
        "karakas": ["Moon", "Rahu"],
        "fields": ["d4Lagna", "currentDasha"],
    },
    "property": {
        "label": "home / property",
        "houses": [4, 11, 12],
        "vargas": ["D4"],
        "karakas": ["Mars", "Moon"],
        "fields": ["d4Lagna", "currentDasha"],
    },
    "child": {
        "label": "childbirth / child event",
        "houses": [5, 2, 9],
        "vargas": ["D7"],
        "karakas": ["Jupiter"],
        "fields": ["d7Lagna", "currentDasha", "d9Lagna"],
    },
    "health": {
        "label": "health / surgery",
        "houses": [1, 6, 8, 12],
        "vargas": ["D30"],
        "karakas": ["Mars", "Saturn"],
        "fields": ["d30Lagna", "lagnaSign", "currentDasha"],
    },
    "family": {
        "label": "family event",
        "houses": [2, 4, 8],
        "vargas": ["D12"],
        "karakas": ["Moon", "Sun"],
        "fields": ["d12Lagna", "lagnaSign", "currentDasha"],
    },
    "finance": {
        "label": "finance / income shock",
        "houses": [2, 6, 8, 11],
        "vargas": ["D2"],
        "karakas": ["Jupiter", "Venus", "Saturn"],
        "fields": ["d2Lagna", "currentDasha", "lagnaSign"],
    },
    "legal": {
        "label": "legal / dispute",
        "houses": [6, 8, 12],
        "vargas": ["D30"],
        "karakas": ["Mars", "Saturn", "Rahu"],
        "fields": ["d30Lagna", "lagnaSign", "currentDasha"],
    },
    "loss": {
        "label": "bereavement / major loss",
        "houses": [8, 12, 4],
        "vargas": ["D12", "D30"],
        "karakas": ["Saturn", "Ketu"],
        "fields": ["d12Lagna", "d30Lagna", "lagnaSign", "currentDasha"],
    },
    "spiritual": {
        "label": "spiritual turn",
        "houses": [5, 9, 12],
        "vargas": ["D9", "D20"],
        "karakas": ["Jupiter", "Ketu"],
        "fields": ["d20Lagna", "d9Lagna", "currentDasha"],
    },
    "unknown": {
        "label": "dated life event",
        "houses": [],
        "vargas": [],
        "karakas": [],
        "fields": ["currentDasha"],
    },
}


KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("marriage", ("结婚", "婚礼", "领证", "订婚", "married", "marriage", "wedding")),
    ("relationship", ("恋爱", "分手", "离婚", "伴侣", "relationship", "breakup", "divorce")),
    (
        "career",
        ("工作", "跳槽", "创业", "升职", "失业", "职业", "career", "job", "promotion", "startup"),
    ),
    (
        "education",
        (
            "高考",
            "考研",
            "毕业",
            "入学",
            "留学",
            "考试",
            "education",
            "exam",
            "college",
            "graduate",
        ),
    ),
    (
        "relocation",
        ("搬家", "搬到", "迁居", "移民", "出国", "换城市", "relocation", "moved", "migration"),
    ),
    ("property", ("买房", "卖房", "房产", "装修", "home", "property", "house")),
    ("child", ("生子", "孩子", "怀孕", "剖腹产", "早产", "child", "birth", "pregnant")),
    ("health", ("手术", "住院", "病", "车祸", "受伤", "health", "surgery", "hospital")),
    ("family", ("父亲", "母亲", "家人", "家庭", "family", "father", "mother")),
    ("finance", ("破财", "亏损", "收入", "投资", "债务", "finance", "money", "income", "debt")),
    ("legal", ("官司", "诉讼", "纠纷", "legal", "lawsuit", "court")),
    ("loss", ("去世", "离世", "丧", "死亡", "loss", "death", "bereavement")),
    ("spiritual", ("修行", "宗教", "信仰", "spiritual", "religion", "meditation")),
]


DATE_PATTERN = re.compile(
    r"(?P<year>19\d{2}|20\d{2})(?:\s*(?:年|-|/|\.)\s*(?P<month>1[0-2]|0?[1-9])\s*月?)?"
)


def parse_life_event_ledger(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    events: list[dict[str, Any]] = []
    for index, line in enumerate(_candidate_lines(text), start=1):
        event = _parse_event_line(line, index)
        if event is not None:
            events.append(event)

    category_counts = Counter(str(event.get("category") or "unknown") for event in events)
    return {
        "schemaVersion": "life-event-ledger/v1",
        "raw": text,
        "events": events,
        "categoryCounts": dict(sorted(category_counts.items())),
        "eventCollectionRequired": len(events) < 2,
        "recommendedMinimumEvents": 3,
        "recommendedRectificationUse": (
            "Use dated life events as the primary rectification evidence before generic traits."
            if events
            else "Ask the user for 2-5 dated life events before deep rectification."
        ),
    }


def build_life_event_focus(
    ledger: dict[str, Any],
    discriminating_fields: list[str],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    events = ledger.get("events") if isinstance(ledger, dict) else None
    if not isinstance(events, list):
        return []
    field_set = {str(field) for field in discriminating_fields if field}
    focus: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        rules = event.get("rectificationRules")
        if not isinstance(rules, dict):
            rules = EVENT_RULES["unknown"]
        fields = [str(field) for field in rules.get("fields") or []]
        overlap = [field for field in fields if field in field_set]
        focus.append(
            {
                "eventId": event.get("eventId"),
                "category": event.get("category"),
                "date": event.get("date"),
                "datePrecision": event.get("datePrecision"),
                "description": event.get("description"),
                "relevantHouses": rules.get("houses") or [],
                "vargas": rules.get("vargas") or [],
                "karakas": rules.get("karakas") or [],
                "preferredFields": fields,
                "fieldOverlap": overlap,
                "use": (
                    "primary"
                    if overlap or not field_set or event.get("datePrecision") in {"month", "year"}
                    else "secondary"
                ),
            }
        )
        if len(focus) >= limit:
            break
    return focus


def _candidate_lines(text: str) -> list[str]:
    if not text:
        return []
    lines = []
    for raw_line in re.split(r"[\n;；。]+", text):
        line = re.sub(r"^\s*(?:[-*•]\s+|\d+[.、)）]\s*)", "", raw_line).strip()
        if line:
            lines.append(line)
    return lines


def _parse_event_line(line: str, index: int) -> dict[str, Any] | None:
    date_match = DATE_PATTERN.search(line)
    if not date_match:
        return None
    year = int(date_match.group("year"))
    month_raw = date_match.group("month")
    month = int(month_raw) if month_raw else None
    category = _classify_category(line)
    rules = EVENT_RULES[category]
    date_value = f"{year:04d}-{month:02d}" if month is not None else f"{year:04d}"
    date_precision = "month" if month is not None else "year"
    return {
        "eventId": f"evt_{index}_{date_value.replace('-', '')}_{category}",
        "date": date_value,
        "datePrecision": date_precision,
        "category": category,
        "categoryLabel": rules["label"],
        "description": line,
        "confidence": "medium",
        "rectificationRules": {
            "houses": rules["houses"],
            "vargas": rules["vargas"],
            "karakas": rules["karakas"],
            "fields": rules["fields"],
        },
    }


def _classify_category(line: str) -> str:
    lowered = line.lower()
    for category, keywords in KEYWORDS:
        if any(keyword.lower() in lowered for keyword in keywords):
            return category
    return "unknown"
