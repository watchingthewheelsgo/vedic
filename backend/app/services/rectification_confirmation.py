from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
import re
from typing import Any

from app.schemas import BirthInput


CONFIRMATION_SCHEMA_VERSION = "vedicdust-rectification-conclusion/1.0.0"
MAX_CONFIRMATION_EXAMPLES = 2

# These are prompts for a post-selection user check, not evidence used to rank
# candidates. Sensitive topics are intentionally excluded from this optional
# post-selection step.
CONFIRMATION_CATEGORIES = {
    "education",
    "career",
    "relationship",
    "relocation",
    "child",
    "family",
    "finance",
    "property",
    "spiritual",
}
_DATE_PATTERN = re.compile(r"^(?:19|20)\d{2}(?:-(?:0[1-9]|1[0-2]))?(?:-(?:0[1-9]|[12]\d|3[01]))?$")
_FORBIDDEN_PROMPT_TERMS = re.compile(
    r"(?:dasha|varga|lagna|nakshatra|planet|house|chart|candidate|astrology|占星|星盘|行星|宫位|大运|候选盘)",
    re.IGNORECASE,
)


def build_rectification_conclusion(
    state: dict[str, Any],
    *,
    rectified_input: BirthInput,
    chart_revision: int,
) -> dict[str, Any]:
    """Create the user-facing checkpoint after deterministic selection.

    The fallback examples deliberately come from the submitted ledger. They
    are honest when the optional LLM-generated retrospective prompts are not
    available, and they never pretend that a repeated user fact is a new
    prediction.
    """

    selected_id = str(state.get("selectedCandidateId") or "")
    candidate = next(
        (
            item
            for item in state.get("candidates") or []
            if isinstance(item, dict) and str(item.get("candidateId") or "") == selected_id
        ),
        {},
    )
    interval = candidate.get("interval") if isinstance(candidate.get("interval"), dict) else {}
    timezone_id = _timezone_id(candidate)
    examples = _submitted_examples(state)
    evidence = state.get("selectionEvidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    return {
        "schemaVersion": CONFIRMATION_SCHEMA_VERSION,
        "status": "ready_for_confirmation",
        "chartRevision": chart_revision,
        "candidateId": selected_id,
        "confidence": str(state.get("selectionConfidence") or "medium"),
        "correctedBirthTime": {
            "localDate": rectified_input.birth_date,
            "localTime": rectified_input.birth_time,
            "timezoneId": timezone_id,
            "utcOffsetSeconds": rectified_input.utc_offset_seconds,
            "displayPrecision": "representative_minute_with_bounded_interval",
        },
        "selectedInterval": interval,
        "evidenceSummary": {
            "calibrationEventCount": int(evidence.get("calibrationEventCount") or 0),
            "calibrationCategoryCount": int(evidence.get("calibrationCategoryCount") or 0),
            "holdoutEventCount": int(evidence.get("holdoutEventCount") or 0),
            "holdoutResult": str(state.get("holdoutResult") or "not_run"),
            "selectionPolicyId": state.get("selectionPolicyId"),
            "method": "dated_life_events_plus_reserved_holdout",
        },
        "examples": examples,
        "generation": {
            "source": "deterministic_submitted_evidence",
            "postSelectionOnly": False,
            "usedForSelection": True,
            "disclaimer": (
                "Submitted events are shown as an honest fallback. They are not new chart-derived facts."
            ),
        },
        "confirmation": {"status": "pending", "responses": []},
    }


