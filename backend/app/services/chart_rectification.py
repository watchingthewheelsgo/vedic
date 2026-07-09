from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any

from app.schemas import BirthInput


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
        risk_level = str(self._scan_summary(sensitivity_scan).get("riskLevel") or "unknown")
        mode = str(readiness.get("mode") or "unknown")

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

        return {
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
                    "radiusKm": (birth_input_context.get("place") or {}).get("radiusKm"),
                    "accuracy": (birth_input_context.get("place") or {}).get("accuracy"),
                },
            },
            "candidates": self._scoreless_candidates(candidates),
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
                "timeSearchMustStayWithinReportedWindow": (
                    birth_input_context.get("constraints") or {}
                ).get("timeSearchMustStayWithinReportedWindow", True),
                "placeSearchMustStayWithinRadiusKm": (
                    birth_input_context.get("constraints") or {}
                ).get("placeSearchMustStayWithinRadiusKm", True),
                "rejectRectificationOutsideUserFacts": (
                    birth_input_context.get("constraints") or {}
                ).get("rejectRectificationOutsideUserFacts", True),
            },
        }

    def update_from_feedback(
        self,
        state: dict[str, Any],
        prevalidation_markdown: str,
        feedback_markdown: str,
        prevalidation_result: dict[str, Any],
    ) -> dict[str, Any]:
        next_state = copy.deepcopy(state)
        anchors = self._parse_candidate_anchors(prevalidation_markdown, feedback_markdown)
        candidates = self._reset_candidate_scores(next_state.get("candidates"))
        by_id = {str(candidate.get("candidateId")): candidate for candidate in candidates}
        contract_errors = self.validate_prevalidation_contract(next_state, prevalidation_markdown)

        candidate_bound_count = 0
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
        next_round = int(next_state.get("rectificationRound") or 0) + 1
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

        next_state.update(
            {
                "revision": int(next_state.get("revision") or 0) + 1,
                "rectificationRound": next_round,
                "updatedAt": self._now(),
                "status": status,
                "selectedCandidateId": selected.get("candidateId") if selected else None,
                "selectionConfidence": confidence,
                "candidateBoundAnchorCount": candidate_bound_count,
                "feedbackAnchorCount": len(anchors),
                "candidates": candidates,
                "feedbackAnchors": anchors,
                "roundHistory": round_history,
                "anchorContractErrors": contract_errors,
                "reportGate": gate,
            }
        )
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
            if member.get("axis") == "place" and isinstance(coordinates, dict):
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
    def _reset_candidate_scores(raw_candidates: object) -> list[dict[str, Any]]:
        candidates = raw_candidates if isinstance(raw_candidates, list) else []
        result = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            item = copy.deepcopy(candidate)
            item["score"] = 0.0
            item["support"] = 0
            item["reject"] = 0
            result.append(item)
        return result

    @staticmethod
    def _round_history(state: dict[str, Any]) -> list[dict[str, Any]]:
        history = state.get("roundHistory")
        if not isinstance(history, list):
            return []
        return [copy.deepcopy(item) for item in history if isinstance(item, dict)]

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
                    "answer": answers.get(index, "pending"),
                }
            )
        return parsed

    @staticmethod
    def _statement_from_anchor_block(block: str) -> str:
        statement = re.sub(
            r"(?m)^>\s*(?:推导|Derivation|根拠|Candidate|候选盘|候選盤|Field|Fields|字段|不稳定字段)\s*[：:].*$",
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
