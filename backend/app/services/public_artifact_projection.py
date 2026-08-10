from __future__ import annotations

import copy
import json
from typing import Any, Callable


PUBLIC_PROJECTED_ARTIFACTS = frozenset(
    {
        "birth_input_context.json",
        "sensitivity_scan.json",
        "chart_record.json",
        "chart_rectification_state.json",
    }
)


def project_public_artifact(path: str, content: str) -> str | None:
    """Return a fail-closed client projection for a private runtime artifact."""

    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    projectors: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
        "birth_input_context.json": _public_birth_input_context,
        "sensitivity_scan.json": _public_sensitivity_scan,
        "chart_record.json": _public_chart_record,
        "chart_rectification_state.json": _public_rectification_state,
    }
    projector = projectors.get(path)
    if projector is None:
        return None
    return json.dumps(projector(payload), ensure_ascii=False, indent=2) + "\n"


def _public_birth_input_context(payload: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    result.pop("lifeEvents", None)
    result.pop("lifeEventSemantics", None)
    return result


def _public_sensitivity_scan(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _mapping(payload.get("summary"))
    readiness = _mapping(payload.get("reportReadiness"))
    return {
        "schemaVersion": "vedicdust-sensitivity-public/1.0.0",
        "sourceSchemaVersion": payload.get("schemaVersion"),
        "summary": _copy_keys(
            summary,
            (
                "riskLevel",
                "riskFactors",
                "rectificationAxes",
                "placeRectificationAllowed",
                "placeRectificationPolicy",
            ),
        ),
        "reportReadiness": _copy_keys(
            readiness,
            (
                "mode",
                "scope",
                "prevalidationRequired",
                "coreAllowedWithoutRectification",
                "stableBoundedWindow",
                "rectificationAxes",
                "placeRectificationAllowed",
                "placeRectificationPolicy",
                "blockingFactors",
            ),
        ),
    }


def _public_chart_record(payload: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    # Candidate intervals, event roles, round scores, and boundary fingerprints
    # are backend evidence. Public rectification progress has its own projection.
    result.pop("rectification", None)
    result.pop("sensitivityBoundaries", None)
    return result


def _public_rectification_state(payload: dict[str, Any]) -> dict[str, Any]:
    result = _copy_keys(
        payload,
        (
            "revision",
            "generatedAt",
            "updatedAt",
            "status",
            "riskLevel",
            "reportReadinessMode",
            "selectionConfidence",
            "methodMaturity",
            "validationStatus",
            "availableRectificationCategories",
        ),
    )
    result["schemaVersion"] = "vedicdust-rectification-public/1.0.0"
    result["sourceSchemaVersion"] = payload.get("schemaVersion")

    equivalent_ids = payload.get("equivalentCandidateIds")
    result["equivalentCandidateCount"] = (
        len(equivalent_ids) if isinstance(equivalent_ids, list) else 0
    )

    result["reportGate"] = _copy_keys(
        _mapping(payload.get("reportGate")),
        ("fullReportAllowed", "reason", "reportScope", "nextStep"),
    )
    result["rectificationPlan"] = _copy_keys(
        _mapping(payload.get("rectificationPlan")),
        ("action", "eventCollectionRequired"),
    )
    result["selectionEvidence"] = _copy_keys(
        _mapping(payload.get("selectionEvidence")),
        (
            "calibrationEventCount",
            "calibrationEpisodeCount",
            "calibrationCategoryCount",
            "holdoutEventCount",
            "holdoutEpisodeCount",
            "submittedEventCount",
            "correlatedEventCount",
        ),
    )

    ledger = _mapping(payload.get("lifeEventLedger"))
    events = ledger.get("events")
    result["lifeEventLedger"] = {
        **_copy_keys(
            ledger,
            (
                "eligibleEventCount",
                "independentEpisodeCount",
                "correlatedEventCount",
            ),
        ),
        "events": [
            _copy_keys(
                event,
                ("date", "datePrecision", "category", "eventSubtype", "description"),
            )
            for event in events or []
            if isinstance(event, dict) and str(event.get("role") or "") != "context_only"
        ],
    }

    rounds = payload.get("rectificationRounds")
    result["rectificationRounds"] = [
        {
            "round": item.get("round"),
            "decision": _copy_keys(_mapping(item.get("decision")), ("outcome",)),
        }
        for item in rounds or []
        if isinstance(item, dict)
    ]
    result["activeChartRevision"] = _copy_keys(
        _mapping(payload.get("activeChartRevision")),
        ("revision", "source"),
    )

    conclusion = payload.get("rectificationConclusion")
    if isinstance(conclusion, dict):
        result["rectificationConclusion"] = _public_rectification_conclusion(conclusion)
    return result


def _public_rectification_conclusion(payload: dict[str, Any]) -> dict[str, Any]:
    result = _copy_keys(payload, ("schemaVersion", "status", "chartRevision", "confidence"))
    nested_fields = {
        "correctedBirthTime": (
            "localDate",
            "localTime",
            "timezoneId",
            "utcOffsetSeconds",
            "displayPrecision",
        ),
        "selectedInterval": ("start", "end", "boundarySemantics"),
        "methodAssurance": (
            "methodMaturity",
            "validationStatus",
            "independentProfessionalReviewCompleted",
        ),
        "evidenceSummary": (
            "calibrationEventCount",
            "calibrationEpisodeCount",
            "calibrationCategoryCount",
            "holdoutEventCount",
            "holdoutEpisodeCount",
            "correlatedEventCount",
            "holdoutResult",
            "method",
        ),
        "generation": ("source", "postSelectionOnly", "usedForSelection", "disclaimer"),
    }
    for field, keys in nested_fields.items():
        value = payload.get(field)
        if isinstance(value, dict):
            result[field] = _copy_keys(value, keys)

    highlights = payload.get("evidenceHighlights")
    if isinstance(highlights, list):
        result["evidenceHighlights"] = [
            _copy_keys(
                item,
                (
                    "date",
                    "datePrecision",
                    "category",
                    "eventSubtype",
                    "description",
                    "role",
                    "result",
                    "usedForSelection",
                ),
            )
            for item in highlights
            if isinstance(item, dict)
        ]

    examples = payload.get("examples")
    if isinstance(examples, list):
        result["examples"] = [
            _copy_keys(
                item,
                (
                    "exampleId",
                    "startDate",
                    "endDate",
                    "category",
                    "prompt",
                    "description",
                    "source",
                    "usedForSelection",
                ),
            )
            for item in examples
            if isinstance(item, dict)
        ]

    confirmation = payload.get("confirmation")
    if isinstance(confirmation, dict):
        result["confirmation"] = _copy_keys(confirmation, ("status",))
    return result


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _copy_keys(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: copy.deepcopy(payload[key]) for key in keys if key in payload}
