from __future__ import annotations

import hashlib
import re
from calendar import monthrange
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

import pytz

from app.calculator.constants import SIGNS, SIGN_LORDS
from app.vedicdust.event_time import (
    EVENT_TIMEZONE_BASIS,
    event_utc_envelope,
    event_utc_sample_envelope,
)
from app.vedicdust.rectification_policy import (
    RECTIFICATION_EVENT_MAPPING_ID,
    RECTIFICATION_EVENT_RULES,
    RECTIFICATION_HOLDOUT_POLICY_ID,
    RECTIFICATION_KP_RULE_ID,
    MINIMUM_RECTIFICATION_EVENTS,
    RECTIFICATION_RULE_ID,
    RECTIFICATION_SELECTION_COMPONENTS,
    RECTIFICATION_SOURCE_IDS,
    RECTIFICATION_SCORING_POLICY,
    rectification_rules_for,
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
MAX_RECTIFICATION_EVENTS = 5
MIN_RECTIFICATION_EVENTS = MINIMUM_RECTIFICATION_EVENTS


def parse_life_event_ledger(
    raw: str,
    *,
    semantic_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    text = (raw or "").strip()
    semantic_by_fingerprint: dict[str, list[dict[str, Any]]] = {}
    for item in semantic_evidence or []:
        if (
            not isinstance(item, dict)
            or not str(item.get("date") or "").strip()
            or not str(item.get("category") or "").strip()
        ):
            continue
        match_key = _event_match_fingerprint(
            str(item.get("date") or ""),
            str(item.get("category") or ""),
            str(item.get("description") or ""),
        )
        semantic_by_fingerprint.setdefault(match_key, []).append(item)
    events: list[dict[str, Any]] = []
    for index, line in enumerate(_candidate_lines(text), start=1):
        event = _parse_event_line(line, index)
        if event is not None:
            event["intakeSequence"] = index
            semantic_matches = semantic_by_fingerprint.get(
                str(event.get("eventFingerprint") or ""), []
            )
            semantic = semantic_matches.pop(0) if semantic_matches else None
            if semantic:
                event["questionId"] = str(semantic.get("questionId") or "")
                event["semanticFacts"] = dict(semantic.get("eventFacts") or {})
                event_subtype = str(semantic.get("eventSubtype") or "").strip().casefold()
                if event_subtype:
                    event["eventSubtype"] = event_subtype
                    _apply_event_rules(event, event_subtype=event_subtype)
                    event_fingerprint = _event_fingerprint(
                        str(event.get("date") or ""),
                        str(event.get("category") or ""),
                        str(event.get("description") or ""),
                        event_subtype,
                    )
                    event["eventFingerprint"] = event_fingerprint
                    event["eventId"] = f"evt_{event_fingerprint[:16]}"
            events.append(event)

    eligible_events = [event for event in events if event.get("category") != "unknown"]
    for event in events:
        event["role"] = "context_only"
    episode_primaries = _assign_life_episodes(eligible_events)
    for primary in episode_primaries:
        primary["role"] = "calibration"
        for member in primary.get("episodeMembers") or []:
            if member is not primary:
                member["role"] = "calibration_context"
    # Reserve the third independent episode as soon as it exists. Waiting for a
    # fourth would let private holdout evidence influence candidate ranking and
    # the next adaptive question during the preceding round.
    if len(episode_primaries) >= 3:
        holdout_primary = _select_holdout_event(episode_primaries)
        holdout_primary["role"] = "holdout"
        for member in holdout_primary.get("episodeMembers") or []:
            if member is not holdout_primary:
                member["role"] = "holdout_context"
    for event in eligible_events:
        event.pop("episodeMembers", None)
    events.sort(
        key=lambda event: (
            str(event.get("date") or ""),
            int(event.get("intakeSequence") or 0),
        )
    )
    calibration_categories = {
        str(event.get("category"))
        for event in episode_primaries
        if event.get("role") == "calibration" and event.get("category")
    }
    category_counts = Counter(str(event.get("category") or "unknown") for event in events)
    return {
        "schemaVersion": "life-event-ledger/v1",
        "raw": text,
        "events": events,
        "categoryCounts": dict(sorted(category_counts.items())),
        "eligibleEventCount": len(eligible_events),
        "independentEpisodeCount": len(episode_primaries),
        "correlatedEventCount": max(0, len(eligible_events) - len(episode_primaries)),
        "calibrationEpisodeCount": sum(
            1 for event in episode_primaries if event.get("role") == "calibration"
        ),
        "holdoutEpisodeCount": sum(
            1 for event in episode_primaries if event.get("role") == "holdout"
        ),
        "calibrationCategoryCount": len(calibration_categories),
        "eventCollectionRequired": len(episode_primaries) < MIN_RECTIFICATION_EVENTS,
        "recommendedMinimumEvents": MIN_RECTIFICATION_EVENTS,
        "maximumAcceptedEvents": MAX_RECTIFICATION_EVENTS,
        "holdoutPolicyId": RECTIFICATION_HOLDOUT_POLICY_ID,
        "recommendedRectificationUse": (
            "Use dated life events as the primary rectification evidence before generic traits."
            if events
            else "Ask the user for 4-5 dated life events before deep rectification."
        ),
        "semanticEvidence": [item for item in semantic_evidence or [] if isinstance(item, dict)],
    }


def _semantic_adjustment_for_event(event: dict[str, Any]) -> dict[str, Any] | None:
    facts = event.get("semanticFacts")
    if not isinstance(facts, dict):
        return None
    # The non-Agent fallback emits default facts so the schema stays stable. Do
    # not silently treat those defaults as an LLM judgement.
    if not any(
        facts.get(field) not in {None, "", "unknown", "occurred"}
        for field in ("occurrence", "impact", "dateConfidence")
    ):
        return None

    return {
        "applied": False,
        "componentMultipliers": {},
        "usedFields": [],
        "contextOnlyFields": ["occurrence", "agency", "impact", "dateConfidence"],
        "reason": (
            "Agent-classified event facts are retained as context for the interview and report. "
            "They do not change deterministic candidate scores; only the user-supplied date "
            "precision and versioned Jyotish rules may affect scoring."
        ),
    }


def _apply_semantic_adjustment(
    event: dict[str, Any],
) -> dict[str, Any] | None:
    adjustment = _semantic_adjustment_for_event(event)
    if adjustment is None:
        return None
    return adjustment


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
        return {
            "evidenceScores": [],
            "aggregateScore": None,
            "holdoutScore": None,
            "vimshottariDashaScore": None,
            "charaDashaScore": None,
            "charaDashaDiagnostics": [],
        }

    local_timezone = pytz.timezone(timezone_id)
    event_local_moments = [_event_midpoint(event) for event in events]
    event_period_intervals = [_event_interval_bounds(event) for event in events]
    event_period_utc_intervals = [
        event_utc_envelope(start, end) for start, end in event_period_intervals
    ]
    # Chara Dasha remains diagnostic-only and is sampled over broad user date
    # ranges. Primary Vimshottari evidence uses exact interval boundaries below.
    event_period_samples = [_event_interval_samples(event) for event in events]
    event_period_sample_indices: list[tuple[int, int]] = []
    event_period_utc_moments: list[datetime] = []
    for samples in event_period_samples:
        start_index = len(event_period_utc_moments)
        for moment in samples:
            event_period_utc_moments.extend(event_utc_sample_envelope(moment))
        event_period_sample_indices.append((start_index, len(event_period_utc_moments)))
    localized_birth = _localized_birth_moment(representative_moment, local_timezone)
    from app.calculator.dasha_pyjhora import calculate_dasha_lords_for_intervals
    from app.calculator.chara_dasha_pyjhora import calculate_chara_dasha_lords_at, rasi_drishti
    from app.calculator.engine import SPECIAL_DRISHTI, calc_transits

    dasha_lords = calculate_dasha_lords_for_intervals(
        localized_birth.year,
        localized_birth.month,
        localized_birth.day,
        localized_birth.hour,
        localized_birth.minute,
        latitude,
        longitude,
        localized_birth.utcoffset().total_seconds() / 3600.0,
        event_period_utc_intervals,
        birth_second=localized_birth.second,
    )
    if len(dasha_lords) != len(events):
        raise RuntimeError(
            "Vimshottari event lookup returned an incomplete event-interval result set"
        )
    chara_dasha_periods: list[dict[str, Any]] | None
    try:
        chara_dasha_periods = calculate_chara_dasha_lords_at(
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
        if len(chara_dasha_periods) != len(event_period_utc_moments):
            raise RuntimeError(
                "Chara Dasha event lookup returned an incomplete event-boundary result set"
            )
    except Exception:
        # Chara Dasha is a diagnostic-only, non-additive signal (see below); a
        # calculation failure must not break the primary Vimshottari-based score.
        chara_dasha_periods = None
    for event_index, period in enumerate(dasha_lords):
        unstable_levels = {str(level) for level in period.get("unstableLevels") or []}
        missing_levels = [
            short_level
            for short_level, level in (
                ("md", "mahadasha"),
                ("ad", "antardasha"),
                ("pd", "pratyantardasha"),
            )
            if not str(period.get(level) or "").strip() and short_level not in unstable_levels
        ]
        if missing_levels:
            raise RuntimeError(
                "Vimshottari event lookup returned an incomplete hierarchy "
                f"for event {event_index}: {', '.join(missing_levels)}"
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
    chara_dasha_event_scores: list[dict[str, Any]] = []
    for event, event_local, sample_range, event_period in zip(
        events,
        event_local_moments,
        event_period_sample_indices,
        dasha_lords,
        strict=True,
    ):
        chara_sample_periods = (
            chara_dasha_periods[sample_range[0] : sample_range[1]]
            if chara_dasha_periods is not None
            else []
        )
        rules = event.get("rectificationRules") or RECTIFICATION_EVENT_RULES["unknown"]
        relevant_houses = {int(value) for value in rules.get("houses") or []}
        karakas = {str(value) for value in rules.get("karakas") or []}
        relevant_vargas = [str(value) for value in rules.get("vargas") or []]
        observations: list[dict[str, Any]] = []
        support_score = 0.0
        contradiction_score = 0.0
        semantic_facts = event.get("semanticFacts")
        semantic_adjustment = None
        period_entries: list[tuple[str, str]] = []
        unstable_periods = {str(level) for level in event_period.get("unstableLevels") or []}
        for short_level, level in (
            ("md", "mahadasha"),
            ("ad", "antardasha"),
            ("pd", "pratyantardasha"),
        ):
            lord = str(event_period.get(level) or "")
            if lord:
                period_entries.append((short_level, lord))
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
                                "period_changes_within_reported_date_or_timezone_envelope"
                                if level in unstable_periods
                                else "period_lord_unavailable"
                            ),
                            "exactBoundaryCheck": True,
                            "reportedDate": event.get("date"),
                            "eventTimezoneBasis": EVENT_TIMEZONE_BASIS,
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
            for transit_utc in event_utc_sample_envelope(transit_local):
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

        node_house_samples = [
            {
                int(transit[node]["house"])
                for node in ("Rahu", "Ketu")
                if isinstance(transit.get(node), dict)
            }
            for transit in transit_samples
        ]
        observed_node_houses = sorted(set().union(*node_house_samples))
        stable_node_houses = sorted(
            set.intersection(*node_house_samples) if node_house_samples else set()
        )
        node_activated = relevant_houses & set(stable_node_houses)
        if event.get("datePrecision") == "year":
            observations.append(
                _observation(
                    candidate_id,
                    event["eventId"],
                    "node_transit.unavailable",
                    component="node_transit",
                    outcome="missing",
                    weight=0.0,
                    details={
                        "reason": "reported_year_too_broad_for_transit_evidence",
                        "observedHouses": observed_node_houses,
                    },
                )
            )
        elif node_activated:
            weight = RECTIFICATION_SCORING_POLICY.node_transit_support_weight
            support_score += weight
            observations.append(
                _observation(
                    candidate_id,
                    event["eventId"],
                    "node_transit.activation",
                    component="node_transit",
                    outcome="support",
                    weight=weight,
                    details={
                        "activatedHouses": sorted(node_activated),
                        "stableAcrossReportedInterval": True,
                        "sampleCount": len(node_house_samples),
                    },
                )
            )
        else:
            observations.append(
                _observation(
                    candidate_id,
                    event["eventId"],
                    "node_transit.activation_not_observed",
                    component="node_transit",
                    outcome="missing",
                    weight=0.0,
                    details={
                        "reason": (
                            "activation_not_stable_across_reported_interval"
                            if relevant_houses and set(observed_node_houses) & relevant_houses
                            else "positive_activation_rule_not_matched"
                            if relevant_houses
                            else "event_category_has_no_house_mapping"
                        ),
                        "observedHouses": observed_node_houses,
                        "stableHouses": stable_node_houses,
                    },
                )
            )

        sade_sati_relevant = bool(rules.get("sadeSatiRelevant"))
        sade_sati_samples = [
            str(transit.get("sade_sati") or "inactive") for transit in transit_samples
        ]
        distinct_sade_sati_states = sorted(set(sade_sati_samples))
        if not sade_sati_relevant:
            observations.append(
                _observation(
                    candidate_id,
                    event["eventId"],
                    "sade_sati.not_applicable",
                    component="sade_sati",
                    outcome="missing",
                    weight=0.0,
                    details={"reason": "event_category_not_sade_sati_relevant"},
                )
            )
        elif event.get("datePrecision") == "year":
            observations.append(
                _observation(
                    candidate_id,
                    event["eventId"],
                    "sade_sati.unavailable",
                    component="sade_sati",
                    outcome="missing",
                    weight=0.0,
                    details={
                        "reason": "reported_year_too_broad_for_transit_evidence",
                        "observedStates": distinct_sade_sati_states,
                    },
                )
            )
        elif (
            sade_sati_samples
            and len(distinct_sade_sati_states) == 1
            and distinct_sade_sati_states[0] != "inactive"
        ):
            weight = RECTIFICATION_SCORING_POLICY.sade_sati_support_weight
            support_score += weight
            observations.append(
                _observation(
                    candidate_id,
                    event["eventId"],
                    "sade_sati.active",
                    component="sade_sati",
                    outcome="support",
                    weight=weight,
                    details={
                        "phase": distinct_sade_sati_states[0],
                        "stableAcrossReportedInterval": True,
                        "sampleCount": len(sade_sati_samples),
                    },
                )
            )
        else:
            observations.append(
                _observation(
                    candidate_id,
                    event["eventId"],
                    "sade_sati.activation_not_observed",
                    component="sade_sati",
                    outcome="missing",
                    weight=0.0,
                    details={
                        "reason": (
                            "phase_changes_within_reported_date_range"
                            if len(distinct_sade_sati_states) > 1
                            else "sade_sati_not_active"
                        ),
                        "observedStates": distinct_sade_sati_states,
                    },
                )
            )

        kp_data = signature.get("kpCuspalSubLords")
        if not isinstance(kp_data, dict) or not kp_data.get("houses"):
            observations.append(
                _observation(
                    candidate_id,
                    event["eventId"],
                    "kp_sub_lord.unavailable",
                    component="kp_sub_lord",
                    outcome="missing",
                    weight=0.0,
                    details={"reason": "kp_calculation_unavailable"},
                )
            )
        elif not relevant_houses:
            observations.append(
                _observation(
                    candidate_id,
                    event["eventId"],
                    "kp_sub_lord.activation_not_observed",
                    component="kp_sub_lord",
                    outcome="missing",
                    weight=0.0,
                    details={"reason": "event_category_has_no_house_mapping"},
                )
            )
        else:
            cusp_by_house = {int(item["house"]): item for item in kp_data["houses"]}
            matched_houses: list[dict[str, Any]] = []
            for house in sorted(relevant_houses):
                cusp = cusp_by_house.get(house)
                if not cusp:
                    continue
                matched_dimensions: list[str] = []
                for role, lord in (
                    ("starLord", cusp.get("starLord")),
                    ("subLord", cusp.get("subLord")),
                ):
                    if not lord:
                        continue
                    if lord in karakas:
                        matched_dimensions.append(f"{role}_karaka")
                    if any(SIGN_LORDS[(lagna_index + h - 1) % 12] == lord for h in relevant_houses):
                        matched_dimensions.append(f"{role}_rules_relevant_house")
                    sign_index = planet_signs.get(lord)
                    if sign_index is not None:
                        occupied_house = (int(sign_index) - lagna_index) % 12 + 1
                        if occupied_house in relevant_houses:
                            matched_dimensions.append(f"{role}_occupies_relevant_house")
                if matched_dimensions:
                    matched_houses.append(
                        {
                            "house": house,
                            "starLord": cusp.get("starLord"),
                            "subLord": cusp.get("subLord"),
                            "matchedDimensions": matched_dimensions,
                        }
                    )
            if matched_houses:
                weight = RECTIFICATION_SCORING_POLICY.kp_sub_lord_support_weight
                observations.append(
                    _observation(
                        candidate_id,
                        event["eventId"],
                        "kp_sub_lord.activation",
                        component="kp_sub_lord",
                        outcome="support",
                        weight=weight,
                        details={
                            "matchedHouses": matched_houses,
                            "ayanamsaUsed": kp_data.get("ayanamsa"),
                            "cuspMethod": kp_data.get("cuspMethod"),
                        },
                    )
                )
            else:
                observations.append(
                    _observation(
                        candidate_id,
                        event["eventId"],
                        "kp_sub_lord.activation_not_observed",
                        component="kp_sub_lord",
                        outcome="missing",
                        weight=0.0,
                        details={
                            "reason": "positive_activation_rule_not_matched",
                            "relevantHouses": sorted(relevant_houses),
                        },
                    )
                )

        # KP is a new, unvalidated evidence channel: it must not be able to carry an
        # event on its own. If it is the only support source, downgrade it to missing
        # rather than let it contribute to support_score.
        kp_support_observations = [
            item
            for item in observations
            if item["outcome"] == "support" and item["component"] == "kp_sub_lord"
        ]
        if kp_support_observations:
            corroborated = any(
                item["outcome"] == "support"
                and item["component"] in {"dasha", "varga", "double_transit"}
                for item in observations
            )
            if not corroborated:
                for item in kp_support_observations:
                    item["outcome"] = "missing"
                    item["weight"] = 0.0
                    item["details"] = {
                        **item["details"],
                        "suppressedReason": "kp_sub_lord_requires_corroboration_from_dasha_varga_or_double_transit",
                    }

        # Jaimini Chara Dasha is a distinct rasi-based dasha system from Vimshottari.
        # Its activation logic operates on rasis, not planets, so it cannot reuse the
        # dasha block above: occupation is the rasi's own house position, aspect uses
        # Jaimini rasi drishti (not Parashari graha drishti), and karaka/lordship look
        # at the rasi's lord rather than a period-lord planet. Per the plan, this is
        # kept out of `observations`/support_score entirely (a separate, unvalidated
        # dasha system should not silently inflate the same additive score) and is
        # instead surfaced as a standalone per-candidate `charaDashaScore` used only
        # to compare which candidate each dasha system independently prefers.
        chara_levels: list[dict[str, Any]] = []
        for short_level, level in (
            ("md", "mahaRasi"),
            ("ad", "antarRasi"),
            ("pd", "pratyantarRasi"),
        ):
            sampled_rasis = [str(period.get(level) or "") for period in chara_sample_periods]
            distinct_rasis = sorted({rasi for rasi in sampled_rasis if rasi})
            if not (sampled_rasis and all(sampled_rasis) and len(distinct_rasis) == 1):
                chara_levels.append(
                    {
                        "level": short_level,
                        "outcome": "unavailable",
                        "reason": (
                            "period_changes_within_reported_date_range"
                            if len(distinct_rasis) > 1
                            else "period_rasi_unavailable"
                        ),
                    }
                )
                continue
            rasi_name = distinct_rasis[0]
            rasi_index = SIGNS.index(rasi_name)
            matched_dimensions: list[str] = []
            occupied_house = (rasi_index - lagna_index) % 12 + 1
            if occupied_house in relevant_houses:
                matched_dimensions.append("occupant")
            aspected_relevant_houses = sorted(
                relevant_houses
                & {
                    (aspected_rasi - lagna_index) % 12 + 1
                    for aspected_rasi in rasi_drishti(rasi_index)
                }
            )
            if aspected_relevant_houses:
                matched_dimensions.append("rasi_drishti")
            rasi_lord = SIGN_LORDS[rasi_index]
            if rasi_lord in karakas:
                matched_dimensions.append("karaka")
            ruled_houses = sorted(
                house
                for house in relevant_houses
                if SIGN_LORDS[(lagna_index + house - 1) % 12] == rasi_lord
            )
            if ruled_houses:
                matched_dimensions.append("lord")
            weight = RECTIFICATION_SCORING_POLICY.chara_dasha_level_weights[short_level]
            chara_levels.append(
                {
                    "level": short_level,
                    "rasi": rasi_name,
                    "outcome": "support" if matched_dimensions else "not_observed",
                    "weight": weight if matched_dimensions else 0.0,
                    "matchedDimensions": matched_dimensions,
                    "aspectedRelevantHouses": aspected_relevant_houses,
                    "ruledHouses": ruled_houses,
                }
            )
        chara_dasha_event_scores.append(
            {
                "eventId": event["eventId"],
                "role": event.get("role", "calibration"),
                "score": round(min(sum(item.get("weight", 0.0) for item in chara_levels), 1.0), 3),
                "levels": chara_levels,
            }
        )

        semantic_adjustment = _apply_semantic_adjustment(event)
        support_score = round(
            min(sum(item["weight"] for item in observations if item["outcome"] == "support"), 1),
            3,
        )
        contradiction_score = round(
            min(
                sum(item["weight"] for item in observations if item["outcome"] == "contradiction"),
                1,
            ),
            3,
        )
        score = round(max(-1.0, min(1.0, support_score - contradiction_score)), 3)
        selection_support_score = round(
            min(
                sum(
                    item["weight"]
                    for item in observations
                    if item["outcome"] == "support"
                    and item["component"] in RECTIFICATION_SELECTION_COMPONENTS
                ),
                1,
            ),
            3,
        )
        selection_contradiction_score = round(
            min(
                sum(
                    item["weight"]
                    for item in observations
                    if item["outcome"] == "contradiction"
                    and item["component"] in RECTIFICATION_SELECTION_COMPONENTS
                ),
                1,
            ),
            3,
        )
        selection_score = round(
            max(-1.0, min(1.0, selection_support_score - selection_contradiction_score)),
            3,
        )
        primary_method_components = sorted(
            {
                str(item["component"])
                for item in observations
                if item["outcome"] == "support"
                and item["component"] in {"dasha", "varga", "double_transit"}
            }
        )
        method_convergence_layers: list[str] = []
        if "dasha" in primary_method_components:
            method_convergence_layers.append("d1_period_activation")
        if "varga" in primary_method_components:
            method_convergence_layers.append("domain_varga_activation")
        if "double_transit" in primary_method_components:
            method_convergence_layers.append("double_transit")
        method_convergence_count = len(method_convergence_layers)
        method_convergence_met = (
            method_convergence_count
            >= RECTIFICATION_SCORING_POLICY.minimum_evidence_layers_per_event
        )
        rule_ids = [RECTIFICATION_RULE_ID]
        if any(
            item["component"] == "kp_sub_lord" and item["outcome"] == "support"
            for item in observations
        ):
            rule_ids.append(RECTIFICATION_KP_RULE_ID)
        evidence_scores.append(
            {
                "eventId": event["eventId"],
                "episodeId": event.get("episodeId") or event["eventId"],
                "eventFingerprint": event.get("eventFingerprint"),
                "eventSubtype": event.get("eventSubtype"),
                "semanticFacts": dict(semantic_facts) if isinstance(semantic_facts, dict) else None,
                "semanticAdjustment": semantic_adjustment,
                "role": event.get("role", "calibration"),
                "score": score,
                "supportScore": support_score,
                "contradictionScore": contradiction_score,
                "selectionScore": selection_score,
                "selectionSupportScore": selection_support_score,
                "selectionContradictionScore": selection_contradiction_score,
                "methodConvergenceComponents": primary_method_components,
                "methodConvergenceLayers": method_convergence_layers,
                "methodConvergenceCount": method_convergence_count,
                "methodConvergenceMet": method_convergence_met,
                "observations": observations,
                "ruleIds": rule_ids,
                "sourceIds": list(RECTIFICATION_SOURCE_IDS),
                "scoringPolicyId": RECTIFICATION_SCORING_POLICY.policy_id,
                "eventMappingId": RECTIFICATION_EVENT_MAPPING_ID,
                "eventTimezoneBasis": EVENT_TIMEZONE_BASIS,
                "explanation": (
                    f"{event.get('categoryLabel')}: Dasha lords {period_lords or ['unavailable']}; "
                    f"relevant vargas {relevant_vargas or ['none']}; "
                    "double-transit houses stable across the reported interval "
                    f"{stable_transit_houses}."
                    " Vimshottari eligibility checked against exact period boundaries;"
                    " slow-transit and diagnostic Chara checks sampled across the "
                    "unknown event-location UTC-offset envelope; "
                    f"display midpoint {event_local.isoformat()}."
                ),
            }
        )

    calibration = [
        item["selectionScore"] for item in evidence_scores if item["role"] == "calibration"
    ]
    holdout = [item["selectionScore"] for item in evidence_scores if item["role"] == "holdout"]
    vimshottari_dasha_calibration = [
        round(
            min(
                sum(
                    observation["weight"]
                    for observation in item["observations"]
                    if observation["component"] == "dasha" and observation["outcome"] == "support"
                ),
                1.0,
            ),
            3,
        )
        for item in evidence_scores
        if item["role"] == "calibration"
    ]
    convergent_calibration_event_count = sum(
        1
        for item in evidence_scores
        if item["role"] == "calibration" and item["methodConvergenceMet"]
    )
    chara_dasha_calibration = [
        item["score"] for item in chara_dasha_event_scores if item["role"] == "calibration"
    ]
    return {
        "evidenceScores": evidence_scores,
        "aggregateScore": round(sum(calibration) / len(calibration), 3) if calibration else None,
        "holdoutScore": round(sum(holdout) / len(holdout), 3) if holdout else None,
        "vimshottariDashaScore": (
            round(sum(vimshottari_dasha_calibration) / len(vimshottari_dasha_calibration), 3)
            if vimshottari_dasha_calibration
            else None
        ),
        "convergentCalibrationEventCount": convergent_calibration_event_count,
        "scoringPolicy": RECTIFICATION_SCORING_POLICY.policy_id,
        "charaDashaScore": (
            round(sum(chara_dasha_calibration) / len(chara_dasha_calibration), 3)
            if chara_dasha_calibration and chara_dasha_periods is not None
            else None
        ),
        "charaDashaDiagnostics": chara_dasha_event_scores,
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
    event_intervals: list[tuple[datetime, datetime]] = []
    for event in events:
        start, end = _event_interval_bounds(event)
        event_intervals.append(event_utc_envelope(start, end))
    current_moments: list[datetime] = []
    if reference_moment is not None:
        if reference_moment.tzinfo is None or reference_moment.utcoffset() is None:
            raise ValueError("rectification reference moment must be timezone-aware")
        current_moments.append(reference_moment.astimezone(timezone.utc))
    from app.calculator.dasha_pyjhora import (
        calculate_dasha_lords_at,
        calculate_dasha_lords_for_intervals,
    )

    birth_args = (
        localized_birth.year,
        localized_birth.month,
        localized_birth.day,
        localized_birth.hour,
        localized_birth.minute,
        latitude,
        longitude,
        localized_birth.utcoffset().total_seconds() / 3600.0,
    )
    periods = calculate_dasha_lords_for_intervals(
        *birth_args,
        event_intervals,
        birth_second=localized_birth.second,
    )
    if len(periods) != len(events):
        raise RuntimeError(
            "Vimshottari event fingerprint lookup returned an incomplete interval result set"
        )
    event_fingerprint = [
        "/".join(
            str(period.get(level) or "unavailable")
            for level in ("mahadasha", "antardasha", "pratyantardasha")
        )
        for period in periods
    ]
    current_dasha = None
    if current_moments:
        current_period = calculate_dasha_lords_at(
            *birth_args,
            current_moments,
            birth_second=localized_birth.second,
        )[0]
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


def _localize_event_interval(
    start: datetime,
    end: datetime,
    local_timezone,
) -> tuple[datetime, datetime]:
    """Map a user-supplied civil interval to every real instant it represents."""

    localized_start = _localize_civil_boundary(start, local_timezone, direction="forward")
    localized_end = _localize_civil_boundary(end, local_timezone, direction="backward")
    start_utc = localized_start.astimezone(timezone.utc)
    end_utc = localized_end.astimezone(timezone.utc)
    if start_utc > end_utc:
        raise ValueError(
            "life-event date does not contain a valid civil instant in the selected timezone"
        )
    return start_utc, end_utc


def _localize_event_sample(
    value: datetime,
    local_timezone,
    *,
    index: int,
    total: int,
) -> datetime:
    direction = "backward" if total > 1 and index == total - 1 else "forward"
    return _localize_civil_boundary(value, local_timezone, direction=direction).astimezone(
        timezone.utc
    )


def _localize_civil_boundary(
    value: datetime,
    local_timezone,
    *,
    direction: str,
) -> datetime:
    """Resolve DST gaps/folds without dropping a broad dated event."""

    try:
        return local_timezone.localize(value, is_dst=None)
    except pytz.AmbiguousTimeError:
        alternatives = [
            local_timezone.localize(value, is_dst=True),
            local_timezone.localize(value, is_dst=False),
        ]
        key = lambda item: item.astimezone(timezone.utc)
        return min(alternatives, key=key) if direction == "forward" else max(alternatives, key=key)
    except pytz.NonExistentTimeError:
        step = timedelta(minutes=1 if direction == "forward" else -1)
        probe = value
        for _ in range(6 * 60):
            probe += step
            try:
                return local_timezone.localize(probe, is_dst=None)
            except pytz.AmbiguousTimeError:
                alternatives = [
                    local_timezone.localize(probe, is_dst=True),
                    local_timezone.localize(probe, is_dst=False),
                ]
                key = lambda item: item.astimezone(timezone.utc)
                return (
                    min(alternatives, key=key)
                    if direction == "forward"
                    else max(alternatives, key=key)
                )
            except pytz.NonExistentTimeError:
                continue
        raise ValueError(
            "life-event civil time cannot be resolved inside the selected timezone"
        ) from None


def _event_midpoint(event: dict[str, Any]) -> datetime:
    raw = str(event.get("date") or "")
    if re.fullmatch(r"\d{4}-\d{2}", raw):
        year, month = (int(value) for value in raw.split("-"))
        return datetime(year, month, 15, 12)
    if re.fullmatch(r"\d{4}", raw):
        return datetime(int(raw), 7, 1, 12)
    return datetime.fromisoformat(raw).replace(hour=12, minute=0, second=0, microsecond=0)


def _event_interval_bounds(event: dict[str, Any]) -> tuple[datetime, datetime]:
    """Return the full local civil interval represented by a partial event date."""

    raw = str(event.get("date") or "")
    if re.fullmatch(r"\d{4}-\d{2}", raw):
        year, month = (int(value) for value in raw.split("-"))
        return (
            datetime(year, month, 1),
            datetime(year, month, monthrange(year, month)[1], 23, 59, 59),
        )
    if re.fullmatch(r"\d{4}", raw):
        year = int(raw)
        return datetime(year, 1, 1), datetime(year, 12, 31, 23, 59, 59)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        day = datetime.fromisoformat(raw)
        return day, day.replace(hour=23, minute=59, second=59)
    midpoint = _event_midpoint(event)
    return midpoint, midpoint


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
                "eventSubtype": event.get("eventSubtype"),
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
    rules = rectification_rules_for(category)
    date_value = (
        f"{year:04d}-{month:02d}-{day:02d}"
        if day is not None
        else f"{year:04d}-{month:02d}"
        if month is not None
        else f"{year:04d}"
    )
    date_precision = "day" if day is not None else "month" if month is not None else "year"
    # The raw ledger omits subtype by design. Use the text-only key for the
    # semantic join, then replace it with the full identity after attachment.
    event_fingerprint = _event_match_fingerprint(date_value, category, line)
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
            "sadeSatiRelevant": bool(rules.get("sadeSatiRelevant")),
        },
    }


def _apply_event_rules(event: dict[str, Any], *, event_subtype: str | None) -> None:
    rules = rectification_rules_for(str(event.get("category") or "unknown"), event_subtype)
    event["categoryLabel"] = rules["label"]
    event["rectificationRules"] = {
        "houses": rules["houses"],
        "vargas": rules["vargas"],
        "karakas": rules["karakas"],
        "fields": rules["fields"],
        "sadeSatiRelevant": bool(rules.get("sadeSatiRelevant")),
    }


def _event_match_fingerprint(date_value: str, category: str, description: str) -> str:
    """Join the text ledger to structured evidence before subtype attachment."""

    normalized_description = _clean_event_description(description, date_value, category)
    payload = "|".join(
        (
            " ".join(str(date_value).split()),
            str(category).strip().casefold(),
            normalized_description,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _event_fingerprint(
    date_value: str,
    category: str,
    description: str,
    event_subtype: str | None = None,
) -> str:
    """Identify a scored event, including the backend-bound subtype."""

    match_fingerprint = _event_match_fingerprint(date_value, category, description)
    payload = "|".join((match_fingerprint, str(event_subtype or "").strip().casefold()))
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


def _assign_life_episodes(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group overlapping reported date intervals into independent evidence units.

    Partial dates represent the whole civil interval the user supplied. Treating two
    overlapping intervals as separate votes would allow one real-world period to meet
    the evidence minimum more than once. The earliest submitted event remains the
    scored primary; later events are retained as corroborating context.
    """

    episodes: list[dict[str, Any]] = []
    ordered = sorted(events, key=lambda event: int(event.get("intakeSequence") or 0))
    for event in ordered:
        start, end = _event_interval_bounds(event)
        overlapping = [
            episode for episode in episodes if start <= episode["end"] and end >= episode["start"]
        ]
        if not overlapping:
            episodes.append({"start": start, "end": end, "events": [event]})
            continue

        # Existing primaries and their date boundaries are immutable. A later,
        # broader partial date may corroborate the earliest overlapping episode,
        # but it cannot bridge two earlier episodes and retroactively move holdout.
        overlapping[0]["events"].append(event)

    primaries: list[dict[str, Any]] = []
    for episode in sorted(
        episodes,
        key=lambda item: min(int(event.get("intakeSequence") or 0) for event in item["events"]),
    ):
        members = episode["events"]
        primary = members[0]
        fingerprint = str(primary.get("eventFingerprint") or primary.get("eventId") or "")
        episode_id = f"episode_{fingerprint[:16]}"
        event_ids = [str(member.get("eventId") or "") for member in members]
        categories = sorted({str(member.get("category") or "unknown") for member in members})
        for member in members:
            member["episodeId"] = episode_id
            member["episodePrimaryEventId"] = str(primary.get("eventId") or "")
            member["episodeEventIds"] = event_ids
            member["episodeCategories"] = categories
            member["episodeEventCount"] = len(members)
            member["episodeRelation"] = "primary" if member is primary else "corroborating"
        primary["episodeMembers"] = members
        primaries.append(primary)
    return primaries


def _select_holdout_event(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Reserve the third independent episode before it can enter calibration."""

    return sorted(events, key=lambda event: int(event.get("intakeSequence") or 0))[2]


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
