from __future__ import annotations

import copy
import re
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from app.schemas import BirthInput, ReaderRelationship
from app.services.life_event_rectification import build_life_event_focus
from app.vedicdust.rectification_policy import (
    RECTIFICATION_EVENT_MAPPING_ID,
    RECTIFICATION_HOLDOUT_POLICY_ID,
    RECTIFICATION_METHOD_MATURITY,
    RECTIFICATION_SCORING_POLICY,
    RECTIFICATION_SOURCE_IDS,
    RECTIFICATION_VALIDATION_STATUS,
)


class ChartRectificationService:
    """Keeps chart-candidate correction behind one small interface."""

    schema_version = "chart-rectification-state/v1"

    def initial_state(
        self,
        birth_input_context: dict[str, Any],
        sensitivity_scan: dict[str, Any],
    ) -> dict[str, Any]:
        candidates = self._candidate_groups(sensitivity_scan)
        base_candidate_id = self._base_candidate_id(candidates)
        readiness = self._report_readiness(sensitivity_scan)
        scan_summary = self._scan_summary(sensitivity_scan)
        risk_level = str(scan_summary.get("riskLevel") or "unknown")
        mode = str(readiness.get("mode") or "unknown")
        constraints = birth_input_context.get("constraints") or {}
        place_context = birth_input_context.get("place") or {}
        place_rectification_allowed = constraints.get(
            "placeRectificationAllowed",
            self._place_rectification_allowed(place_context)
            if isinstance(place_context, dict)
            else True,
        )
        rectification_axes = constraints.get(
            "rectificationAxes",
            ["time", "place"] if place_rectification_allowed else ["time"],
        )
        raw_life_event_ledger = birth_input_context.get("lifeEvents")
        life_event_ledger_supplied = isinstance(raw_life_event_ledger, dict)
        life_event_ledger = raw_life_event_ledger
        if not isinstance(life_event_ledger, dict):
            life_event_ledger = {}

        scored_candidates = self._normalized_candidates(candidates)
        scan_errors = copy.deepcopy(scan_summary.get("scanErrors") or [])
        candidate_scoring_errors = copy.deepcopy(scan_summary.get("candidateScoringErrors") or [])

        if scan_errors:
            status = "input_resolution_required"
            gate_reason = (
                "Part of the reported search window could not be resolved as a valid civil "
                "time or place. Narrow the input or resolve the timezone ambiguity first."
            )
            full_report_allowed = False
        elif candidate_scoring_errors:
            status = "calculation_failed"
            gate_reason = (
                "One or more candidate charts could not be scored consistently. Retry the "
                "deterministic calculation before asking rectification questions."
            )
            full_report_allowed = False
        elif mode == "rectification_required" and (
            not life_event_ledger_supplied
            or life_event_ledger.get("eventCollectionRequired") is True
        ):
            status = "collecting_evidence"
            gate_reason = (
                "Dated life events are required before chart candidates can be compared. "
                "Generic traits cannot select a birth time."
            )
            full_report_allowed = False
        elif mode == "rectification_required" and len(candidates) > 1:
            status = "comparing_candidates"
            gate_reason = (
                "Chart-changing candidates require deterministic calibration ranking and a "
                "reserved-event check. Reader testimony cannot select a candidate."
            )
            full_report_allowed = False
        elif mode == "rectification_required":
            status = "not_required"
            gate_reason = (
                "The bounded sensitivity scan found one stable chart fingerprint across the "
                "reported time and place window. The exact birth moment remains uncertain, so "
                "the report must retain that interval and use only scan-stable evidence."
            )
            full_report_allowed = True
        else:
            status = "not_required"
            gate_reason = "Sensitivity scan does not require candidate rectification."
            full_report_allowed = True

        state = {
            "schemaVersion": self.schema_version,
            "revision": 0,
            "generatedAt": self._now(),
            "updatedAt": self._now(),
            "status": status,
            "riskLevel": risk_level,
            "reportReadinessMode": mode,
            "baseCandidateId": base_candidate_id,
            "activeCandidateId": base_candidate_id,
            "selectedCandidateId": None,
            "selectionConfidence": "none",
            "selectionPolicyId": RECTIFICATION_SCORING_POLICY.policy_id,
            "eventMappingId": RECTIFICATION_EVENT_MAPPING_ID,
            "holdoutPolicyId": RECTIFICATION_HOLDOUT_POLICY_ID,
            "methodMaturity": RECTIFICATION_METHOD_MATURITY,
            "validationStatus": RECTIFICATION_VALIDATION_STATUS,
            "sourceIds": list(RECTIFICATION_SOURCE_IDS),
            "reportGate": {
                "fullReportAllowed": full_report_allowed,
                "reason": gate_reason,
                "nextStep": "evaluate_calibration_events"
                if status == "comparing_candidates"
                else "resolve_civil_time_or_place_input"
                if status == "input_resolution_required"
                else "retry_deterministic_calculation"
                if status == "calculation_failed"
                else "collect_dated_life_events"
                if status == "collecting_evidence"
                else "standard_prevalidation",
            },
            "searchBounds": {
                "time": (birth_input_context.get("time") or {}).get("window"),
                "place": {
                    "radiusKm": place_context.get("radiusKm")
                    if isinstance(place_context, dict)
                    else None,
                    "accuracy": place_context.get("accuracy")
                    if isinstance(place_context, dict)
                    else None,
                    "rectificationAllowed": place_rectification_allowed,
                },
            },
            "candidates": scored_candidates,
            "lifeEventLedger": copy.deepcopy(life_event_ledger),
            "divisionalSensitivity": copy.deepcopy(
                scan_summary.get("divisionalSensitivity")
                if isinstance(scan_summary.get("divisionalSensitivity"), list)
                else []
            ),
            "advancedVargaPolicy": copy.deepcopy(
                scan_summary.get("advancedVargaPolicy")
                if isinstance(scan_summary.get("advancedVargaPolicy"), dict)
                else {}
            ),
            "scanErrors": scan_errors,
            "candidateScoringErrors": candidate_scoring_errors,
            "activeChartRevision": {
                "revision": 0,
                "source": "initial_input",
                "candidateId": base_candidate_id,
            },
            "rectifiedInput": None,
            "guardrails": {
                "timeSearchMustStayWithinReportedWindow": constraints.get(
                    "timeSearchMustStayWithinReportedWindow",
                    True,
                ),
                "placeSearchMustStayWithinRadiusKm": constraints.get(
                    "placeSearchMustStayWithinRadiusKm",
                    True,
                ),
                "placeRectificationAllowed": place_rectification_allowed,
                "rectificationAxes": rectification_axes,
                "rejectRectificationOutsideUserFacts": constraints.get(
                    "rejectRectificationOutsideUserFacts",
                    True,
                ),
            },
        }
        state["rectificationPlan"] = self._build_rectification_plan(state)
        if state["status"] == "comparing_candidates":
            state = self._apply_initial_deterministic_event_decision(state)
        return state

    def _apply_initial_deterministic_event_decision(
        self,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """Select only from calibration scores, then evaluate the blind holdout.

        The user's confirmation of an event they already submitted is not new
        evidence and therefore cannot alter candidate ranking.
        """

        next_state = copy.deepcopy(state)
        candidates = self._candidate_score_state(next_state.get("candidates"))
        selection_blockers = self._deterministic_selection_blockers(next_state, candidates)
        selected = (
            None if selection_blockers else self._select_deterministic_event_candidate(candidates)
        )
        next_state["selectionEvidence"] = self._selection_evidence_summary(
            next_state,
            selection_blockers=selection_blockers,
        )
        if selected is None:
            next_state.update(
                {
                    "status": "underdetermined",
                    "selectedCandidateId": None,
                    "provisionalCandidateId": None,
                    "selectionConfidence": "none",
                    "holdoutResult": "not_run",
                    "candidates": candidates,
                    "reportGate": {
                        "fullReportAllowed": False,
                        "reason": (
                            "Calibration evidence is not independently broad enough or does not "
                            "separate the bounded chart candidates with the minimum deterministic "
                            "margin. Reconfirm the source time or provide additional dated events "
                            "from distinct life domains."
                        ),
                        "nextStep": "provide_more_precise_or_additional_event_evidence",
                    },
                }
            )
            next_state["rectificationPlan"] = self._build_rectification_plan(next_state)
            return next_state

        equivalent_ids = self._equivalent_candidate_ids(selected, candidates)
        holdout_result = self._holdout_result(
            selected,
            candidates,
            selected_candidate_ids=equivalent_ids,
        )
        next_state.update(
            {
                "candidates": candidates,
                "provisionalCandidateId": selected.get("candidateId"),
                "holdoutResult": holdout_result,
            }
        )
        if holdout_result != "passed":
            next_state.update(
                {
                    "status": "underdetermined",
                    "selectedCandidateId": None,
                    "selectionConfidence": "none",
                    "reportGate": {
                        "fullReportAllowed": False,
                        "reason": (
                            "The calibration leader did not pass the reserved event check. "
                            "The system will preserve the bounded candidate set rather than "
                            "fit the reserved event or ask a circular confirmation question."
                        ),
                        "nextStep": "provide_more_precise_or_additional_event_evidence",
                    },
                }
            )
        elif len(equivalent_ids) > 1:
            next_state.update(
                {
                    "status": "multiple_equivalent",
                    "selectedCandidateId": None,
                    "equivalentCandidateIds": equivalent_ids,
                    "selectionConfidence": "medium",
                    "reportGate": {
                        "fullReportAllowed": False,
                        "reason": (
                            "Several bounded birth hypotheses remain equivalent under all "
                            "calibration evidence. Preserve their stable intersection instead "
                            "of choosing an exact time."
                        ),
                        "nextStep": "build_equivalent_candidate_intersection",
                    },
                }
            )
        else:
            selected_id = str(selected.get("candidateId") or "")
            next_state.update(
                {
                    "status": "needs_recalculation",
                    "selectedCandidateId": selected_id,
                    "equivalentCandidateIds": [],
                    "selectionConfidence": "medium",
                    "reportGate": {
                        "fullReportAllowed": False,
                        "reason": (
                            "Calibration events selected a bounded interval and the reserved "
                            "event independently validated it; materialize its representative "
                            "moment before report synthesis."
                        ),
                        "nextStep": "apply_candidate_recalculation",
                    },
                }
            )
        next_state["rectificationPlan"] = self._build_rectification_plan(next_state)
        return next_state

    @staticmethod
    def _deterministic_selection_blockers(
        state: dict[str, Any], candidates: list[dict[str, Any]]
    ) -> list[str]:
        ledger = state.get("lifeEventLedger")
        ledger = ledger if isinstance(ledger, dict) else {}
        events = ledger.get("events")
        events = events if isinstance(events, list) else []
        calibration_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("role") == "calibration"
        ]
        categories = {
            str(event.get("category"))
            for event in calibration_events
            if event.get("category") and event.get("category") != "unknown"
        }
        holdout_count = sum(
            1 for event in events if isinstance(event, dict) and event.get("role") == "holdout"
        )
        blockers: list[str] = []
        if len(calibration_events) < RECTIFICATION_SCORING_POLICY.minimum_calibration_events:
            blockers.append("insufficient_calibration_events")
        if len(categories) < RECTIFICATION_SCORING_POLICY.minimum_calibration_categories:
            blockers.append("insufficient_calibration_category_diversity")
        if holdout_count != 1:
            blockers.append("missing_single_holdout_event")
        if len(candidates) < 2:
            blockers.append("insufficient_candidate_classes")
        return blockers

    @staticmethod
    def _selection_evidence_summary(
        state: dict[str, Any], *, selection_blockers: list[str]
    ) -> dict[str, Any]:
        ledger = state.get("lifeEventLedger")
        ledger = ledger if isinstance(ledger, dict) else {}
        events = ledger.get("events")
        events = events if isinstance(events, list) else []
        calibration = [
            event
            for event in events
            if isinstance(event, dict) and event.get("role") == "calibration"
        ]
        return {
            "selectionPolicyId": RECTIFICATION_SCORING_POLICY.policy_id,
            "eventMappingId": RECTIFICATION_EVENT_MAPPING_ID,
            "holdoutPolicyId": RECTIFICATION_HOLDOUT_POLICY_ID,
            "methodMaturity": RECTIFICATION_METHOD_MATURITY,
            "validationStatus": RECTIFICATION_VALIDATION_STATUS,
            "sourceIds": list(RECTIFICATION_SOURCE_IDS),
            "calibrationEventCount": len(calibration),
            "calibrationCategoryCount": len(
                {
                    str(event.get("category"))
                    for event in calibration
                    if event.get("category") and event.get("category") != "unknown"
                }
            ),
            "holdoutEventCount": sum(
                1 for event in events if isinstance(event, dict) and event.get("role") == "holdout"
            ),
            "blockers": selection_blockers,
        }

    @staticmethod
    def _select_deterministic_event_candidate(
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if len(candidates) < 2:
            return None
        event_sets: list[set[str]] = []
        for candidate in candidates:
            event_ids = {
                str(item.get("eventId"))
                for item in candidate.get("evidenceScores") or []
                if isinstance(item, dict)
                and item.get("role") == "calibration"
                and item.get("eventId")
            }
            if len(event_ids) < RECTIFICATION_SCORING_POLICY.minimum_calibration_events:
                return None
            event_sets.append(event_ids)
        if any(event_ids != event_sets[0] for event_ids in event_sets[1:]):
            return None

        representatives: list[dict[str, Any]] = []
        seen_classes: set[str] = set()
        for candidate in sorted(
            candidates,
            key=lambda item: (
                float(item.get("deterministicScore") or 0.0),
                1 if item.get("isBase") else 0,
            ),
            reverse=True,
        ):
            class_id = str(
                candidate.get("equivalenceClassId") or candidate.get("candidateId") or ""
            )
            if class_id in seen_classes:
                continue
            seen_classes.add(class_id)
            representatives.append(candidate)
        if not representatives:
            return None
        top = representatives[0]
        top_score = float(top.get("deterministicScore") or 0.0)
        if top_score < RECTIFICATION_SCORING_POLICY.candidate_selection_min_score:
            return None
        if len(representatives) > 1:
            second_score = float(representatives[1].get("deterministicScore") or 0.0)
            if (
                top_score - second_score
                < RECTIFICATION_SCORING_POLICY.candidate_selection_min_margin
            ):
                return None
        return top

    @staticmethod
    def _holdout_result(
        selected: dict[str, Any] | None,
        candidates: list[dict[str, Any]],
        *,
        selected_candidate_ids: list[str] | None = None,
    ) -> str:
        if selected is None or selected.get("holdoutScore") is None:
            return "not_run"
        selected_ids = set(selected_candidate_ids or [])
        selected_ids.add(str(selected.get("candidateId") or ""))
        alternatives = [
            float(candidate["holdoutScore"])
            for candidate in candidates
            if candidate.get("holdoutScore") is not None
            and str(candidate.get("candidateId") or "") not in selected_ids
        ]
        selected_score = float(selected["holdoutScore"])
        if selected_score < RECTIFICATION_SCORING_POLICY.holdout_min_score:
            return "inconclusive"
        if not alternatives:
            return "passed"
        best_alternative = max(alternatives)
        margin = selected_score - best_alternative
        if margin >= RECTIFICATION_SCORING_POLICY.holdout_pass_margin:
            return "passed"
        if margin <= -RECTIFICATION_SCORING_POLICY.holdout_pass_margin:
            return "failed"
        return "inconclusive"

    @staticmethod
    def _equivalent_candidate_ids(
        selected: dict[str, Any] | None,
        candidates: list[dict[str, Any]],
    ) -> list[str]:
        if selected is None:
            return []
        selected_id = str(selected.get("candidateId") or "")
        class_id = str(selected.get("equivalenceClassId") or "")
        if not class_id:
            return [selected_id] if selected_id else []
        return [
            str(candidate.get("candidateId"))
            for candidate in candidates
            if candidate.get("candidateId")
            and str(candidate.get("equivalenceClassId") or "") == class_id
        ]

    def rectified_birth_input(
        self,
        state: dict[str, Any],
        birth_input_context: dict[str, Any],
        chart_record: dict[str, Any],
    ) -> BirthInput | None:
        candidate = self.selected_candidate(state)
        if not candidate:
            return None

        subject = chart_record.get("subject")
        if not isinstance(subject, dict):
            subject = {}
        birth_assertion = chart_record.get("birthAssertion")
        if not isinstance(birth_assertion, dict):
            birth_assertion = {}
        time_context = birth_input_context.get("time")
        if not isinstance(time_context, dict):
            time_context = {}
        place_context = birth_input_context.get("place")
        if not isinstance(place_context, dict):
            place_context = {}
        life_event_context = birth_input_context.get("lifeEvents")
        if not isinstance(life_event_context, dict):
            life_event_context = {}
        locale = str(subject.get("locale")) if subject.get("locale") in {"zh", "en", "ja"} else "en"
        missing_value = (
            "未提供" if locale == "zh" else "未記入" if locale == "ja" else "[not provided]"
        )

        birth_date = str(birth_assertion.get("localDate") or time_context.get("date") or "")
        birth_time = str(
            birth_assertion.get("reportedLocalTime") or time_context.get("reported") or ""
        )
        birth_place = str(
            place_context.get("reported")
            or birth_assertion.get("reportedPlace")
            or place_context.get("resolvedLabel")
            or ""
        )
        place_rectification_allowed = self._place_rectification_allowed(place_context)

        axis_changes = []
        representative = candidate.get("representativeDatetime")
        if representative:
            date_part, time_part = self._split_datetime(str(representative))
            if date_part:
                birth_date = date_part
            if time_part:
                birth_time = time_part
            axis_changes.append("time")
        for member in candidate.get("members") or []:
            if not isinstance(member, dict):
                continue
            if not representative and member.get("axis") == "time" and member.get("datetime"):
                date_part, time_part = self._split_datetime(str(member["datetime"]))
                if date_part:
                    birth_date = date_part
                if time_part:
                    birth_time = time_part
                axis_changes.append("time")
            coordinates = member.get("coordinates")
            if (
                member.get("axis") == "place"
                and place_rectification_allowed
                and isinstance(coordinates, dict)
            ):
                lat = coordinates.get("lat")
                lon = coordinates.get("lon")
                if lat is not None and lon is not None:
                    timezone_id = str(member.get("timezone") or "").strip()
                    timezone_token = f", tz={timezone_id}" if timezone_id else ""
                    birth_place = (
                        f"{birth_place.split('|', 1)[0].strip()} | "
                        f"lat={lat}, lon={lon}{timezone_token}, "
                        "source=rectification, accuracy=coordinate"
                    )
                    axis_changes.append("place")

        if not axis_changes or not birth_date or not birth_place:
            return None

        return BirthInput(
            birthDate=birth_date,
            birthTime=birth_time,
            birthPlace=birth_place,
            # Internal calculation uses the representative moment of an already selected
            # interval. The user's reported precision remains in the persisted assertion.
            birthTimePrecision="exact",
            gender=str(subject.get("genderContext") or missing_value),
            relationship=str(subject.get("relationshipStatus") or missing_value),
            readerRelationship=self._reader_relationship(subject),
            timeSource=self._rectified_time_source(time_context.get("source")),
            readingFocus=str(birth_input_context.get("readingFocus") or ""),
            lifeEvents=str(life_event_context.get("raw") or ""),
            utcOffsetSeconds=(
                int(candidate["utcOffsetSeconds"])
                if candidate.get("civilTimeFold") and candidate.get("utcOffsetSeconds") is not None
                else None
            ),
            locale=locale,
        )

    def birth_input_with_life_events(
        self,
        birth_input_context: dict[str, Any],
        chart_record: dict[str, Any],
        life_events: str,
    ) -> BirthInput:
        """Rebuild the reported input while replacing only rectification evidence."""

        subject = chart_record.get("subject")
        subject = subject if isinstance(subject, dict) else {}
        assertion = chart_record.get("birthAssertion")
        assertion = assertion if isinstance(assertion, dict) else {}
        time_context = birth_input_context.get("time")
        time_context = time_context if isinstance(time_context, dict) else {}
        place_context = birth_input_context.get("place")
        place_context = place_context if isinstance(place_context, dict) else {}
        locale = str(subject.get("locale")) if subject.get("locale") in {"zh", "en", "ja"} else "en"
        missing_value = (
            "未提供" if locale == "zh" else "未記入" if locale == "ja" else "[not provided]"
        )
        birth_date = str(assertion.get("localDate") or time_context.get("date") or "")
        birth_place = str(
            place_context.get("reported")
            or assertion.get("reportedPlace")
            or place_context.get("resolvedLabel")
            or ""
        )
        if not birth_date or not birth_place:
            raise ValueError("session is missing the reported birth date or place")
        utc_offset = time_context.get("utcOffsetSeconds")
        return BirthInput(
            birthDate=birth_date,
            birthTime=str(assertion.get("reportedLocalTime") or time_context.get("reported") or ""),
            birthPlace=birth_place,
            birthTimePrecision=str(time_context.get("precision") or "approximate"),
            gender=str(subject.get("genderContext") or missing_value),
            relationship=str(subject.get("relationshipStatus") or missing_value),
            readerRelationship=self._reader_relationship(subject),
            timeSource=str(time_context.get("source") or "未追问"),
            readingFocus=str(birth_input_context.get("readingFocus") or ""),
            lifeEvents=life_events,
            utcOffsetSeconds=int(utc_offset) if utc_offset is not None else None,
            locale=locale,
        )

    @staticmethod
    def _place_rectification_allowed(place_context: dict[str, Any]) -> bool:
        return str(place_context.get("accuracy") or "city") in {"city", "district"}

    @staticmethod
    def _reader_relationship(subject: dict[str, Any]) -> ReaderRelationship:
        value = str(subject.get("readerRelationship") or "self")
        if value not in {"self", "parent", "partner", "family", "professional"}:
            return "self"
        return cast(ReaderRelationship, value)

    def selected_candidate(self, state: dict[str, Any]) -> dict[str, Any] | None:
        selected_id = state.get("selectedCandidateId")
        if not selected_id:
            return None
        for candidate in state.get("candidates") or []:
            if isinstance(candidate, dict) and candidate.get("candidateId") == selected_id:
                return candidate
        return None

    def apply_chart_revision(
        self,
        state: dict[str, Any],
        *,
        rectified_input: BirthInput,
        chart_revision: int,
    ) -> dict[str, Any]:
        next_state = copy.deepcopy(state)
        selected_id = next_state.get("selectedCandidateId")
        next_state.update(
            {
                "revision": int(next_state.get("revision") or 0) + 1,
                "updatedAt": self._now(),
                "status": "corrected_chart_ready",
                "activeCandidateId": selected_id,
                "reportGate": {
                    "fullReportAllowed": True,
                    "reason": (
                        "Calibration events selected a bounded candidate, the reserved event "
                        "validated it, and the chart was recalculated."
                    ),
                    "nextStep": "full_report",
                },
                "activeChartRevision": {
                    "revision": chart_revision,
                    "source": "deterministic_event_selection",
                    "candidateId": selected_id,
                },
                "rectifiedInput": rectified_input.model_dump(by_alias=True),
            }
        )
        next_state["rectificationPlan"] = self._build_rectification_plan(next_state)
        return next_state

    def reject_unmaterializable_selection(self, state: dict[str, Any]) -> dict[str, Any]:
        """Stop rectification when a selected hypothesis cannot become calculator input."""

        next_state = copy.deepcopy(state)
        next_state.update(
            {
                "revision": int(next_state.get("revision") or 0) + 1,
                "updatedAt": self._now(),
                "status": "underdetermined",
                "selectedCandidateId": None,
                "selectionConfidence": "none",
                "reportGate": {
                    "fullReportAllowed": False,
                    "reason": (
                        "The provisional candidate did not contain a bounded time or place that "
                        "can be materialized as a deterministic calculation input. Preserve the "
                        "candidate set instead of asking the Reader to choose a chart."
                    ),
                    "nextStep": "provide_more_precise_or_additional_event_evidence",
                },
            }
        )
        next_state["rectificationPlan"] = self._build_rectification_plan(next_state)
        return next_state

    def apply_prevalidation_decision(
        self,
        decision: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        next_decision = copy.deepcopy(decision)
        status = str(state.get("status") or "")
        gate = state.get("reportGate") if isinstance(state.get("reportGate"), dict) else {}
        next_decision["rectification"] = {
            "status": status,
            "selectedCandidateId": state.get("selectedCandidateId"),
            "activeCandidateId": state.get("activeCandidateId"),
            "selectionConfidence": state.get("selectionConfidence"),
            "activeChartRevision": state.get("activeChartRevision"),
            "reason": gate.get("reason"),
            "plan": state.get("rectificationPlan"),
        }
        if status == "not_required":
            next_decision.update(
                {
                    "nextStep": "report_allowed_with_stable_interval",
                    "timeConfidence": "low",
                    "reportAllowed": True,
                    "reportScope": "guarded_full_report",
                    "reason": gate.get("reason")
                    or "No chart-changing candidate exists inside the bounded input window.",
                }
            )
        elif status == "corrected_chart_ready":
            next_decision.update(
                {
                    "nextStep": "report_allowed_after_rectification",
                    "timeConfidence": "medium"
                    if state.get("selectionConfidence") == "medium"
                    else "high",
                    "reportAllowed": True,
                    "reportScope": "guarded_full_report",
                    "reason": gate.get("reason") or "Rectification gate passed.",
                }
            )
        elif status == "needs_recalculation":
            next_decision.update(
                {
                    "nextStep": status,
                    "timeConfidence": "low",
                    "reportAllowed": False,
                    "reportScope": "prevalidation_or_d1_only",
                    "reason": gate.get("reason") or "Candidate rectification is not complete.",
                }
            )
        elif status == "underdetermined":
            next_decision.update(
                {
                    "nextStep": "rectification_inconclusive",
                    "timeConfidence": "low",
                    "reportAllowed": False,
                    "reportScope": "prevalidation_or_d1_only",
                    "reason": gate.get("reason")
                    or "The reported birth-time interval remains underdetermined.",
                }
            )
        elif status == "multiple_equivalent":
            next_decision.update(
                {
                    "nextStep": "build_equivalent_candidate_intersection",
                    "timeConfidence": "low",
                    "reportAllowed": False,
                    "reportScope": "prevalidation_or_d1_only",
                    "reason": gate.get("reason")
                    or "Multiple bounded hypotheses remain equivalent for rectification.",
                }
            )
        elif status == "input_resolution_required":
            next_decision.update(
                {
                    "nextStep": "resolve_civil_time_or_place_input",
                    "timeConfidence": "low",
                    "reportAllowed": False,
                    "reportScope": "input_resolution_only",
                    "reason": gate.get("reason")
                    or "The reported search window contains unresolved civil-time or place input.",
                }
            )
        elif status == "calculation_failed":
            next_decision.update(
                {
                    "nextStep": "retry_deterministic_calculation",
                    "timeConfidence": "low",
                    "reportAllowed": False,
                    "reportScope": "calculation_retry_only",
                    "reason": gate.get("reason")
                    or "Candidate scoring did not complete for every birth-time hypothesis.",
                }
            )
        return next_decision

    def validate_prevalidation_contract(
        self,
        state: dict[str, Any],
        prevalidation_markdown: str,
        *,
        enforce_user_facing_quality: bool = False,
    ) -> list[str]:
        """Validate Reader questions without granting candidate-selection authority."""

        anchors = self._parse_prevalidation_blocks(prevalidation_markdown)
        errors: list[str] = []
        if not anchors:
            return ["reader_prevalidation.md does not contain numbered validation anchors."]
        if enforce_user_facing_quality:
            if not 1 <= len(anchors) <= 5:
                errors.append("reader_prevalidation.md must contain 1 to 5 validation questions.")

            for anchor in anchors:
                index = int(anchor["index"])
                block = str(anchor["block"])
                statement = self._statement_from_anchor_block(block)
                if len(statement) < 8:
                    errors.append(
                        f"Anchor {index} does not contain a concrete user-facing question."
                    )
                elif not statement.rstrip().endswith(("?", "？")):
                    errors.append(f"Anchor {index} must be written as a direct question.")
                if len(statement) > 180:
                    errors.append(f"Anchor {index} visible question is too long.")
                if self._contains_visible_astrology_terms(statement):
                    errors.append(
                        f"Anchor {index} exposes astrology or candidate terminology in the visible question."
                    )
                if not re.search(r"(?im)^>\s*(?:推导|Derivation|根拠)\s*[：:]", block):
                    errors.append(f"Anchor {index} is missing a quoted derivation line.")
        return errors

    @staticmethod
    def _contains_visible_astrology_terms(statement: str) -> bool:
        return bool(
            re.search(
                r"(?:"
                r"(?:Sun|Moon|Mars|Mercury|Jupiter|Venus|Saturn|Rahu|Ketu)\b|"
                r"(?:planet|zodiac|ascendant|lagna|nakshatra|dasha|yoga|varga)\b|"
                r"\bD(?:1|2|3|4|5|7|9|10|12|16|20|24|27|30|60)\b|"
                r"\b(?:candidate|field)\s*[A-Za-z0-9_-]*\b|"
                r"\b\d+(?:st|nd|rd|th)\s+house\b|"
                r"行星|星座|上升|宫位|分盘|大运|小运|星宿|候选盘|"
                r"太阳|月亮|火星|水星|木星|金星|土星|罗喉|计都"
                r")",
                statement,
                re.IGNORECASE,
            )
        )

    def _candidate_groups(self, sensitivity_scan: dict[str, Any]) -> list[dict[str, Any]]:
        groups = sensitivity_scan.get("candidateGroups")
        if isinstance(groups, list) and groups:
            return [copy.deepcopy(item) for item in groups if isinstance(item, dict)]
        base = sensitivity_scan.get("base")
        return [
            {
                "candidateId": "A",
                "signature": base if isinstance(base, dict) else {},
                "members": [],
                "changedFromBase": [],
                "isBase": True,
            }
        ]

    @staticmethod
    def _normalized_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for candidate in candidates:
            item = copy.deepcopy(candidate)
            item.setdefault("candidateId", "")
            deterministic_score = item.get("aggregateScore")
            item["deterministicScore"] = (
                round(float(deterministic_score), 3) if deterministic_score is not None else None
            )
            item["score"] = item["deterministicScore"] or 0.0
            result.append(item)
        return result

    @staticmethod
    def _base_candidate_id(candidates: list[dict[str, Any]]) -> str:
        for candidate in candidates:
            if candidate.get("isBase"):
                return str(candidate.get("candidateId") or "A")
        return str(candidates[0].get("candidateId") or "A") if candidates else "A"

    @staticmethod
    def _scan_summary(sensitivity_scan: dict[str, Any]) -> dict[str, Any]:
        summary = sensitivity_scan.get("summary")
        return summary if isinstance(summary, dict) else {}

    @staticmethod
    def _report_readiness(sensitivity_scan: dict[str, Any]) -> dict[str, Any]:
        readiness = sensitivity_scan.get("reportReadiness")
        return readiness if isinstance(readiness, dict) else {}

    @staticmethod
    def _candidate_score_state(raw_candidates: object) -> list[dict[str, Any]]:
        candidates = raw_candidates if isinstance(raw_candidates, list) else []
        result = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            item = copy.deepcopy(candidate)
            deterministic = item.get("deterministicScore")
            if deterministic is None:
                deterministic = item.get("aggregateScore")
            item["deterministicScore"] = (
                round(float(deterministic), 3) if deterministic is not None else None
            )
            item["score"] = item["deterministicScore"] or 0.0
            result.append(item)
        return result

    @staticmethod
    def _statement_from_anchor_block(block: str) -> str:
        statement = re.sub(
            r"(?m)^>\s*(?:推导|Derivation|根拠|Candidate|候选盘|候選盤|Field|Fields|字段|不稳定字段|Event|事件|Contrast|对比|對比)\s*[：:].*$",
            "",
            block,
        )
        return statement.replace("**", "").replace("`", "").replace("\n", " ").strip()

    @staticmethod
    def _parse_prevalidation_blocks(content: str) -> list[dict[str, object]]:
        anchors: list[dict[str, object]] = []
        pattern = re.compile(
            r"(?ms)^\*\*(\d+)\.\*\*\s*(.*?)(?=^\*\*\d+\.\*\*|\n请逐条回复|\nReply to each anchor|\Z)"
        )
        for match in pattern.finditer(content):
            anchors.append({"index": int(match.group(1)), "block": match.group(2).strip()})
        return anchors

    def _build_rectification_plan(self, state: dict[str, Any]) -> dict[str, Any]:
        """Build the backend-owned next step for multi-round birth time correction."""

        status = str(state.get("status") or "unknown")
        candidates = self._candidate_score_state(state.get("candidates"))
        selected_id = state.get("selectedCandidateId")
        sorted_candidates = self._sorted_candidates(candidates)
        target_candidates = self._target_candidates(sorted_candidates, selected_id)
        target_ids = [str(candidate.get("candidateId")) for candidate in target_candidates]
        fields = self._discriminating_fields(target_candidates, state)
        axes = self._rectification_axes(state)
        time_window = self._narrow_time_window(state, target_candidates)
        place_window = self._place_window(state, target_candidates)
        life_event_focus = self._life_event_focus(state, fields)
        event_collection_required = self._event_collection_required(state)
        divisional_sensitivity = (
            state.get("divisionalSensitivity")
            if isinstance(state.get("divisionalSensitivity"), list)
            else []
        )
        advanced_varga_policy = (
            state.get("advancedVargaPolicy")
            if isinstance(state.get("advancedVargaPolicy"), dict)
            else {}
        )
        gate = state.get("reportGate") if isinstance(state.get("reportGate"), dict) else {}

        if status == "not_required":
            action = "full_report"
            directive = "Rectification is not required; run standard prevalidation only."
        elif status == "corrected_chart_ready":
            action = "full_report"
            directive = "Rectified chart has been recalculated; use activeChartRevision as source."
        elif status == "needs_recalculation":
            action = "apply_candidate_recalculation"
            directive = "Selected bounded candidate must be recalculated before report synthesis."
        elif status == "underdetermined":
            action = "rectification_inconclusive"
            directive = (
                "Stop adaptive questioning. Preserve the bounded candidate set and ask "
                "for a narrower source time or additional dated events."
            )
        elif status == "multiple_equivalent":
            action = "build_equivalent_candidate_intersection"
            directive = (
                "Stop asking questions that cannot distinguish equivalent candidates. "
                "Preserve every bounded hypothesis and calculate their shared stable facts "
                "before releasing any scoped interpretation."
            )
        elif status == "input_resolution_required":
            action = "resolve_civil_time_or_place_input"
            directive = (
                "Do not ask astrological discriminator questions. Ask the user to narrow the "
                "reported time/place or explicitly resolve the civil-time ambiguity."
            )
        elif status == "calculation_failed":
            action = "retry_deterministic_calculation"
            directive = (
                "Do not ask rectification questions or compare incomplete candidate scores. "
                "Retry the deterministic calculation and rebuild the candidate set."
            )
        elif status == "collecting_evidence":
            action = "collect_dated_life_events"
            directive = (
                "Collect 3 to 5 dated, user-supplied life events before generating any "
                "candidate-scoring question."
            )
        elif status == "comparing_candidates":
            action = "evaluate_calibration_events"
            directive = (
                "Evaluate versioned calibration scores and the reserved event in the backend. "
                "Do not invoke Reader or accept testimony as candidate-selection evidence."
            )
        elif status == "needs_boundary_scan":
            action = "boundary_scan"
            directive = "Run a deeper time boundary scan before allowing report synthesis."
        else:
            action = "stop_unknown_rectification_state"
            directive = "Stop and rebuild the rectification state from deterministic artifacts."

        return {
            "schemaVersion": "chart-rectification-plan/v1",
            "selectionPolicyId": RECTIFICATION_SCORING_POLICY.policy_id,
            "eventMappingId": RECTIFICATION_EVENT_MAPPING_ID,
            "holdoutPolicyId": RECTIFICATION_HOLDOUT_POLICY_ID,
            "status": status,
            "action": action,
            "targetCandidateIds": target_ids,
            "candidateSummaries": [
                self._candidate_summary(candidate) for candidate in target_candidates
            ],
            "discriminatingFields": fields,
            "focusAxes": axes,
            "timeWindow": time_window,
            "placeWindow": place_window,
            "lifeEventFocus": life_event_focus,
            "divisionalSensitivity": self._plan_divisional_sensitivity(
                divisional_sensitivity,
                fields,
            ),
            "advancedVargaPolicy": advanced_varga_policy,
            "eventCollectionRequired": event_collection_required,
            "eventQuestionStrategy": (
                "Collect genuinely new structured dated events when evidence is insufficient. "
                "Never restate an existing event to create another vote. D16/D20/D24/D27/D30 "
                "remain corroborative and D60 remains final-confirmation-only."
            ),
            "directive": directive,
            "gateReason": gate.get("reason"),
            "stopConditions": [
                "A candidate has clear calibration margin and passes a reserved life event.",
                "A bounded interval has a clear calibration margin, passes holdout evidence, "
                "and is recalculated before report synthesis.",
                "Equivalent candidates remain explicit; do not publish one exact interval.",
                "If dated calibration evidence remains tied, return underdetermined rather than "
                "using generic testimony to force a birth time.",
            ],
        }

    @staticmethod
    def _plan_divisional_sensitivity(
        divisional_sensitivity: list[Any],
        discriminating_fields: list[str],
    ) -> list[dict[str, Any]]:
        fields = set(discriminating_fields)
        result: list[dict[str, Any]] = []
        for item in divisional_sensitivity:
            if not isinstance(item, dict):
                continue
            include = (
                item.get("field") in fields
                or item.get("changedInScan")
                or item.get("recommendedUse") in {"final_confirmation_only", "corroboration_only"}
            )
            if not include:
                continue
            result.append(
                {
                    "division": item.get("division"),
                    "field": item.get("field"),
                    "confidence": item.get("confidence"),
                    "usageTier": item.get("usageTier"),
                    "recommendedUse": item.get("recommendedUse"),
                    "changedInScan": item.get("changedInScan"),
                    "role": item.get("role"),
                }
            )
        return result

    def _life_event_focus(self, state: dict[str, Any], fields: list[str]) -> list[dict[str, Any]]:
        ledger = state.get("lifeEventLedger")
        if not isinstance(ledger, dict):
            return []
        return build_life_event_focus(ledger, fields)

    @staticmethod
    def _event_collection_required(state: dict[str, Any]) -> bool:
        ledger = state.get("lifeEventLedger")
        if not isinstance(ledger, dict):
            return True
        return bool(ledger.get("eventCollectionRequired"))

    @staticmethod
    def _sorted_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            candidates,
            key=lambda item: (
                float(item.get("score") or 0),
                int(item.get("support") or 0),
                -int(item.get("reject") or 0),
                1 if item.get("isBase") else 0,
                str(item.get("candidateId") or ""),
            ),
            reverse=True,
        )

    @staticmethod
    def _target_candidates(
        sorted_candidates: list[dict[str, Any]],
        selected_id: object,
    ) -> list[dict[str, Any]]:
        if not sorted_candidates:
            return []
        if selected_id:
            selected = [
                candidate
                for candidate in sorted_candidates
                if str(candidate.get("candidateId")) == str(selected_id)
            ]
            base = [
                candidate
                for candidate in sorted_candidates
                if candidate.get("isBase") and str(candidate.get("candidateId")) != str(selected_id)
            ]
            return (selected + base)[:2] or selected
        representatives: list[dict[str, Any]] = []
        seen_classes: set[str] = set()
        for candidate in sorted_candidates:
            class_id = str(
                candidate.get("equivalenceClassId") or candidate.get("candidateId") or ""
            )
            if class_id in seen_classes:
                continue
            seen_classes.add(class_id)
            representatives.append(candidate)
            if len(representatives) == 3:
                break
        return representatives

    @staticmethod
    def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "candidateId": candidate.get("candidateId"),
            "isBase": bool(candidate.get("isBase")),
            "score": round(float(candidate.get("score") or 0), 3),
            "deterministicScore": candidate.get("deterministicScore"),
            "changedFromBase": candidate.get("changedFromBase") or [],
            "equivalenceClassId": candidate.get("equivalenceClassId"),
            "equivalentCandidateIds": candidate.get("equivalentCandidateIds") or [],
            "members": candidate.get("members") or [],
        }

    def _discriminating_fields(
        self,
        candidates: list[dict[str, Any]],
        _state: dict[str, Any],
    ) -> list[str]:
        fields: list[str] = []
        for candidate in candidates:
            for field in candidate.get("changedFromBase") or []:
                if isinstance(field, str) and field and field not in fields:
                    fields.append(field)
        if fields:
            return fields
        return ["lagnaSign", "moonNakshatra", "d9Lagna", "d10Lagna", "currentDasha"]

    @staticmethod
    def _rectification_axes(state: dict[str, Any]) -> list[str]:
        guardrails = state.get("guardrails") if isinstance(state.get("guardrails"), dict) else {}
        axes = guardrails.get("rectificationAxes")
        if isinstance(axes, list) and axes:
            return [str(axis) for axis in axes]
        place_allowed = guardrails.get("placeRectificationAllowed") is not False
        return ["time", "place"] if place_allowed else ["time"]

    def _narrow_time_window(
        self,
        state: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        search_bounds = (
            state.get("searchBounds") if isinstance(state.get("searchBounds"), dict) else {}
        )
        time_bounds = (
            search_bounds.get("time") if isinstance(search_bounds.get("time"), dict) else {}
        )
        original_start = self._parse_datetime(str(time_bounds.get("start") or ""))
        has_exclusive_end = bool(time_bounds.get("endExclusive"))
        original_end = self._parse_datetime(
            str(time_bounds.get("endExclusive") or time_bounds.get("end") or "")
        )
        if original_end is not None and not has_exclusive_end:
            original_end += timedelta(minutes=1)
        if original_start is None or original_end is None:
            return time_bounds or None

        candidate_times: list[datetime] = []
        for candidate in candidates:
            interval = candidate.get("interval")
            if isinstance(interval, dict):
                interval_start = self._parse_datetime(str(interval.get("start") or ""))
                interval_end = self._parse_datetime(str(interval.get("end") or ""))
                if interval_start is not None:
                    candidate_times.append(interval_start)
                if interval_end is not None:
                    candidate_times.append(interval_end)
                continue
            for member in candidate.get("members") or []:
                if not isinstance(member, dict) or member.get("axis") != "time":
                    continue
                value = self._parse_datetime(str(member.get("datetime") or ""))
                if value is not None:
                    candidate_times.append(value)
        if not candidate_times:
            return {
                **time_bounds,
                "basis": "reported_window",
                "targetCandidateIds": [
                    str(candidate.get("candidateId"))
                    for candidate in candidates
                    if candidate.get("candidateId")
                ],
            }

        span_minutes = max(1, int((original_end - original_start).total_seconds() / 60))
        padding = max(2, min(15, span_minutes // 6))
        narrowed_start = max(original_start, min(candidate_times) - timedelta(minutes=padding))
        narrowed_end = min(original_end, max(candidate_times) + timedelta(minutes=padding))
        return {
            "start": narrowed_start.strftime("%Y-%m-%d %H:%M"),
            "end": (narrowed_end - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"),
            "endExclusive": narrowed_end.strftime("%Y-%m-%d %H:%M"),
            "radiusMinutes": int((narrowed_end - narrowed_start).total_seconds() / 120),
            "basis": "candidate_intervals",
            "paddingMinutes": padding,
            "targetCandidateIds": [
                str(candidate.get("candidateId"))
                for candidate in candidates
                if candidate.get("candidateId")
            ],
        }

    @staticmethod
    def _place_window(
        state: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        guardrails = state.get("guardrails") if isinstance(state.get("guardrails"), dict) else {}
        if guardrails.get("placeRectificationAllowed") is False:
            return {
                "rectificationAllowed": False,
                "reason": "Detailed place coordinates are locked.",
            }
        coords = []
        for candidate in candidates:
            for member in candidate.get("members") or []:
                if not isinstance(member, dict) or member.get("axis") != "place":
                    continue
                coordinates = member.get("coordinates")
                if not isinstance(coordinates, dict):
                    continue
                try:
                    coords.append((float(coordinates["lat"]), float(coordinates["lon"])))
                except (KeyError, TypeError, ValueError):
                    continue
        search_bounds = (
            state.get("searchBounds") if isinstance(state.get("searchBounds"), dict) else {}
        )
        place_bounds = (
            search_bounds.get("place") if isinstance(search_bounds.get("place"), dict) else {}
        )
        if not coords:
            return place_bounds or None
        lats = [item[0] for item in coords]
        lons = [item[1] for item in coords]
        return {
            "rectificationAllowed": True,
            "radiusKm": place_bounds.get("radiusKm"),
            "boundingBox": {
                "minLat": round(min(lats), 6),
                "maxLat": round(max(lats), 6),
                "minLon": round(min(lons), 6),
                "maxLon": round(max(lons), 6),
            },
        }

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        for format_string in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(value.strip(), format_string)
            except ValueError:
                continue
        return None

    @staticmethod
    def _split_datetime(value: str) -> tuple[str | None, str | None]:
        match = re.match(
            r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}(?::\d{2})?)$",
            value.strip(),
        )
        if not match:
            return None, None
        return match.group(1), match.group(2)

    @staticmethod
    def _rectified_time_source(source: object) -> str:
        raw = str(source or "未追问")
        value = f"rectified-from-event-evidence; original={raw}"
        return value[:120]

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
