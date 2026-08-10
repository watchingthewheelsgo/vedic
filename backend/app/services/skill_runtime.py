from __future__ import annotations

import asyncio
import copy
from contextlib import asynccontextmanager
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows deployments use the in-process lock.
    fcntl = None  # type: ignore[assignment]

from app.agents.claude_runtime import ClaudeRuntime
from app.calculator.civil_time import resolve_civil_time
from app.schemas import (
    BaziSessionInput,
    BirthInput,
    ConsultationAnswerResponse,
    ConsultationConversationResponse,
    ConsultationQuestionInput,
    RectificationConfirmationInput,
    RectificationInterviewInput,
    RectificationLifeEventsInput,
    RectificationLifeEventsResetInput,
    SkillBirthInput,
    SkillRunInput,
    SkillSessionResponse,
    SynastryBirthInput,
)
from app.services.chart_rectification import ChartRectificationService
from app.services.life_event_rectification import MAX_RECTIFICATION_EVENTS
from app.services.metadata_store import MetadataStore
from app.services.rectification_interview import (
    build_rectification_interview,
    validate_agent_event_evidence,
    validate_agent_question_wording,
    validate_rectification_event_bindings,
    validate_rectification_event_dates,
    validate_rectification_episode_independence,
)
from app.services.skill_workspace import SkillWorkspace
from app.services.vedic_calculator import ChartRecordIdentity, VedicCalculator
from app.tools.registry import BackendToolRunner
from app.utils.ids import make_id
from app.vedicdust.models import (
    CandidateInterval,
    ChartRecord,
    ClaimGraph,
    ConfidenceGrade,
    ConsultationDossier,
    JudgementContext,
    ReadingSession,
    RectificationRoundRecord,
    TimeRange,
)
from app.vedicdust.judgement import build_judgement_context
from app.vedicdust.claims import build_claim_graph
from app.vedicdust.orchestrator import audit_chart_record
from app.vedicdust.reporting import (
    build_agent_context,
    build_report_manifest,
    materialize_consultation_dossier,
    render_consultation_report,
)
from app.vedicdust.source_registry import load_rule_catalog
from app.vedicdust.synastry import build_synastry_context
from app.vedicdust.validation import (
    validate_agent_context,
    validate_claim_graph,
    validate_consultation_dossier,
    validate_consumer_astrology_language,
    validate_judgement_context,
)

CHART_RECORD_JSON = "chart_record.json"
READING_SESSION_JSON = "reading_session.json"
CHART_AUDIT_JSON = "chart_audit.json"
JUDGEMENT_CONTEXT_JSON = "judgement_context.json"
CLAIM_GRAPH_JSON = "claim_graph.json"
CONSULTATION_DOSSIER_JSON = "consultation_dossier.json"
CONSULTATION_REPORT_MANIFEST_JSON = "consultation_report_manifest.json"
AGENT_CONTEXT_JSON = "agent_context.json"
CONSULTATION_REPORT_MD = "consultation_report.md"
ACTIVE_CHART_SENSITIVITY_JSON = "active_chart_sensitivity.json"
RECTIFICATION_INTERVIEW_JSON = "rectification_interview.json"
LIFE_EVENT_EVIDENCE_VALIDATION_JSON = "life_event_evidence_validation.json"
CONSULTATION_GROUNDING_AUDIT_JSON = "consultation_grounding_audit.json"
CHART_RECORD_B_JSON = "chart_record_B.json"
SYNASTRY_CONTEXT_JSON = "synastry_context.json"
PREVALIDATION_DEPENDENCY_PATHS = [
    CHART_RECORD_JSON,
    "sensitivity_scan.json",
    "reader_prevalidation.md",
    "user_context.md",
]


