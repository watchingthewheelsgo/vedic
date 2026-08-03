from __future__ import annotations

import hashlib
import re
from calendar import monthrange
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import pytz

from app.calculator.constants import SIGNS, SIGN_LORDS
from app.vedicdust.rectification_policy import (
    RECTIFICATION_EVENT_MAPPING_ID,
    RECTIFICATION_EVENT_RULES,
    RECTIFICATION_HOLDOUT_POLICY_ID,
    RECTIFICATION_RULE_ID,
    RECTIFICATION_SOURCE_IDS,
    RECTIFICATION_SCORING_POLICY,
)


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
    r"(?P<year>19\d{2}|20\d{2})"
    r"(?:\s*(?:年|-|/|\.)\s*(?P<month>1[0-2]|0?[1-9])\s*月?"
    r"(?:\s*(?:-|/|\.)?\s*(?P<day>3[01]|[12]\d|0?[1-9])\s*日?)?"
    r")?"
)


def parse_life_event_ledger(
    raw: str,
    *,
    semantic_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    text = (raw or "").strip()
    semantic_by_fingerprint = {
        _event_fingerprint(
            str(item.get("date") or ""),
            str(item.get("category") or ""),
            str(item.get("description") or ""),
        ): item
        for item in semantic_evidence or []
        if isinstance(item, dict)
        and str(item.get("date") or "").strip()
        and str(item.get("category") or "").strip()
    }
    events: list[dict[str, Any]] = []
    for index, line in enumerate(_candidate_lines(text), start=1):
        event = _parse_event_line(line, index)
        if event is not None:
            semantic = semantic_by_fingerprint.get(str(event.get("eventFingerprint") or ""))
            if semantic:
                event["questionId"] = str(semantic.get("questionId") or "")
                event["semanticFacts"] = dict(semantic.get("eventFacts") or {})
            events.append(event)

    events.sort(key=lambda event: str(event.get("date") or ""))
    eligible_events = [event for event in events if event.get("category") != "unknown"]
    for event in events:
        event["role"] = "calibration" if event in eligible_events else "context_only"
    if len(eligible_events) >= 3:
        _select_holdout_event(eligible_events)["role"] = "holdout"
    calibration_categories = {
        str(event.get("category"))
        for event in eligible_events
        if event.get("role") == "calibration" and event.get("category")
    }
    category_counts = Counter(str(event.get("category") or "unknown") for event in events)
    return {
        "schemaVersion": "life-event-ledger/v1",
        "raw": text,
        "events": events,
        "categoryCounts": dict(sorted(category_counts.items())),
        "eligibleEventCount": len(eligible_events),
        "calibrationCategoryCount": len(calibration_categories),
        "eventCollectionRequired": len(eligible_events) < 3,
        "recommendedMinimumEvents": 3,
        "holdoutPolicyId": RECTIFICATION_HOLDOUT_POLICY_ID,
        "recommendedRectificationUse": (
            "Use dated life events as the primary rectification evidence before generic traits."
            if events
            else "Ask the user for 3-5 dated life events before deep rectification."
        ),
        "semanticEvidence": [item for item in semantic_evidence or [] if isinstance(item, dict)],
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

    events = [
        event
        for event in ledger.get("events") or []
        if isinstance(event, dict) and event.get("role") in {"calibration", "holdout"}
    ]
    if not events:
        return {"evidenceScores": [], "aggregateScore": None, "holdoutScore": None}

    local_timezone = pytz.timezone(timezone_id)
    event_local_moments = [_event_midpoint(event) for event in events]
    event_period_samples = [_event_interval_samples(event) for event in events]
    event_period_sample_indices: list[tuple[int, int]] = []
    event_period_utc_moments: list[datetime] = []
    for samples in event_period_samples:
        start_index = len(event_period_utc_moments)
        event_period_utc_moments.extend(
            local_timezone.localize(moment, is_dst=None).astimezone(timezone.utc)
            for moment in samples
        )
        event_period_sample_indices.append((start_index, len(event_period_utc_moments)))
    localized_birth = _localized_birth_moment(representative_moment, local_timezone)
    from app.calculator.dasha_pyjhora import calculate_dasha_lords_at
    from app.calculator.engine import SPECIAL_DRISHTI, calc_transits

    dasha_lords = calculate_dasha_lords_at(
        localized_birth.year,
        localized_birth.month,
        localized_birth.day,
        localized_birth.hour,
        localized_birth.minute,
        latitude,
        longitude,
        localized_birth.utcoffset().total_seconds() / 3600.0,
        event_period_utc_moments,
        birth_second=localized_birth.second,
    )
    if len(dasha_lords) != len(event_period_utc_moments):
        raise RuntimeError(
            "Vimshottari event lookup returned an incomplete event-boundary result set"
        )
    for sample_index, period in enumerate(dasha_lords):
        missing_levels = [
            level
            for level in ("mahadasha", "antardasha", "pratyantardasha")
            if not str(period.get(level) or "").strip()
        ]
        if missing_levels:
            raise RuntimeError(
                "Vimshottari event lookup returned an incomplete hierarchy "
                f"at sample {sample_index}: {', '.join(missing_levels)}"
            )
    lagna_sign = str(signature.get("lagnaSign") or "")
    if lagna_sign not in SIGNS:
        raise RuntimeError("rectification signature has no valid D1 Lagna sign")
    lagna_index = SIGNS.index(lagna_sign)
    planet_signs = signature.get("planetSignIndices") or {}
    if not isinstance(planet_signs, dict):
        raise RuntimeError("rectification signature has no D1 planetary sign map")
    moon_sign_index = _required_sign_index(planet_signs, "Moon", scope="D1")
    varga_planet_signs = signature.get("vargaPlanetSignIndices") or {}
    if not isinstance(varga_planet_signs, dict):
        raise RuntimeError("rectification signature has no divisional planetary sign map")
    evidence_scores: list[dict[str, Any]] = []
    for event, event_local, sample_range in zip(
        events, event_local_moments, event_period_sample_indices, strict=True
    ):
        sample_periods = dasha_lords[sample_range[0] : sample_range[1]]
        rules = event.get("rectificationRules") or RECTIFICATION_EVENT_RULES["unknown"]
        relevant_houses = {int(value) for value in rules.get("houses") or []}
        karakas = {str(value) for value in rules.get("karakas") or []}
        relevant_vargas = [str(value) for value in rules.get("vargas") or []]
        observations: list[dict[str, Any]] = []
        support_score = 0.0
        contradiction_score = 0.0
        semantic_facts = event.get("semanticFacts")
        period_entries: list[tuple[str, str]] = []
        unstable_periods: dict[str, list[str]] = {}
        for short_level, level in (
            ("md", "mahadasha"),
            ("ad", "antardasha"),
            ("pd", "pratyantardasha"),
        ):
            sampled_lords = [str(period.get(level) or "") for period in sample_periods]
            distinct_lords = sorted({lord for lord in sampled_lords if lord})
            if sampled_lords and all(sampled_lords) and len(distinct_lords) == 1:
                period_entries.append((short_level, distinct_lords[0]))
            elif len(distinct_lords) > 1:
                unstable_periods[short_level] = distinct_lords
        period_lords = [lord for _, lord in period_entries]
        for lord in period_lords:
            _required_sign_index(planet_signs, lord, scope="D1")
        available_levels = {level for level, _ in period_entries}
        for level in ("md", "ad", "pd"):
            if level not in available_levels:
                observations.append(
                    _observation(
                        candidate_id,
                        event["eventId"],
                        f"{level}.unavailable",
                        component="dasha",
                        outcome="missing",
                        weight=0.0,
                        details={
                            "level": level,
                            "reason": (
                                "period_changes_within_reported_date_range"
                                if level in unstable_periods
                                else "period_lord_unavailable"
                            ),
                            "sampledLords": unstable_periods.get(level, []),
                        },
                    )
                )
        for level, lord in period_entries:
            weight = RECTIFICATION_SCORING_POLICY.dasha_level_weights[level]
            matched_dimensions: list[str] = []
            if lord in karakas:
                matched_dimensions.append("karaka")
            sign_index = planet_signs.get(lord)
            if sign_index is not None:
                occupied_house = (int(sign_index) - lagna_index) % 12 + 1
                if occupied_house in relevant_houses:
                    matched_dimensions.append("occupant")
            aspected_relevant_houses: list[int] = []
            if sign_index is not None and lord not in {"Rahu", "Ketu"}:
                aspected_relevant_houses = sorted(
                    relevant_houses
                    & {
                        (int(sign_index) + aspect_number - 1 - lagna_index) % 12 + 1
                        for aspect_number in [7, *SPECIAL_DRISHTI.get(lord, [])]
                    }
                )
                if aspected_relevant_houses:
                    matched_dimensions.append("graha_drishti")
            ruled_houses = {
                house
                for house in relevant_houses
                if SIGN_LORDS[(lagna_index + house - 1) % 12] == lord
            }
            if ruled_houses:
                matched_dimensions.append("lord")
            if matched_dimensions:
                support_score += weight
                observations.append(
                    _observation(
                        candidate_id,
                        event["eventId"],
                        f"{level}.activation",
                        component="dasha",
                        outcome="support",
                        weight=weight,
                        details={
                            "level": level,
                            "lord": lord,
                            "matchedDimensions": matched_dimensions,
                            "aspectedRelevantHouses": aspected_relevant_houses,
                        },
                    )
                )
            else:
                observations.append(
                    _observation(
                        candidate_id,
                        event["eventId"],
                        f"{level}.activation_not_observed",
                        component="dasha",
                        outcome="missing",
                        weight=0.0,
                        details={
                            "level": level,
                            "lord": lord,
                            "reason": "positive_activation_rule_not_matched",
                        },
                    )
                )

        for varga in relevant_vargas:
            factor_field = f"d{varga[1:]}Lagna"
            varga_sign = signature.get(factor_field)
            varga_signs = (
                varga_planet_signs.get(varga) if isinstance(varga_planet_signs, dict) else None
            )
            if not period_lords:
                observations.append(
                    _observation(
                        candidate_id,
                        event["eventId"],
                        f"{varga.lower()}.unavailable",
                        component="varga",
                        outcome="missing",
                        weight=0.0,
                        details={
                            "varga": varga,
                            "reason": "varga_structure_or_period_lord_unavailable",
                        },
                    )
                )
                continue
            if varga_sign not in SIGNS or not isinstance(varga_signs, dict):
                raise RuntimeError(f"rectification signature has incomplete {varga} structure")
            for lord in period_lords:
                _required_sign_index(varga_signs, lord, scope=varga)

            varga_lagna_index = SIGNS.index(varga_sign)
            activated_lords: dict[str, list[str]] = {}
            for lord in period_lords:
                dimensions: list[str] = []
                sign_index = varga_signs.get(lord)
                if sign_index is not None:
                    occupied_house = (int(sign_index) - varga_lagna_index) % 12 + 1
                    if occupied_house in relevant_houses:
                        dimensions.append(f"occupies_H{occupied_house}")
                ruled_houses = sorted(
                    house
                    for house in relevant_houses
                    if SIGN_LORDS[(varga_lagna_index + house - 1) % 12] == lord
                )
                dimensions.extend(f"rules_H{house}" for house in ruled_houses)
                if dimensions:
                    activated_lords[lord] = dimensions

            if activated_lords:
                weight = RECTIFICATION_SCORING_POLICY.varga_lagna_lord_support_weight
                support_score += weight
                observations.append(
                    _observation(
                        candidate_id,
                        event["eventId"],
                        f"{varga.lower()}.domain_activation",
                        component="varga",
                        outcome="support",
                        weight=weight,
                        details={
                            "varga": varga,
                            "lagnaSign": varga_sign,
                            "activatedPeriodLords": activated_lords,
                        },
                    )
                )
            else:
                observations.append(
                    _observation(
                        candidate_id,
                        event["eventId"],
                        f"{varga.lower()}.activation_not_observed",
                        component="varga",
                        outcome="missing",
                        weight=0.0,
                        details={
                            "varga": varga,
                            "lagnaSign": varga_sign,
                            "relevantHouses": sorted(relevant_houses),
                            "periodLords": period_lords,
                            "reason": "positive_activation_rule_not_matched",
                        },
                    )
                )

        transit_samples: list[dict[str, Any]] = []
        for transit_local in _event_transit_moments(event):
            transit_utc = local_timezone.localize(transit_local, is_dst=None).astimezone(
                timezone.utc
            )
            transit_samples.append(
                calc_transits(
                    lagna_index,
                    moon_sign_index,
                    as_of=transit_utc,
                )
            )
        transit_house_samples = [
            {int(house) for house in transit.get("double_transit_houses") or []}
            for transit in transit_samples
        ]
        observed_transit_houses = sorted(set().union(*transit_house_samples))
        stable_transit_houses = sorted(
            set.intersection(*transit_house_samples) if transit_house_samples else set()
        )
        activated = relevant_houses & set(stable_transit_houses)
        if event.get("datePrecision") == "year":
            observations.append(
                _observation(
                    candidate_id,
                    event["eventId"],
                    "double_transit.unavailable",
                    component="double_transit",
                    outcome="missing",
                    weight=0.0,
                    details={
                        "reason": "reported_year_too_broad_for_transit_evidence",
                        "observedHouses": observed_transit_houses,
                    },
                )
            )
        elif activated:
            weight = RECTIFICATION_SCORING_POLICY.double_transit_support_weight
            support_score += weight
            observations.append(
                _observation(
                    candidate_id,
                    event["eventId"],
                    "double_transit.activation",
                    component="double_transit",
                    outcome="support",
                    weight=weight,
                    details={
                        "activatedHouses": sorted(activated),
                        "stableAcrossReportedInterval": True,
                        "sampleCount": len(transit_house_samples),
                    },
                )
            )
        else:
            observations.append(
                _observation(
                    candidate_id,
                    event["eventId"],
                    "double_transit.activation_not_observed",
                    component="double_transit",
                    outcome="missing",
                    weight=0.0,
                    details={
                        "reason": (
                            "activation_not_stable_across_reported_interval"
                            if relevant_houses and set(observed_transit_houses) & relevant_houses
                            else "positive_activation_rule_not_matched"
                            if relevant_houses
                            else "event_category_has_no_house_mapping"
                        ),
                        "observedHouses": observed_transit_houses,
                        "stableHouses": stable_transit_houses,
                    },
                )
            )

        support_score = round(min(support_score, 1.0), 3)
        contradiction_score = round(min(contradiction_score, 1.0), 3)
        score = round(max(-1.0, min(1.0, support_score - contradiction_score)), 3)
        evidence_scores.append(
            {
                "eventId": event["eventId"],
                "eventFingerprint": event.get("eventFingerprint"),
                "semanticFacts": dict(semantic_facts) if isinstance(semantic_facts, dict) else None,
                "role": event.get("role", "calibration"),
                "score": score,
                "supportScore": support_score,
                "contradictionScore": contradiction_score,
                "observations": observations,
                "ruleIds": [RECTIFICATION_RULE_ID],
                "sourceIds": list(RECTIFICATION_SOURCE_IDS),
                "scoringPolicyId": RECTIFICATION_SCORING_POLICY.policy_id,
                "eventMappingId": RECTIFICATION_EVENT_MAPPING_ID,
                "explanation": (
                    f"{event.get('categoryLabel')}: Dasha lords {period_lords or ['unavailable']}; "
                    f"relevant vargas {relevant_vargas or ['none']}; "
                    "double-transit houses stable across the reported interval "
                    f"{stable_transit_houses}."
                    f" Event interval sampled at its start, midpoint, and end in {timezone_id}; "
                    f"display midpoint {event_local.isoformat()}."
                ),
            }
        )

    calibration = [item["score"] for item in evidence_scores if item["role"] == "calibration"]
    holdout = [item["score"] for item in evidence_scores if item["role"] == "holdout"]
    return {
        "evidenceScores": evidence_scores,
        "aggregateScore": round(sum(calibration) / len(calibration), 3) if calibration else None,
        "holdoutScore": round(sum(holdout) / len(holdout), 3) if holdout else None,
        "scoringPolicy": RECTIFICATION_SCORING_POLICY.policy_id,
    }


def _required_sign_index(values: dict[str, Any], graha: str, *, scope: str) -> int:
    value = values.get(graha)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 12:
        raise RuntimeError(f"rectification signature has no valid {scope} sign index for {graha}")
    return value


def candidate_event_period_fingerprint(
    *,
    birth_moment: datetime,
    latitude: float,
    longitude: float,
    timezone_id: str,
    ledger: dict[str, Any],
    reference_moment: datetime | None = None,
) -> dict[str, Any] | None:
    """Return private Dasha partition keys for dated events and the report epoch.

    The key only prevents one candidate interval from spanning different
    calibration-event period evidence or a current MD/AD boundary. Reserved
    holdout evidence must not influence candidate construction; it is evaluated
    only after calibration selects a candidate or equivalence class.
    """

    events = [
        event
        for event in ledger.get("events") or []
        if isinstance(event, dict) and event.get("role") == "calibration"
    ]
    if not events and reference_moment is None:
        return None

    local_timezone = pytz.timezone(timezone_id)
    localized_birth = _localized_birth_moment(birth_moment, local_timezone)
    event_sample_counts: list[int] = []
    event_moments: list[datetime] = []
    for event in events:
        samples = _event_interval_samples(event)
        event_sample_counts.append(len(samples))
        event_moments.extend(
            local_timezone.localize(moment, is_dst=None).astimezone(timezone.utc)
            for moment in samples
        )
    current_index = None
    if reference_moment is not None:
        if reference_moment.tzinfo is None or reference_moment.utcoffset() is None:
            raise ValueError("rectification reference moment must be timezone-aware")
        current_index = len(event_moments)
        event_moments.append(reference_moment.astimezone(timezone.utc))
    from app.calculator.dasha_pyjhora import calculate_dasha_lords_at

    periods = calculate_dasha_lords_at(
        localized_birth.year,
        localized_birth.month,
        localized_birth.day,
        localized_birth.hour,
        localized_birth.minute,
        latitude,
        longitude,
        localized_birth.utcoffset().total_seconds() / 3600.0,
        event_moments,
        birth_second=localized_birth.second,
    )
    event_fingerprint: list[str] = []
    period_index = 0
    for sample_count in event_sample_counts:
        sample_keys = [
            "/".join(
                str(period.get(level) or "unavailable")
                for level in ("mahadasha", "antardasha", "pratyantardasha")
            )
            for period in periods[period_index : period_index + sample_count]
        ]
        event_fingerprint.append("|".join(sample_keys))
        period_index += sample_count
    current_dasha = None
    if current_index is not None:
        current_period = periods[current_index]
        current_dasha = "-".join(
            str(current_period.get(level) or "unavailable") for level in ("mahadasha", "antardasha")
        )
    return {
        "eventPeriods": tuple(event_fingerprint),
        "currentDasha": current_dasha,
    }


def _localized_birth_moment(value: datetime, local_timezone) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return local_timezone.localize(value, is_dst=None)
    return value.astimezone(local_timezone)


def _event_midpoint(event: dict[str, Any]) -> datetime:
    raw = str(event.get("date") or "")
    if re.fullmatch(r"\d{4}-\d{2}", raw):
        year, month = (int(value) for value in raw.split("-"))
        return datetime(year, month, 15, 12)
    if re.fullmatch(r"\d{4}", raw):
        return datetime(int(raw), 7, 1, 12)
    return datetime.fromisoformat(raw).replace(hour=12, minute=0, second=0, microsecond=0)


def _event_interval_samples(event: dict[str, Any]) -> list[datetime]:
    """Return start, midpoint, and end samples for an uncertain event interval."""

    raw = str(event.get("date") or "")
    if re.fullmatch(r"\d{4}-\d{2}", raw):
        year, month = (int(value) for value in raw.split("-"))
        return [
            datetime(year, month, 1, 12),
            datetime(year, month, 15, 12),
            datetime(year, month, monthrange(year, month)[1], 12),
        ]
    if re.fullmatch(r"\d{4}", raw):
        year = int(raw)
        return [
            datetime(year, 1, 1, 12),
            datetime(year, 7, 1, 12),
            datetime(year, 12, 31, 12),
        ]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        date = datetime.fromisoformat(raw)
        return [date.replace(hour=0), date.replace(hour=12), date.replace(hour=23, minute=59)]
    return [_event_midpoint(event)]


def _event_transit_moments(event: dict[str, Any]) -> list[datetime]:
    """Sample slow-planet activation without inventing an exact event date."""

    return _event_interval_samples(event)


def build_life_event_focus(
    ledger: dict[str, Any],
    discriminating_fields: list[str],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return calibration events that may be used to generate rectification questions.

    Holdout events are deliberately excluded. They are reserved for the backend
    selection check and must not leak into the Agent's fitting context.
    """

    events = ledger.get("events") if isinstance(ledger, dict) else None
    if not isinstance(events, list):
        return []
    field_set = {str(field) for field in discriminating_fields if field}
    focus: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("role") != "calibration":
            continue
        rules = event.get("rectificationRules")
        if not isinstance(rules, dict):
            rules = RECTIFICATION_EVENT_RULES["unknown"]
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
    day_raw = date_match.group("day")
    month = int(month_raw) if month_raw else None
    day = int(day_raw) if day_raw else None
    if day is not None:
        try:
            datetime(year, int(month), day)
        except (TypeError, ValueError):
            return None
    category = _explicit_category(line) or _classify_category(line)
    rules = RECTIFICATION_EVENT_RULES[category]
    date_value = (
        f"{year:04d}-{month:02d}-{day:02d}"
        if day is not None
        else f"{year:04d}-{month:02d}"
        if month is not None
        else f"{year:04d}"
    )
    date_precision = "day" if day is not None else "month" if month is not None else "year"
    event_fingerprint = _event_fingerprint(date_value, category, line)
    return {
        "eventId": f"evt_{event_fingerprint[:16]}",
        "eventFingerprint": event_fingerprint,
        "date": date_value,
        "datePrecision": date_precision,
        "category": category,
        "categoryLabel": rules["label"],
        "description": line,
        "confidence": "medium",
        "rectificationEventMappingId": RECTIFICATION_EVENT_MAPPING_ID,
        "rectificationRules": {
            "houses": rules["houses"],
            "vargas": rules["vargas"],
            "karakas": rules["karakas"],
            "fields": rules["fields"],
        },
    }


def _event_fingerprint(date_value: str, category: str, description: str) -> str:
    normalized_description = _clean_event_description(description, date_value, category)
    payload = "|".join(
        (
            " ".join(str(date_value).split()),
            str(category).strip().casefold(),
            normalized_description,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _clean_event_description(description: str, date_value: str, category: str) -> str:
    value = " ".join(str(description or "").split())
    prefix = f"{date_value} {category}:"
    if value.casefold().startswith(prefix.casefold()):
        value = value[len(prefix) :].strip()
    return value.casefold()


def _classify_category(line: str) -> str:
    lowered = line.lower()
    for category, keywords in KEYWORDS:
        if any(keyword.lower() in lowered for keyword in keywords):
            return category
    return "unknown"


def _explicit_category(line: str) -> str | None:
    match = re.match(
        r"^\s*(?:19|20)\d{2}(?:-\d{2}(?:-\d{2})?)?\s+([a-z_]+)\s*:",
        line,
        re.IGNORECASE,
    )
    if not match:
        return None
    category = match.group(1).lower()
    return category if category in RECTIFICATION_EVENT_RULES and category != "unknown" else None


def _select_holdout_event(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Reserve evidence without inspecting any candidate score.

    Prefer a precise event while preserving the broadest possible category
    coverage in calibration. The final date tie-break keeps the split stable.
    """

    precision_rank = {"year": 0, "month": 1, "day": 2}

    def rank(item: tuple[int, dict[str, Any]]) -> tuple[int, int, str, int]:
        index, holdout = item
        calibration_categories = {
            str(event.get("category"))
            for candidate_index, event in enumerate(events)
            if candidate_index != index and event.get("category")
        }
        return (
            len(calibration_categories),
            precision_rank.get(str(holdout.get("datePrecision") or ""), -1),
            str(holdout.get("date") or ""),
            index,
        )

    return max(enumerate(events), key=rank)[1]


def _observation(
    candidate_id: str,
    event_id: str,
    suffix: str,
    *,
    component: str,
    outcome: str,
    weight: float,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "observationId": f"rectification.{candidate_id}.{event_id}.{suffix}",
        "component": component,
        "outcome": outcome,
        "weight": round(weight, 4),
        "details": details,
    }