def replace_with_agent_examples(
    conclusion: dict[str, Any],
    payload: dict[str, Any],
    *,
    birth_date: str,
    excluded_dates: set[str] | None = None,
    timing_periods: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate and install optional retrospective prompts from the Agent.

    These prompts are explicitly post-selection. They are not fed back into
    candidate scoring, and the validator rejects chart terminology or exact
    certainty language before anything reaches the user.
    """

    raw_examples = payload.get("examples")
    if not isinstance(raw_examples, list) or not raw_examples:
        raise ValueError("rectification confirmation must contain examples")
    birth_start, _ = _date_bounds(birth_date)
    today = date.today()
    excluded = excluded_dates or set()
    allowed_periods = _normalized_timing_periods(timing_periods)
    allowed_period_ids = {item[0] for item in allowed_periods}
    examples: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_examples[:MAX_CONFIRMATION_EXAMPLES], start=1):
        if not isinstance(raw, dict):
            raise ValueError("rectification confirmation example must be an object")
        category = str(raw.get("category") or "").strip()
        start_raw = str(raw.get("startDate") or "").strip()
        end_raw = str(raw.get("endDate") or start_raw).strip()
        prompt = str(raw.get("prompt") or "").strip()
        rationale = str(raw.get("rationale") or "").strip()
        raw_period_ids = raw.get("supportingPeriodIds")
        if not isinstance(raw_period_ids, list):
            raise ValueError("rectification confirmation must cite timing periods")
        supporting_period_ids = [
            str(value).strip() for value in raw_period_ids if str(value).strip()
        ]
        if not supporting_period_ids or not set(supporting_period_ids) <= allowed_period_ids:
            raise ValueError("rectification confirmation cited an unknown timing period")
        if category not in CONFIRMATION_CATEGORIES:
            raise ValueError("rectification confirmation used an unsupported category")
        if not _DATE_PATTERN.fullmatch(start_raw) or not _DATE_PATTERN.fullmatch(end_raw):
            raise ValueError("rectification confirmation used an invalid date window")
        start, _ = _date_bounds(start_raw)
        _, end = _date_bounds(end_raw)
        if start > end or start < birth_start or end > today:
            raise ValueError(
                "rectification confirmation date window is outside the subject lifetime"
            )
        cited_periods = [
            period for period in allowed_periods if period[0] in set(supporting_period_ids)
        ]
        if not cited_periods or not any(
            start <= period[2] and period[1] <= end for period in cited_periods
        ):
            raise ValueError("rectification confirmation date is outside its cited timing period")
        if any(_date_overlaps(start_raw, existing) for existing in excluded):
            raise ValueError("rectification confirmation reused a submitted event window")
        if len(prompt) < 12 or len(prompt) > 260 or _FORBIDDEN_PROMPT_TERMS.search(prompt):
            raise ValueError("rectification confirmation prompt is not consumer-safe")
        if len(rationale) > 260:
            raise ValueError("rectification confirmation rationale is too long")
        examples.append(
            {
                "exampleId": f"chart-check-{index}",
                "startDate": start_raw,
                "endDate": end_raw,
                "category": category,
                "prompt": prompt,
                "rationale": rationale,
                "supportingPeriodIds": supporting_period_ids,
                "source": "post_selection_agent",
                "usedForSelection": False,
            }
        )
    if not examples:
        raise ValueError("rectification confirmation did not produce a usable example")
    updated = dict(conclusion)
    updated["examples"] = examples
    updated["generation"] = {
        "source": "post_selection_agent",
        "postSelectionOnly": True,
        "usedForSelection": False,
        "disclaimer": (
            "These are cautious retrospective prompts for a user check. They do not select or alter the birth time."
        ),
    }
    return updated


def _submitted_examples(state: dict[str, Any]) -> list[dict[str, Any]]:
    ledger = state.get("lifeEventLedger")
    events = ledger.get("events") if isinstance(ledger, dict) else []
    if not isinstance(events, list):
        return []
    ordered = sorted(
        (item for item in events if isinstance(item, dict)),
        key=lambda item: (0 if item.get("role") == "holdout" else 1, str(item.get("date") or "")),
    )
    examples: list[dict[str, Any]] = []
    for event in ordered[:MAX_CONFIRMATION_EXAMPLES]:
        event_id = str(event.get("eventId") or "event")
        description = str(event.get("description") or "").strip()
        event_date = str(event.get("date") or "").strip()
        category = str(event.get("category") or "past event").strip()
        if not event_date:
            continue
        prompt = description or (
            f"Please confirm that a significant {category} change was recorded around this time."
        )
        examples.append(
            {
                "exampleId": f"submitted-{event_id}",
                "startDate": event_date,
                "endDate": event_date,
                "category": category,
                "prompt": prompt,
                "description": description,
                "source": "submitted_evidence",
                "usedForSelection": True,
            }
        )
    return examples


def agent_snapshot(chart_record: dict[str, Any]) -> dict[str, Any]:
    """Expose only finalized-chart material needed for retrospective prompts."""

    canonical = chart_record.get("canonicalMoment")
    canonical = canonical if isinstance(canonical, dict) else {}
    raw_periods = chart_record.get("timingPeriods")
    periods = raw_periods if isinstance(raw_periods, list) else []
    raw_facts = chart_record.get("facts")
    facts = raw_facts if isinstance(raw_facts, list) else []
    birth_assertion = chart_record.get("birthAssertion")
    birth_assertion = birth_assertion if isinstance(birth_assertion, dict) else {}
    return {
        "birthDate": str(birth_assertion.get("localDate") or ""),
        "canonicalMoment": {
            "localDateTime": canonical.get("localDateTime"),
            "timezoneId": canonical.get("timezoneId"),
        },
        "timingPeriods": _timing_period_snapshot(periods),
        "facts": facts[:80],
    }


def _timing_period_snapshot(periods: list[Any]) -> list[dict[str, Any]]:
    """Keep all MD/AD windows while omitting the much larger PD expansion."""

    snapshot: list[dict[str, Any]] = []
    for period in periods:
        if not isinstance(period, dict) or period.get("level") not in {
            "mahadasha",
            "antardasha",
        }:
            continue
        interval = period.get("interval")
        if not isinstance(interval, dict):
            continue
        period_id = str(period.get("periodId") or period.get("period_id") or "").strip()
        start = str(interval.get("start") or "").strip()
        end = str(interval.get("end") or "").strip()
        if not period_id or not start or not end:
            continue
        snapshot.append(
            {
                "periodId": period_id,
                "level": period.get("level"),
                "lords": [str(lord) for lord in period.get("lords") or []],
                "start": start,
                "end": end,
            }
        )
    return snapshot


def _normalized_timing_periods(
    periods: list[dict[str, Any]] | None,
) -> list[tuple[str, date, date]]:
    normalized: list[tuple[str, date, date]] = []
    for period in periods or []:
        if not isinstance(period, dict):
            continue
        period_id = str(period.get("periodId") or period.get("period_id") or "").strip()
        start_raw = str(period.get("start") or "").strip()
        end_raw = str(period.get("end") or "").strip()
        if not period_id or not start_raw or not end_raw:
            continue
        try:
            start = datetime.fromisoformat(start_raw.replace("Z", "+00:00")).date()
            end = datetime.fromisoformat(end_raw.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if start <= end:
            normalized.append((period_id, start, end))
    return normalized


def _timezone_id(candidate: dict[str, Any]) -> str | None:
    for key in ("scoringLocation", "placeHypothesis"):
        value = candidate.get(key)
        if isinstance(value, dict):
            timezone_id = str(value.get("timezoneId") or value.get("timezone") or "").strip()
            if timezone_id:
                return timezone_id
    return None


def _date_bounds(value: str) -> tuple[date, date]:
    parts = value.split("-")
    year = int(parts[0])
    if len(parts) == 1:
        return date(year, 1, 1), date(year, 12, 31)
    month = int(parts[1])
    if len(parts) == 2:
        return date(year, month, 1), date(year, month, monthrange(year, month)[1])
    current = date(year, month, int(parts[2]))
    return current, current


def _date_overlaps(value: str, other: str) -> bool:
    left_start, left_end = _date_bounds(value)
    right_start, right_end = _date_bounds(other)
    return left_start <= right_end and right_start <= left_end