def _rectification_event_fingerprint(event: dict[str, Any]) -> str:
    date_value = " ".join(str(event.get("date") or "").split())
    category = str(event.get("category") or "").strip().casefold()
    event_subtype = str(event.get("eventSubtype") or "").strip().casefold()
    description = " ".join(str(event.get("description") or "").split())
    prefix = f"{date_value} {category}:"
    if description.casefold().startswith(prefix):
        description = description[len(prefix) :].strip()
    payload = json.dumps(
        [date_value, category, event_subtype, description.casefold()],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _merge_rectification_semantics(
    previous: Any,
    additions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in previous if isinstance(previous, list) else []:
        if not isinstance(item, dict):
            continue
        key = _rectification_event_fingerprint(item)
        if key:
            merged[key] = dict(item)
    for item in additions:
        if not isinstance(item, dict):
            continue
        key = _rectification_event_fingerprint(item)
        if key:
            merged[key] = dict(item)
    return list(merged.values())


READER_AGENT_INPUT_ARTIFACTS = frozenset(
    {
        CHART_RECORD_JSON,
        "chart_audit.json",
        "birth_input_context.json",
        "sensitivity_scan.json",
        "chart_rectification_state.json",
        "prevalidation_result.json",
        "user_context.md",
    }
)


@dataclass(frozen=True)
class _AgentWorkspaceSnapshot:
    files: dict[str, bytes]
    writable_files: dict[str, bytes | None]


class SkillRuntime:
    """Web adapter for repo-local astrology skill file workflows."""

    def __init__(
        self,
        calculator: VedicCalculator,
        workspace: SkillWorkspace,
        agent_runtime: ClaudeRuntime,
        metadata_store: MetadataStore | None = None,
    ) -> None:
        self.calculator = calculator
        self.workspace = workspace
        self.agent_runtime = agent_runtime
        self.metadata_store = metadata_store
        self.tools = BackendToolRunner(workspace.settings)
        self.rectification = ChartRectificationService()
        self._rectification_lock_guard = asyncio.Lock()
        self._rectification_locks: dict[str, asyncio.Lock] = {}

    async def _rectification_lock_for(self, session_id: str) -> asyncio.Lock:
        async with self._rectification_lock_guard:
            lock = self._rectification_locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._rectification_locks[session_id] = lock
            return lock

    @asynccontextmanager
    async def _rectification_transaction_lock(self, session_id: str):
        """Serialize rectification writes in-process and across workers on Unix."""

        lock = await self._rectification_lock_for(session_id)
        async with lock:
            lock_handle = None
            try:
                lock_path = (
                    self.workspace.require_session_dir(session_id) / ".runtime/rectification.lock"
                )
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                lock_handle = lock_path.open("a+")
                if fcntl is not None:
                    while True:
                        try:
                            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            await asyncio.sleep(0.05)
                yield
            finally:
                if lock_handle is not None:
                    if fcntl is not None:
                        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                    lock_handle.close()

    def _write_agent_prompt_trace(
        self,
        session_id: str,
        run_id: str,
        attempt: int,
        prompt: str,
    ) -> tuple[str, str]:
        prompt_path = f".runtime/prompts/{run_id}/attempt-{attempt:02d}.md"
        self.workspace.write_artifact(session_id, prompt_path, prompt)
        return prompt_path, hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def _persist_agent_run_trace(
        self,
        session_id: str,
        scope_kind: str,
        scope_id: str,
        execution: dict[str, object],
    ) -> None:
        safe_scope = re.sub(r"[^a-zA-Z0-9._-]+", "-", scope_id).strip("-") or "unknown"
        path = f".runtime/agent-runs/{scope_kind}/{safe_scope}.json"
        existing = self._json_dict(self.workspace.read_artifact_text(session_id, path) or "")
        raw_attempts = execution.get("attempts")
        attempts = raw_attempts if isinstance(raw_attempts, list) else []
        stored_execution = {
            **execution,
            "attemptCount": len(attempts),
            "retryCount": max(0, len(attempts) - 1),
            "finalStatus": (
                str(attempts[-1].get("status"))
                if attempts and isinstance(attempts[-1], dict)
                else "unknown"
            ),
        }
        raw_executions = existing.get("executions")
        executions = (
            [
                item
                for item in raw_executions
                if isinstance(item, dict) and item.get("runId") != stored_execution.get("runId")
            ]
            if isinstance(raw_executions, list)
            else []
        )
        executions.append(stored_execution)
        payload = {
            "schemaVersion": "vedicdust-agent-run-trace/1.0.0",
            "scopeKind": scope_kind,
            "scopeId": scope_id,
            "executions": executions[-20:],
        }
        self.workspace.write_artifact(
            session_id,
            path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            path,
            producer="vedicdust-consultation-qa",
            dependency_paths=[AGENT_CONTEXT_JSON],
        )

    @staticmethod
    def _agent_result_trace(result: object) -> dict[str, object]:
        return {
            "sdkSessionId": getattr(result, "session_id", None),
            "durationMs": getattr(result, "duration_ms", None),
            "totalCostUsd": getattr(result, "total_cost_usd", None),
            "stopReason": getattr(result, "stop_reason", None),
            "model": getattr(result, "model", None),
            "mode": getattr(result, "mode", None),
        }

    async def create_reader_session(
        self, input_data: SkillBirthInput, *, owner_user_id: str | None = None
    ) -> SkillSessionResponse:
        session_id = make_id("session")
        started = datetime.now(timezone.utc)
        identity = ChartRecordIdentity(
            reading_session_id=session_id,
            chart_record_id=make_id("chart"),
            subject_id=make_id("subject"),
        )
        calculation = self.calculator.calculate(input_data, identity=identity)
        self.workspace.create_session(session_id)
        finished = datetime.now(timezone.utc)
        self.workspace.write_artifact(
            session_id,
            "birth_input_context.json",
            calculation.birth_input_context_json,
        )
        self.workspace.write_artifact(
            session_id,
            "sensitivity_scan.json",
            calculation.sensitivity_scan_json,
        )
        self.workspace.write_artifact(
            session_id,
            CHART_RECORD_JSON,
            calculation.chart_record_json,
        )
        updated_state = self._write_initial_rectification_state(
            session_id,
            calculation.birth_input_context_json,
            calculation.sensitivity_scan_json,
        )
        current_artifacts = {
            artifact.path: artifact.content
            for artifact in self.workspace.read_artifacts(session_id, include_internal=True)
        }
        updated_state = self._materialize_rectification_selection(
            session_id,
            updated_state,
            current_artifacts,
        )
        self.workspace.write_artifact(
            session_id,
            "chart_rectification_state.json",
            json.dumps(updated_state, ensure_ascii=False, indent=2) + "\n",
        )
        self._sync_chart_record_rectification(session_id, updated_state)
        updated_state = await self._prepare_rectification_confirmation_examples(
            session_id,
            updated_state,
        )
        self.workspace.write_artifact(
            session_id,
            "chart_rectification_state.json",
            json.dumps(updated_state, ensure_ascii=False, indent=2) + "\n",
        )
        self._checkpoint_active_chart_sensitivity(session_id)
        updated_chart_record = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON)
        if updated_chart_record is None:
            raise ValueError("initial chart setup did not persist chart_record.json")
        self._write_reading_session(
            session_id,
            identity=identity,
            locale=self.workspace.read_session_locale(session_id),
            stage="chart_ready",
            rectification_status=self._chart_rectification_status(updated_chart_record),
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            READING_SESSION_JSON,
            producer="vedicdust-reading-orchestrator",
        )
        self.workspace.write_artifact(
            session_id,
            "run_metrics.json",
            json.dumps(
                {
                    "sessionId": session_id,
                    "status": "calculator_complete",
                    "calculator": {
                        "startedAt": started.isoformat(),
                        "finishedAt": finished.isoformat(),
                        "durationSeconds": round((finished - started).total_seconds(), 3),
                    },
                    "waves": [],
                    "nodes": [],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        self.workspace.write_session_manifest(session_id, locale=input_data.locale)
        self.workspace.mark_artifact_checkpoint(
            session_id, "birth_input_context.json", producer="calculator"
        )
        self.workspace.mark_artifact_checkpoint(
            session_id, "sensitivity_scan.json", producer="calculator"
        )
        self.workspace.mark_artifact_checkpoint(
            session_id, CHART_RECORD_JSON, producer="vedicdust-chart-calculation"
        )
        self.workspace.mark_artifact_checkpoint(
            session_id, READING_SESSION_JSON, producer="vedicdust-reading-orchestrator"
        )
        self.workspace.mark_artifact_checkpoint(
            session_id, CHART_AUDIT_JSON, producer="vedicdust-chart-audit"
        )
        self.workspace.mark_artifact_checkpoint(
            session_id, "chart_rectification_state.json", producer="chart-rectification"
        )
        await self._sync_metadata(
            session_id, stage="reader_ready", status="draft", owner_user_id=owner_user_id
        )

        chat_message = (
            "Your chart data is ready.\n\n"
            "Next, the system will prepare a few pre-reading checkpoints for you to confirm."
        )
        return SkillSessionResponse(
            session_id=session_id,
            stage="reader_ready",
            chat_message=chat_message,
            artifacts=self.workspace.read_artifacts(session_id),
            active_artifact="birth_input_context.json",
        )

    async def record_rectification_life_events(
        self,
        input_data: RectificationLifeEventsInput,
        *,
        owner_user_id: str | None = None,
    ) -> SkillSessionResponse:
        async with self._rectification_transaction_lock(input_data.session_id):
            return await self._record_rectification_life_events(
                input_data,
                owner_user_id=owner_user_id,
            )

    async def _record_rectification_life_events(
        self,
        input_data: RectificationLifeEventsInput,
        *,
        owner_user_id: str | None = None,
    ) -> SkillSessionResponse:
        session_id = input_data.session_id
        artifacts = {
            artifact.path: artifact.content
            for artifact in self.workspace.read_artifacts(session_id, include_internal=True)
        }
        context = self._json_dict(artifacts.get("birth_input_context.json", ""))
        record_payload = self._json_dict(artifacts.get(CHART_RECORD_JSON, ""))
        state = self._json_dict(artifacts.get("chart_rectification_state.json", ""))
        if not context or not record_payload or not state:
            raise ValueError("session is missing the chart inputs required to add life events")
        current_record = ChartRecord.model_validate_json(artifacts[CHART_RECORD_JSON])
        submitted_events = [event.model_dump(by_alias=True) for event in input_data.events]
        mutation_key = (
            input_data.idempotency_key
            or hashlib.sha256(
                json.dumps(
                    sorted(_rectification_event_fingerprint(event) for event in submitted_events),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
        )
        mutation_ledger = state.get("rectificationMutations")
        existing_mutation = (
            next(
                (
                    item
                    for item in mutation_ledger
                    if isinstance(item, dict) and item.get("key") == mutation_key
                ),
                None,
            )
            if isinstance(mutation_ledger, list)
            else None
        )
        submitted_fingerprints = {
            _rectification_event_fingerprint(event) for event in submitted_events
        }
        if isinstance(existing_mutation, dict):
            stored_fingerprints = {
                str(value)
                for value in existing_mutation.get("eventFingerprints") or []
                if str(value).strip()
            }
            if stored_fingerprints == submitted_fingerprints:
                return self.load_session(session_id)
            raise ValueError("idempotency key was already used for different life events")
        life_event_context = context.get("lifeEvents")
        life_event_context = life_event_context if isinstance(life_event_context, dict) else {}
        existing_event_fingerprints = {
            _rectification_event_fingerprint(item)
            for item in life_event_context.get("events", [])
            if isinstance(item, dict)
        }
        if all(
            _rectification_event_fingerprint(event) in existing_event_fingerprints
            for event in submitted_events
        ):
            return self.load_session(session_id)
        if (
            input_data.expected_chart_revision is not None
            and input_data.expected_chart_revision != current_record.revision
        ):
            raise ValueError(
                "This verification question is outdated. Refresh the session before answering."
            )

        plan = state.get("rectificationPlan")
        plan = plan if isinstance(plan, dict) else {}
        if plan.get("eventCollectionRequired") is not True:
            raise ValueError("this rectification session does not require more life events")
        state_ledger = state.get("lifeEventLedger")
        state_ledger = state_ledger if isinstance(state_ledger, dict) else {}
        independent_episode_count = int(
            state_ledger.get("independentEpisodeCount")
            or state_ledger.get("eligibleEventCount")
            or 0
        )
        if independent_episode_count >= MAX_RECTIFICATION_EVENTS:
            raise ValueError("this rectification session has reached its independent event limit")

        raw_time_context = context.get("time")
        time_context = (
            cast(dict[str, Any], raw_time_context) if isinstance(raw_time_context, dict) else {}
        )
        validate_rectification_event_dates(
            submitted_events,
            birth_date=str(time_context.get("date") or ""),
        )
        interview = self._json_dict(artifacts.get(RECTIFICATION_INTERVIEW_JSON, ""))
        if not interview:
            raise ValueError("the current rectification interview is missing or expired")
        new_events = validate_rectification_event_bindings(
            submitted_events,
            state=state,
            interview=interview,
        )
        validate_rectification_episode_independence(
            new_events,
            existing_events=[
                item for item in state_ledger.get("events", []) if isinstance(item, dict)
            ],
        )
        evidence_validation = await self._validate_rectification_event_evidence(new_events)
        latest_record_text = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON)
        latest_record = (
            ChartRecord.model_validate_json(latest_record_text) if latest_record_text else None
        )
        if latest_record is None or latest_record.revision != current_record.revision:
            raise ValueError(
                "The chart changed while this answer was being verified. Refresh and answer the current question."
            )
        self.workspace.write_artifact(
            session_id,
            LIFE_EVENT_EVIDENCE_VALIDATION_JSON,
            json.dumps(evidence_validation, ensure_ascii=False, indent=2) + "\n",
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            LIFE_EVENT_EVIDENCE_VALIDATION_JSON,
            producer="vedicdust-rectification-evidence-validator",
            dependency_paths=[RECTIFICATION_INTERVIEW_JSON],
        )

        revision = current_record.revision + 1
        previous_life_events = context.get("lifeEvents")
        previous_life_events = (
            previous_life_events if isinstance(previous_life_events, dict) else {}
        )
        previous_raw_events = str(previous_life_events.get("raw") or "").strip()
        submitted_raw_events = input_data.ledger_text().strip()
        combined_life_events = "\n".join(
            value for value in (previous_raw_events, submitted_raw_events) if value
        )
        semantic_evidence = _merge_rectification_semantics(
            context.get("lifeEventSemantics"),
            evidence_validation.get("results")
            if isinstance(evidence_validation.get("results"), list)
            else [],
        )
        birth_input = self.rectification.birth_input_with_life_events(
            context,
            record_payload,
            combined_life_events,
        )
        birth_input.life_event_facts = json.dumps(semantic_evidence, ensure_ascii=False)
        identity = self._chart_record_identity(session_id, revision=revision)
        calculation = self.calculator.calculate(birth_input, identity=identity)
        updated_context = self._json_dict(calculation.birth_input_context_json)
        event_ledger = updated_context.get("lifeEvents")
        if (
            not isinstance(event_ledger, dict)
            or int(
                event_ledger.get("independentEpisodeCount")
                or event_ledger.get("eligibleEventCount")
                or 0
            )
            < 1
        ):
            raise ValueError("at least one independent, dated life episode is required")

        self._archive_current_chart_artifacts(session_id, current_record.revision, artifacts)
        session_dir = self.workspace.require_session_dir(session_id)
        for stale_path in [
            "reader_prevalidation.md",
            "prevalidation_result.json",
            "user_context.md",
            "rectification_question_set.json",
            "rectification_answer_batch.json",
            RECTIFICATION_INTERVIEW_JSON,
            ACTIVE_CHART_SENSITIVITY_JSON,
        ]:
            (session_dir / stale_path).unlink(missing_ok=True)
        self._write_chart_calculation(
            session_id,
            calculation.birth_input_context_json,
            calculation.sensitivity_scan_json,
            calculation.chart_record_json,
            producer="calculator:life-event-evidence",
            identity=identity,
        )
        updated_state = self._write_initial_rectification_state(
            session_id,
            calculation.birth_input_context_json,
            calculation.sensitivity_scan_json,
        )
        skipped_categories = state.get("skippedRectificationCategories")
        if isinstance(skipped_categories, list):
            updated_state["skippedRectificationCategories"] = [
                str(category) for category in skipped_categories if str(category).strip()
            ]
        available_categories = state.get("availableRectificationCategories")
        if isinstance(available_categories, list):
            updated_state["availableRectificationCategories"] = [
                str(category) for category in available_categories if str(category).strip()
            ]
        prior_mutations = state.get("rectificationMutations")
        prior_mutations = prior_mutations if isinstance(prior_mutations, list) else []
        updated_state["rectificationMutations"] = [
            *[
                item
                for item in prior_mutations[-19:]
                if isinstance(item, dict) and str(item.get("key") or "").strip()
            ],
            {
                "key": mutation_key,
                "chartRevision": revision,
                "eventFingerprints": [
                    _rectification_event_fingerprint(event) for event in submitted_events
                ],
            },
        ]
        current_artifacts = {
            artifact.path: artifact.content
            for artifact in self.workspace.read_artifacts(session_id, include_internal=True)
        }
        updated_state = self._materialize_rectification_selection(
            session_id,
            updated_state,
            current_artifacts,
        )
        active_chart_revision = updated_state.get("activeChartRevision")
        active_chart_revision = (
            active_chart_revision if isinstance(active_chart_revision, dict) else {}
        )
        updated_state = self.rectification.record_evidence_round(
            state,
            updated_state,
            submitted_events=submitted_events,
            chart_revision=int(active_chart_revision.get("revision") or revision),
        )
        self.workspace.write_artifact(
            session_id,
            "chart_rectification_state.json",
            json.dumps(updated_state, ensure_ascii=False, indent=2) + "\n",
        )
        self._sync_chart_record_rectification(session_id, updated_state)
        updated_state = await self._prepare_rectification_confirmation_examples(
            session_id,
            updated_state,
        )
        self.workspace.write_artifact(
            session_id,
            "chart_rectification_state.json",
            json.dumps(updated_state, ensure_ascii=False, indent=2) + "\n",
        )
        self._checkpoint_active_chart_sensitivity(session_id)
        updated_chart_record = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON)
        if updated_chart_record is None:
            raise ValueError("life-event recalculation did not persist chart_record.json")
        active_record = ChartRecord.model_validate_json(updated_chart_record)
        active_identity = ChartRecordIdentity(
            reading_session_id=session_id,
            chart_record_id=active_record.chart_record_id,
            subject_id=active_record.subject.subject_id,
            revision=active_record.revision,
        )
        self._write_reading_session(
            session_id,
            identity=active_identity,
            locale=self.workspace.read_session_locale(session_id),
            stage="rectification",
            rectification_status=self._chart_rectification_status(updated_chart_record),
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            READING_SESSION_JSON,
            producer="vedicdust-reading-orchestrator",
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            "chart_rectification_state.json",
            producer="chart-rectification:life-event-evidence",
        )
        self.workspace.write_session_manifest(
            session_id,
            locale=self.workspace.read_session_locale(session_id),
        )
        await self._sync_metadata(
            session_id,
            stage="reader_ready",
            status="draft",
            owner_user_id=owner_user_id,
        )
        return SkillSessionResponse(
            session_id=session_id,
            stage="reader_ready",
            chat_message=(
                "Your dated life events are saved. The system can now compare the bounded "
                "birth-time candidates."
            ),
            artifacts=self.workspace.read_artifacts(session_id),
            active_artifact="chart_rectification_state.json",
        )

    async def reset_rectification_life_events(
        self,
        input_data: RectificationLifeEventsResetInput,
        *,
        owner_user_id: str | None = None,
    ) -> SkillSessionResponse:
        async with self._rectification_transaction_lock(input_data.session_id):
            session_id = input_data.session_id
            artifacts = {
                artifact.path: artifact.content
                for artifact in self.workspace.read_artifacts(session_id, include_internal=True)
            }
            context = self._json_dict(artifacts.get("birth_input_context.json", ""))
            record_payload = self._json_dict(artifacts.get(CHART_RECORD_JSON, ""))
            state = self._json_dict(artifacts.get("chart_rectification_state.json", ""))
            if not context or not record_payload or not state:
                raise ValueError(
                    "session is missing the chart inputs required to reset life events"
                )
            if state.get("status") not in {
                "collecting_evidence",
                "underdetermined",
                "rectification_confirmation_required",
            }:
                raise ValueError("this session is not accepting rectification evidence changes")
            current_record = ChartRecord.model_validate_json(artifacts[CHART_RECORD_JSON])
            if (
                input_data.expected_chart_revision is not None
                and input_data.expected_chart_revision != current_record.revision
            ):
                raise ValueError("This chart changed. Refresh the session before restarting.")

            birth_input = self.rectification.birth_input_with_life_events(
                context,
                record_payload,
                "",
            )
            birth_input.life_event_facts = "[]"
            revision = current_record.revision + 1
            identity = self._chart_record_identity(session_id, revision=revision)
            calculation = self.calculator.calculate(birth_input, identity=identity)

            self._archive_current_chart_artifacts(
                session_id,
                current_record.revision,
                artifacts,
            )
            session_dir = self.workspace.require_session_dir(session_id)
            for stale_path in [
                "reader_prevalidation.md",
                "prevalidation_result.json",
                "user_context.md",
                "rectification_question_set.json",
                "rectification_answer_batch.json",
                RECTIFICATION_INTERVIEW_JSON,
                LIFE_EVENT_EVIDENCE_VALIDATION_JSON,
                ACTIVE_CHART_SENSITIVITY_JSON,
            ]:
                (session_dir / stale_path).unlink(missing_ok=True)
            self._write_chart_calculation(
                session_id,
                calculation.birth_input_context_json,
                calculation.sensitivity_scan_json,
                calculation.chart_record_json,
                producer="calculator:life-event-reset",
                identity=identity,
            )
            updated_state = self._write_initial_rectification_state(
                session_id,
                calculation.birth_input_context_json,
                calculation.sensitivity_scan_json,
            )
            updated_state["rectificationMutations"] = []
            self.workspace.write_artifact(
                session_id,
                "chart_rectification_state.json",
                json.dumps(updated_state, ensure_ascii=False, indent=2) + "\n",
            )
            self._sync_chart_record_rectification(session_id, updated_state)
            self._checkpoint_active_chart_sensitivity(session_id)

            updated_record_text = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON)
            if not updated_record_text:
                raise ValueError("life-event reset did not persist chart_record.json")
            updated_record = ChartRecord.model_validate_json(updated_record_text)
            active_identity = ChartRecordIdentity(
                reading_session_id=session_id,
                chart_record_id=updated_record.chart_record_id,
                subject_id=updated_record.subject.subject_id,
                revision=updated_record.revision,
            )
            self._write_reading_session(
                session_id,
                identity=active_identity,
                locale=self.workspace.read_session_locale(session_id),
                stage="rectification",
                rectification_status=self._chart_rectification_status(updated_record_text),
            )
            self.workspace.mark_artifact_checkpoint(
                session_id,
                READING_SESSION_JSON,
                producer="vedicdust-reading-orchestrator",
            )
            self.workspace.mark_artifact_checkpoint(
                session_id,
                "chart_rectification_state.json",
                producer="chart-rectification:life-event-reset",
            )
            self.workspace.write_session_manifest(
                session_id,
                locale=self.workspace.read_session_locale(session_id),
            )
            await self._sync_metadata(
                session_id,
                stage="reader_ready",
                status="draft",
                owner_user_id=owner_user_id,
            )
            return SkillSessionResponse(
                session_id=session_id,
                stage="reader_ready",
                chat_message="The previous verification events were cleared. Start again with one dated event.",
                artifacts=self.workspace.read_artifacts(session_id),
                active_artifact="chart_rectification_state.json",
            )

    async def _prepare_rectification_confirmation_examples(
        self,
        session_id: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """Keep confirmation grounded in submitted events and deterministic scores.

        Generating new retrospective events from finalized timing periods creates
        unverified claims. The Agent therefore has no production role at this
        gate until each example can reference a backend-released claim.
        """

        _ = session_id
        return state

    async def confirm_rectification_result(
        self,
        input_data: RectificationConfirmationInput,
        *,
        owner_user_id: str | None = None,
    ) -> SkillSessionResponse:
        async with self._rectification_transaction_lock(input_data.session_id):
            session_id = input_data.session_id
            state = self._json_dict(
                self.workspace.read_artifact_text(session_id, "chart_rectification_state.json")
                or ""
            )
            if state.get("status") != "rectification_confirmation_required":
                raise ValueError("this session is not waiting for a rectification confirmation")
            conclusion = state.get("rectificationConclusion")
            if not isinstance(conclusion, dict):
                raise ValueError("rectification conclusion is missing or expired")
            chart_record_text = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON)
            if not chart_record_text:
                raise ValueError("session is missing the recalculated chart")
            chart_record = ChartRecord.model_validate_json(chart_record_text)
            active_chart_revision = state.get("activeChartRevision")
            active_chart_revision = (
                active_chart_revision if isinstance(active_chart_revision, dict) else {}
            )
            active_revision = int(active_chart_revision.get("revision") or chart_record.revision)
            if input_data.expected_chart_revision is not None and (
                input_data.expected_chart_revision != chart_record.revision
                or input_data.expected_chart_revision != active_revision
            ):
                raise ValueError("This rectification conclusion is outdated. Refresh the session.")
            if int(conclusion.get("chartRevision") or 0) != chart_record.revision:
                raise ValueError(
                    "rectification conclusion does not belong to the active chart revision"
                )
            examples = conclusion.get("examples")
            if not isinstance(examples, list) or not examples:
                raise ValueError("rectification conclusion has no confirmation examples")
            expected_ids = {
                str(example.get("exampleId") or "")
                for example in examples
                if isinstance(example, dict) and example.get("exampleId")
            }
            responses = [
                {
                    "exampleId": response.example_id,
                    "answer": response.answer,
                    "note": response.note.strip(),
                }
                for response in input_data.responses
            ]
            response_ids = {str(item["exampleId"]) for item in responses}
            if response_ids != expected_ids:
                raise ValueError(
                    "Please answer each rectification confirmation example exactly once."
                )

            next_state = copy.deepcopy(state)
            next_conclusion = copy.deepcopy(conclusion)
            has_inaccurate = any(item["answer"] == "inaccurate" for item in responses)
            has_partly = any(item["answer"] == "partly" for item in responses)
            next_conclusion["confirmation"] = {
                "status": "rejected"
                if has_inaccurate
                else "confirmed_with_caveat"
                if has_partly
                else "confirmed",
                "responses": responses,
            }
            next_conclusion["status"] = "rejected" if has_inaccurate else "confirmed"
            next_state["rectificationConclusion"] = next_conclusion
            generation = conclusion.get("generation")
            generation = generation if isinstance(generation, dict) else {}
            input_review_only = generation.get("source") == "deterministic_input_review"
            if has_inaccurate:
                ledger = next_state.get("lifeEventLedger")
                ledger = ledger if isinstance(ledger, dict) else {}
                next_state["lifeEventLedger"] = ledger
                self.rectification._set_additional_event_request(next_state)
                can_collect_more = ledger.get("eventCollectionRequired") is True
                next_state.update(
                    {
                        "revision": int(next_state.get("revision") or 0) + 1,
                        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "status": "underdetermined",
                        "provisionalCandidateId": next_state.get("selectedCandidateId"),
                        "selectedCandidateId": None,
                        "selectionConfidence": "none",
                        "reportGate": {
                            "fullReportAllowed": False,
                            "reason": (
                                "The user did not accept the corrected time interval. The system will "
                                "not force the chart; provide one new dated event or review the "
                                "reported birth time."
                                if can_collect_more
                                else "The user did not accept the corrected time interval and the "
                                "maximum independent evidence set has already been reached. The "
                                "system will preserve an inconclusive result until the reported "
                                "birth window is reviewed."
                            ),
                            "nextStep": (
                                "provide_more_precise_or_additional_event_evidence"
                                if can_collect_more
                                else "review_reported_birth_window_or_stop"
                            ),
                        },
                    }
                )
                message = (
                    "Thanks for checking. The corrected interval was not accepted, so the chart will "
                    "not be forced. Add one new dated event to continue the birth-time check."
                    if can_collect_more
                    else "The corrected interval was not accepted and the maximum independent "
                    "evidence set has been reached. Review the reported birth window before "
                    "continuing."
                )
            else:
                report_reason = (
                    "The bounded candidate passed the dated-event and reserved-holdout checks "
                    "and was recalculated. The user retained the bounded interval with an "
                    "explicit uncertainty caveat; the report must use only interval-stable facts "
                    "and must not present the representative minute as exact."
                    if has_partly
                    else (
                        "The bounded candidate passed the dated-event and reserved-holdout "
                        "checks and was recalculated. The user acknowledged the bounded result; "
                        "this acknowledgement did not increase selection confidence."
                        if input_review_only
                        else "The bounded candidate passed and the corrected interval was acknowledged."
                    )
                )
                next_state.update(
                    {
                        "revision": int(next_state.get("revision") or 0) + 1,
                        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "status": "corrected_chart_ready",
                        "reportGate": {
                            "fullReportAllowed": True,
                            "reason": report_reason,
                            "nextStep": "full_report",
                        },
                    }
                )
                message = (
                    "The bounded birth-time range is retained with your uncertainty note. "
                    "The report will use only conclusions stable across that range."
                    if has_partly
                    else "The corrected birth-time checkpoint is confirmed. The full Vedic report can now begin."
                )
            next_state["rectificationPlan"] = self.rectification._build_rectification_plan(
                next_state
            )
            return await self._persist_rectification_state(
                session_id,
                next_state,
                message=message,
                owner_user_id=owner_user_id,
            )

    async def _persist_rectification_state(
        self,
        session_id: str,
        state: dict[str, Any],
        *,
        message: str,
        owner_user_id: str | None,
    ) -> SkillSessionResponse:
        session_dir = self.workspace.require_session_dir(session_id)
        (session_dir / RECTIFICATION_INTERVIEW_JSON).unlink(missing_ok=True)
        self.workspace.write_artifact(
            session_id,
            "chart_rectification_state.json",
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        )
        self._sync_chart_record_rectification(session_id, state)
        self.workspace.mark_artifact_checkpoint(
            session_id,
            "chart_rectification_state.json",
            producer="vedicdust-rectification-confirmation",
        )
        record_text = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON)
        if not record_text:
            raise ValueError("rectification confirmation did not persist chart_record.json")
        record = ChartRecord.model_validate_json(record_text)
        identity = ChartRecordIdentity(
            reading_session_id=session_id,
            chart_record_id=record.chart_record_id,
            subject_id=record.subject.subject_id,
            revision=record.revision,
        )
        self._write_reading_session(
            session_id,
            identity=identity,
            locale=self.workspace.read_session_locale(session_id),
            stage="rectification",
            rectification_status=self._chart_rectification_status(record_text),
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            READING_SESSION_JSON,
            producer="vedicdust-reading-orchestrator",
        )
        self.workspace.write_session_manifest(
            session_id,
            locale=self.workspace.read_session_locale(session_id),
        )
        await self._sync_metadata(
            session_id,
            stage="reader_ready",
            status="draft",
            owner_user_id=owner_user_id,
        )
        return SkillSessionResponse(
            session_id=session_id,
            stage="reader_ready",
            chat_message=message,
            artifacts=self.workspace.read_artifacts(session_id),
            active_artifact="chart_rectification_state.json",
        )

    async def prepare_rectification_interview(
        self,
        input_data: RectificationInterviewInput,
        *,
        owner_user_id: str | None = None,
        use_agent: bool = True,
    ) -> SkillSessionResponse:
        async with self._rectification_transaction_lock(input_data.session_id):
            return await self._prepare_rectification_interview(
                input_data,
                owner_user_id=owner_user_id,
                use_agent=use_agent,
            )

    async def _prepare_rectification_interview(
        self,
        input_data: RectificationInterviewInput,
        *,
        owner_user_id: str | None = None,
        use_agent: bool = True,
    ) -> SkillSessionResponse:
        session_id = input_data.session_id
        state_text = self.workspace.read_artifact_text(session_id, "chart_rectification_state.json")
        if not state_text:
            raise ValueError("session is missing chart rectification state")
        state = self._json_dict(state_text)
        plan = state.get("rectificationPlan")
        plan = plan if isinstance(plan, dict) else {}
        if (
            state.get("status") == "underdetermined"
            and plan.get("eventCollectionRequired") is not True
        ):
            raise ValueError("this rectification session has no remaining adaptive interview round")
        if state.get("status") not in {"collecting_evidence", "underdetermined"}:
            raise ValueError("this session does not require a rectification interview")

        skipped_categories = {
            str(category)
            for category in (state.get("skippedRectificationCategories") or [])
            if str(category).strip()
        }
        available_categories = {
            str(category)
            for category in (state.get("availableRectificationCategories") or [])
            if str(category).strip()
        }
        current_interview = self._json_dict(
            self.workspace.read_artifact_text(session_id, RECTIFICATION_INTERVIEW_JSON) or ""
        )
        if input_data.reset_skipped:
            skipped_categories.clear()
        elif input_data.skipped_category:
            if not input_data.current_question_id:
                raise ValueError("skipping a question requires its current question id")
            current_question = next(
                (
                    item
                    for item in current_interview.get("questions", [])
                    if isinstance(item, dict)
                    and item.get("questionId") == input_data.current_question_id
                ),
                None,
            )
            if not isinstance(current_question, dict):
                raise ValueError("the question to skip is missing or expired")
            if current_question.get("category") != input_data.skipped_category:
                raise ValueError("skipped category does not match the current question")
            skipped_categories.add(input_data.skipped_category)
        if input_data.available_categories is not None:
            available_categories = set(input_data.available_categories)
            ledger = state.get("lifeEventLedger")
            ledger = ledger if isinstance(ledger, dict) else {}
            existing_episode_count = int(ledger.get("independentEpisodeCount") or 0)
            if existing_episode_count == 0:
                existing_episode_count = sum(
                    1
                    for event in (ledger.get("events") or [])
                    if isinstance(event, dict) and event.get("role") in {"calibration", "holdout"}
                )
            if existing_episode_count == 0 and len(available_categories) < 2:
                raise ValueError(
                    "birth-time rectification needs at least two available life-event domains"
                )
            skipped_categories &= available_categories
            state["availableRectificationCategories"] = sorted(available_categories)
        if (
            input_data.reset_skipped
            or input_data.skipped_category
            or input_data.available_categories is not None
        ):
            state["skippedRectificationCategories"] = sorted(skipped_categories)
            state["updatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self.workspace.write_artifact(
                session_id,
                "chart_rectification_state.json",
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            )
            self.workspace.mark_artifact_checkpoint(
                session_id,
                "chart_rectification_state.json",
                producer="vedicdust-rectification-interview",
            )

        chart_record_text = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON)
        life_stage = None
        if chart_record_text:
            life_stage = ChartRecord.model_validate_json(chart_record_text).subject.life_stage
        interview = build_rectification_interview(
            state,
            session_id=session_id,
            locale=input_data.locale,
            life_stage=life_stage,
            skipped_categories=skipped_categories,
            available_categories=available_categories or None,
        )
        if (
            interview.get("questions")
            and use_agent
            and self.agent_runtime is not None
            and self.agent_runtime.is_configured()
        ):
            try:
                prompt = self._rectification_interview_prompt(interview, input_data.locale)
                result = await self.agent_runtime.run_skill_prompt_task(
                    "vedicdust-rectification-interview",
                    prompt,
                    skills=["vedicdust-rectification-interview"],
                    max_turns=3,
                    allow_file_tools=False,
                )
                wording = self._parse_json_object(result.raw_text)
                interview = validate_agent_question_wording(interview, wording)
            except Exception as exc:
                interview["source"] = "deterministic_fallback"
                interview["agentFallbackReason"] = self._safe_agent_failure_reason(exc)

        # The candidate-ranking pool is backend-private. The client receives only
        # the single question selected for this round.
        interview.pop("questionPool", None)
        interview.pop("lifeEventFocus", None)
        for question in interview.get("questions", []):
            if isinstance(question, dict):
                question.pop("questionValue", None)

        self.workspace.write_artifact(
            session_id,
            RECTIFICATION_INTERVIEW_JSON,
            json.dumps(interview, ensure_ascii=False, indent=2) + "\n",
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            RECTIFICATION_INTERVIEW_JSON,
            producer="vedicdust-rectification-interview",
            dependency_paths=["chart_rectification_state.json"],
        )
        await self._sync_metadata(
            session_id,
            stage="reader_ready",
            status="draft",
            owner_user_id=owner_user_id,
        )
        return SkillSessionResponse(
            session_id=session_id,
            stage="reader_ready",
            chat_message=(
                "The next birth-time verification questions are ready."
                if input_data.locale != "zh"
                else "下一组生时校正问题已准备好。"
            ),
            artifacts=self.workspace.read_artifacts(session_id),
            active_artifact=RECTIFICATION_INTERVIEW_JSON,
        )

    async def answer_consultation_question(
        self,
        input_data: ConsultationQuestionInput,
    ) -> ConsultationAnswerResponse:
        session_id = input_data.session_id
        context_text = self.workspace.read_artifact_text(session_id, AGENT_CONTEXT_JSON)
        dossier_text = self.workspace.read_artifact_text(session_id, CONSULTATION_DOSSIER_JSON)
        if not context_text or not dossier_text:
            raise ValueError(
                "the approved consultation must be completed before follow-up questions"
            )
        dossier = ConsultationDossier.model_validate_json(dossier_text)
        if dossier.release_status != "approved":
            raise ValueError("follow-up questions require an approved consultation")
        if self.agent_runtime is None or not self.agent_runtime.is_configured():
            raise ValueError("the consultation assistant is not configured")

        context = self._parse_json_object(context_text)
        base_prompt = self._consultation_question_prompt(
            context,
            input_data.question,
            dossier.locale,
        )
        audit_feedback = ""
        response: ConsultationAnswerResponse | None = None
        for attempt in range(2):
            prompt = base_prompt + audit_feedback
            result = await self.agent_runtime.run_skill_prompt_task(
                "vedicdust-consultation-qa",
                prompt,
                skills=["vedicdust-consultation"],
                max_turns=4,
                allow_file_tools=False,
            )
            payload = self._parse_json_object(result.raw_text)
            candidate = self._validate_consultation_answer_payload(payload, context)
            if candidate.answerability != "answered":
                response = candidate
                break
            try:
                await self._audit_consultation_answer(
                    question=input_data.question,
                    response=candidate,
                    context=context,
                    locale=dossier.locale,
                )
                response = candidate
                break
            except ValueError as exc:
                if attempt == 1:
                    raise
                audit_feedback = (
                    "\n\nThe previous draft failed the evidence audit. Produce a new answer "
                    "that is narrower and supported only by the cited approved claims. Audit "
                    f"feedback: {self._safe_agent_failure_reason(exc)}"
                )
        if response is None:
            raise ValueError("consultation assistant did not produce an auditable answer")
        self._append_consultation_exchange(session_id, input_data.question, response)
        return response

    def get_consultation_conversation(
        self,
        session_id: str,
    ) -> ConsultationConversationResponse:
        self.workspace.require_session_dir(session_id)
        content = self.workspace.read_artifact_text(session_id, "consultation_conversation.json")
        if not content:
            return ConsultationConversationResponse(sessionId=session_id, exchanges=[])
        return ConsultationConversationResponse.model_validate_json(content)

    @classmethod
    def _validate_consultation_answer_payload(
        cls,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> ConsultationAnswerResponse:
        answer = str(payload.get("answer") or "").strip()
        if len(answer) < 20 or len(answer) > 4000:
            raise ValueError("consultation answer has invalid length")
        validate_consumer_astrology_language(answer, label="consultation answer")
        claim_ids = payload.get("supportingClaimIds")
        if not isinstance(claim_ids, list):
            raise ValueError("consultation answer must provide a claim reference list")
        answerability = str(payload.get("answerability") or "")
        if answerability not in {"answered", "insufficient_evidence"}:
            raise ValueError("consultation answer has an invalid answerability status")
        if answerability == "answered" and not claim_ids:
            raise ValueError("an answered consultation question must cite approved claims")
        if answerability == "insufficient_evidence" and claim_ids:
            raise ValueError("an insufficient-evidence answer cannot imply claim support")
        known_claim_ids = {
            str(item.get("claimId"))
            for item in context.get("approvedClaims", [])
            if isinstance(item, dict) and item.get("claimId")
        }
        normalized_claim_ids = [str(value) for value in claim_ids]
        unknown_claim_ids = sorted(set(normalized_claim_ids) - known_claim_ids)
        if unknown_claim_ids:
            raise ValueError(
                "consultation answer cites unknown claims: " + ", ".join(unknown_claim_ids)
            )
        limitations = cls._bounded_string_list(payload.get("limitations"), limit=5, max_length=400)
        if answerability == "insufficient_evidence" and not limitations:
            raise ValueError("an insufficient-evidence answer must explain the missing evidence")
        follow_ups = cls._bounded_string_list(
            payload.get("followUpQuestions"),
            limit=3,
            max_length=240,
        )
        return ConsultationAnswerResponse(
            answerability=answerability,
            answer=answer,
            supportingClaimIds=normalized_claim_ids,
            limitations=limitations,
            followUpQuestions=follow_ups,
        )

    async def create_bazi_session(
        self, input_data: BaziSessionInput, *, owner_user_id: str | None = None
    ) -> SkillSessionResponse:
        session_id = self.workspace.create_session()
        session_dir = self.workspace.require_session_dir(session_id)
        started = datetime.now(timezone.utc)
        self.tools.calculate_bazi_chart(
            birth_date=input_data.birth_date,
            birth_time=input_data.birth_time,
            birth_place=input_data.birth_place,
            gender=input_data.gender,
            current_date=input_data.current_date,
            out_dir=session_dir,
            calendar_type=input_data.calendar_type,
            time_precision=input_data.birth_time_precision,
            timezone="Asia/Shanghai",
            audience=input_data.audience,
            relationship=input_data.relationship,
            topic=input_data.topic,
            day_boundary_sect=2,
            luck_sect=2,
            solar_time_policy="civil",
        )
        finished = datetime.now(timezone.utc)
        self.workspace.write_artifact(
            session_id,
            "run_metrics.json",
            json.dumps(
                {
                    "sessionId": session_id,
                    "status": "bazi_calculator_complete",
                    "calculator": {
                        "startedAt": started.isoformat(),
                        "finishedAt": finished.isoformat(),
                        "durationSeconds": round((finished - started).total_seconds(), 3),
                    },
                    "waves": [],
                    "nodes": [
                        {
                            "id": "bazi_chart",
                            "label": "BaZi Chart Facts",
                            "files": [
                                "bazi_chart_record.json",
                                "bazi_chart_foundation.md",
                                "bazi_report_context.md",
                            ],
                            "dependencies": [],
                            "wave": 0,
                            "status": "completed",
                            "startedAt": started.isoformat(),
                            "finishedAt": finished.isoformat(),
                            "durationSeconds": round((finished - started).total_seconds(), 3),
                        },
                        {
                            "id": "bazi_report",
                            "label": "Classical BaZi Report",
                            "files": [
                                "bazi_data_audit.md",
                                "bazi_overview.md",
                                "bazi_classics_audit.md",
                                "bazi_timing_report.md",
                                "bazi_life_report.md",
                                "bazi_appendix.md",
                            ],
                            "dependencies": ["bazi_chart"],
                            "wave": 1,
                            "status": "pending",
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        self.workspace.write_session_manifest(session_id, locale=input_data.locale)
        for artifact_path in [
            "bazi_chart_record.json",
            "bazi_chart_foundation.md",
            "bazi_report_context.md",
            "run_metrics.json",
        ]:
            self.workspace.mark_artifact_checkpoint(
                session_id,
                artifact_path,
                producer="bazi-calculator",
            )
        await self._sync_metadata(
            session_id, stage="bazi_ready", status="draft", owner_user_id=owner_user_id
        )

        return SkillSessionResponse(
            session_id=session_id,
            stage="bazi_ready",
            chat_message=(
                "BaZi chart facts are ready. Generate the classical report when you are ready."
            ),
            artifacts=self.workspace.read_artifacts(session_id),
            active_artifact="bazi_chart_foundation.md",
        )

    def load_session(self, session_id: str) -> SkillSessionResponse:
        self._ensure_runtime_contracts(session_id)
        artifacts = self.workspace.read_artifacts(session_id)
        paths = {artifact.path for artifact in artifacts}
        if "bazi_life_report.md" in paths:
            stage = "bazi_complete"
            active = "bazi_life_report.md"
            message = "Your BaZi classical report is ready."
        elif "bazi_chart_foundation.md" in paths:
            stage = "bazi_ready"
            active = "bazi_chart_foundation.md"
            message = "Your BaZi chart facts are ready."
        elif CONSULTATION_REPORT_MD in paths:
            stage = "core_complete"
            active = CONSULTATION_REPORT_MD
            message = "Your VedicDust consultation is ready."
        elif CHART_RECORD_JSON in paths:
            stage = "reader_ready"
            active = "birth_input_context.json"
            message = "Your chart data is ready."
        else:
            stage = "reader_ready"
            active = artifacts[0].path if artifacts else None
            message = "Your reading session is ready."
        return SkillSessionResponse(
            session_id=session_id,
            stage=stage,
            chat_message=message,
            artifacts=artifacts,
            active_artifact=active,
        )

    async def create_synastry_subject(
        self, input_data: SynastryBirthInput, *, owner_user_id: str | None = None
    ) -> SkillSessionResponse:
        session_dir = self.workspace.require_session_dir(input_data.session_id)
        a_record_path = session_dir / CHART_RECORD_JSON
        if not a_record_path.exists():
            raise ValueError("A chart_record.json is required before synastry")

        folder = self._synastry_folder(input_data.label)
        b_identity = ChartRecordIdentity(
            reading_session_id=input_data.session_id,
            chart_record_id=make_id("chart"),
            subject_id=make_id("subject"),
        )
        calculation = self.calculator.calculate(input_data.birth, identity=b_identity)
        b_path = f"{folder}/{CHART_RECORD_B_JSON}"
        self.workspace.write_artifact(
            input_data.session_id,
            b_path,
            calculation.chart_record_json,
        )
        a_record = ChartRecord.model_validate_json(a_record_path.read_text(encoding="utf-8"))
        b_record = ChartRecord.model_validate_json(calculation.chart_record_json)
        context = build_synastry_context(
            a_record,
            b_record,
            b_label=input_data.label or "B",
            relationship_type=input_data.relationship_type,
            current_stage=input_data.current_stage,
            question=input_data.question,
        )
        context_path = f"{folder}/{SYNASTRY_CONTEXT_JSON}"
        self.workspace.write_artifact(
            input_data.session_id,
            context_path,
            context.model_dump_json(by_alias=True, indent=2) + "\n",
        )
        self.workspace.mark_artifact_checkpoint(
            input_data.session_id,
            b_path,
            producer="vedicdust-chart-calculation",
        )
        self.workspace.mark_artifact_checkpoint(
            input_data.session_id,
            context_path,
            producer="vedicdust-synastry-context",
            dependency_paths=[CHART_RECORD_JSON, b_path],
        )
        await self._sync_metadata(
            input_data.session_id,
            stage="synastry_ready",
            status="draft",
            owner_user_id=owner_user_id,
        )

        return SkillSessionResponse(
            session_id=input_data.session_id,
            stage="synastry_ready",
            chat_message=(
                "合盘证据上下文已生成。\n\n"
                f"已生成: {b_path}\n"
                f"已生成: {context_path}\n\n"
                "下一步将基于双盘的确定性证据生成关系判断。"
            ),
            artifacts=self.workspace.read_artifacts(input_data.session_id),
            active_artifact=context_path,
        )

    async def run_skill(
        self, input_data: SkillRunInput, *, owner_user_id: str | None = None
    ) -> SkillSessionResponse:
        self.workspace.require_session_dir(input_data.session_id)
        if input_data.skill == "vedic-core":
            return await self._run_core(input_data, owner_user_id=owner_user_id)
        if input_data.skill == "vedic-reader":
            self._assert_reader_readiness(input_data.session_id)

        base_prompt = self._artifact_prompt_for(input_data)
        prompt = base_prompt
        max_contract_attempts = 2 if input_data.skill == "vedic-reader" else 1
        max_transient_retries, retry_base_delay_ms = self._agent_retry_policy()
        contract_rejections = 0
        transient_failures = 0
        attempt = 0
        parsed: dict[str, object] | None = None
        trace_run_id = make_id("agent_run")
        trace_attempts: list[dict[str, object]] = []
        trace_execution: dict[str, object] = {
            "runId": trace_run_id,
            "taskName": input_data.skill,
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "attempts": trace_attempts,
        }
        while True:
            attempt += 1
            prompt_path, prompt_sha256 = self._write_agent_prompt_trace(
                input_data.session_id,
                trace_run_id,
                attempt,
                prompt,
            )
            attempt_trace: dict[str, object] = {
                "attempt": attempt,
                "promptPath": prompt_path,
                "promptSha256": prompt_sha256,
                "startedAt": datetime.now(timezone.utc).isoformat(),
            }
            try:
                result = await self.agent_runtime.run_skill_prompt_task(
                    input_data.skill,
                    prompt,
                    skills=[input_data.skill],
                    max_turns=self._max_turns_for(input_data.skill),
                    allow_file_tools=input_data.skill != "vedic-reader",
                )
            except Exception as exc:
                retryable = self._is_transient_agent_error(exc)
                will_retry = retryable and transient_failures < max_transient_retries
                delay_ms = retry_base_delay_ms * (2**transient_failures) if will_retry else 0
                attempt_trace.update(
                    {
                        "status": "agent_failed",
                        "error": str(exc),
                        "retryable": retryable,
                        "willRetry": will_retry,
                        "retryDelayMs": delay_ms,
                        "finishedAt": datetime.now(timezone.utc).isoformat(),
                    }
                )
                trace_attempts.append(attempt_trace)
                trace_execution["finishedAt"] = datetime.now(timezone.utc).isoformat()
                self._persist_agent_run_trace(
                    input_data.session_id,
                    "skill",
                    input_data.skill,
                    trace_execution,
                )
                if will_retry:
                    transient_failures += 1
                    if delay_ms:
                        await asyncio.sleep(delay_ms / 1000)
                    continue
                raise
            attempt_trace.update(self._agent_result_trace(result))
            try:
                parsed = self._parse_artifact_response(result.raw_text)
                self._validate_skill_artifacts(input_data.session_id, input_data.skill, parsed)
                attempt_trace["status"] = "accepted"
                attempt_trace["finishedAt"] = datetime.now(timezone.utc).isoformat()
                trace_attempts.append(attempt_trace)
                trace_execution["finishedAt"] = datetime.now(timezone.utc).isoformat()
                self._persist_agent_run_trace(
                    input_data.session_id,
                    "skill",
                    input_data.skill,
                    trace_execution,
                )
                break
            except ValueError as exc:
                contract_rejections += 1
                attempt_trace.update(
                    {
                        "status": "contract_rejected",
                        "error": str(exc),
                        "finishedAt": datetime.now(timezone.utc).isoformat(),
                    }
                )
                trace_attempts.append(attempt_trace)
                trace_execution["finishedAt"] = datetime.now(timezone.utc).isoformat()
                self._persist_agent_run_trace(
                    input_data.session_id,
                    "skill",
                    input_data.skill,
                    trace_execution,
                )
                if contract_rejections >= max_contract_attempts:
                    raise
                prompt = (
                    f"{base_prompt}\n\n"
                    "The previous artifact was rejected by the deterministic output contract. "
                    "Regenerate it from scratch and fix every issue below; do not explain the retry:\n"
                    f"- {exc}"
                )
        if parsed is None:
            raise ValueError(f"{input_data.skill} did not return an artifact response")
        for artifact in parsed["artifacts"]:
            artifact_path = str(artifact["path"])
            self.workspace.write_artifact(
                input_data.session_id,
                artifact_path,
                str(artifact["content"]),
            )
            self.workspace.mark_artifact_checkpoint(
                input_data.session_id,
                artifact_path,
                producer=input_data.skill,
            )
        if input_data.skill == "vedic-reader":
            self._write_prevalidation_result(input_data.session_id, feedback_markdown="")
        stage = self._stage_for(input_data.skill)
        await self._sync_metadata(
            input_data.session_id,
            stage=stage,
            status=self._status_for_stage(stage),
            owner_user_id=owner_user_id,
        )
        artifacts = self.workspace.read_artifacts(input_data.session_id)
        return SkillSessionResponse(
            session_id=input_data.session_id,
            stage=stage,
            chat_message=str(parsed["chatMessage"]),
            artifacts=artifacts,
            active_artifact=self._preferred_artifact(input_data.skill, artifacts),
        )

    async def _run_core(
        self, input_data: SkillRunInput, *, owner_user_id: str | None = None
    ) -> SkillSessionResponse:
        session_dir = self.workspace.require_session_dir(input_data.session_id)
        self.assert_core_readiness(input_data.session_id, input_data.user_message)
        locale = self._run_locale(input_data)
        batches = self.core_batches(input_data.user_message, locale)
        existing_paths = self._session_paths(session_dir)
        batch = next(
            (
                item
                for item in batches
                if not set(self.core_batch_files(item)).issubset(existing_paths)
                or not self.core_batch_resume_valid(input_data.session_id, item)
            ),
            None,
        )
        if batch is None:
            await self._finalize_consultation_artifacts(input_data.session_id)
            if not self._consultation_artifacts_complete(input_data.session_id):
                raise ValueError(
                    "VedicDust core batches exist, but the released consultation artifacts "
                    "are missing or stale. Regenerate the consultation dossier."
                )
            return self.core_progress_response(
                session_id=input_data.session_id,
                stage="core_complete",
                chat_message="Your full reading is ready.",
            )

        return await self.run_core_batch(
            input_data, batch, batches=batches, owner_user_id=owner_user_id
        )

    def assert_core_readiness(self, session_id: str, user_message: str = "") -> None:
        session_dir = self.workspace.require_session_dir(session_id)
        read_artifact_text = getattr(self.workspace, "read_artifact_text", None)
        if callable(read_artifact_text) and read_artifact_text(session_id, CHART_RECORD_JSON):
            self._ensure_runtime_contracts(session_id)
            chart_audit = self._json_dict(read_artifact_text(session_id, CHART_AUDIT_JSON) or "")
            permitted = chart_audit.get("permittedNextSteps")
            if not isinstance(permitted, list) or "judge" not in permitted:
                findings = chart_audit.get("findings")
                raise ValueError(
                    "当前盘面尚未通过确定性审计，不能生成完整报告。"
                    f" 审计结果：{findings if isinstance(findings, list) else 'unknown'}"
                )
        state_text = (
            read_artifact_text(session_id, "chart_rectification_state.json")
            if callable(read_artifact_text)
            else (session_dir / "chart_rectification_state.json").read_text(encoding="utf-8")
            if (session_dir / "chart_rectification_state.json").exists()
            else ""
        )
        state = self._json_dict(state_text or "")
        conclusion = state.get("rectificationConclusion")
        conclusion = conclusion if isinstance(conclusion, dict) else {}
        confirmation = conclusion.get("confirmation")
        confirmation = confirmation if isinstance(confirmation, dict) else {}
        if state.get("status") == "rectification_confirmation_required" or (
            confirmation.get("status") == "pending"
        ):
            raise ValueError("请先确认阶段性的生时校正结论，再生成完整报告。")
        state_status = str(state.get("status") or "")
        raw_state_gate = state.get("reportGate")
        state_gate: dict[str, object] = raw_state_gate if isinstance(raw_state_gate, dict) else {}
        if (
            state_status == "corrected_chart_ready"
            and state.get("holdoutResult") == "passed"
            and state_gate.get("fullReportAllowed") is True
        ):
            if callable(read_artifact_text) and read_artifact_text(session_id, CHART_RECORD_JSON):
                self._prepare_judgement_context(session_id, user_message)
            return
        if (
            state_status == "multiple_equivalent"
            and state.get("holdoutResult") == "passed"
            and state_gate.get("fullReportAllowed") is True
            and state_gate.get("reportScope") == "stable_intersection_only"
        ):
            if callable(read_artifact_text) and read_artifact_text(session_id, CHART_RECORD_JSON):
                self._prepare_judgement_context(session_id, user_message)
            return
        result_path = session_dir / "prevalidation_result.json"
        if not result_path.exists():
            raise ValueError(
                "请先运行验前事并提交反馈。完整报告需要 prevalidation_result.json "
                "确认输入风险和命中率后才能生成。"
            )
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("prevalidation_result.json 格式损坏，请重新运行验前事。") from exc
        if (
            not isinstance(result, dict)
            or result.get("schemaVersion") != "vedic-prevalidation-result/2.0.0"
        ):
            raise ValueError("prevalidation_result.json 合同版本已过期，请重新运行验前事。")
        checkpoint_valid = getattr(self.workspace, "artifact_checkpoint_valid", None)
        if callable(checkpoint_valid) and not checkpoint_valid(
            session_id,
            "prevalidation_result.json",
            producer="vedic-reader:prevalidation-result",
            dependency_paths=PREVALIDATION_DEPENDENCY_PATHS,
        ):
            raise ValueError(
                "prevalidation_result.json 已过期或被修改，请基于当前盘面重新运行验前事。"
            )
        chart_record_text = (
            read_artifact_text(session_id, CHART_RECORD_JSON)
            if callable(read_artifact_text)
            else None
        )
        if isinstance(chart_record_text, str) and chart_record_text:
            active_record = ChartRecord.model_validate_json(chart_record_text)
            expected_hash = hashlib.sha256(chart_record_text.encode("utf-8")).hexdigest()
            if (
                not isinstance(result, dict)
                or result.get("chartRecordId") != active_record.chart_record_id
                or result.get("chartRevision") != active_record.revision
                or result.get("chartRecordSha256") != expected_hash
            ):
                raise ValueError("prevalidation_result.json 不属于当前盘面版本，请重新运行验前事。")
        decision = result.get("decision") if isinstance(result, dict) else {}
        if not isinstance(decision, dict):
            raise ValueError("prevalidation_result.json 缺少 decision，请重新运行验前事。")
        if decision.get("reportAllowed") is not True:
            reason = decision.get("reason") or "输入风险或验前事反馈未达到完整报告门槛。"
            next_step = decision.get("nextStep") or "review_birth_details_or_stop"
            raise ValueError(f"完整报告暂不允许生成：{reason} 下一步：{next_step}")
        scope = str(decision.get("reportScope") or "")
        if scope == "prevalidation_or_d1_only":
            raise ValueError(
                "当前输入只允许验前事/低置信D1-only说明，不允许生成完整 vedic-core 报告。"
            )
        if callable(read_artifact_text) and read_artifact_text(session_id, CHART_RECORD_JSON):
            self._prepare_judgement_context(session_id, user_message)

    def _assert_reader_readiness(self, session_id: str) -> None:
        read_artifact_text = getattr(self.workspace, "read_artifact_text", None)
        if not callable(read_artifact_text):
            return
        state_text = read_artifact_text(session_id, "chart_rectification_state.json")
        if not state_text:
            return
        state = self._json_dict(state_text)
        status = str(state.get("status") or "")
        if status != "not_required":
            raise ValueError(
                "vedic-reader is limited to scan-stable charts. Birth-time candidate selection "
                "is backend-owned; collect dated events or follow the deterministic "
                f"rectification result instead (status={status or 'unknown'})."
            )

    def core_batches(self, user_message: str, locale: str = "en") -> list[dict[str, object]]:
        return self._core_batches(user_message, locale)

    def core_batch_files(self, batch: dict[str, object]) -> list[str]:
        return self._batch_files(batch)

    def core_batch_complete(self, session_id: str, batch: dict[str, object]) -> bool:
        session_dir = self.workspace.require_session_dir(session_id)
        existing_paths = self._session_paths(session_dir)
        return set(self.core_batch_files(batch)).issubset(existing_paths)

    def core_batch_resume_valid(self, session_id: str, batch: dict[str, object]) -> bool:
        session_dir = self.workspace.require_session_dir(session_id)
        expected = set(self.core_batch_files(batch))
        if not expected.issubset(self._session_paths(session_dir)):
            return False
        if str(batch.get("id") or "") == "vedicdust_consultation":
            dossier_text = self.workspace.read_artifact_text(session_id, CONSULTATION_DOSSIER_JSON)
            if not dossier_text:
                return False
            try:
                dossier = ConsultationDossier.model_validate_json(dossier_text)
            except ValueError:
                return False
            narrative_kinds = {
                "executive_synthesis",
                "chart_foundation",
                "core_architecture",
                "priority_domain",
                "timing_outlook",
                "decision_support",
            }
            if any(
                section.section_kind in narrative_kinds
                and section.claim_ids
                and not section.narratives
                for section in dossier.sections
            ):
                return False
        producer = self._batch_producer(batch)
        dependency_paths = self._core_batch_dependency_paths(str(batch.get("id") or ""))
        return all(
            self.workspace.artifact_checkpoint_valid(
                session_id,
                path,
                producer=producer,
                **({"dependency_paths": dependency_paths} if dependency_paths else {}),
            )
            for path in expected
        )

    def _consultation_artifacts_complete(self, session_id: str) -> bool:
        dependency_paths = [
            JUDGEMENT_CONTEXT_JSON,
            CLAIM_GRAPH_JSON,
            CONSULTATION_DOSSIER_JSON,
        ]
        return all(
            self.workspace.artifact_checkpoint_valid(
                session_id,
                path,
                producer="vedicdust-consultation-renderer",
                dependency_paths=dependency_paths,
            )
            for path in (
                CONSULTATION_REPORT_MANIFEST_JSON,
                AGENT_CONTEXT_JSON,
                CONSULTATION_REPORT_MD,
            )
        )

    def core_progress_response(
        self,
        session_id: str,
        chat_message: str,
        *,
        stage: str = "core_in_progress",
        active_artifact: str | None = None,
    ) -> SkillSessionResponse:
        artifacts = self.workspace.read_artifacts(session_id)
        return SkillSessionResponse(
            session_id=session_id,
            stage=stage,
            chat_message=chat_message,
            artifacts=artifacts,
            active_artifact=active_artifact or self._preferred_artifact("vedic-core", artifacts),
        )

    async def run_core_batch(
        self,
        input_data: SkillRunInput,
        batch: dict[str, object],
        *,
        batches: list[dict[str, object]] | None = None,
        force: bool = False,
        owner_user_id: str | None = None,
    ) -> SkillSessionResponse:
        session_dir = self.workspace.require_session_dir(input_data.session_id)
        self.assert_core_readiness(input_data.session_id, input_data.user_message)
        locale = self._run_locale(input_data)
        batches = batches or self.core_batches(input_data.user_message, locale)
        expected = set(self.core_batch_files(batch))
        if not force and self.core_batch_resume_valid(input_data.session_id, batch):
            await self._finalize_consultation_artifacts(input_data.session_id)
            await self._sync_metadata(
                input_data.session_id,
                stage="core_in_progress",
                status="running",
                owner_user_id=owner_user_id,
            )
            artifacts = self.workspace.read_artifacts(input_data.session_id)
            return SkillSessionResponse(
                session_id=input_data.session_id,
                stage="core_in_progress",
                chat_message=f"{self._chat_message_for_batch(batch, '')}\n\n该批次已存在，已跳过。",
                artifacts=artifacts,
                active_artifact=self._active_artifact_for_batch(batch, artifacts),
            )

        self.workspace.assert_no_project_runtime_artifacts()
        selected_skills = [str(skill) for skill in batch.get("skills", [input_data.skill])]
        batch_id = str(batch.get("id") or "")
        is_consultation_batch = batch_id == "vedicdust_consultation"
        prompt = str(batch["prompt"])
        result = None
        trace_run_id = make_id("agent_run")
        trace_attempts: list[dict[str, object]] = []
        trace_execution: dict[str, object] = {
            "runId": trace_run_id,
            "taskName": str(batch.get("task_name") or input_data.skill),
            "batchId": batch_id,
            "skills": selected_skills,
            "expectedArtifacts": sorted(expected),
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "attempts": trace_attempts,
        }
        max_transient_retries, retry_base_delay_ms = self._agent_retry_policy()
        contract_rejections = 0
        transient_failures = 0
        attempt = 0
        while True:
            attempt += 1
            prompt_path, prompt_sha256 = self._write_agent_prompt_trace(
                input_data.session_id,
                trace_run_id,
                attempt,
                prompt,
            )
            attempt_trace: dict[str, object] = {
                "attempt": attempt,
                "promptPath": prompt_path,
                "promptSha256": prompt_sha256,
                "startedAt": datetime.now(timezone.utc).isoformat(),
            }
            workspace_snapshot = self._snapshot_agent_workspace(session_dir, expected)
            try:
                result = await self.agent_runtime.run_skill_task(
                    str(batch.get("task_name") or input_data.skill),
                    prompt,
                    cwd=session_dir,
                    skills=selected_skills,
                    max_turns=max(self._max_turns_for(skill) for skill in selected_skills),
                )
            except Exception as exc:
                self._restore_failed_agent_attempt(
                    session_dir,
                    expected,
                    workspace_snapshot,
                )
                retryable = self._is_transient_agent_error(exc)
                will_retry = retryable and transient_failures < max_transient_retries
                delay_ms = retry_base_delay_ms * (2**transient_failures) if will_retry else 0
                attempt_trace.update(
                    {
                        "status": "agent_failed",
                        "error": str(exc),
                        "retryable": retryable,
                        "willRetry": will_retry,
                        "retryDelayMs": delay_ms,
                        "finishedAt": datetime.now(timezone.utc).isoformat(),
                    }
                )
                trace_attempts.append(attempt_trace)
                trace_execution["finishedAt"] = datetime.now(timezone.utc).isoformat()
                self._persist_agent_run_trace(
                    input_data.session_id,
                    "core",
                    batch_id,
                    trace_execution,
                )
                if will_retry:
                    transient_failures += 1
                    if delay_ms:
                        await asyncio.sleep(delay_ms / 1000)
                    continue
                raise
            attempt_trace.update(self._agent_result_trace(result))
            boundary_errors = self._restore_agent_workspace_boundary(
                session_dir,
                expected,
                workspace_snapshot,
            )
            self.workspace.assert_no_project_runtime_artifacts()
            missing = [path for path in expected if not (session_dir / path).exists()]
            try:
                if boundary_errors:
                    raise ValueError(
                        "agent modified files outside its declared output contract: "
                        + ", ".join(boundary_errors)
                    )
                if missing:
                    raise ValueError("missing expected artifact(s): " + ", ".join(missing))
                if is_consultation_batch:
                    await self._finalize_consultation_artifacts(input_data.session_id)
                attempt_trace["status"] = "accepted"
                attempt_trace["finishedAt"] = datetime.now(timezone.utc).isoformat()
                trace_attempts.append(attempt_trace)
                trace_execution["finishedAt"] = datetime.now(timezone.utc).isoformat()
                self._persist_agent_run_trace(
                    input_data.session_id,
                    "core",
                    batch_id,
                    trace_execution,
                )
                break
            except ValueError as exc:
                contract_rejections += 1
                attempt_trace.update(
                    {
                        "status": "contract_rejected",
                        "error": str(exc),
                        "finishedAt": datetime.now(timezone.utc).isoformat(),
                    }
                )
                trace_attempts.append(attempt_trace)
                trace_execution["finishedAt"] = datetime.now(timezone.utc).isoformat()
                self._persist_agent_run_trace(
                    input_data.session_id,
                    "core",
                    batch_id,
                    trace_execution,
                )
                if contract_rejections >= 2:
                    raise ValueError(
                        f"VedicDust {batch_id} failed its deterministic contract after retry: {exc}"
                    ) from exc
                prompt = (
                    f"{batch['prompt']}\n\n"
                    "The previous output failed the deterministic contract. Overwrite the exact "
                    "requested file and fix every issue below. Do not explain the retry or create "
                    f"another file:\n- {exc}"
                )
        if result is None:
            raise ValueError(f"VedicDust {batch_id} did not return an Agent result")
        producer = self._batch_producer(batch)
        dependency_paths = self._core_batch_dependency_paths(batch_id)
        for path in expected:
            self.workspace.mark_artifact_checkpoint(
                input_data.session_id,
                path,
                producer=producer,
                **({"dependency_paths": dependency_paths} if dependency_paths else {}),
            )

        if not is_consultation_batch:
            await self._finalize_consultation_artifacts(input_data.session_id)
        artifacts = self.workspace.read_artifacts(input_data.session_id)
        core_complete = all(
            self.core_batch_resume_valid(input_data.session_id, item) for item in batches
        ) and self._consultation_artifacts_complete(input_data.session_id)
        await self._sync_metadata(
            input_data.session_id,
            stage="core_complete" if core_complete else "core_in_progress",
            status="completed" if core_complete else "running",
            owner_user_id=owner_user_id,
        )
        next_message = (
            "vedic-core 全部批次已完成。"
            if core_complete
            else "继续点击 vedic-core，可按原流程生成下一批文件。"
        )
        return SkillSessionResponse(
            session_id=input_data.session_id,
            stage="core_complete" if core_complete else "core_in_progress",
            chat_message=f"{self._chat_message_for_batch(batch, result.raw_text)}\n\n{next_message}",
            artifacts=artifacts,
            active_artifact=self._active_artifact_for_batch(batch, artifacts),
        )

    def agent_run_summary(
        self,
        session_id: str,
        *,
        scope: str,
        key: str,
    ) -> dict[str, object] | None:
        path = (
            self.workspace.session_dir(session_id)
            / ".runtime"
            / "agent-runs"
            / scope
            / f"{key}.json"
        )
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        executions = payload.get("executions") if isinstance(payload, dict) else None
        if not isinstance(executions, list) or not executions:
            return None
        latest = executions[-1]
        if not isinstance(latest, dict):
            return None
        return {
            "runId": latest.get("runId"),
            "attemptCount": latest.get("attemptCount", 0),
            "retryCount": latest.get("retryCount", 0),
            "finalStatus": latest.get("finalStatus"),
        }

    def _agent_retry_policy(self) -> tuple[int, int]:
        settings = getattr(self.agent_runtime, "settings", None)
        return (
            int(getattr(settings, "agent_transient_retries", 2)),
            int(getattr(settings, "agent_retry_base_delay_ms", 0)),
        )

    @staticmethod
    def _is_transient_agent_error(exc: Exception) -> bool:
        error_type = type(exc).__name__
        message = str(exc).lower()
        permanent_markers = (
            "not configured",
            "not found or not installed",
            "invalid api key",
            "invalid authentication",
            "authentication_error",
            "permission denied",
            "unauthorized",
            "forbidden",
        )
        if any(marker in message for marker in permanent_markers):
            return False
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return True
        if error_type in {
            "CLIConnectionError",
            "CLIJSONDecodeError",
            "MessageParseError",
        }:
            return error_type != "CLINotFoundError"
        transient_markers = (
            "connection closed",
            "connection reset",
            "connection refused",
            "timed out",
            "timeout",
            "rate limit",
            "rate_limit",
            "overloaded",
            "temporarily unavailable",
            "service unavailable",
            "http 429",
            "status 429",
            "http 500",
            "http 502",
            "http 503",
            "http 504",
            "status 500",
            "status 502",
            "status 503",
            "status 504",
        )
        return any(marker in message for marker in transient_markers)

    @staticmethod
    def _snapshot_agent_workspace(
        session_dir: Path,
        writable_paths: set[str],
    ) -> _AgentWorkspaceSnapshot:
        files: dict[str, bytes] = {}
        for path in session_dir.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(session_dir).as_posix()
            if relative in writable_paths or relative.startswith(".meta/"):
                continue
            files[relative] = path.read_bytes()
        writable_files = {
            relative: (
                (session_dir / relative).read_bytes()
                if (session_dir / relative).is_file()
                else None
            )
            for relative in writable_paths
        }
        return _AgentWorkspaceSnapshot(files=files, writable_files=writable_files)

    @classmethod
    def _restore_failed_agent_attempt(
        cls,
        session_dir: Path,
        writable_paths: set[str],
        snapshot: _AgentWorkspaceSnapshot,
    ) -> None:
        cls._restore_agent_workspace_boundary(session_dir, writable_paths, snapshot)
        for relative, original in snapshot.writable_files.items():
            target = session_dir / relative
            if original is None:
                target.unlink(missing_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original)

    @staticmethod
    def _restore_agent_workspace_boundary(
        session_dir: Path,
        writable_paths: set[str],
        snapshot: _AgentWorkspaceSnapshot,
    ) -> list[str]:
        errors: list[str] = []
        current_paths = {
            path.relative_to(session_dir).as_posix(): path
            for path in session_dir.rglob("*")
            if path.is_file()
            and not path.relative_to(session_dir).as_posix().startswith(".meta/")
            and path.relative_to(session_dir).as_posix() not in writable_paths
        }

        for relative, original in snapshot.files.items():
            target = session_dir / relative
            current = target.read_bytes() if target.exists() else None
            if current == original:
                continue
            errors.append(f"modified:{relative}" if current is not None else f"deleted:{relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original)

        for relative, target in current_paths.items():
            if relative in snapshot.files:
                continue
            errors.append(f"created:{relative}")
            target.unlink(missing_ok=True)

        return sorted(errors)

    async def record_reader_feedback(
        self,
        session_id: str,
        feedback_markdown: str,
        *,
        owner_user_id: str | None = None,
    ) -> SkillSessionResponse:
        self._assert_reader_readiness(session_id)
        existing = ""
        artifacts = {
            artifact.path: artifact.content
            for artifact in self.workspace.read_artifacts(session_id, include_internal=True)
        }
        if "user_context.md" in artifacts:
            existing = artifacts["user_context.md"].rstrip() + "\n\n"
        content = (
            f"{existing}"
            "## 验前事反馈\n\n"
            f"{feedback_markdown.strip()}\n\n"
            f"_updated_at: {datetime.now(timezone.utc).isoformat()}_\n"
        )
        self.workspace.write_artifact(session_id, "user_context.md", content)
        self.workspace.mark_artifact_checkpoint(
            session_id, "user_context.md", producer="vedic-reader-feedback"
        )
        prevalidation_result = self._write_prevalidation_result(
            session_id, feedback_markdown=feedback_markdown
        )
        if prevalidation_result is not None:
            self._apply_reader_quality_decision(
                session_id,
                prevalidation_result,
            )
        decision = (
            prevalidation_result.get("decision") if isinstance(prevalidation_result, dict) else None
        )
        report_allowed = isinstance(decision, dict) and decision.get("reportAllowed") is True
        read_locale = getattr(self.workspace, "read_session_locale", None)
        locale = read_locale(session_id) if callable(read_locale) else "en"
        await self._sync_metadata(
            session_id,
            stage="reader_validation",
            status="validation",
            owner_user_id=owner_user_id,
        )
        return SkillSessionResponse(
            session_id=session_id,
            stage="reader_validation",
            chat_message=self._reader_quality_message(locale, report_allowed),
            artifacts=self.workspace.read_artifacts(session_id),
            active_artifact="user_context.md",
        )

    @staticmethod
    def _reader_quality_message(locale: str, report_allowed: bool) -> str:
        messages = {
            "zh": (
                "反馈已保存，可以开始完整解读。",
                "反馈已保存，但当前质量校验未达到完整报告门槛。请复核出生信息，"
                "不要为了生成报告而强行确定盘面。",
            ),
            "ja": (
                "フィードバックを保存しました。完全なリーディングを開始できます。",
                "フィードバックを保存しましたが、完全なレポートの品質基準を満たしていません。"
                "出生情報を再確認し、無理にチャートを確定しないでください。",
            ),
            "en": (
                "Your feedback has been saved. The full reading can now begin.",
                "Your feedback has been saved, but the quality check did not meet the full-report "
                "threshold. Review the recorded birth details instead of forcing a chart.",
            ),
        }
        allowed, blocked = messages.get(locale, messages["en"])
        return allowed if report_allowed else blocked

    async def _sync_metadata(
        self,
        session_id: str,
        *,
        stage: str,
        status: str,
        owner_user_id: str | None = None,
    ) -> None:
        self._sync_reading_session_stage(session_id, stage)
        if self.metadata_store is None:
            return
        await self.metadata_store.sync_session_from_files(
            session_id,
            stage=stage,
            status=status,
            owner_user_id=owner_user_id,
        )

    def _status_for_stage(self, stage: str) -> str:
        if stage in {
            "core_complete",
            "rectifier_complete",
            "synastry_complete",
            "bazi_complete",
            "qa_complete",
        }:
            return "completed"
        if stage == "reader_validation":
            return "validation"
        if stage == "core_in_progress":
            return "running"
        if stage == "error":
            return "failed"
        return "draft"

    def _run_locale(self, input_data: SkillRunInput) -> str:
        if input_data.locale in {"zh", "en", "ja"}:
            return input_data.locale
        return self.workspace.read_session_locale(input_data.session_id)

    def _language_instruction(self, locale: str) -> str:
        if locale == "zh":
            return (
                "Output language: Simplified Chinese. Keep Jyotish/Sanskrit technical terms "
                "such as Lagna, Dasha, Navamsha, Mahadasha, and Antardasha in English or "
                "Sanskrit with short Chinese clarification where useful."
            )
        if locale == "ja":
            return (
                "Output language: Japanese. Keep Jyotish/Sanskrit technical terms such as "
                "Lagna, Dasha, Navamsha, Mahadasha, and Antardasha in English or Sanskrit "
                "with short Japanese clarification where useful."
            )
        return (
            "Output language: English. Keep Jyotish/Sanskrit technical terms such as Lagna, "
            "Dasha, Navamsha, Mahadasha, and Antardasha consistent."
        )

    def _rectification_interview_prompt(
        self,
        brief: dict[str, Any],
        locale: str,
    ) -> str:
        public_questions = []
        for item in brief.get("questions", []):
            if not isinstance(item, dict):
                continue
            public_questions.append(
                {
                    key: item[key]
                    for key in (
                        "questionId",
                        "category",
                        "title",
                        "prompt",
                        "whyWeAsk",
                        "detailsPlaceholder",
                    )
                    if key in item
                }
            )
        return f"""Rewrite the backend-selected birth-time verification question for a calm,
clear consumer product.

{self._language_instruction(locale)}

The backend has already selected exactly one question for this round. Rewrite only that question.
The backend will recalculate candidates after the answer and select the next question. You may
improve title, prompt, whyWeAsk, and detailsPlaceholder, but you must not invent or switch a
questionId or category. Candidate-ranking context is not included in this prompt. Do not mention candidate charts,
scores, houses, planets, vargas, D1-D60, or imply that an answer is expected. Keep every
question factual and non-leading. Never add personality or physical-trait questions.

BACKEND QUESTION BRIEF
{json.dumps({"questions": public_questions}, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "questions": [
    {{
      "questionId": "the unchanged backend questionId",
      "category": "the unchanged backend category",
      "title": "short readable title",
      "prompt": "concrete examples of qualifying events",
      "whyWeAsk": "one plain-language sentence",
      "detailsPlaceholder": "one short factual placeholder"
    }}
  ]
}}"""

    async def _validate_rectification_event_evidence(
        self,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        def bound_event_result(
            *, source: str, agent_failure: Exception | None = None
        ) -> dict[str, Any]:
            payload = {
                "schemaVersion": "vedicdust-life-event-evidence-validation/1.0.0",
                "source": source,
                "results": [
                    {
                        "questionId": event["questionId"],
                        "category": event["category"],
                        "eventSubtype": event.get("eventSubtype"),
                        "date": event.get("date", ""),
                        "description": event.get("description", ""),
                        "accepted": True,
                        "reason": "Backend-issued question, subtype, and category binding validated.",
                        "eventFacts": {
                            "occurrence": "occurred",
                            "agency": "unknown",
                            "impact": "unknown",
                            "dateConfidence": "unknown",
                        },
                    }
                    for event in events
                ],
            }
            if agent_failure is not None:
                payload["agentFallbackReason"] = self._safe_agent_failure_reason(agent_failure)
            return payload

        if self.agent_runtime is None or not self.agent_runtime.is_configured():
            return bound_event_result(source="question_binding_only")

        prompt = f"""Classify optional semantic context for each structured life event. The backend
has already validated the current question, selected subtype, category, and date; you do not decide
whether the event is accepted. This is evidence enrichment, not astrology interpretation. Do not
infer chart meaning, score candidates, rewrite the user's statement, or change a category or
eventSubtype. Use `unknown` whenever the submitted details do not support a semantic label. A
year-only date is valid.

SUBMITTED EVENTS
{json.dumps(events, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "results": [
    {{
      "questionId": "exact submitted questionId",
	      "category": "exact submitted category",
	      "eventSubtype": "exact submitted eventSubtype",
	      "reason": "short audit note about available semantic detail",
	      "eventFacts": {{
            "occurrence": "occurred|ongoing|uncertain",
	        "agency": "active|passive|mixed|unknown",
	        "impact": "major|moderate|minor|unknown",
	        "dateConfidence": "year|month|day|unknown"
	      }}
	    }}
  ]
}}"""
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                result = await self.agent_runtime.run_skill_prompt_task(
                    "vedicdust-rectification-evidence-validation",
                    prompt,
                    skills=["vedicdust-rectification-interview"],
                    max_turns=2,
                    allow_file_tools=False,
                )
                payload = self._parse_json_object(result.raw_text)
                validated = validate_agent_event_evidence(events, payload)
                return {
                    "schemaVersion": "vedicdust-life-event-evidence-validation/1.0.0",
                    "source": "agent_semantic_enrichment",
                    "results": validated,
                }
            except ValueError as exc:
                last_error = exc
            except Exception as exc:
                last_error = exc
        if last_error is None:
            last_error = RuntimeError("Agent evidence validation returned no usable result")
        return bound_event_result(
            source="question_binding_fallback",
            agent_failure=last_error,
        )

    def _consultation_question_prompt(
        self,
        context: dict[str, Any],
        question: str,
        locale: str,
    ) -> str:
        return f"""Answer one follow-up question about an approved VedicDust consultation.

{self._language_instruction(locale)}

Use only approvedClaims, timingWindows, stableFacts, subject framing, and uncertainties in
the supplied Agent Context. Every substantive sentence must be supported by the returned
supportingClaimIds. If the context cannot answer the question, say so directly and explain
what evidence is missing; set answerability to insufficient_evidence and supportingClaimIds
to an empty list. Otherwise set answerability to answered. Do not calculate a new chart,
invent a placement, promote
certainty, diagnose health, promise outcomes, or prescribe an irreversible decision.
Prefer a direct answer, then practical interpretation, then limits. Avoid raw internal IDs
in the prose.

USER QUESTION
{question}

APPROVED AGENT CONTEXT
{json.dumps(context, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "answerability": "answered or insufficient_evidence",
  "answer": "clear answer in the requested language",
  "supportingClaimIds": ["exact approved claim IDs; empty only for insufficient_evidence"],
  "limitations": ["important boundary or uncertainty"],
  "followUpQuestions": ["up to three useful next questions"]
}}"""

    async def _audit_consultation_answer(
        self,
        *,
        question: str,
        response: ConsultationAnswerResponse,
        context: dict[str, Any],
        locale: str,
    ) -> None:
        cited_ids = set(response.supporting_claim_ids)
        cited_claims = [
            claim
            for claim in context.get("approvedClaims", [])
            if isinstance(claim, dict) and str(claim.get("claimId")) in cited_ids
        ]
        prompt = f"""Audit a proposed answer against only the cited approved claims.

{self._language_instruction(locale)}

Mark supported=false if any substantive statement introduces a prediction, event, diagnosis,
certainty, recommendation, or chart fact that is not entailed by the cited claims. Do not repair
or rewrite the answer. Mark unsafeCertainty=true for guaranteed or deterministic outcomes.

QUESTION
{question}

PROPOSED ANSWER
{response.answer}

CITED APPROVED CLAIMS
{json.dumps(cited_claims, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "supported": true,
  "unsafeCertainty": false,
  "unsupportedStatements": []
}}"""
        payload: dict[str, Any] | None = None
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                result = await self.agent_runtime.run_skill_prompt_task(
                    "vedicdust-consultation-grounding-audit",
                    prompt,
                    skills=["vedicdust-consultation"],
                    max_turns=2,
                    allow_file_tools=False,
                )
                payload = self._parse_json_object(result.raw_text)
                break
            except (RuntimeError, ValueError) as exc:
                last_error = exc
        if payload is None:
            raise ValueError(
                "consultation grounding audit did not return valid JSON"
            ) from last_error
        unsupported = self._bounded_string_list(
            payload.get("unsupportedStatements"),
            limit=4,
            max_length=500,
        )
        if payload.get("supported") is not True or payload.get("unsafeCertainty") is True:
            detail = unsupported[0] if unsupported else "answer exceeded its cited evidence"
            raise ValueError(f"consultation answer failed grounding audit: {detail}")

    @staticmethod
    def _safe_agent_failure_reason(exc: Exception) -> str:
        message = re.sub(r"\s+", " ", str(exc)).strip()
        return message[:180] or type(exc).__name__

    @staticmethod
    def _bounded_string_list(value: Any, *, limit: int, max_length: int) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Agent response list field has an invalid shape")
        result = [str(item).strip() for item in value[:limit] if str(item).strip()]
        if any(len(item) > max_length for item in result):
            raise ValueError("Agent response list item is too long")
        return result

    def _append_consultation_exchange(
        self,
        session_id: str,
        question: str,
        response: ConsultationAnswerResponse,
    ) -> None:
        path = "consultation_conversation.json"
        existing_text = self.workspace.read_artifact_text(session_id, path)
        existing = self._json_dict(existing_text or "")
        raw_exchanges = existing.get("exchanges")
        exchanges: list[Any] = list(raw_exchanges) if isinstance(raw_exchanges, list) else []
        exchanges.append(
            {
                "askedAt": datetime.now(timezone.utc).isoformat(),
                "question": question,
                **response.model_dump(by_alias=True),
            }
        )
        payload = {
            "schemaVersion": "vedicdust-consultation-conversation/1.0.0",
            "sessionId": session_id,
            "exchanges": exchanges[-20:],
        }
        self.workspace.write_artifact(
            session_id,
            path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        )

    def _write_initial_rectification_state(
        self,
        session_id: str,
        birth_input_context_json: str,
        sensitivity_scan_json: str,
    ) -> dict[str, object]:
        state = self.rectification.initial_state(
            self._json_dict(birth_input_context_json),
            self._json_dict(sensitivity_scan_json),
        )
        self.workspace.write_artifact(
            session_id,
            "chart_rectification_state.json",
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        )
        return state

    def _write_prevalidation_result(
        self, session_id: str, *, feedback_markdown: str | None = None
    ) -> dict[str, object] | None:
        artifact_paths = (
            "reader_prevalidation.md",
            "user_context.md",
            CHART_RECORD_JSON,
            "sensitivity_scan.json",
            "prevalidation_result.json",
        )
        artifacts = {
            path: self.workspace.read_artifact_text(session_id, path) or ""
            for path in artifact_paths
        }
        prevalidation = artifacts.get("reader_prevalidation.md", "")
        if not prevalidation.strip():
            return None
        feedback = (
            feedback_markdown
            if feedback_markdown is not None
            else artifacts.get("user_context.md", "")
        )
        result = self._build_prevalidation_result(
            prevalidation,
            feedback,
            artifacts.get(CHART_RECORD_JSON, ""),
            artifacts.get("sensitivity_scan.json", ""),
        )
        previous = self._json_dict(artifacts.get("prevalidation_result.json", ""))
        previous_attempt = int(previous.get("qualityAttempt") or 0)
        quality_attempt = previous_attempt
        if result.get("status") == "scored":
            quality_attempt += 1
        result["qualityAttempt"] = quality_attempt
        decision = result.get("decision")
        if (
            quality_attempt >= 2
            and isinstance(decision, dict)
            and decision.get("reportAllowed") is not True
        ):
            decision.update(
                {
                    "nextStep": "review_birth_details_or_stop",
                    "reason": (
                        "Two independent Reader validation rounds did not meet the publication "
                        "threshold. Stop regenerating questions and review the recorded birth "
                        "details or subject identity; these answers must not select another chart."
                    ),
                }
            )
        self.workspace.write_artifact(
            session_id,
            "prevalidation_result.json",
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            "prevalidation_result.json",
            producer="vedic-reader:prevalidation-result",
            dependency_paths=PREVALIDATION_DEPENDENCY_PATHS,
        )
        return result

    def _apply_reader_quality_decision(
        self,
        session_id: str,
        prevalidation_result: dict[str, object],
    ) -> None:
        state = self._json_dict(
            self.workspace.read_artifact_text(session_id, "chart_rectification_state.json") or ""
        )
        if not state:
            return
        if state.get("status") == "not_required":
            decision = prevalidation_result.get("decision")
            if isinstance(decision, dict):
                prevalidation_result["decision"] = self.rectification.apply_prevalidation_decision(
                    decision,
                    state,
                )
                self.workspace.write_artifact(
                    session_id,
                    "prevalidation_result.json",
                    json.dumps(prevalidation_result, ensure_ascii=False, indent=2) + "\n",
                )
                self.workspace.mark_artifact_checkpoint(
                    session_id,
                    "prevalidation_result.json",
                    producer="vedic-reader:prevalidation-result",
                )
            return
        raise ValueError(
            "Reader feedback cannot update a chart-candidate state. Rebuild the session from "
            "structured dated events and the deterministic rectification policy."
        )

    def _materialize_rectification_selection(
        self,
        session_id: str,
        updated_state: dict[str, Any],
        artifacts: dict[str, str],
    ) -> dict[str, Any]:
        """Refine and recalculate an already selected bounded candidate."""

        if updated_state.get("status") == "needs_recalculation":
            updated_state = self.calculator.refine_selected_time_boundary(
                updated_state,
                self._json_dict(artifacts.get("birth_input_context.json", "")),
            )
            boundary_refinement = updated_state.get("boundaryRefinement")
            if (
                isinstance(boundary_refinement, dict)
                and boundary_refinement.get("status") == "skipped"
            ):
                return self.rectification.reject_unresolved_boundary_selection(updated_state)

        if updated_state.get("status") == "needs_recalculation":
            rectified_input = self.rectification.rectified_birth_input(
                updated_state,
                self._json_dict(artifacts.get("birth_input_context.json", "")),
                self._json_dict(artifacts.get(CHART_RECORD_JSON, "")),
            )
            if rectified_input is not None:
                chart_revision = self._next_chart_revision(updated_state)
                self._archive_current_chart_artifacts(session_id, chart_revision - 1, artifacts)
                identity = self._chart_record_identity(
                    session_id,
                    revision=chart_revision,
                )
                previous_record = ChartRecord.model_validate_json(
                    artifacts.get(CHART_RECORD_JSON, "")
                )
                selected_id = str(updated_state.get("selectedCandidateId") or "")
                selected_candidate = next(
                    (
                        candidate
                        for candidate in updated_state.get("candidates") or []
                        if isinstance(candidate, dict)
                        and str(candidate.get("candidateId") or "") == selected_id
                    ),
                    None,
                )
                selected_window = (
                    self._state_time_range(
                        selected_candidate.get("interval"),
                        previous_record.canonical_moment.timezone_id,
                    )
                    if isinstance(selected_candidate, dict)
                    and previous_record.canonical_moment is not None
                    else None
                )
                if selected_window is None:
                    raise ValueError(
                        "Rectification selection is missing its authoritative candidate interval"
                    )
                calculation = self.calculator.calculate(
                    rectified_input,
                    identity=identity,
                    timing_window_override=selected_window,
                )
                recalculated_record = ChartRecord.model_validate_json(calculation.chart_record_json)
                recalculated_record.birth_assertion = previous_record.birth_assertion
                recalculated_record.rectification = previous_record.rectification
                recalculated_record.sensitivity_boundaries = previous_record.sensitivity_boundaries
                recalculated_record.status = "rectification_required"
                recalculated_chart_record_json = (
                    recalculated_record.model_dump_json(by_alias=True, indent=2) + "\n"
                )
                recalculated_input_context_json = self._preserve_reported_input_context(
                    artifacts.get("birth_input_context.json", ""),
                    calculation.birth_input_context_json,
                    rectified_input,
                    updated_state,
                )
                self._write_chart_calculation(
                    session_id,
                    recalculated_input_context_json,
                    artifacts.get("sensitivity_scan.json", "") or calculation.sensitivity_scan_json,
                    recalculated_chart_record_json,
                    producer="calculator:rectification",
                    identity=identity,
                )
                self.workspace.write_artifact(
                    session_id,
                    ACTIVE_CHART_SENSITIVITY_JSON,
                    calculation.sensitivity_scan_json,
                )
                self.workspace.write_session_manifest(
                    session_id, locale=self.workspace.read_session_locale(session_id)
                )
                updated_state = self.rectification.apply_chart_revision(
                    updated_state,
                    rectified_input=rectified_input,
                    chart_revision=chart_revision,
                )
            else:
                updated_state = self.rectification.reject_unmaterializable_selection(updated_state)
        return updated_state

    def _preserve_reported_input_context(
        self,
        original_context_json: str,
        recalculated_context_json: str,
        rectified_input: BirthInput,
        rectification_state: dict[str, Any] | None = None,
    ) -> str:
        """Keep user assertions distinct from the active rectified calculation input."""

        original = self._json_dict(original_context_json)
        recalculated = self._json_dict(recalculated_context_json)
        original_time = original.get("time")
        original_time = original_time if isinstance(original_time, dict) else {}
        original_place = original.get("place")
        original_place = original_place if isinstance(original_place, dict) else {}
        active_time = recalculated.get("time")
        active_time = active_time if isinstance(active_time, dict) else {}
        active_place = recalculated.get("place")
        active_place = active_place if isinstance(active_place, dict) else {}
        selected_id = str((rectification_state or {}).get("selectedCandidateId") or "")
        selected_candidate = next(
            (
                candidate
                for candidate in (rectification_state or {}).get("candidates") or []
                if isinstance(candidate, dict)
                and str(candidate.get("candidateId") or "") == selected_id
            ),
            None,
        )
        selected_interval = (
            selected_candidate.get("interval") if isinstance(selected_candidate, dict) else None
        )

        recalculated["reportedInput"] = {
            "time": copy.deepcopy(original_time),
            "place": copy.deepcopy(original_place),
        }
        recalculated["activeCanonicalInput"] = {
            "localDate": rectified_input.birth_date,
            "localTime": rectified_input.birth_time,
            "place": {
                "resolvedLabel": active_place.get("resolvedLabel"),
                "coordinates": copy.deepcopy(active_place.get("coordinates")),
                "timezone": active_place.get("timezone"),
            },
            "source": "deterministic_event_selection",
            "precision": "bounded_interval",
            "candidateId": (
                selected_candidate.get("candidateId")
                if isinstance(selected_candidate, dict)
                else None
            ),
            "selectedInterval": copy.deepcopy(selected_interval),
        }
        for field in ("reported", "date", "precision", "source", "window"):
            if field in original_time:
                active_time[field] = copy.deepcopy(original_time[field])
        active_time["rectificationApplied"] = True
        active_time["rectifiedNormalized"] = rectified_input.birth_time
        if "reported" in original_place:
            active_place["reported"] = original_place["reported"]
        recalculated["time"] = active_time
        recalculated["place"] = active_place
        for field in ("readingFocus", "lifeEvents", "constraints"):
            if field in original:
                recalculated[field] = copy.deepcopy(original[field])
        return json.dumps(recalculated, ensure_ascii=False, indent=2) + "\n"

    def _write_chart_calculation(
        self,
        session_id: str,
        birth_input_context_json: str,
        sensitivity_scan_json: str,
        chart_record_json: str,
        *,
        producer: str,
        identity: ChartRecordIdentity | None = None,
    ) -> None:
        if identity is not None and identity.revision > 1:
            session_dir = self.workspace.require_session_dir(session_id)
            for stale_path in [
                JUDGEMENT_CONTEXT_JSON,
                CLAIM_GRAPH_JSON,
                CONSULTATION_DOSSIER_JSON,
                CONSULTATION_REPORT_MANIFEST_JSON,
                AGENT_CONTEXT_JSON,
                CONSULTATION_REPORT_MD,
            ]:
                (session_dir / stale_path).unlink(missing_ok=True)
        chart_artifacts = {
            "birth_input_context.json": birth_input_context_json,
            "sensitivity_scan.json": sensitivity_scan_json,
            CHART_RECORD_JSON: chart_record_json,
        }
        for path, content in chart_artifacts.items():
            self.workspace.write_artifact(session_id, path, content)
            self.workspace.mark_artifact_checkpoint(session_id, path, producer=producer)
        if identity is not None:
            self._write_reading_session(
                session_id,
                identity=identity,
                locale=self.workspace.read_session_locale(session_id),
                stage="rectification",
                rectification_status=self._chart_rectification_status(chart_record_json),
            )
            self.workspace.mark_artifact_checkpoint(
                session_id,
                READING_SESSION_JSON,
                producer="vedicdust-reading-orchestrator",
            )
            self._write_chart_audit(session_id, chart_record_json)
            self.workspace.mark_artifact_checkpoint(
                session_id,
                CHART_AUDIT_JSON,
                producer="vedicdust-chart-audit",
            )

    def _checkpoint_active_chart_sensitivity(self, session_id: str) -> None:
        if self.workspace.read_artifact_text(session_id, ACTIVE_CHART_SENSITIVITY_JSON) is None:
            return
        self.workspace.mark_artifact_checkpoint(
            session_id,
            ACTIVE_CHART_SENSITIVITY_JSON,
            producer="calculator:rectification-active-sensitivity",
            dependency_paths=[CHART_RECORD_JSON],
        )

    def _archive_current_chart_artifacts(
        self,
        session_id: str,
        revision: int,
        artifacts: dict[str, str],
    ) -> None:
        for path in [
            "birth_input_context.json",
            "sensitivity_scan.json",
            ACTIVE_CHART_SENSITIVITY_JSON,
            CHART_RECORD_JSON,
            JUDGEMENT_CONTEXT_JSON,
            CLAIM_GRAPH_JSON,
            CONSULTATION_DOSSIER_JSON,
            CONSULTATION_REPORT_MANIFEST_JSON,
            AGENT_CONTEXT_JSON,
            CONSULTATION_REPORT_MD,
        ]:
            content = artifacts.get(path)
            if content is None:
                continue
            self.workspace.write_artifact(
                session_id,
                f".runtime/chart_revisions/rev_{revision}/{path}",
                content,
            )

    def _ensure_runtime_contracts(self, session_id: str) -> None:
        current = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON)
        if current is not None:
            if self.workspace.read_artifact_text(session_id, CHART_AUDIT_JSON) is None:
                self._write_chart_audit(session_id, current)
            if self.workspace.read_artifact_text(session_id, READING_SESSION_JSON) is None:
                record = ChartRecord.model_validate_json(current)
                identity = ChartRecordIdentity(
                    reading_session_id=session_id,
                    chart_record_id=record.chart_record_id,
                    subject_id=record.subject.subject_id,
                    revision=record.revision,
                )
                self._write_reading_session(
                    session_id,
                    identity=identity,
                    locale=self.workspace.read_session_locale(session_id),
                    stage="chart_ready",
                    rectification_status=self._chart_rectification_status(current),
                )
            return

    def _chart_record_identity(
        self,
        session_id: str,
        *,
        revision: int,
    ) -> ChartRecordIdentity:
        self._ensure_runtime_contracts(session_id)
        content = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON)
        if content is None:
            raise ValueError("Session is missing chart_record.json")
        record = ChartRecord.model_validate_json(content)
        return ChartRecordIdentity(
            reading_session_id=session_id,
            chart_record_id=record.chart_record_id,
            subject_id=record.subject.subject_id,
            revision=revision,
        )

    def _write_reading_session(
        self,
        session_id: str,
        *,
        identity: ChartRecordIdentity,
        locale: str,
        stage: str,
        rectification_status: str,
        report_status: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        existing = self.workspace.read_artifact_text(session_id, READING_SESSION_JSON)
        created_at = now
        resolved_report_status = report_status or "not_started"
        if existing:
            previous = ReadingSession.model_validate_json(existing)
            created_at = previous.created_at
            resolved_report_status = report_status or previous.report_status
        reading = ReadingSession(
            reading_session_id=session_id,
            subject_id=identity.subject_id,
            chart_record_id=identity.chart_record_id,
            active_chart_revision=identity.revision,
            created_at=created_at,
            updated_at=now,
            locale=locale if locale in {"zh", "en", "ja"} else "en",
            stage="blocked"
            if rectification_status in {"input_resolution_required", "calculation_failed"}
            else stage,
            rectification_status=rectification_status,
            report_status=resolved_report_status,
        )
        self.workspace.write_artifact(
            session_id,
            READING_SESSION_JSON,
            reading.model_dump_json(by_alias=True, indent=2) + "\n",
        )

    @staticmethod
    def _chart_rectification_status(chart_record_json: str) -> str:
        record = ChartRecord.model_validate_json(chart_record_json)
        if record.rectification is None:
            return "not_required"
        return record.rectification.decision.status

    def _write_chart_audit(self, session_id: str, chart_record_json: str) -> None:
        record = ChartRecord.model_validate_json(chart_record_json)
        audit = audit_chart_record(record)
        self.workspace.write_artifact(
            session_id,
            CHART_AUDIT_JSON,
            audit.model_dump_json(by_alias=True, indent=2) + "\n",
        )

    def _sync_chart_record_rectification(
        self,
        session_id: str,
        state: dict[str, object],
    ) -> None:
        content = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON)
        if content is None:
            return
        record = ChartRecord.model_validate_json(content)
        if record.rectification is None:
            return
        record.rectification.selection_policy_id = str(state.get("selectionPolicyId") or "") or None
        record.rectification.event_mapping_id = str(state.get("eventMappingId") or "") or None
        record.rectification.holdout_policy_id = str(state.get("holdoutPolicyId") or "") or None
        method_maturity = str(state.get("methodMaturity") or "product_hypothesis")
        record.rectification.method_maturity = (
            "professionally_validated"
            if method_maturity == "professionally_validated"
            else "product_hypothesis"
        )
        validation_status = str(state.get("validationStatus") or "internal_regression_only")
        record.rectification.validation_status = (
            "independent_professional_review"
            if validation_status == "independent_professional_review"
            else "internal_regression_only"
        )
        record.rectification.source_ids = [
            str(source_id) for source_id in (state.get("sourceIds") or []) if source_id
        ]
        record.rectification.professional_review_fixture_ids = [
            str(fixture_id)
            for fixture_id in (state.get("professionalReviewFixtureIds") or [])
            if fixture_id
        ]
        record.rectification.rectification_benchmark_fixture_ids = [
            str(fixture_id)
            for fixture_id in (state.get("rectificationBenchmarkFixtureIds") or [])
            if fixture_id
        ]
        record.rectification.rounds = [
            RectificationRoundRecord.model_validate(item)
            for item in (state.get("rectificationRounds") or [])
            if isinstance(item, dict)
        ]
        self._sync_candidate_time_bounds(record, state)
        rectification_state_status = str(state.get("status") or "")
        if rectification_state_status == "not_required":
            decision_status = "not_required"
        elif rectification_state_status == "input_resolution_required":
            decision_status = "input_resolution_required"
        elif rectification_state_status == "calculation_failed":
            decision_status = "calculation_failed"
        elif rectification_state_status in {
            "rectification_confirmation_required",
            "corrected_chart_ready",
        }:
            decision_status = "bounded_interval"
        elif rectification_state_status == "underdetermined":
            decision_status = "underdetermined"
        elif rectification_state_status == "multiple_equivalent":
            decision_status = "multiple_equivalent"
        elif rectification_state_status == "needs_recalculation":
            decision_status = "comparing_candidates"
        else:
            decision_status = "collecting_evidence"
        selected = state.get("selectedCandidateId")
        equivalent_ids = [
            str(candidate_id)
            for candidate_id in (state.get("equivalentCandidateIds") or [])
            if candidate_id
        ]
        record.rectification.decision.status = decision_status
        record.rectification.decision.selected_candidate_ids = (
            equivalent_ids
            if decision_status == "multiple_equivalent"
            else [str(selected)]
            if selected
            else []
        )
        record.rectification.decision.confidence = self._selection_confidence(
            state.get("selectionConfidence")
        )
        holdout_result = str(state.get("holdoutResult") or "not_run")
        if holdout_result == "passed":
            record.rectification.decision.holdout_result = "passed"
        elif holdout_result == "failed":
            record.rectification.decision.holdout_result = "failed"
        elif holdout_result == "inconclusive":
            record.rectification.decision.holdout_result = "inconclusive"
        else:
            record.rectification.decision.holdout_result = "not_run"
        raw_report_gate = state.get("reportGate")
        report_gate: dict[str, object] = (
            raw_report_gate if isinstance(raw_report_gate, dict) else {}
        )
        record.rectification.decision.reasons = [
            str(
                report_gate.get("reason")
                or f"Rectification state: {rectification_state_status or 'unknown'}."
            )
        ]
        if decision_status == "bounded_interval":
            selected_candidate = next(
                (
                    candidate
                    for candidate in record.rectification.candidates
                    if candidate.candidate_id == str(selected)
                ),
                None,
            )
            if selected_candidate is None:
                raise ValueError(
                    "Rectification selected candidate is absent from the persisted candidate set"
                )
            record.status = "rectified"
            record.rectification.decision.unresolved_questions = []
            if selected_candidate.ayanamsa_risk == "high":
                if record.rectification.decision.confidence.rank > ConfidenceGrade.PROVISIONAL.rank:
                    record.rectification.decision.confidence = ConfidenceGrade.PROVISIONAL
                record.rectification.decision.reasons = [
                    *record.rectification.decision.reasons,
                    "Selected candidate sits on an ayanamsa sign-boundary; the sidereal "
                    "cross-check disagrees with the configured ayanamsa near this candidate's lagna.",
                ]
                record.rectification.decision.unresolved_questions = [
                    "Confirm the birth lagna against an alternate ayanamsa before treating "
                    "this bounded interval as final."
                ]
            record.rectification.decision.resulting_interval = selected_candidate.interval
            record.rectification.decision.resulting_intervals = []
            if record.canonical_moment is not None:
                place_confidences = [
                    evidence.confidence for evidence in record.canonical_moment.place.evidence
                ]
                record.canonical_moment.resolution_confidence = self._minimum_confidence(
                    [
                        record.rectification.decision.confidence,
                        *place_confidences,
                    ]
                )
        elif decision_status == "not_required":
            record.status = "ready_for_judgement"
            record.rectification.decision.resulting_interval = None
            record.rectification.decision.resulting_intervals = []
        elif decision_status == "input_resolution_required":
            record.status = "blocked"
            record.rectification.decision.resulting_interval = None
            record.rectification.decision.resulting_intervals = []
            record.rectification.decision.unresolved_questions = [
                "Resolve the civil-time ambiguity or place input before rectification."
            ]
        elif decision_status == "calculation_failed":
            record.status = "blocked"
            record.rectification.decision.resulting_interval = None
            record.rectification.decision.resulting_intervals = []
            record.rectification.decision.unresolved_questions = [
                "Retry deterministic candidate scoring before rectification."
            ]
        elif decision_status == "underdetermined":
            record.status = "rectification_required"
            record.rectification.decision.resulting_interval = None
            record.rectification.decision.unresolved_questions = [
                "The birth-time interval remains underdetermined; provide a narrower source "
                "time or additional dated life events."
            ]
            record.rectification.decision.resulting_intervals = []
        elif decision_status == "multiple_equivalent":
            record.status = "ready_for_judgement"
            record.rectification.decision.resulting_interval = None
            candidates_by_id = {
                candidate.candidate_id: candidate for candidate in record.rectification.candidates
            }
            missing_candidate_ids = [
                candidate_id
                for candidate_id in equivalent_ids
                if candidate_id not in candidates_by_id
            ]
            if missing_candidate_ids:
                raise ValueError(
                    "Equivalent rectification candidates are absent from the persisted candidate set: "
                    + ", ".join(missing_candidate_ids)
                )
            record.rectification.decision.resulting_intervals = [
                candidates_by_id[candidate_id].interval for candidate_id in equivalent_ids
            ]
            record.rectification.decision.unresolved_questions = [
                "Equivalent bounded birth-time ranges remain. This report uses only facts "
                "stable across the complete reported time window and does not claim one exact time."
            ]
        else:
            record.status = "rectification_required"
            record.rectification.decision.resulting_interval = None
            record.rectification.decision.resulting_intervals = []
        record = ChartRecord.model_validate(record.model_dump(by_alias=True, mode="json"))
        updated = record.model_dump_json(by_alias=True, indent=2) + "\n"
        self.workspace.write_artifact(session_id, CHART_RECORD_JSON, updated)
        self.workspace.mark_artifact_checkpoint(
            session_id,
            CHART_RECORD_JSON,
            producer="vedicdust-rectification-orchestrator",
        )
        self._write_chart_audit(session_id, updated)
        self.workspace.mark_artifact_checkpoint(
            session_id,
            CHART_AUDIT_JSON,
            producer="vedicdust-chart-audit",
        )

    @classmethod
    def _sync_candidate_time_bounds(
        cls,
        record: ChartRecord,
        state: dict[str, object],
    ) -> None:
        if record.rectification is None or record.canonical_moment is None:
            return
        timezone_id = record.canonical_moment.timezone_id
        raw_candidates = {
            str(candidate.get("candidateId") or ""): candidate
            for candidate in state.get("candidates") or []
            if isinstance(candidate, dict) and candidate.get("candidateId")
        }
        synchronized: list[CandidateInterval] = []
        for candidate in record.rectification.candidates:
            raw = raw_candidates.get(candidate.candidate_id)
            if not isinstance(raw, dict):
                synchronized.append(candidate)
                continue
            interval = cls._state_time_range(raw.get("interval"), timezone_id)
            left_uncertainty = cls._state_time_range(
                raw.get("leftBoundaryUncertainty"), timezone_id
            )
            payload = candidate.model_dump(by_alias=False)
            if interval is not None:
                payload["interval"] = interval
            payload["boundary_resolution_seconds"] = int(
                raw.get("boundaryResolutionSeconds") or candidate.boundary_resolution_seconds
            )
            payload["left_boundary_uncertainty"] = left_uncertainty
            synchronized.append(CandidateInterval.model_validate(payload))
        record.rectification.candidates = synchronized

        for raw in raw_candidates.values():
            members = raw.get("members") or []
            if any(
                isinstance(member, dict) and member.get("axis") == "place" for member in members
            ):
                continue
            refined = cls._state_time_range(raw.get("leftBoundaryUncertainty"), timezone_id)
            resolution = int(raw.get("boundaryResolutionSeconds") or 60)
            if refined is None or resolution >= 60:
                continue
            for boundary in record.sensitivity_boundaries:
                uncertainty = boundary.uncertainty_interval
                if (
                    boundary.axis == "time"
                    and uncertainty is not None
                    and uncertainty.start <= refined.start
                    and refined.end <= uncertainty.end
                ):
                    boundary.uncertainty_interval = refined
                    boundary.at = refined.end
                    boundary.resolution_seconds = resolution
                    break

    @staticmethod
    def _state_time_range(value: object, timezone_id: str) -> TimeRange | None:
        if not isinstance(value, dict):
            return None

        def parse(key: str) -> datetime:
            utc_value = value.get(f"{key}Utc")
            if utc_value:
                parsed = datetime.fromisoformat(str(utc_value))
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    raise ValueError(f"{key}Utc must include an offset")
                return parsed
            local_value = value.get(key)
            if not local_value:
                raise ValueError(f"candidate interval is missing {key}")
            parsed = datetime.fromisoformat(str(local_value).replace(" ", "T"))
            if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                return parsed
            return resolve_civil_time(parsed, timezone_id)

        return TimeRange(start=parse("start"), end=parse("end"))

    @staticmethod
    def _selection_confidence(value: object) -> ConfidenceGrade:
        normalized = str(value or "").lower()
        if normalized == "high":
            return ConfidenceGrade.CORROBORATED
        if normalized == "medium":
            return ConfidenceGrade.PROVISIONAL
        return ConfidenceGrade.PROVISIONAL

    @staticmethod
    def _minimum_confidence(values: list[ConfidenceGrade]) -> ConfidenceGrade:
        rank = {
            ConfidenceGrade.UNAVAILABLE: 0,
            ConfidenceGrade.DISPUTED: 1,
            ConfidenceGrade.PROVISIONAL: 2,
            ConfidenceGrade.CORROBORATED: 3,
            ConfidenceGrade.VERIFIED: 4,
        }
        return min(values, key=lambda value: rank[value])

    def _sync_reading_session_stage(self, session_id: str, runtime_stage: str) -> None:
        if self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON) is None:
            return
        identity = self._chart_record_identity(
            session_id,
            revision=self._active_chart_revision(session_id),
        )
        record_json = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON) or ""
        rectification_status = self._chart_rectification_status(record_json)
        stage_map = {
            "reader_ready": "chart_ready",
            "reader_validation": (
                "ready_for_judgement"
                if rectification_status
                in {"not_required", "bounded_interval", "multiple_equivalent"}
                else "rectification"
            ),
            "core_in_progress": "report_in_progress",
            "core_complete": "report_ready",
            "rectifier_complete": (
                "ready_for_judgement"
                if rectification_status
                in {"not_required", "bounded_interval", "multiple_equivalent"}
                else "rectification"
            ),
            "qa_complete": "report_ready",
            "error": "blocked",
        }
        report_status_map = {
            "core_in_progress": "in_progress",
            "core_complete": "ready",
            "qa_complete": "ready",
            "error": "blocked",
        }
        self._write_reading_session(
            session_id,
            identity=identity,
            locale=self.workspace.read_session_locale(session_id),
            stage=stage_map.get(runtime_stage, "chart_ready"),
            rectification_status=rectification_status,
            report_status=report_status_map.get(runtime_stage),
        )

    def _active_chart_revision(self, session_id: str) -> int:
        content = self.workspace.read_artifact_text(session_id, READING_SESSION_JSON)
        if content:
            return ReadingSession.model_validate_json(content).active_chart_revision
        record = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON)
        if record:
            return ChartRecord.model_validate_json(record).revision
        return 1

    @staticmethod
    def _next_chart_revision(state: dict[str, object]) -> int:
        active = state.get("activeChartRevision")
        if isinstance(active, dict):
            try:
                return int(active.get("revision") or 0) + 1
            except (TypeError, ValueError):
                return 1
        return 1

    @staticmethod
    def _json_dict(content: str) -> dict[str, object]:
        try:
            payload = json.loads(content) if content.strip() else {}
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _build_prevalidation_result(
        self,
        prevalidation_markdown: str,
        feedback_markdown: str,
        chart_record_json: str,
        sensitivity_scan_json: str,
    ) -> dict[str, object]:
        try:
            chart_payload = json.loads(chart_record_json) if chart_record_json.strip() else {}
        except json.JSONDecodeError:
            chart_payload = {}
        anchors = self._parse_prevalidation_anchors(prevalidation_markdown)
        answers = self._parse_prevalidation_feedback(feedback_markdown)
        subject = self._prevalidation_subject_context(chart_record_json, sensitivity_scan_json)
        scored_anchors: list[dict[str, object]] = []
        total_score = 0.0
        answered_count = 0
        for anchor in anchors:
            answer = answers.get(int(anchor["index"]))
            score = self._prevalidation_answer_score(answer)
            if score is not None:
                total_score += score
                answered_count += 1
            scored_anchors.append(
                {
                    **anchor,
                    "answer": answer or "pending",
                    "score": score,
                }
            )
        max_score = len(anchors)
        hit_rate = (total_score / max_score) if max_score else None
        status = (
            "scored" if answered_count == max_score and max_score > 0 else "waiting_for_feedback"
        )
        decision = self._prevalidation_decision(
            total_score,
            max_score,
            status=status,
            time_reliability=str(subject.get("timeReliability") or "uncertain"),
            input_risk_level=str(subject.get("inputRiskLevel") or "unknown"),
            report_readiness=(
                subject.get("reportReadiness")
                if isinstance(subject.get("reportReadiness"), dict)
                else {}
            ),
        )
        return {
            "schemaVersion": "vedic-prevalidation-result/2.0.0",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "chartRecordId": (
                chart_payload.get("chartRecordId") if isinstance(chart_payload, dict) else None
            ),
            "chartRevision": (
                chart_payload.get("revision") if isinstance(chart_payload, dict) else None
            ),
            "chartRecordSha256": hashlib.sha256(chart_record_json.encode("utf-8")).hexdigest(),
            "status": status,
            "subject": subject,
            "score": {
                "answered": answered_count,
                "total": round(total_score, 2),
                "max": max_score,
                "hitRate": round(hit_rate, 4) if hit_rate is not None else None,
            },
            "decision": decision,
            "anchors": scored_anchors,
        }

    def _parse_prevalidation_anchors(self, content: str) -> list[dict[str, object]]:
        anchors: list[dict[str, object]] = []
        pattern = re.compile(
            r"(?ms)^\*\*(\d+)\.\*\*\s*(.*?)(?=^\*\*\d+\.\*\*|\n请逐条回复|\nReply to each anchor|\Z)"
        )
        for match in pattern.finditer(content):
            index = int(match.group(1))
            block = match.group(2).strip()
            rationale_match = re.search(
                r"(?m)^>\s*(?:推导|Derivation|根拠)\s*[：:]\s*(.+)$",
                block,
            )
            rationale = rationale_match.group(1).strip() if rationale_match else ""
            statement = re.sub(
                r"(?m)^>\s*(?:推导|Derivation|根拠|Candidate|候选盘|候選盤|Field|Fields|字段|不稳定字段)\s*[：:].*$",
                "",
                block,
            )
            statement = self._plain_markdown_text(statement)
            anchors.append(
                {
                    "index": index,
                    "statement": statement,
                    "rationale": rationale,
                }
            )
        return anchors

    def _parse_prevalidation_feedback(self, content: str) -> dict[int, str]:
        answers: dict[int, str] = {}
        anchor_pattern = re.compile(
            r"(?ms)^####\s+Anchor\s+(\d+)\s*\n(.*?)(?=^####\s+Anchor\s+\d+\s*\n|\Z)"
        )
        for match in anchor_pattern.finditer(content):
            index = int(match.group(1))
            block = match.group(2)
            answer_raw = re.search(r"(?m)^-\s*User answer:\s*(.+)$", block)
            if answer_raw:
                answers[index] = self._normalize_prevalidation_answer(answer_raw.group(1))
        if answers:
            return answers
        for line in content.splitlines():
            match = re.match(r"\s*(?:\*\*)?(\d+)(?:\.\*\*|[.、:：])?\s*(准|部分准|不准)", line)
            if match:
                answers[int(match.group(1))] = self._normalize_prevalidation_answer(match.group(2))
        return answers

    @staticmethod
    def _discriminating_fact_ids(
        record: ChartRecord,
        field: str,
        candidates: list[object],
    ) -> list[str]:
        existing = {fact.fact_id for fact in record.facts}
        lagna_match = re.fullmatch(r"[dD](\d+)Lagna", field)
        if lagna_match:
            fact_id = f"fact.D{lagna_match.group(1)}.Lagna.position"
            return [fact_id] if fact_id in existing else []

        structure_match = re.fullmatch(r"[dD](\d+)Structure", field)
        if structure_match:
            factor = structure_match.group(1)
            structures: list[dict[str, object]] = []
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                signature = candidate.get("signature")
                if not isinstance(signature, dict):
                    continue
                if factor == "1":
                    structure = signature.get("planetSignIndices")
                else:
                    varga_structures = signature.get("vargaPlanetSignIndices")
                    structure = (
                        varga_structures.get(f"D{factor}")
                        if isinstance(varga_structures, dict)
                        else None
                    )
                if isinstance(structure, dict):
                    structures.append(structure)

            grahas = sorted({str(name) for structure in structures for name in structure})
            changed_grahas = [
                graha
                for graha in grahas
                if len(
                    {json.dumps(structure.get(graha), sort_keys=True) for structure in structures}
                )
                > 1
            ]
            return [
                fact_id
                for graha in changed_grahas
                for fact_id in [f"fact.D{factor}.{graha}.position"]
                if fact_id in existing
            ]

        if field in {"moonSign", "moonNakshatra", "moonPada", "currentDasha"}:
            return ["fact.D1.Moon.position"] if "fact.D1.Moon.position" in existing else []
        if field in {"lagna", "lagnaSign", "ascendant"}:
            return ["fact.D1.Lagna.position"] if "fact.D1.Lagna.position" in existing else []
        return []

    def _normalize_prevalidation_answer(self, raw: str) -> str:
        value = raw.strip().lower()
        if "inaccurate" in value or "not accurate" in value or "不准" in raw:
            return "inaccurate"
        if "partly" in value or "部分" in raw:
            return "partly"
        if "accurate" in value or "准" in raw:
            return "accurate"
        return "recorded"

    def _prevalidation_answer_score(self, answer: str | None) -> float | None:
        if answer == "accurate":
            return 1.0
        if answer == "partly":
            return 0.5
        if answer == "inaccurate":
            return 0.0
        return None

    def _prevalidation_subject_context(
        self,
        chart_record_json: str,
        sensitivity_scan_json: str,
    ) -> dict[str, object]:
        try:
            payload = json.loads(chart_record_json) if chart_record_json.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        subject = payload.get("subject") if isinstance(payload, dict) else {}
        if not isinstance(subject, dict):
            subject = {}
        birth_assertion = payload.get("birthAssertion") if isinstance(payload, dict) else {}
        if not isinstance(birth_assertion, dict):
            birth_assertion = {}
        try:
            sensitivity = json.loads(sensitivity_scan_json) if sensitivity_scan_json.strip() else {}
        except json.JSONDecodeError:
            sensitivity = {}
        if not isinstance(sensitivity, dict):
            sensitivity = {}
        summary = sensitivity.get("summary") if isinstance(sensitivity, dict) else {}
        if not isinstance(summary, dict):
            summary = {}
        report_readiness = sensitivity.get("reportReadiness")
        if not isinstance(report_readiness, dict):
            report_readiness = {}
        stability = sensitivity.get("stability")
        if not isinstance(stability, dict):
            stability = {}
        time_certainty = str(birth_assertion.get("timeCertainty") or "")
        time_precision = {
            "exact_minute": "exact",
            "bounded_window": "approximate",
            "part_of_day": "part_of_day",
            "unknown": "unknown",
        }.get(time_certainty, time_certainty)
        evidence = birth_assertion.get("evidence")
        first_evidence = evidence[0] if isinstance(evidence, list) and evidence else {}
        time_source = (
            str(first_evidence.get("sourceLabel") or "") if isinstance(first_evidence, dict) else ""
        )
        time_reliability = "reported_exact" if time_precision == "exact" else "uncertain"
        return {
            "birthDate": birth_assertion.get("localDate"),
            "birthTime": birth_assertion.get("reportedLocalTime"),
            "birthPlace": birth_assertion.get("reportedPlace"),
            "timePrecision": time_precision or None,
            "timeSource": time_source or None,
            "timeReliability": time_reliability,
            "inputRiskLevel": summary.get("riskLevel"),
            "changedFields": summary.get("changedFields") or [],
            "divisionalConfidence": summary.get("divisionalConfidence") or {},
            "reportReadiness": report_readiness,
            "llmRestrictedEvidence": stability.get("llmRestrictedEvidence") or [],
        }

    def _prevalidation_decision(
        self,
        total_score: float,
        max_score: int,
        *,
        status: str,
        time_reliability: str,
        input_risk_level: str,
        report_readiness: dict[str, object],
    ) -> dict[str, object]:
        min_hit_rate = float(report_readiness.get("minimumHitRateForCore") or 0.8)
        mode = str(report_readiness.get("mode") or "unknown")
        scope = str(report_readiness.get("scope") or "unknown")
        core_allowed_without_rectification = bool(
            report_readiness.get("coreAllowedWithoutRectification", False)
        )
        llm_contract = (
            report_readiness.get("llmContract")
            if isinstance(report_readiness.get("llmContract"), dict)
            else {}
        )
        if status != "scored" or max_score == 0:
            return {
                "nextStep": "await_feedback",
                "timeConfidence": "pending",
                "reportAllowed": False,
                "reportScope": "none",
                "inputRiskLevel": input_risk_level,
                "llmContract": llm_contract,
                "reason": "Feedback is not complete yet.",
            }
        hit_rate = total_score / max_score
        threshold_high = hit_rate >= 0.8
        threshold_medium = hit_rate >= 0.6
        meets_readiness_threshold = hit_rate >= min_hit_rate
        reliable_exact = time_reliability in {"reported_exact", "reliable_exact"}
        if mode == "rectification_required":
            return {
                "nextStep": "complete_deterministic_rectification",
                "timeConfidence": "low",
                "reportAllowed": False,
                "reportScope": scope,
                "inputRiskLevel": input_risk_level,
                "llmContract": llm_contract,
                "reason": (
                    "Input sensitivity scan found chart-changing candidates. "
                    "Complete deterministic dated-event rectification before the full report."
                ),
            }
        if reliable_exact:
            if not meets_readiness_threshold:
                return {
                    "nextStep": "regenerate_prevalidation_or_review_subject",
                    "timeConfidence": "high",
                    "reportAllowed": False,
                    "reportScope": scope,
                    "inputRiskLevel": input_risk_level,
                    "llmContract": llm_contract,
                    "reason": (
                        "The recorded birth time remains the authoritative calculation input, "
                        "but the Reader validation did not meet the publication threshold. "
                        "Regenerate neutral validation questions or review subject identity; "
                        "do not select a different chart from these answers."
                    ),
                }
            return {
                "nextStep": (
                    "report_allowed_with_limits"
                    if input_risk_level in {"medium", "high"}
                    else "report_allowed"
                ),
                "timeConfidence": "high",
                "reportAllowed": True,
                "reportScope": "guarded_full_report" if input_risk_level == "high" else scope,
                "inputRiskLevel": input_risk_level,
                "llmContract": llm_contract,
                "reason": (
                    "The user reported an exact time, the sensitivity scan did not require "
                    "rectification, and validation feedback passed the publication threshold. "
                    "The source label itself did not change confidence."
                ),
            }
        if core_allowed_without_rectification and meets_readiness_threshold:
            return {
                "nextStep": "report_allowed"
                if input_risk_level == "low"
                else "report_allowed_with_limits",
                "timeConfidence": "high" if threshold_high else "medium",
                "reportAllowed": True,
                "reportScope": scope,
                "inputRiskLevel": input_risk_level,
                "llmContract": llm_contract,
                "reason": "Validation feedback satisfies the input-risk report readiness threshold.",
            }
        if threshold_medium:
            return {
                "nextStep": "report_allowed_with_limits"
                if input_risk_level == "low"
                else "review_birth_details_or_stop",
                "timeConfidence": "medium",
                "reportAllowed": input_risk_level == "low",
                "reportScope": "guarded_full_report" if input_risk_level == "low" else scope,
                "inputRiskLevel": input_risk_level,
                "llmContract": llm_contract,
                "reason": (
                    "Medium validation score is enough only for low input-risk sessions; "
                    "medium/high risk sessions should review the recorded birth details before "
                    "continuing. Reader feedback cannot choose another chart."
                ),
            }
        return {
            "nextStep": "review_birth_details_or_stop",
            "timeConfidence": "low",
            "reportAllowed": False,
            "reportScope": scope,
            "inputRiskLevel": input_risk_level,
            "llmContract": llm_contract,
            "reason": (
                "The scan-stable reading did not meet the quality threshold. Review the recorded "
                "birth details or stop; Reader feedback cannot alter the calculated chart."
            ),
        }

    def _plain_markdown_text(self, value: str) -> str:
        return value.replace("**", "").replace("`", "").replace("\n", " ").strip()

    def _reader_default_user_message(self, locale: str) -> str:
        if locale == "zh":
            return "开始读盘验前事"
        if locale == "ja":
            return "事前リーディング確認を開始"
        return "Begin pre-reading validation"

    def _reader_prevalidation_format_instruction(self, locale: str) -> str:
        if locale == "zh":
            return """- Chat response should be only the original short progress / next-step message and ask the user to reply 准 / 不准 / 部分准.
- reader_prevalidation.md must follow the original Step 5 output template:
  - Start with: 在进入完整分析之前，我先验证几个时间锚点来确认出生数据的精度——
- Output 1 to 5 numbered items using only facts stable across the reported input window.
  - Each item uses a bold markdown number followed by one direct, user-answerable lived-experience question in Chinese, e.g. **1.** 2018年前后，您是否经历过一次工作方向的明显变化？
  - The visible question must describe exactly one concrete family, education, relocation, career, relationship, or dated life-event fact. Prefer a dated major event when evidence supports one.
  - Keep the visible question to one short sentence, ideally no more than 45 Chinese characters, and end it with ？.
  - Never put planets, signs, houses, degrees, Yoga, Nakshatra, Dasha, Sanskrit terms, candidate IDs, field IDs, scores, or astrological reasoning in the visible numbered question.
  - Do not ask flattering personality generalities, leading questions, or bundle multiple unrelated events in one item.
  - For a minor, never ask about adult marriage, career, or childbirth; use already-observable family, development, education, or care facts.
  - Each item is followed by one blank line and a quoted derivation line: > 推导：...
  - Do not add signal tables, Yoga tables, 综合轮廓, advice, disclaimers, or app-specific explanation.
  - Do not emit Candidate, Contrast, Event, or Field machine lines. This check cannot select or reject a birth-time candidate.
  - End with: 请逐条回复：**准 / 不准 / 部分准**"""
        if locale == "ja":
            return """- Chat response should be only the original short progress / next-step message and ask the user to reply 正確 / 不正確 / 一部正確.
- reader_prevalidation.md must follow the original Step 5 output template:
  - Start with: 完全な分析に入る前に、出生データの精度を確認するため、いくつかの時間アンカーを検証します——
- Output 1 to 5 numbered items using only facts stable across the reported input window.
  - Each item uses a bold markdown number followed by one short, direct lived-experience question in Japanese, ending with ？.
  - The visible question must cover exactly one concrete or dated fact and must not expose planets, signs, houses, degrees, Yoga, Nakshatra, Dasha, Sanskrit terms, candidate IDs, field IDs, scores, or astrological reasoning.
  - Do not ask flattering personality generalities or bundle unrelated events. For a minor, do not ask adult marriage, career, or childbirth questions.
  - Each item is followed by one blank line and a quoted derivation line: > 根拠：...
  - Do not add signal tables, Yoga tables, synthesis profile, advice, disclaimers, or app-specific explanation.
  - Do not emit Candidate, Contrast, Event, or Field machine lines. This check cannot select or reject a birth-time candidate.
  - End with: 各項目に返信してください：**正確 / 不正確 / 一部正確**"""
        return """- Chat response should be only the original short progress / next-step message and ask the user to reply Accurate / Not accurate / Partly accurate.
- reader_prevalidation.md must follow the original Step 5 output template:
  - Start with: Before entering the full analysis, I will first validate several timing anchors to check the precision of the birth data—
- Output 1 to 5 numbered items using only facts stable across the reported input window.
  - Each item uses a bold markdown number followed by one direct, user-answerable lived-experience question, e.g. **1.** Around 2018, did you make one major change in your work direction?
  - The visible question must describe exactly one concrete family, education, relocation, career, relationship, or dated life-event fact. Keep it to one short sentence, ideally no more than 35 words.
  - Never put planets, signs, houses, degrees, Yoga, Nakshatra, Dasha, Sanskrit terms, candidate IDs, field IDs, scores, or astrological reasoning in the visible question.
  - Do not ask flattering personality generalities, leading questions, or bundle unrelated events. For a minor, do not ask about adult marriage, career, or childbirth.
  - Each item is followed by one blank line and a quoted derivation line: > Derivation: ...
  - Do not add signal tables, Yoga tables, synthesis profile, advice, disclaimers, or app-specific explanation.
  - Do not emit Candidate, Contrast, Event, or Field machine lines. This check cannot select or reject a birth-time candidate.
  - End with: Reply to each anchor: **Accurate / Not accurate / Partly accurate**"""

    def _validate_skill_artifacts(
        self,
        session_id: str,
        skill: str,
        parsed: dict[str, object],
    ) -> None:
        artifacts = parsed.get("artifacts")
        if not isinstance(artifacts, list):
            raise ValueError("Artifact response missing artifacts")
        allowed = self._allowed_output_artifacts(skill)
        if allowed is not None:
            unexpected = [
                str(artifact.get("path"))
                for artifact in artifacts
                if isinstance(artifact, dict) and str(artifact.get("path")) not in allowed
            ]
            if unexpected:
                raise ValueError(
                    f"{skill} returned unexpected artifact(s): {', '.join(unexpected)}"
                )
        if skill == "vedic-synastry":
            unexpected = [
                str(artifact.get("path"))
                for artifact in artifacts
                if isinstance(artifact, dict)
                and not re.fullmatch(
                    r"synastry_[^/]+_\d{8}/reports/relationship_consultation\.md",
                    str(artifact.get("path")),
                )
            ]
            if unexpected:
                raise ValueError(
                    f"{skill} returned unexpected artifact(s): {', '.join(unexpected)}"
                )
        if skill != "vedic-reader":
            return
        prevalidation = ""
        for artifact in artifacts:
            if isinstance(artifact, dict) and artifact.get("path") == "reader_prevalidation.md":
                prevalidation = str(artifact.get("content") or "")
                break
        if not prevalidation.strip():
            raise ValueError("vedic-reader must return reader_prevalidation.md")
        state = self._json_dict(
            self.workspace.read_artifact_text(session_id, "chart_rectification_state.json") or ""
        )
        errors = self.rectification.validate_prevalidation_contract(
            state,
            prevalidation,
            enforce_user_facing_quality=True,
        )
        if errors:
            raise ValueError("vedic-reader output failed validation: " + "; ".join(errors[:4]))

    @staticmethod
    def _allowed_output_artifacts(skill: str) -> set[str] | None:
        if skill == "vedic-reader":
            return {"reader_prevalidation.md"}
        if skill == "vedic-rectifier":
            return {"rectification_report.md"}
        return None

    def _prompt_for(self, input_data: SkillRunInput) -> str:
        locale = self._run_locale(input_data)
        if input_data.skill == "vedic-reader":
            return self._reader_prompt(input_data.user_message, locale)
        if input_data.skill == "vedic-core":
            raise ValueError("vedic-core must run through the native core job")
        if input_data.skill == "vedic-rectifier":
            return self._rectifier_prompt(input_data.user_message, locale)
        if input_data.skill == "vedic-synastry":
            return self._synastry_prompt(input_data.user_message, locale)
        if input_data.skill == "bazi-calculator":
            return self._bazi_calculator_prompt(input_data.user_message, locale)
        if input_data.skill == "bazi-classics-core":
            return self._bazi_prompt(input_data.user_message, locale)
        raise ValueError(f"Unsupported skill: {input_data.skill}")

    def _artifact_prompt_for(self, input_data: SkillRunInput) -> str:
        artifacts = self._artifacts_for_skill(
            input_data.skill,
            self.workspace.read_artifacts(input_data.session_id, include_internal=True),
        )
        if input_data.skill == "vedic-reader":
            artifacts = self._reader_agent_artifacts(artifacts)
        base_prompt = self._prompt_for(input_data)
        return self._artifact_prompt(base_prompt, artifacts)

    @classmethod
    def _reader_agent_artifacts(cls, artifacts: dict[str, str]) -> dict[str, str]:
        """Build the minimal blind-calibration view supplied to the Reader Agent."""

        sanitized: dict[str, str] = {}
        for path, content in artifacts.items():
            if path not in READER_AGENT_INPUT_ARTIFACTS:
                continue
            if not path.endswith(".json"):
                sanitized[path] = content
                continue
            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                # Fail closed: malformed structured input cannot be proven free
                # of reserved evidence and therefore is not Agent-visible.
                continue
            sanitized[path] = (
                json.dumps(
                    cls._without_holdout_evidence(payload),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
        return sanitized

    @classmethod
    def _without_holdout_evidence(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [
                cls._without_holdout_evidence(item)
                for item in value
                if not (
                    isinstance(item, dict) and str(item.get("role") or "").startswith("holdout")
                )
            ]
        if isinstance(value, dict):
            is_life_event_ledger = value.get("schemaVersion") == "life-event-ledger/v1"
            hidden_ledger_fields = {
                "raw",
                "categoryCounts",
                "eligibleEventCount",
                "independentEpisodeCount",
                "correlatedEventCount",
                "calibrationEpisodeCount",
                "holdoutEpisodeCount",
                "eventCollectionRequired",
                "recommendedMinimumEvents",
                "recommendedRectificationUse",
                "semanticEvidence",
            }
            return {
                key: cls._without_holdout_evidence(item)
                for key, item in value.items()
                if "holdout" not in key.lower()
                and not (is_life_event_ledger and key in hidden_ledger_fields)
                and not (
                    value.get("schemaVersion") == "birth-input-context/v1"
                    and key == "lifeEventSemantics"
                )
            }
        if isinstance(value, str) and "holdout" in value.lower():
            return "Reserved validation evidence is hidden from the Agent."
        return value

    def _artifact_prompt(self, base_prompt: str, artifacts: dict[str, str]) -> str:
        artifact_context = "\n\n".join(
            f"--- FILE: {path} ---\n{content}" for path, content in artifacts.items()
        )
        return f"""{base_prompt}

CURRENT WORKSPACE FILES
{artifact_context}

Return valid JSON only, no markdown fence:
{{
  "chatMessage": "short chat-box progress or next-step message matching the selected skill",
  "artifacts": [
    {{
      "path": "exact original output file name, for example reader_prevalidation.md",
      "content": "complete markdown file content"
    }}
  ]
}}

Rules:
- Preserve the selected skill's expected output file names and markdown style.
- Do not omit important sections with phrases like see above.
- Do not include any artifact outside the selected skill's expected file set.
- The JSON wrapper is only for the backend; the user sees the markdown artifacts."""

    def _core_batches(self, user_message: str, locale: str = "en") -> list[dict[str, object]]:
        """Return the VedicDust production DAG."""

        user_line = user_message or "开始分析"
        language_instruction = self._language_instruction(locale)
        return [
            {
                "id": "vedicdust_consultation",
                "label": "VedicDust 专业咨询档案",
                "files": [CONSULTATION_DOSSIER_JSON],
                "dependencies": [],
                "active": CONSULTATION_REPORT_MD,
                "progress_message": "VedicDust 专业咨询档案已完成。",
                "task_name": "vedicdust-consultation",
                "skills": ["vedicdust-consultation"],
                "prompt": f"""Build the native VedicDust Consultation Dossier.

Read:
- chart_record.json and chart_audit.json;
- judgement_context.json;
- claim_graph.json;
- prevalidation_result.json and chart_rectification_state.json.

Use only the listed typed contracts. Do not add a new astrological judgement.
Your primary value is synthesis: turn approved Claims into concise, humane prose
without changing their meaning.

{language_instruction}

Write exactly one file: {CONSULTATION_DOSSIER_JSON}
The file must be valid camelCase JSON conforming to
vedicdust-consultation-dossier/1.0.0. Do not write the final report or any
other file; the backend renders consultation_report.md deterministically.

Hard contract:
- Copy chartRecordId, chartRevision, methodProfileId, and claimGraphVersion.
- Select 3 to 5 executive Claims.
- Use exactly one each of scope, executive_synthesis, chart_foundation,
  timing_outlook, decision_support, follow_up, and technical_evidence; add
  core_architecture when useful and at most five priority_domain sections.
- Assign every released Claim to exactly one section, or record its omission in
  omittedClaimIds. Executive Claims belong to executive_synthesis.
- For executive_synthesis, chart_foundation, core_architecture, priority_domain,
  timing_outlook, and decision_support, write one or two `narratives`. Every
  narrative must have a unique narrativeId, kind, readable text, and 1-4 claimIds.
  The claimIds must be assigned to that same section. Each sentence must be a
  faithful synthesis of those Claims; do not introduce a new event, prediction,
  diagnosis, remedy, or degree of certainty. Keep technical terms out of narrative
  prose unless immediately explained.
- Treat each narrative as an integrated consultation paragraph, not a claim-by-claim
  paraphrase. Start with the practical thesis, connect the cited Claims into one coherent
  pattern, include a realistic manifestation or decision implication only when the cited
  Claims contain it, and state the most important counterweight. Do not repeat titles,
  confidence labels, or technical evidence that the deterministic renderer already supplies.
- Leave narratives empty in scope, follow_up, and technical_evidence.
- chart_foundation and decision_support each require their own assigned Claim.
  technical_evidence must keep claimIds empty.
- Assign timing Claims only to timing_outlook. Return timingWindows as an empty list;
  the backend materializes exact windows, intervals, evidence, language, and confidence.
- Organize priority domains by requested topic and judgementContext priority,
  not by the calculator's technical order.
- The backend replaces dossier ID, scope, confidence, timing windows, locale,
  audience, section titles/order/purpose, omission reasons, unresolved questions,
  visual references, and confidence-disclosure flags from authoritative contracts.
  It preserves narratives only after their Claim references pass validation.
  Do not try to reinterpret those release fields.
- Preserve child/adult life-stage and reader-relationship framing from the Chart Record.
- releaseStatus may be approved only when chart_audit permits judgement, all
  released Claims are accounted for, and dossier qualityChecks pass. Otherwise
  block and explain unresolvedQuestions.
- When rectification status is multiple_equivalent, retain every interval as valid.
  Use only non-restricted, scan-stable Claims and never imply that the calculation
  reference moment is the uniquely corrected birth time.

User request:
{user_line}""",
            },
        ]

    def _batch_files(self, batch: dict[str, object]) -> list[str]:
        return [str(path) for path in batch["files"]]

    def _batch_producer(self, batch: dict[str, object]) -> str:
        return f"vedic-core:{batch.get('id') or 'unknown'}"

    @staticmethod
    def _core_batch_dependency_paths(batch_id: str) -> list[str]:
        if batch_id == "vedicdust_consultation":
            return [JUDGEMENT_CONTEXT_JSON, CLAIM_GRAPH_JSON]
        return []

    def _session_paths(self, session_dir: Path) -> set[str]:
        return {
            path.relative_to(session_dir).as_posix()
            for path in session_dir.rglob("*")
            if path.is_file()
        }

    def _prepare_judgement_context(self, session_id: str, user_message: str = "") -> None:
        chart_record_json = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON)
        if not chart_record_json:
            raise ValueError("Session is missing chart_record.json")
        record = ChartRecord.model_validate_json(chart_record_json)
        sensitivity = self._judgement_sensitivity(session_id)
        restricted_fact_ids, restrict_timing = self._restricted_judgement_evidence(
            record, sensitivity
        )
        catalog = load_rule_catalog()
        context = build_judgement_context(
            record,
            catalog,
            restricted_fact_ids=restricted_fact_ids,
            restrict_timing=restrict_timing,
            requested_topics=[user_message] if user_message.strip() else [],
            now=datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0),
        )
        validate_judgement_context(record, context, catalog)
        graph = build_claim_graph(record, context)
        validate_claim_graph(record, graph, catalog, context)
        self.workspace.write_artifact(
            session_id,
            JUDGEMENT_CONTEXT_JSON,
            context.model_dump_json(by_alias=True, indent=2) + "\n",
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            JUDGEMENT_CONTEXT_JSON,
            producer="vedicdust-judgement-context",
        )
        self.workspace.write_artifact(
            session_id,
            CLAIM_GRAPH_JSON,
            graph.model_dump_json(by_alias=True, indent=2) + "\n",
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            CLAIM_GRAPH_JSON,
            producer="vedicdust-claim-graph",
            dependency_paths=[JUDGEMENT_CONTEXT_JSON],
        )

    def _judgement_sensitivity(self, session_id: str) -> dict[str, object]:
        active = self.workspace.read_artifact_text(session_id, ACTIVE_CHART_SENSITIVITY_JSON)
        original = self.workspace.read_artifact_text(session_id, "sensitivity_scan.json")
        sensitivity = self._json_dict(active or original or "")
        state = self._json_dict(
            self.workspace.read_artifact_text(session_id, "chart_rectification_state.json") or ""
        )
        intersection = state.get("equivalentCandidateIntersection")
        if state.get("status") != "multiple_equivalent" or not isinstance(intersection, dict):
            return sensitivity

        unstable = {str(field) for field in (intersection.get("unstableFields") or []) if field}
        summary = sensitivity.get("summary")
        summary = dict(summary) if isinstance(summary, dict) else {}
        summary["changedFields"] = sorted(
            unstable | {str(field) for field in (summary.get("changedFields") or []) if field}
        )
        sensitivity["summary"] = summary

        readiness = sensitivity.get("reportReadiness")
        readiness = dict(readiness) if isinstance(readiness, dict) else {}
        contract = readiness.get("llmContract")
        contract = dict(contract) if isinstance(contract, dict) else {}
        contract["mustNotUseAsPrimaryEvidence"] = sorted(
            unstable
            | {str(field) for field in (contract.get("mustNotUseAsPrimaryEvidence") or []) if field}
        )
        readiness["llmContract"] = contract
        readiness["scope"] = "stable_intersection_only"
        sensitivity["reportReadiness"] = readiness
        return sensitivity

    @staticmethod
    def _restricted_judgement_evidence(
        record: ChartRecord,
        sensitivity: dict[str, object],
    ) -> tuple[set[str], bool]:
        readiness = sensitivity.get("reportReadiness")
        readiness_data = readiness if isinstance(readiness, dict) else {}
        contract = readiness_data.get("llmContract")
        contract_data = contract if isinstance(contract, dict) else {}
        values = contract_data.get("mustNotUseAsPrimaryEvidence")
        restrictions = [str(value) for value in values] if isinstance(values, list) else []
        restricted: set[str] = {
            fact.fact_id
            for fact in record.facts
            if getattr(fact, "input_stability", ConfidenceGrade.VERIFIED).rank
            < ConfidenceGrade.CORROBORATED.rank
        }
        restrict_timing = False

        # Optional PyJHora capacity outputs may be partially present. A warning is
        # not a reason to block the whole chart, but partial output must not become
        # evidence for a rule that expects the complete measure.
        supplemental_check = next(
            (
                check
                for check in getattr(record, "quality_checks", [])
                if check.check_id == "calculation.supplemental-input-integrity"
            ),
            None,
        )
        if supplemental_check is not None and supplemental_check.status != "passed":
            observed = supplemental_check.observed
            observed_items = observed if isinstance(observed, list) else []
            optional_fact_types: set[str] = set()
            for item in observed_items:
                if not isinstance(item, dict):
                    continue
                field = str(item.get("field") or "")
                if field == "bhava_bala":
                    optional_fact_types.add("strength.bhava_bala")
                elif field == "special_lagnas":
                    optional_fact_types.add("point.special_lagna")
                elif field.startswith("vargeeya_bala"):
                    optional_fact_types.add("strength.vargeeya_bala")
            if not optional_fact_types:
                optional_fact_types = {
                    "strength.bhava_bala",
                    "strength.vargeeya_bala",
                    "point.special_lagna",
                }
            restricted.update(
                fact.fact_id for fact in record.facts if fact.fact_type in optional_fact_types
            )

        d1_lagna_dependent_types = {
            "rashi.lagna.position",
            "rashi.house.lord",
            "rashi.house.occupant",
            "role.house_ownership",
            "relationship.parivartana",
            "yoga.raja.kendra_trikona",
            "strength.shadbala",
            "strength.digbala",
            "strength.bhava_bala",
            "ashtakavarga.sav.house",
            "point.arudha",
            "timing.transit.house",
            "timing.transit.double_transit",
        }

        for value in restrictions:
            normalized = value.strip()
            lagna_match = re.fullmatch(r"[dD](\d+)Lagna", normalized)
            structure_match = re.fullmatch(r"[dD](\d+)Structure", normalized)
            varga_match = re.fullmatch(r"[dD](\d+)", normalized)
            if lagna_match:
                factor = lagna_match.group(1)
                if factor == "1":
                    restricted.update(
                        fact.fact_id
                        for fact in record.facts
                        if fact.fact_type in d1_lagna_dependent_types
                        or (
                            fact.fact_type == "aspect.graha_drishti"
                            and re.search(r"->H(?:[1-9]|1[0-2])$", fact.subject_ref)
                        )
                    )
                else:
                    prefix = f"fact.D{factor}."
                    restricted.update(
                        fact.fact_id for fact in record.facts if fact.fact_id.startswith(prefix)
                    )
            elif structure_match:
                factor = structure_match.group(1)
                if factor == "1":
                    restricted.update(
                        fact.fact_id
                        for fact in record.facts
                        if fact.fact_id.startswith("fact.D1.")
                        and fact.fact_id != "fact.D1.Lagna.position"
                    )
                else:
                    prefix = f"fact.D{factor}."
                    restricted.update(
                        fact.fact_id for fact in record.facts if fact.fact_id.startswith(prefix)
                    )
                    if factor == "9":
                        restricted.update(
                            fact.fact_id
                            for fact in record.facts
                            if fact.fact_type == "varga.vargottama"
                        )
            elif varga_match:
                prefix = f"fact.D{varga_match.group(1)}."
                restricted.update(
                    fact.fact_id for fact in record.facts if fact.fact_id.startswith(prefix)
                )
            elif normalized in {"lagna", "ascendant", "lagnaSign"}:
                restricted.update(
                    fact.fact_id
                    for fact in record.facts
                    if fact.fact_type in d1_lagna_dependent_types
                    or (
                        fact.fact_type == "aspect.graha_drishti"
                        and re.search(r"->H(?:[1-9]|1[0-2])$", fact.subject_ref)
                    )
                )
            elif normalized == "moonSign":
                restricted.update(
                    fact.fact_id
                    for fact in record.facts
                    if fact.fact_id == "fact.D1.Moon.position"
                    or fact.fact_type == "timing.transit.sade_sati"
                    or (
                        fact.fact_type
                        in {
                            "rashi.house.occupant",
                            "relationship.same_sign",
                            "relationship.parivartana",
                            "relationship.dispositor_chain",
                            "aspect.graha_drishti",
                            "strength.dignity",
                            "yoga.raja.kendra_trikona",
                            "yoga.gaja_kesari.structure",
                        }
                        and "Moon" in fact.subject_ref
                    )
                )
            elif normalized in {"moonNakshatra", "moonPada"}:
                restricted.update(
                    fact.fact_id for fact in record.facts if fact.fact_id == "fact.D1.Moon.position"
                )
                restrict_timing = True
            elif normalized in {"currentDasha", "dasha", "vimshottari"}:
                restrict_timing = True
            elif normalized == "charaKaraka7k":
                restricted.update(
                    fact.fact_id for fact in record.facts if fact.fact_type == "karaka.chara"
                )
            elif normalized == "moonPhase":
                restricted.update(
                    fact.fact_id
                    for fact in record.facts
                    if fact.fact_type in {"state.moon_phase", "yoga.gaja_kesari.structure"}
                )
            elif normalized == "combustionStatus":
                restricted.update(
                    fact.fact_id
                    for fact in record.facts
                    if fact.fact_type in {"strength.combustion", "yoga.gaja_kesari.structure"}
                )
            elif normalized == "shadbalaClassification":
                restricted.update(
                    fact.fact_id for fact in record.facts if fact.fact_type == "strength.shadbala"
                )
            elif normalized == "digbalaStatus":
                restricted.update(
                    fact.fact_id for fact in record.facts if fact.fact_type == "strength.digbala"
                )
            elif normalized == "specialPointSigns":
                restricted.update(
                    fact.fact_id for fact in record.facts if fact.fact_type == "point.arudha"
                )
            elif normalized == "specialLagnaSigns":
                restricted.update(
                    fact.fact_id for fact in record.facts if fact.fact_type == "point.special_lagna"
                )
        return restricted, restrict_timing

    async def _finalize_consultation_artifacts(self, session_id: str) -> None:
        chart_record_json = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON)
        judgement_context_json = self.workspace.read_artifact_text(
            session_id, JUDGEMENT_CONTEXT_JSON
        )
        claim_graph_json = self.workspace.read_artifact_text(session_id, CLAIM_GRAPH_JSON)
        dossier_json = self.workspace.read_artifact_text(session_id, CONSULTATION_DOSSIER_JSON)
        if (
            not chart_record_json
            or not judgement_context_json
            or not claim_graph_json
            or not dossier_json
        ):
            return

        self.assert_core_readiness(session_id)

        record = ChartRecord.model_validate_json(chart_record_json)
        context = JudgementContext.model_validate_json(judgement_context_json)
        graph = ClaimGraph.model_validate_json(claim_graph_json)
        dossier = ConsultationDossier.model_validate_json(dossier_json)
        catalog = load_rule_catalog()
        validate_judgement_context(record, context, catalog)
        validate_claim_graph(record, graph, catalog, context)
        dossier = materialize_consultation_dossier(record, graph, context, dossier)
        self.workspace.write_artifact(
            session_id,
            CONSULTATION_DOSSIER_JSON,
            dossier.model_dump_json(by_alias=True, indent=2) + "\n",
        )
        validate_consultation_dossier(record, graph, dossier, context)
        if dossier.release_status != "approved":
            raise ValueError(
                "VedicDust consultation dossier did not pass its release gate: "
                f"{dossier.release_status}"
            )
        await self._audit_consultation_narratives(session_id, dossier, graph)

        manifest = build_report_manifest(dossier)
        agent_context = build_agent_context(record, graph, dossier)
        validate_agent_context(record, graph, dossier, agent_context)
        report = render_consultation_report(record, graph, dossier)

        generated = {
            CONSULTATION_REPORT_MANIFEST_JSON: (
                manifest.model_dump_json(by_alias=True, indent=2) + "\n"
            ),
            AGENT_CONTEXT_JSON: (agent_context.model_dump_json(by_alias=True, indent=2) + "\n"),
            CONSULTATION_REPORT_MD: report,
        }
        for path, content in generated.items():
            self.workspace.write_artifact(session_id, path, content)
            self.workspace.mark_artifact_checkpoint(
                session_id,
                path,
                producer="vedicdust-consultation-renderer",
                dependency_paths=[
                    JUDGEMENT_CONTEXT_JSON,
                    CLAIM_GRAPH_JSON,
                    CONSULTATION_DOSSIER_JSON,
                ],
            )

    async def _audit_consultation_narratives(
        self,
        session_id: str,
        dossier: ConsultationDossier,
        graph: ClaimGraph,
    ) -> None:
        if self.agent_runtime is None or not self.agent_runtime.is_configured():
            return
        if self.workspace.artifact_checkpoint_valid(
            session_id,
            CONSULTATION_GROUNDING_AUDIT_JSON,
            producer="vedicdust-consultation-grounding-audit",
            dependency_paths=[CONSULTATION_DOSSIER_JSON],
        ):
            return
        claims_by_id = {claim.claim_id: claim for claim in graph.claims}
        units: list[dict[str, Any]] = []
        for section in dossier.sections:
            for narrative in section.narratives:
                units.append(
                    {
                        "narrativeId": narrative.narrative_id,
                        "text": narrative.text,
                        "claims": [
                            {
                                "claimId": claims_by_id[claim_id].claim_id,
                                "title": claims_by_id[claim_id].title,
                                "plainStatement": claims_by_id[claim_id].plain_statement,
                                "realWorldExpressions": claims_by_id[
                                    claim_id
                                ].real_world_expressions,
                                "userRelevance": claims_by_id[claim_id].user_relevance,
                                "conditions": claims_by_id[claim_id].conditions,
                                "practicalImplications": claims_by_id[
                                    claim_id
                                ].practical_implications,
                                "limitations": claims_by_id[claim_id].limitations,
                                "certainty": claims_by_id[claim_id].certainty,
                                "timeScope": (
                                    claims_by_id[claim_id].time_scope.model_dump(by_alias=True)
                                    if claims_by_id[claim_id].time_scope is not None
                                    else None
                                ),
                            }
                            for claim_id in narrative.claim_ids
                            if claim_id in claims_by_id
                        ],
                    }
                )
        if not units:
            raise ValueError("consultation has no grounded narrative to audit")
        prompt = f"""Audit each consultation narrative against only its attached approved claims.

{self._language_instruction(dossier.locale)}

Set supported=false if the narrative introduces any event, prediction, diagnosis, remedy,
placement, recommendation, or degree of certainty that the attached claims do not support.
Do not rewrite the narrative and do not use outside astrology knowledge.

NARRATIVES AND CITED CLAIMS
{json.dumps(units, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "results": [
    {{
      "narrativeId": "exact narrativeId",
      "supported": true,
      "unsafeCertainty": false,
      "unsupportedStatements": []
    }}
  ]
}}"""
        expected_ids = {unit["narrativeId"] for unit in units}
        raw_results: list[Any] | None = None
        observed: dict[str, dict[str, Any]] = {}
        audit_model: str | None = None
        audit_attempts = 0
        last_error: Exception | None = None
        for audit_attempts in range(1, 3):
            try:
                result = await self.agent_runtime.run_skill_prompt_task(
                    "vedicdust-consultation-grounding-audit",
                    prompt,
                    skills=["vedicdust-consultation"],
                    max_turns=3,
                    allow_file_tools=False,
                )
                audit_model = getattr(result, "model", None)
                payload = self._parse_json_object(result.raw_text)
                candidate_results = payload.get("results")
                if not isinstance(candidate_results, list):
                    raise ValueError("consultation grounding audit must contain results")
                candidate_observed: dict[str, dict[str, Any]] = {}
                for item in candidate_results:
                    if not isinstance(item, dict):
                        raise ValueError("consultation grounding audit result must be an object")
                    narrative_id = str(item.get("narrativeId") or "")
                    if narrative_id not in expected_ids or narrative_id in candidate_observed:
                        raise ValueError("consultation grounding audit changed the narrative set")
                    candidate_observed[narrative_id] = item
                if set(candidate_observed) != expected_ids:
                    raise ValueError("consultation grounding audit omitted a narrative")
                raw_results = candidate_results
                observed = candidate_observed
                break
            except (RuntimeError, ValueError) as exc:
                last_error = exc
        if raw_results is None:
            raise ValueError(
                "consultation grounding audit returned an invalid contract"
            ) from last_error
        failed = [
            narrative_id
            for narrative_id, item in observed.items()
            if item.get("supported") is not True or item.get("unsafeCertainty") is True
        ]
        if failed:
            raise ValueError(
                "consultation narratives exceeded their cited claims: " + ", ".join(failed)
            )
        audit_payload = {
            "schemaVersion": "vedicdust-consultation-grounding-audit/1.0.0",
            "dossierId": dossier.dossier_id,
            "auditModel": audit_model,
            "auditAttempts": audit_attempts,
            "results": raw_results,
        }
        self.workspace.write_artifact(
            session_id,
            CONSULTATION_GROUNDING_AUDIT_JSON,
            json.dumps(audit_payload, ensure_ascii=False, indent=2) + "\n",
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            CONSULTATION_GROUNDING_AUDIT_JSON,
            producer="vedicdust-consultation-grounding-audit",
            dependency_paths=[CONSULTATION_DOSSIER_JSON],
        )

    def _active_artifact_for_batch(self, batch: dict[str, object], artifacts: list[object]) -> str:
        paths = {str(getattr(artifact, "path")) for artifact in artifacts}
        active = str(batch.get("active") or self._batch_files(batch)[0])
        if active in paths:
            return active
        for fallback in [
            CONSULTATION_REPORT_MD,
            "reader_prevalidation.md",
            "birth_input_context.json",
            CHART_RECORD_JSON,
        ]:
            if fallback in paths:
                return fallback
        return active

    def _chat_message_for_batch(self, batch: dict[str, object], raw_text: str) -> str:
        progress = batch.get("progress_message")
        if progress:
            return str(progress)
        return raw_text.strip()

    def _artifacts_for_skill(self, skill: str, artifacts: list[object]) -> dict[str, str]:
        selected: dict[str, str] = {}
        for artifact in artifacts:
            path = str(getattr(artifact, "path"))
            content = str(getattr(artifact, "content"))
            if skill == "vedic-synastry":
                if path == CHART_RECORD_JSON or path.startswith("synastry_"):
                    selected[path] = content
                continue
            if skill in {"bazi-calculator", "bazi-classics-core"}:
                if path.startswith("bazi_"):
                    selected[path] = content
                continue
            if "/" not in path:
                selected[path] = content
        return selected

    def _reader_prompt(self, user_message: str, locale: str) -> str:
        return f"""Run vedic-reader in Calc mode.

Workspace contains chart_record.json generated by the VedicDust calculation engine.

Follow the active VedicDust reader contract, adapted for the web runtime:
- {self._language_instruction(locale)}
- Do not ask for setup or dependency installation.
- Do not run shell commands.
- Treat chart_record.json as the authoritative deterministic record.
- Read birth_input_context.json, sensitivity_scan.json, and chart_rectification_state.json before writing anchors.
- Proceed only when chart_rectification_state.status is not_required. The bounded scan must be stable; do not use unstable fields as claims.
- Birth-time candidate ranking, holdout evaluation, and chart recalculation are backend-owned. This skill cannot change them.
- Use concrete, past, user-answerable facts as reading-quality checks. Generic personality, appearance, or preference questions remain weak testimony.
- Never restate submitted life events as if the user's confirmation were new independent evidence.
- Stop analysis as soon as you have the required number of concrete, non-duplicative questions that satisfy the format contract. Do not keep expanding the visible reading after sufficient evidence exists.
- Do not emit candidate IDs, event IDs, candidate scores, rectification mappings, times, or coordinates.
- Execute Calc mode Stage 2 and Stage 3 only: signal pre-scan, Yoga scan, and pre-validation reading.
- Write the user-facing pre-validation output to reader_prevalidation.md.
{self._reader_prevalidation_format_instruction(locale)}
- Treat pre-validation as a scoring gate, not as performance writing: do not show the internal SOP, do not add full candidate tables, and do not reframe misses as hits.
- Do not generate core report, career report, love report, daily note, or app-specific claims.
- The backend will deterministically create prevalidation_result.json from reader_prevalidation.md and user feedback; do not hand-write it. Reader feedback cannot select a birth time or recalculate chart_record.json.

User message:
{user_message or self._reader_default_user_message(locale)}"""

    def _rectifier_prompt(self, user_message: str, locale: str) -> str:
        return f"""Render the backend-owned VedicDust rectification audit.

Workspace contains chart_record.json and chart_rectification_state.json.

Rules:
- {self._language_instruction(locale)}
- Treat chart_record.json and chart_rectification_state.json as immutable source records.
- Report only the persisted candidate interval, decision, evidence counts, holdout result,
  confidence, residual uncertainty, and permitted next step.
- Never rank candidates, reinterpret Reader feedback, propose a new time, or ask the user
  to confirm a model-selected time. Candidate selection and recalculation are backend-owned.
- Write rectification_report.md.
- If the state is underdetermined or equivalent, preserve that result exactly and explain what
  additional user evidence the persisted report gate requests.
- Do not run shell commands or request an unrecorded recalculation.
- Do not output app cards, claims, daily notes, or JSON.

User message:
{user_message or "解释生时校正结果"}"""

    def _synastry_prompt(self, user_message: str, locale: str) -> str:
        return f"""Run the VedicDust relationship consultation skill.

Workspace contains chart_record.json for subject A and a synastry_<B>_<YYYYMMDD> folder with:
- chart_record_B.json
- synastry_context.json

Rules:
- {self._language_instruction(locale)}
- Do not read user_context.md.
- Treat synastry_context.json as the authoritative deterministic cross-chart evidence.
- Use chart_record.json and chart_record_B.json only to verify cited placements and timing limits.
- Do not introduce Western degree aspects, composite charts, or Ashtakoota scores because the active method profile does not calculate them.
- Separate observable cross-chart evidence, interpretation, counter-evidence, timing limits, and practical guidance.
- Write one report under the existing folder at reports/relationship_consultation.md.
- Artifact JSON paths must include the synastry_<B>_<YYYYMMDD>/ prefix.
- Chat response should only report progress/completion and the report path.
- Do not output app cards, claims, daily notes, or JSON.

User message:
{user_message or "开始合盘平扫"}"""

    def _bazi_calculator_prompt(self, user_message: str, locale: str) -> str:
        return f"""Run bazi-calculator exactly as the repo-local skill.

Rules:
- {self._bazi_language_instruction(locale)}
- Extract birth details, report context, and calculation settings from the user message.
- If birth_date or calendar_type cannot be determined, stop and ask for the missing fields in chatMessage only.
- If birth_time is missing, use birth_time="" and time_precision="unknown"; preserve the uncertainty warning.
- If birth_place is missing, use "[not provided]" and state that location/solar-time handling is limited.
- If current_date is missing, use today's date from the runtime context if available; otherwise ask for it.
- Call mcp__vedic_backend_tools__bazi_calculate_chart once with emit_artifact_content=true and out_dir="".
- Do not hand-calculate pillars, solar terms, ten gods, hidden stems, relations, luck cycles, or ages.
- Parse the tool result JSON and copy the returned artifacts verbatim into output artifacts:
  bazi_chart_record.json, bazi_chart_foundation.md, bazi_report_context.md.
- Chat response should say the BaZi chart data is ready, mention any warning count or key boundary warning, and recommend bazi-classics-core for the classical report.
- Do not create bazi_life_report.md or any classics interpretation in this skill.

User message:
{user_message or "计算八字排盘数据"}"""

    def _bazi_prompt(self, user_message: str, locale: str) -> str:
        return f"""Run bazi-classics-core exactly as the repo-local skill.

Workspace must contain:
- bazi_chart_foundation.md or bazi_chart_record.json
- bazi_report_context.md

Rules:
- {self._bazi_language_instruction(locale)}
- Use only the BaZi calculator artifacts as the chart fact source of truth.
- Do not hand-calculate pillars, luck cycles, solar terms, or ten gods.
- Follow the skill's three-layer audit: Qiongtong tiaohou, Ziping geju, and Ditiansui qi.
- Preserve the expected markdown outputs: bazi_data_audit.md, bazi_overview.md, bazi_classics_audit.md, bazi_timing_report.md, bazi_life_report.md, bazi_appendix.md.
- If required BaZi calculator artifacts are absent, stop with bazi_data_audit.md explaining that the BaZi calculator must run first.
- Chat response should only report progress/completion and file paths.
- Do not output app cards, daily notes, deterministic claims, or JSON.

User message:
{user_message or "生成八字经典报告"}"""

    def _bazi_language_instruction(self, locale: str) -> str:
        if locale == "zh":
            return (
                "Output language: Simplified Chinese. Keep BaZi terms precise and distinguish "
                "调候用神, 格局用神, 扶抑喜忌, and 通关之神."
            )
        if locale == "ja":
            return (
                "Output language: Japanese. Keep core BaZi terms in Chinese where precision "
                "matters, with short Japanese clarification."
            )
        return (
            "Output language: English. Keep BaZi technical terms in pinyin/Chinese with short "
            "English clarification where useful."
        )

    def _max_turns_for(self, skill: str) -> int:
        return {
            "vedic-reader": 6,
            # vedic-core batches still need several tool turns to load skill
            # resources, inspect prior artifacts, and write the target report.
            "vedic-core": 40,
            "vedic-rectifier": 6,
            "vedic-synastry": 8,
            "vedicdust-consultation": 12,
            "bazi-calculator": 6,
            "bazi-classics-core": 12,
        }[skill]

    def _stage_for(self, skill: str) -> str:
        return {
            "vedic-reader": "reader_validation",
            "vedic-core": "core_complete",
            "vedic-rectifier": "rectifier_complete",
            "vedic-synastry": "synastry_complete",
            "bazi-calculator": "bazi_ready",
            "bazi-classics-core": "bazi_complete",
        }[skill]

    def _preferred_artifact(self, skill: str, artifacts: list[object] | None = None) -> str:
        if skill == "vedic-core" and artifacts:
            if any(
                getattr(artifact, "path", "") == CONSULTATION_REPORT_MD for artifact in artifacts
            ):
                return CONSULTATION_REPORT_MD
        if skill == "vedic-synastry" and artifacts:
            for artifact in artifacts:
                path = getattr(artifact, "path", "")
                if path.endswith("/reports/relationship_consultation.md"):
                    return path
        return {
            "vedic-reader": "reader_prevalidation.md",
            "vedic-core": "reader_prevalidation.md",
            "vedic-rectifier": "rectification_report.md",
            "vedic-synastry": "reports/relationship_consultation.md",
            "bazi-calculator": "bazi_chart_foundation.md",
            "bazi-classics-core": "bazi_life_report.md",
        }[skill]

    def _synastry_folder(self, label: str) -> str:
        slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", label.strip() or "B").strip("_")
        slug = slug[:40] or "B"
        return f"synastry_{slug}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"

    def _parse_artifact_response(self, raw_text: str) -> dict[str, object]:
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            fenced = list(re.finditer(r"```(?:json)?\s*([\s\S]*?)```", raw_text, re.IGNORECASE))
            if fenced:
                payload = json.loads(fenced[-1].group(1))
            else:
                start = raw_text.find("{")
                end = raw_text.rfind("}")
                if start == -1 or end == -1 or end <= start:
                    raise ValueError("Agent did not return artifact JSON")
                payload = json.loads(raw_text[start : end + 1])

        if not isinstance(payload, dict):
            raise ValueError("Artifact response must be a JSON object")
        if not isinstance(payload.get("chatMessage"), str):
            raise ValueError("Artifact response missing chatMessage")
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError("Artifact response missing artifacts")
        for artifact in artifacts:
            if (
                not isinstance(artifact, dict)
                or not artifact.get("path")
                or not artifact.get("content")
            ):
                raise ValueError("Artifact response contains an invalid artifact")
        return payload

    @staticmethod
    def _parse_json_object(raw_text: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            fenced = list(re.finditer(r"```(?:json)?\s*([\s\S]*?)```", raw_text, re.IGNORECASE))
            if fenced:
                payload = json.loads(fenced[-1].group(1))
            else:
                start = raw_text.find("{")
                end = raw_text.rfind("}")
                if start == -1 or end <= start:
                    raise ValueError("Agent did not return a JSON object")
                payload = json.loads(raw_text[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("Agent response must be a JSON object")
        return payload
