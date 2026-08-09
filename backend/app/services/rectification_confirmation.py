from __future__ import annotations

from typing import Any

from app.schemas import BirthInput


CONFIRMATION_SCHEMA_VERSION = "vedicdust-rectification-conclusion/1.1.0"


def build_rectification_conclusion(
    state: dict[str, Any],
    *,
    rectified_input: BirthInput,
    chart_revision: int,
) -> dict[str, Any]:
    """Create the user-facing checkpoint after deterministic selection.

    The checkpoint asks only for acknowledgement of the bounded corrected time.
    It never invents a chart-derived life event or presents submitted evidence
    as independent validation.
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
    examples = [_input_review_example(rectified_input, interval)]
    evidence_highlights = _evidence_highlights(state, candidate)
    evidence = state.get("selectionEvidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    method_maturity = str(state.get("methodMaturity") or "product_hypothesis")
    validation_status = str(state.get("validationStatus") or "internal_regression_only")
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
        "selectedInterval": {
            **interval,
            "boundarySemantics": "start_inclusive_end_exclusive",
        },
        "methodAssurance": {
            "methodMaturity": method_maturity,
            "validationStatus": validation_status,
            "independentProfessionalReviewCompleted": (
                method_maturity == "professionally_validated"
                and validation_status == "independent_professional_review"
            ),
        },
        "evidenceSummary": {
            "calibrationEventCount": int(evidence.get("calibrationEventCount") or 0),
            "calibrationEpisodeCount": int(
                evidence.get("calibrationEpisodeCount")
                or evidence.get("calibrationEventCount")
                or 0
            ),
            "calibrationCategoryCount": int(evidence.get("calibrationCategoryCount") or 0),
            "holdoutEventCount": int(evidence.get("holdoutEventCount") or 0),
            "holdoutEpisodeCount": int(
                evidence.get("holdoutEpisodeCount") or evidence.get("holdoutEventCount") or 0
            ),
            "correlatedEventCount": int(evidence.get("correlatedEventCount") or 0),
            "holdoutResult": str(state.get("holdoutResult") or "not_run"),
            "selectionPolicyId": state.get("selectionPolicyId"),
            "method": "dated_life_events_plus_reserved_holdout",
        },
        "evidenceHighlights": evidence_highlights,
        "examples": examples,
        "generation": {
            "source": "deterministic_input_review",
            "postSelectionOnly": True,
            "usedForSelection": False,
            "disclaimer": (
                "This fallback only asks the user to review the bounded corrected time. "
                "It is not independent validation and does not raise confidence."
            ),
        },
        "confirmation": {"status": "pending", "responses": []},
    }


def _evidence_highlights(
    state: dict[str, Any],
    selected_candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    """Explain selection with submitted facts without creating a second vote."""

    ledger = state.get("lifeEventLedger")
    ledger = ledger if isinstance(ledger, dict) else {}
    events = [item for item in ledger.get("events") or [] if isinstance(item, dict)]
    score_by_event = {
        str(item.get("eventId") or ""): item
        for item in selected_candidate.get("evidenceScores") or []
        if isinstance(item, dict) and item.get("eventId")
    }

    calibration = [event for event in events if event.get("role") == "calibration"]
    candidates = [item for item in state.get("candidates") or [] if isinstance(item, dict)]
    calibration.sort(
        key=lambda event: (
            _event_score_spread(candidates, str(event.get("eventId") or "")),
            _selection_score(score_by_event.get(str(event.get("eventId") or ""), {}), -1.0),
            -int(event.get("intakeSequence") or 0),
        ),
        reverse=True,
    )
    holdout = [event for event in events if event.get("role") == "holdout"]
    chosen = [*(calibration[:1]), *(holdout[:1])]
    highlights: list[dict[str, Any]] = []
    for event in chosen:
        role = str(event.get("role") or "calibration")
        highlights.append(
            {
                "date": event.get("date"),
                "datePrecision": event.get("datePrecision"),
                "category": event.get("category"),
                "eventSubtype": event.get("eventSubtype"),
                "description": event.get("description"),
                "role": role,
                "result": (
                    "passed_reserved_cross_check"
                    if role == "holdout" and state.get("holdoutResult") == "passed"
                    else "used_for_candidate_comparison"
                ),
                "usedForSelection": role == "calibration",
            }
        )
    return highlights


def _event_score_spread(candidates: list[dict[str, Any]], event_id: str) -> float:
    scores: list[float] = []
    seen_classes: set[str] = set()
    for candidate in candidates:
        class_id = str(candidate.get("equivalenceClassId") or candidate.get("candidateId") or "")
        if class_id in seen_classes:
            continue
        seen_classes.add(class_id)
        score = next(
            (
                _selection_score(item)
                for item in candidate.get("evidenceScores") or []
                if isinstance(item, dict) and str(item.get("eventId") or "") == event_id
            ),
            None,
        )
        if score is not None:
            scores.append(float(score))
    return max(scores) - min(scores) if len(scores) > 1 else 0.0


def _selection_score(evidence: dict[str, Any], default: float | None = None) -> float | None:
    value = evidence.get("selectionScore")
    if value is None:
        value = evidence.get("score")
    return float(value) if value is not None else default


def _input_review_example(
    rectified_input: BirthInput,
    interval: dict[str, Any],
) -> dict[str, Any]:
    locale = rectified_input.locale
    start = str(interval.get("start") or "")
    end = str(interval.get("end") or "")
    bounded = _bounded_interval_text(locale, start, end, rectified_input.birth_time)
    prompt = (
        f"请确认系统保留的出生时间范围是否可以接受：{bounded}。这只是结果确认，不是新的验前事。"
        if locale == "zh"
        else f"補正後に残った出生時刻の範囲を確認してください：{bounded}。これは新しい検証事例ではありません。"
        if locale == "ja"
        else (
            f"Please review the remaining corrected birth-time range: {bounded}. "
            "This is an acknowledgement, not a new validation event."
        )
    )
    return {
        "exampleId": "corrected-time-review",
        "startDate": rectified_input.birth_date,
        "endDate": rectified_input.birth_date,
        "category": "input_review",
        "prompt": prompt,
        "description": prompt,
        "source": "deterministic_input_review",
        "usedForSelection": False,
    }


def _bounded_interval_text(locale: str, start: str, end: str, fallback: str) -> str:
    if not start or not end:
        return fallback
    if locale == "zh":
        return f"{start} 至 {end} 前"
    if locale == "ja":
        return f"{start} 以上、{end} 未満"
    return f"{start} to before {end}"


def _timezone_id(candidate: dict[str, Any]) -> str | None:
    for key in ("scoringLocation", "placeHypothesis"):
        value = candidate.get(key)
        if isinstance(value, dict):
            timezone_id = str(value.get("timezoneId") or value.get("timezone") or "").strip()
            if timezone_id:
                return timezone_id
    return None
