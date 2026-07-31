from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import pytz


SIGNS = [
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
]
SIGN_LORDS = [
    "Mars",
    "Venus",
    "Mercury",
    "Moon",
    "Sun",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Saturn",
    "Jupiter",
]


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

    events.sort(key=lambda event: str(event.get("date") or ""))
    for event in events:
        event["role"] = "calibration"
    if len(events) >= 3:
        events[-1]["role"] = "holdout"
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


def score_candidate_events(
    *,
    candidate_id: str,
    signature: dict[str, Any],
    representative_moment: datetime,
    latitude: float,
    longitude: float,
    timezone_id: str,
    ledger: dict[str, Any],
) -> dict[str, Any]:
    """Score dated events with explicit, inspectable Jyotish evidence gates.

    The weights are product hypotheses. They rank candidates; they do not prove an
    event or license a deterministic life claim.
    """

    events = [event for event in ledger.get("events") or [] if isinstance(event, dict)]
    if not events:
        return {"evidenceScores": [], "aggregateScore": None, "holdoutScore": None}

    event_moments = [_event_midpoint(event) for event in events]
    local_timezone = pytz.timezone(timezone_id)
    localized_birth = local_timezone.localize(representative_moment, is_dst=None)
    from app.calculator.dasha_pyjhora import calculate_dasha_lords_at
    from app.calculator.engine import calc_transits

    dasha_lords = calculate_dasha_lords_at(
        representative_moment.year,
        representative_moment.month,
        representative_moment.day,
        representative_moment.hour,
        representative_moment.minute,
        latitude,
        longitude,
        localized_birth.utcoffset().total_seconds() / 3600.0,
        event_moments,
    )
    lagna_sign = str(signature.get("lagnaSign") or "")
    lagna_index = SIGNS.index(lagna_sign) if lagna_sign in SIGNS else 0
    planet_signs = signature.get("planetSignIndices") or {}
    evidence_scores: list[dict[str, Any]] = []
    for event, event_moment, periods in zip(events, event_moments, dasha_lords, strict=True):
        rules = event.get("rectificationRules") or EVENT_RULES["unknown"]
        relevant_houses = {int(value) for value in rules.get("houses") or []}
        karakas = {str(value) for value in rules.get("karakas") or []}
        relevant_vargas = [str(value) for value in rules.get("vargas") or []]
        support_ids: list[str] = []
        contributions = 0.0
        period_lords = [
            str(periods.get(level))
            for level in ("mahadasha", "antardasha", "pratyantardasha")
            if periods.get(level)
        ]
        for level, lord in zip(("md", "ad", "pd"), period_lords, strict=False):
            weight = {"md": 0.12, "ad": 0.16, "pd": 0.1}[level]
            if lord in karakas:
                contributions += weight
                support_ids.append(
                    f"rectification.{candidate_id}.{event['eventId']}.{level}.karaka"
                )
            sign_index = planet_signs.get(lord)
            if sign_index is not None:
                occupied_house = (int(sign_index) - lagna_index) % 12 + 1
                if occupied_house in relevant_houses:
                    contributions += weight
                    support_ids.append(
                        f"rectification.{candidate_id}.{event['eventId']}.{level}.occupant"
                    )
            ruled_houses = {
                house
                for house in relevant_houses
                if SIGN_LORDS[(lagna_index + house - 1) % 12] == lord
            }
            if ruled_houses:
                contributions += weight
                support_ids.append(f"rectification.{candidate_id}.{event['eventId']}.{level}.lord")

        for varga in relevant_vargas:
            factor_field = f"d{varga[1:]}Lagna"
            varga_sign = signature.get(factor_field)
            if varga_sign in SIGNS and SIGN_LORDS[SIGNS.index(varga_sign)] in period_lords:
                contributions += 0.08
                support_ids.append(
                    f"rectification.{candidate_id}.{event['eventId']}.{varga.lower()}.lagna_lord"
                )

        transit = calc_transits(
            lagna_index,
            int(planet_signs.get("Moon", lagna_index)),
            as_of=event_moment.replace(tzinfo=timezone.utc),
        )
        activated = relevant_houses & set(transit.get("double_transit_houses") or [])
        if activated:
            contributions += 0.22
            support_ids.append(f"rectification.{candidate_id}.{event['eventId']}.double_transit")

        score = round(min(contributions, 1.0), 3)
        evidence_scores.append(
            {
                "eventId": event["eventId"],
                "role": event.get("role", "calibration"),
                "score": score,
                "supportingFactIds": support_ids,
                "contradictingFactIds": [],
                "ruleIds": ["rectification.event-evidence.v1"],
                "explanation": (
                    f"{event.get('categoryLabel')}: Dasha lords {period_lords or ['unavailable']}; "
                    f"relevant vargas {relevant_vargas or ['none']}; "
                    f"double-transit houses {transit.get('double_transit_houses') or []}."
                ),
            }
        )

    calibration = [item["score"] for item in evidence_scores if item["role"] == "calibration"]
    holdout = [item["score"] for item in evidence_scores if item["role"] == "holdout"]
    return {
        "evidenceScores": evidence_scores,
        "aggregateScore": round(sum(calibration) / len(calibration), 3) if calibration else None,
        "holdoutScore": round(sum(holdout) / len(holdout), 3) if holdout else None,
        "scoringPolicy": "transparent_product_hypothesis_v1",
    }


def _event_midpoint(event: dict[str, Any]) -> datetime:
    raw = str(event.get("date") or "")
    if re.fullmatch(r"\d{4}-\d{2}", raw):
        year, month = (int(value) for value in raw.split("-"))
        return datetime(year, month, 15, 12)
    if re.fullmatch(r"\d{4}", raw):
        return datetime(int(raw), 7, 1, 12)
    return datetime.fromisoformat(raw).replace(hour=12, minute=0, second=0, microsecond=0)


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
