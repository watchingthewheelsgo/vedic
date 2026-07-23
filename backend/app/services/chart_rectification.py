from __future__ import annotations

import copy
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.schemas import BirthInput
from app.services.life_event_rectification import build_life_event_focus


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
        life_event_ledger = birth_input_context.get("lifeEvents")
        if not isinstance(life_event_ledger, dict):
            life_event_ledger = {}

        scored_candidates = self._scoreless_candidates(candidates)

        if mode == "rectification_required" and len(candidates) > 1:
            status = "candidate_feedback_pending"
            gate_reason = "Chart-changing candidates must be confirmed by prevalidation feedback."
            full_report_allowed = False
        elif mode == "rectification_required":
            status = "needs_boundary_scan"
            gate_reason = "High-risk input needs a deeper boundary scan before full synthesis."
            full_report_allowed = False
        else:
            status = "not_required"
            gate_reason = "Sensitivity scan does not require candidate rectification."
            full_report_allowed = True

        state = {
            "schemaVersion": self.schema_version,
            "revision": 0,
            "rectificationRound": 0,
            "generatedAt": self._now(),
            "updatedAt": self._now(),
            "status": status,
            "riskLevel": risk_level,
            "reportReadinessMode": mode,
            "baseCandidateId": base_candidate_id,
            "activeCandidateId": base_candidate_id,
            "selectedCandidateId": None,
            "selectionConfidence": "none",
            "candidateBoundAnchorCount": 0,
            "feedbackAnchorCount": 0,
            "reportGate": {
                "fullReportAllowed": full_report_allowed,
                "reason": gate_reason,
                "nextStep": "prevalidation"
                if status == "candidate_feedback_pending"
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
            "feedbackAnchors": [],
            "roundHistory": [],
            "anchorContractErrors": [],
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
        return state

    def update_from_feedback(
        self,
        state: dict[str, Any],
        prevalidation_markdown: str,
        feedback_markdown: str,
        prevalidation_result: dict[str, Any],
    ) -> dict[str, Any]:
        next_state = copy.deepcopy(state)
        anchors = self._parse_candidate_anchors(prevalidation_markdown, feedback_markdown)
        candidates = self._candidate_score_state(next_state.get("candidates"))
        by_id = {str(candidate.get("candidateId")): candidate for candidate in candidates}
        contract_errors = self.validate_prevalidation_contract(next_state, prevalidation_markdown)

        candidate_bound_count = 0
        next_round = int(next_state.get("rectificationRound") or 0) + 1
        for anchor in anchors:
            answer = str(anchor.get("answer") or "pending")
            weight = self._answer_weight(answer)
            candidate_ids = [
                candidate_id
                for candidate_id in anchor.get("candidateIds", [])
                if candidate_id in by_id
            ]
            if candidate_ids:
                candidate_bound_count += 1
            for candidate_id in candidate_ids:
                candidate = by_id[candidate_id]
                candidate["score"] = round(float(candidate.get("score") or 0) + weight, 3)
                if weight > 0:
                    candidate["support"] = int(candidate.get("support") or 0) + 1
                elif weight < 0:
                    candidate["reject"] = int(candidate.get("reject") or 0) + 1
            anchor["round"] = next_round

        if contract_errors:
            selected = None
            status, confidence, gate = self._candidate_contract_error_state(contract_errors)
        else:
            selected = self._select_candidate(candidates)
            status, confidence, gate = self._state_from_selection(
                next_state,
                selected,
                candidate_bound_count,
            )
        round_history = self._round_history(next_state)
        round_history.append(
            {
                "round": next_round,
                "status": status,
                "selectedCandidateId": selected.get("candidateId") if selected else None,
                "candidateBoundAnchorCount": candidate_bound_count,
                "feedbackAnchorCount": len(anchors),
                "anchorContractErrors": contract_errors,
                "candidateScores": [
                    {
                        "candidateId": candidate.get("candidateId"),
                        "score": candidate.get("score"),
                        "support": candidate.get("support"),
                        "reject": candidate.get("reject"),
                    }
                    for candidate in candidates
                ],
            }
        )
        feedback_anchors = self._feedback_anchors(next_state)
        feedback_anchors.extend(anchors)

        next_state.update(
            {
                "revision": int(next_state.get("revision") or 0) + 1,
                "rectificationRound": next_round,
                "updatedAt": self._now(),
                "status": status,
                "selectedCandidateId": selected.get("candidateId") if selected else None,
                "selectionConfidence": confidence,
                "candidateBoundAnchorCount": int(next_state.get("candidateBoundAnchorCount") or 0)
                + candidate_bound_count,
                "currentRoundCandidateBoundAnchorCount": candidate_bound_count,
                "feedbackAnchorCount": len(feedback_anchors),
                "candidates": candidates,
                "feedbackAnchors": feedback_anchors,
                "roundHistory": round_history,
                "anchorContractErrors": contract_errors,
                "reportGate": gate,
            }
        )
        next_state["rectificationPlan"] = self._build_rectification_plan(next_state)
        return next_state

    def rectified_birth_input(
        self,
        state: dict[str, Any],
        birth_input_context: dict[str, Any],
        structured_data_json: dict[str, Any],
    ) -> BirthInput | None:
        candidate = self.selected_candidate(state)
        if not candidate or candidate.get("isBase"):
            return None

        subject = structured_data_json.get("subject")
        if not isinstance(subject, dict):
            subject = {}
        time_context = birth_input_context.get("time")
        if not isinstance(time_context, dict):
            time_context = {}
        place_context = birth_input_context.get("place")
        if not isinstance(place_context, dict):
            place_context = {}

        birth_date = str(subject.get("birthDate") or time_context.get("date") or "")
        birth_time = str(subject.get("birthTime") or time_context.get("reported") or "")
        birth_place = str(
            place_context.get("reported")
            or subject.get("birthPlace")
            or place_context.get("resolvedLabel")
            or ""
        )
        place_rectification_allowed = self._place_rectification_allowed(place_context)

        axis_changes = []
        for member in candidate.get("members") or []:
            if not isinstance(member, dict):
                continue
            if member.get("axis") == "time" and member.get("datetime"):
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
                    birth_place = (
                        f"{birth_place.split('|', 1)[0].strip()} | "
                        f"lat={lat}, lon={lon}, source=rectification, accuracy=coordinate"
                    )
                    axis_changes.append("place")

        if not axis_changes or not birth_date or not birth_place:
            return None

        return BirthInput(
            birthDate=birth_date,
            birthTime=birth_time,
            birthPlace=birth_place,
            birthTimePrecision=str(time_context.get("precision") or "approximate"),
            gender=str(subject.get("gender") or "未提供"),
            relationship=str(subject.get("relationship") or "未提供"),
            timeSource=self._rectified_time_source(time_context.get("source")),
            locale="zh",
        )

    @staticmethod
    def _place_rectification_allowed(place_context: dict[str, Any]) -> bool:
        return str(place_context.get("accuracy") or "city") in {"city", "district"}

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
                    "reason": "A candidate chart was selected by feedback and recalculated.",
                    "nextStep": "full_report",
                },
                "activeChartRevision": {
                    "revision": chart_revision,
                    "source": "prevalidation_feedback",
                    "candidateId": selected_id,
                },
                "rectifiedInput": rectified_input.model_dump(by_alias=True),
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
            "candidateBoundAnchorCount": state.get("candidateBoundAnchorCount"),
            "activeChartRevision": state.get("activeChartRevision"),
            "reason": gate.get("reason"),
            "plan": state.get("rectificationPlan"),
        }
        if status in {"base_confirmed", "corrected_chart_ready"}:
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
        elif status in {
            "needs_candidate_bound_checks",
            "needs_more_feedback",
            "needs_recalculation",
        }:
            next_decision.update(
                {
                    "nextStep": status,
                    "timeConfidence": "low",
                    "reportAllowed": False,
                    "reportScope": "prevalidation_or_d1_only",
                    "reason": gate.get("reason") or "Candidate rectification is not complete.",
                }
            )
        return next_decision

    def validate_prevalidation_contract(
        self,
        state: dict[str, Any],
        prevalidation_markdown: str,
    ) -> list[str]:
        """Return contract errors for high-risk candidate-bound reader output."""

        if not self._requires_candidate_bound_anchors(state):
            return []

        raw_candidates = state.get("candidates")
        candidates = raw_candidates if isinstance(raw_candidates, list) else []
        candidate_ids = {
            str(candidate.get("candidateId"))
            for candidate in candidates
            if isinstance(candidate, dict) and candidate.get("candidateId")
        }
        anchors = self._parse_prevalidation_blocks(prevalidation_markdown)
        errors: list[str] = []
        if not anchors:
            return ["reader_prevalidation.md does not contain numbered validation anchors."]

        for anchor in anchors:
            index = int(anchor["index"])
            block = str(anchor["block"])
            anchor_candidate_ids = self._candidate_ids_from_block(block)
            fields = self._unstable_fields_from_block(block)
            event_refs = self._event_refs_from_block(block)
            if not anchor_candidate_ids:
                errors.append(f"Anchor {index} is missing a machine-readable Candidate line.")
            invalid_ids = [
                candidate_id
                for candidate_id in anchor_candidate_ids
                if candidate_id not in candidate_ids
            ]
            if invalid_ids:
                errors.append(
                    f"Anchor {index} references unknown candidate ID(s): {', '.join(invalid_ids)}."
                )
            if not fields:
                errors.append(f"Anchor {index} is missing a machine-readable Field line.")
            if self._requires_life_event_bound_anchors(state):
                if not event_refs:
                    errors.append(f"Anchor {index} is missing a machine-readable Event line.")
                invalid_event_refs = [
                    event_ref
                    for event_ref in event_refs
                    if event_ref not in self._known_event_refs(state)
                ]
                if invalid_event_refs:
                    errors.append(
                        f"Anchor {index} references unknown event(s): "
                        f"{', '.join(invalid_event_refs)}."
                    )
            statement = self._statement_from_anchor_block(block)
            if len(statement) < 12:
                errors.append(f"Anchor {index} does not contain a concrete user-facing claim.")

        return errors

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
    def _scoreless_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for candidate in candidates:
            item = copy.deepcopy(candidate)
            item.setdefault("candidateId", "")
            item["score"] = 0.0
            item["support"] = 0
            item["reject"] = 0
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
            item["score"] = round(float(item.get("score") or 0.0), 3)
            item["support"] = int(item.get("support") or 0)
            item["reject"] = int(item.get("reject") or 0)
            result.append(item)
        return result

    @staticmethod
    def _round_history(state: dict[str, Any]) -> list[dict[str, Any]]:
        history = state.get("roundHistory")
        if not isinstance(history, list):
            return []
        return [copy.deepcopy(item) for item in history if isinstance(item, dict)]

    @staticmethod
    def _feedback_anchors(state: dict[str, Any]) -> list[dict[str, Any]]:
        anchors = state.get("feedbackAnchors")
        if not isinstance(anchors, list):
            return []
        return [copy.deepcopy(item) for item in anchors if isinstance(item, dict)]

    def _parse_candidate_anchors(
        self,
        prevalidation_markdown: str,
        feedback_markdown: str,
    ) -> list[dict[str, Any]]:
        anchors = self._parse_prevalidation_blocks(prevalidation_markdown)
        answers = self._parse_feedback_answers(feedback_markdown)
        parsed = []
        for anchor in anchors:
            index = int(anchor["index"])
            parsed.append(
                {
                    "index": index,
                    "candidateIds": self._candidate_ids_from_block(str(anchor["block"])),
                    "unstableFields": self._unstable_fields_from_block(str(anchor["block"])),
                    "eventRefs": self._event_refs_from_block(str(anchor["block"])),
                    "answer": answers.get(index, "pending"),
                }
            )
        return parsed

    @staticmethod
    def _statement_from_anchor_block(block: str) -> str:
        statement = re.sub(
            r"(?m)^>\s*(?:推导|Derivation|根拠|Candidate|候选盘|候選盤|Field|Fields|字段|不稳定字段|Event|事件)\s*[：:].*$",
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

    @staticmethod
    def _parse_feedback_answers(content: str) -> dict[int, str]:
        answers: dict[int, str] = {}
        anchor_pattern = re.compile(
            r"(?ms)^####\s+Anchor\s+(\d+)\s*\n(.*?)(?=^####\s+Anchor\s+\d+\s*\n|\Z)"
        )
        for match in anchor_pattern.finditer(content):
            answer_raw = re.search(r"(?m)^-\s*User answer:\s*(.+)$", match.group(2))
            if answer_raw:
                answers[int(match.group(1))] = ChartRectificationService._normalize_answer(
                    answer_raw.group(1)
                )
        if answers:
            return answers
        for line in content.splitlines():
            match = re.match(r"\s*(?:\*\*)?(\d+)(?:\.\*\*|[.、:：])?\s*(准|部分准|不准)", line)
            if match:
                answers[int(match.group(1))] = ChartRectificationService._normalize_answer(
                    match.group(2)
                )
        return answers

    @staticmethod
    def _normalize_answer(raw: str) -> str:
        value = raw.strip().lower()
        if "inaccurate" in value or "not accurate" in value or "不准" in raw:
            return "inaccurate"
        if "partly" in value or "部分" in raw:
            return "partly"
        if "accurate" in value or "准" in raw:
            return "accurate"
        return "recorded"

    @staticmethod
    def _candidate_ids_from_block(block: str) -> list[str]:
        ids: list[str] = []
        pattern = re.compile(
            r"(?im)^>[ \t]*(?:Candidate(?:[ \t]+IDs?)?|候选盘|候選盤)"
            r"[ \t]*[：:][ \t]*([A-Z](?:[ \t]*[,/，、][ \t]*[A-Z])*)[ \t]*$"
        )
        for match in pattern.finditer(block):
            for candidate_id in re.findall(r"\b[A-Z]\b", match.group(1)):
                if candidate_id not in ids:
                    ids.append(candidate_id)
        return ids

    @staticmethod
    def _unstable_fields_from_block(block: str) -> list[str]:
        match = re.search(
            r"(?im)^>\s*(?:Field|Fields|Unstable Fields?|字段|不稳定字段)\s*[：:]\s*(.+)$",
            block,
        )
        if not match:
            return []
        fields = []
        for raw in re.split(r"[,/，、\s]+", match.group(1).strip()):
            if raw and raw not in fields:
                fields.append(raw)
        return fields

    @staticmethod
    def _event_refs_from_block(block: str) -> list[str]:
        refs: list[str] = []
        for match in re.finditer(r"(?im)^>\s*(?:Event|事件)\s*[：:]\s*(.+)$", block):
            for raw in re.split(r"[,/，、\s]+", match.group(1).strip()):
                if raw and raw not in refs:
                    refs.append(raw)
        return refs

    @staticmethod
    def _answer_weight(answer: str) -> float:
        if answer == "accurate":
            return 1.0
        if answer == "partly":
            return 0.35
        if answer == "inaccurate":
            return -1.0
        return 0.0

    @staticmethod
    def _select_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not candidates:
            return None
        ordered = sorted(
            candidates,
            key=lambda item: (
                float(item.get("score") or 0),
                int(item.get("support") or 0),
                1 if item.get("isBase") else 0,
            ),
            reverse=True,
        )
        top = ordered[0]
        second_score = float(ordered[1].get("score") or 0) if len(ordered) > 1 else 0.0
        top_score = float(top.get("score") or 0)
        support = int(top.get("support") or 0)
        clear_margin = top_score - second_score >= 0.75
        enough_positive_support = support >= 2 and top_score >= 1.25
        alternatives_rejected = bool(ordered[1:]) and all(
            int(candidate.get("reject") or 0) >= 1 for candidate in ordered[1:]
        )
        one_positive_with_rejections = support >= 1 and top_score >= 1.0 and alternatives_rejected
        if clear_margin and (enough_positive_support or one_positive_with_rejections):
            return top
        return None

    @staticmethod
    def _requires_candidate_bound_anchors(state: dict[str, Any]) -> bool:
        status = str(state.get("status") or "")
        mode = str(state.get("reportReadinessMode") or "")
        candidates = state.get("candidates") if isinstance(state.get("candidates"), list) else []
        return (
            mode == "rectification_required"
            and len(candidates) > 1
            and status
            in {
                "candidate_feedback_pending",
                "needs_candidate_bound_checks",
                "needs_more_feedback",
            }
        )

    @staticmethod
    def _requires_life_event_bound_anchors(state: dict[str, Any]) -> bool:
        if not ChartRectificationService._requires_candidate_bound_anchors(state):
            return False
        plan = (
            state.get("rectificationPlan")
            if isinstance(state.get("rectificationPlan"), dict)
            else {}
        )
        focus = plan.get("lifeEventFocus") if isinstance(plan, dict) else None
        return isinstance(focus, list) and len(focus) > 0

    @staticmethod
    def _known_event_refs(state: dict[str, Any]) -> set[str]:
        ledger = state.get("lifeEventLedger")
        events = ledger.get("events") if isinstance(ledger, dict) else None
        refs: set[str] = set()
        if not isinstance(events, list):
            return refs
        for event in events:
            if not isinstance(event, dict):
                continue
            for key in ("eventId", "category"):
                value = event.get(key)
                if value:
                    refs.add(str(value))
        return refs

    @staticmethod
    def _candidate_contract_error_state(
        errors: list[str],
    ) -> tuple[str, str, dict[str, Any]]:
        return (
            "needs_candidate_bound_checks",
            "none",
            {
                "fullReportAllowed": False,
                "reason": "Reader validation anchors do not satisfy the candidate-bound contract: "
                + "; ".join(errors[:3]),
                "nextStep": "rerun_reader_with_candidate_bound_anchors",
            },
        )

    def _state_from_selection(
        self,
        state: dict[str, Any],
        selected: dict[str, Any] | None,
        candidate_bound_count: int,
    ) -> tuple[str, str, dict[str, Any]]:
        current_status = str(state.get("status") or "")
        if current_status == "not_required":
            return (
                "not_required",
                "none",
                {
                    "fullReportAllowed": True,
                    "reason": "Rectification is not required for this chart.",
                    "nextStep": "full_report",
                },
            )
        if candidate_bound_count == 0 and current_status == "candidate_feedback_pending":
            return (
                "needs_candidate_bound_checks",
                "none",
                {
                    "fullReportAllowed": False,
                    "reason": (
                        "High-risk input needs validation anchors bound to chart candidate IDs."
                    ),
                    "nextStep": "rerun_reader_with_candidate_bound_anchors",
                },
            )
        if selected:
            confidence = "high" if int(selected.get("support") or 0) >= 2 else "medium"
            if selected.get("isBase"):
                return (
                    "base_confirmed",
                    confidence,
                    {
                        "fullReportAllowed": True,
                        "reason": "Prevalidation feedback confirmed the base candidate chart.",
                        "nextStep": "full_report",
                    },
                )
            return (
                "needs_recalculation",
                confidence,
                {
                    "fullReportAllowed": False,
                    "reason": "A non-base candidate was selected and must be recalculated.",
                    "nextStep": "apply_candidate_recalculation",
                },
            )
        return (
            "needs_more_feedback",
            "none",
            {
                "fullReportAllowed": False,
                "reason": "Feedback did not select a chart candidate clearly enough.",
                "nextStep": "continue_rectification",
            },
        )

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
        round_number = int(state.get("rectificationRound") or 0)
        gate = state.get("reportGate") if isinstance(state.get("reportGate"), dict) else {}

        if status == "not_required":
            action = "full_report"
            directive = "Rectification is not required; run standard prevalidation only."
        elif status == "base_confirmed":
            action = "full_report"
            directive = (
                "Base candidate is confirmed; full report may proceed with recorded confidence."
            )
        elif status == "corrected_chart_ready":
            action = "full_report"
            directive = "Rectified chart has been recalculated; use activeChartRevision as source."
        elif status == "needs_recalculation":
            action = "apply_candidate_recalculation"
            directive = "Selected non-base candidate must be recalculated before report synthesis."
        elif status == "needs_candidate_bound_checks":
            action = "rerun_reader"
            directive = (
                "Regenerate prevalidation anchors with machine-readable Candidate and Field lines; "
                "when lifeEventFocus exists, also include Event lines."
            )
        elif status == "needs_more_feedback":
            action = "next_rectification_round"
            directive = (
                "Ask narrower candidate-discriminating anchors using target candidates, fields, "
                "and dated life events where available."
            )
        elif status == "needs_boundary_scan":
            action = "boundary_scan"
            directive = "Run a deeper time boundary scan before allowing report synthesis."
        else:
            action = "first_rectification_round"
            directive = (
                "Ask candidate-bound prevalidation anchors before any deterministic full report."
            )

        return {
            "schemaVersion": "chart-rectification-plan/v1",
            "status": status,
            "action": action,
            "round": round_number,
            "maxRounds": 8,
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
                "Use dated life events as primary rectification anchors. Prefer stable D1, "
                "Dasha, D7/D9/D10/D12 differences when available; use D16/D20/D24/D27/D30 "
                "only as corroboration and D60 only as final confirmation after the time "
                "window is very narrow."
            ),
            "requiredAnchorCount": self._required_anchor_count(status, target_candidates),
            "directive": directive,
            "gateReason": gate.get("reason"),
            "stopConditions": [
                "A candidate has clear score margin and enough candidate-bound support.",
                "The base chart is confirmed by candidate-bound anchors.",
                "A non-base candidate is selected and recalculated.",
                "Eight rounds are reached without convergence; keep report D1-only/low-confidence.",
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
        viable = [
            candidate
            for candidate in sorted_candidates
            if int(candidate.get("reject") or 0) == 0 or int(candidate.get("support") or 0) > 0
        ]
        return (viable or sorted_candidates)[: min(3, len(sorted_candidates))]

    @staticmethod
    def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "candidateId": candidate.get("candidateId"),
            "isBase": bool(candidate.get("isBase")),
            "score": round(float(candidate.get("score") or 0), 3),
            "support": int(candidate.get("support") or 0),
            "reject": int(candidate.get("reject") or 0),
            "changedFromBase": candidate.get("changedFromBase") or [],
            "members": candidate.get("members") or [],
        }

    def _discriminating_fields(
        self,
        candidates: list[dict[str, Any]],
        state: dict[str, Any],
    ) -> list[str]:
        fields: list[str] = []
        for candidate in candidates:
            for field in candidate.get("changedFromBase") or []:
                if isinstance(field, str) and field and field not in fields:
                    fields.append(field)
        for anchor in self._feedback_anchors(state):
            for field in anchor.get("unstableFields") or []:
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
        original_end = self._parse_datetime(str(time_bounds.get("end") or ""))
        if original_start is None or original_end is None:
            return time_bounds or None

        candidate_times: list[datetime] = []
        for candidate in candidates:
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
            "end": narrowed_end.strftime("%Y-%m-%d %H:%M"),
            "radiusMinutes": int((narrowed_end - narrowed_start).total_seconds() / 120),
            "basis": "candidate_member_datetimes",
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
    def _required_anchor_count(status: str, candidates: list[dict[str, Any]]) -> int:
        if status in {"not_required", "base_confirmed", "corrected_chart_ready"}:
            return 0
        if len(candidates) <= 1:
            return 3
        return min(5, max(3, len(candidates) + 1))

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            return None

    @staticmethod
    def _split_datetime(value: str) -> tuple[str | None, str | None]:
        match = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})$", value.strip())
        if not match:
            return None, None
        return match.group(1), match.group(2)

    @staticmethod
    def _rectified_time_source(source: object) -> str:
        raw = str(source or "未追问")
        value = f"rectified-from-feedback; original={raw}"
        return value[:120]

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
