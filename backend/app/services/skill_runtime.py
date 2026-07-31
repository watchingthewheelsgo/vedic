from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.agents.claude_runtime import ClaudeRuntime
from app.schemas import (
    BaziSessionInput,
    SkillBirthInput,
    SkillRunInput,
    SkillSessionResponse,
    SynastryBirthInput,
)
from app.services.chart_rectification import ChartRectificationService
from app.services.metadata_store import MetadataStore
from app.services.skill_workspace import SkillWorkspace
from app.services.vedic_calculator import ChartRecordIdentity, VedicCalculator
from app.tools.registry import BackendToolRunner
from app.utils.ids import make_id
from app.vedicdust.models import (
    ChartRecord,
    ClaimGraph,
    ConfidenceGrade,
    ConsultationDossier,
    DiscriminatorOption,
    JudgementContext,
    ReadingSession,
    RectificationAnswer,
    RectificationAnswerBatch,
    RectificationQuestion,
    RectificationQuestionSet,
)
from app.vedicdust.judgement import build_judgement_context
from app.vedicdust.orchestrator import audit_chart_record
from app.vedicdust.reporting import (
    build_agent_context,
    build_report_manifest,
    render_consultation_report,
)
from app.vedicdust.source_registry import load_rule_catalog
from app.vedicdust.synastry import build_synastry_context
from app.vedicdust.validation import (
    validate_agent_context,
    validate_claim_graph,
    validate_consultation_dossier,
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
CHART_RECORD_B_JSON = "chart_record_B.json"
SYNASTRY_CONTEXT_JSON = "synastry_context.json"


@dataclass(frozen=True)
class _AgentWorkspaceSnapshot:
    files: dict[str, bytes]


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

    async def create_reader_session(
        self, input_data: SkillBirthInput, *, owner_user_id: str | None = None
    ) -> SkillSessionResponse:
        session_id = self.workspace.create_session()
        started = datetime.now(timezone.utc)
        identity = ChartRecordIdentity(
            reading_session_id=session_id,
            chart_record_id=make_id("chart"),
            subject_id=make_id("subject"),
        )
        calculation = self.calculator.calculate(input_data, identity=identity)
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
        self._write_reading_session(
            session_id,
            identity=identity,
            locale=input_data.locale,
            stage="chart_ready",
            rectification_status=self._chart_rectification_status(calculation.chart_record_json),
        )
        self._write_chart_audit(session_id, calculation.chart_record_json)
        self._write_initial_rectification_state(
            session_id,
            calculation.birth_input_context_json,
            calculation.sensitivity_scan_json,
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

        base_prompt = self._artifact_prompt_for(input_data)
        prompt = base_prompt
        max_attempts = 2 if input_data.skill == "vedic-reader" else 1
        parsed: dict[str, object] | None = None
        for attempt in range(max_attempts):
            result = await self.agent_runtime.run_skill_prompt_task(
                input_data.skill,
                prompt,
                skills=[input_data.skill],
                max_turns=self._max_turns_for(input_data.skill),
            )
            try:
                parsed = self._parse_artifact_response(result.raw_text)
                self._validate_skill_artifacts(input_data.session_id, input_data.skill, parsed)
                break
            except ValueError as exc:
                if attempt + 1 >= max_attempts:
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
            self._write_rectification_question_set(input_data.session_id)
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
        decision = result.get("decision") if isinstance(result, dict) else {}
        if not isinstance(decision, dict):
            raise ValueError("prevalidation_result.json 缺少 decision，请重新运行验前事。")
        if decision.get("reportAllowed") is not True:
            reason = decision.get("reason") or "输入风险或验前事反馈未达到完整报告门槛。"
            next_step = decision.get("nextStep") or "boundary_scan_or_rectifier"
            raise ValueError(f"完整报告暂不允许生成：{reason} 下一步：{next_step}")
        scope = str(decision.get("reportScope") or "")
        if scope == "prevalidation_or_d1_only":
            raise ValueError(
                "当前输入只允许验前事/低置信D1-only说明，不允许生成完整 vedic-core 报告。"
            )
        if callable(read_artifact_text) and read_artifact_text(session_id, CHART_RECORD_JSON):
            self._prepare_judgement_context(session_id, user_message)

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
        locale = self._run_locale(input_data)
        batches = batches or self.core_batches(input_data.user_message, locale)
        expected = set(self.core_batch_files(batch))
        if not force and self.core_batch_resume_valid(input_data.session_id, batch):
            self._finalize_consultation_artifacts(input_data.session_id)
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
        for attempt in range(2):
            workspace_snapshot = self._snapshot_agent_workspace(session_dir, expected)
            result = await self.agent_runtime.run_skill_task(
                str(batch.get("task_name") or input_data.skill),
                prompt,
                cwd=session_dir,
                skills=selected_skills,
                max_turns=max(self._max_turns_for(skill) for skill in selected_skills),
            )
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
                self._validate_native_core_batch(input_data.session_id, batch_id)
                if is_consultation_batch:
                    self._finalize_consultation_artifacts(input_data.session_id)
                break
            except ValueError as exc:
                if attempt == 1:
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
            self._finalize_consultation_artifacts(input_data.session_id)
        artifacts = self.workspace.read_artifacts(input_data.session_id)
        core_complete = all(
            self.core_batch_resume_valid(input_data.session_id, item) for item in batches
        )
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
        return _AgentWorkspaceSnapshot(files=files)

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
        self._write_rectification_answer_batch(session_id, feedback_markdown)
        if prevalidation_result is not None:
            self._apply_rectification_feedback(
                session_id,
                prevalidation_result,
                feedback_markdown=feedback_markdown,
            )
        decision = (
            prevalidation_result.get("decision") if isinstance(prevalidation_result, dict) else None
        )
        report_allowed = isinstance(decision, dict) and decision.get("reportAllowed") is True
        await self._sync_metadata(
            session_id,
            stage="reader_validation",
            status="validation",
            owner_user_id=owner_user_id,
        )
        return SkillSessionResponse(
            session_id=session_id,
            stage="reader_validation",
            chat_message=(
                "Your feedback has been saved. The full reading can now begin."
                if report_allowed
                else (
                    "Your feedback has been saved. The chart still needs more confirmation "
                    "before the full reading."
                )
            ),
            artifacts=self.workspace.read_artifacts(session_id),
            active_artifact="user_context.md",
        )

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
            "career_complete",
            "love_complete",
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

    def _write_initial_rectification_state(
        self,
        session_id: str,
        birth_input_context_json: str,
        sensitivity_scan_json: str,
    ) -> None:
        state = self.rectification.initial_state(
            self._json_dict(birth_input_context_json),
            self._json_dict(sensitivity_scan_json),
        )
        self.workspace.write_artifact(
            session_id,
            "chart_rectification_state.json",
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        )

    def _write_prevalidation_result(
        self, session_id: str, *, feedback_markdown: str | None = None
    ) -> dict[str, object] | None:
        artifacts = {
            artifact.path: artifact.content
            for artifact in self.workspace.read_artifacts(session_id)
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
        self.workspace.write_artifact(
            session_id,
            "prevalidation_result.json",
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            "prevalidation_result.json",
            producer="vedic-reader:prevalidation-result",
        )
        return result

    def _apply_rectification_feedback(
        self,
        session_id: str,
        prevalidation_result: dict[str, object],
        *,
        feedback_markdown: str | None = None,
    ) -> None:
        artifacts = {
            artifact.path: artifact.content
            for artifact in self.workspace.read_artifacts(session_id)
        }
        state = self._json_dict(artifacts.get("chart_rectification_state.json", ""))
        if not state:
            return
        updated_state = self.rectification.update_from_feedback(
            state,
            artifacts.get("reader_prevalidation.md", ""),
            feedback_markdown
            if feedback_markdown is not None
            else artifacts.get("user_context.md", ""),
            prevalidation_result,
        )

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
                calculation = self.calculator.calculate(rectified_input, identity=identity)
                self._write_chart_calculation(
                    session_id,
                    calculation.birth_input_context_json,
                    calculation.sensitivity_scan_json,
                    calculation.chart_record_json,
                    producer="calculator:rectification",
                    identity=identity,
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
                updated_state["status"] = "needs_more_feedback"
                updated_state["reportGate"] = {
                    "fullReportAllowed": False,
                    "reason": "Selected candidate did not contain a deterministic time or place correction.",
                    "nextStep": "continue_rectification",
                }

        self.workspace.write_artifact(
            session_id,
            "chart_rectification_state.json",
            json.dumps(updated_state, ensure_ascii=False, indent=2) + "\n",
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            "chart_rectification_state.json",
            producer="chart-rectification",
        )
        self._sync_chart_record_rectification(session_id, updated_state)

        decision = prevalidation_result.get("decision")
        if isinstance(decision, dict):
            prevalidation_result["decision"] = self.rectification.apply_prevalidation_decision(
                decision,
                updated_state,
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

    def _archive_current_chart_artifacts(
        self,
        session_id: str,
        revision: int,
        artifacts: dict[str, str],
    ) -> None:
        for path in [
            "birth_input_context.json",
            "sensitivity_scan.json",
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
            stage=stage,
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
        rectification_state_status = str(state.get("status") or "")
        if rectification_state_status == "not_required":
            decision_status = "not_required"
        elif rectification_state_status in {"base_confirmed", "corrected_chart_ready"}:
            decision_status = "bounded_interval"
        elif rectification_state_status == "needs_recalculation":
            decision_status = "comparing_candidates"
        else:
            decision_status = "collecting_evidence"
        selected = state.get("selectedCandidateId")
        record.rectification.decision.status = decision_status
        record.rectification.decision.selected_candidate_ids = [str(selected)] if selected else []
        record.rectification.decision.confidence = self._selection_confidence(
            state.get("selectionConfidence")
        )
        holdout_result = str(state.get("holdoutResult") or "not_run")
        if holdout_result == "passed":
            record.rectification.decision.holdout_result = "passed"
        elif holdout_result == "failed":
            record.rectification.decision.holdout_result = "failed"
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
            record.status = "rectified"
            record.rectification.decision.unresolved_questions = []
            selected_candidate = next(
                (
                    candidate
                    for candidate in record.rectification.candidates
                    if candidate.candidate_id == str(selected)
                ),
                None,
            )
            record.rectification.decision.resulting_interval = (
                selected_candidate.interval if selected_candidate is not None else None
            )
            if selected_candidate is None:
                record.rectification.decision.reasons.append(
                    "The selected candidate has no persisted time interval; the result remains provisional."
                )
        elif decision_status == "not_required":
            record.status = "ready_for_judgement"
            record.rectification.decision.resulting_interval = None
        else:
            record.status = "rectification_required"
            record.rectification.decision.resulting_interval = None
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

    @staticmethod
    def _selection_confidence(value: object) -> ConfidenceGrade:
        normalized = str(value or "").lower()
        if normalized == "high":
            return ConfidenceGrade.CORROBORATED
        if normalized == "medium":
            return ConfidenceGrade.PROVISIONAL
        return ConfidenceGrade.PROVISIONAL

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
                if rectification_status in {"not_required", "bounded_interval"}
                else "rectification"
            ),
            "core_in_progress": "report_in_progress",
            "core_complete": "report_ready",
            "career_complete": "report_ready",
            "love_complete": "report_ready",
            "rectifier_complete": "ready_for_judgement",
            "qa_complete": "report_ready",
            "error": "blocked",
        }
        report_status_map = {
            "core_in_progress": "in_progress",
            "core_complete": "ready",
            "career_complete": "ready",
            "love_complete": "ready",
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
            "schemaVersion": "vedic-prevalidation-result/v1",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
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

    def _write_rectification_question_set(self, session_id: str) -> None:
        read_artifact_text = getattr(self.workspace, "read_artifact_text", None)
        if not callable(read_artifact_text):
            return
        chart_record_json = read_artifact_text(session_id, CHART_RECORD_JSON)
        prevalidation = read_artifact_text(session_id, "reader_prevalidation.md")
        state_json = read_artifact_text(session_id, "chart_rectification_state.json")
        if not chart_record_json or not prevalidation or not state_json:
            return
        state = self._json_dict(state_json)
        candidates = state.get("candidates")
        if not isinstance(candidates, list):
            return
        candidate_ids = [
            str(candidate.get("candidateId"))
            for candidate in candidates
            if isinstance(candidate, dict) and candidate.get("candidateId")
        ]
        if len(candidate_ids) < 2:
            return
        parsed_anchors = self.rectification._parse_candidate_anchors(prevalidation, "")
        blocks = {
            int(item["index"]): str(item["block"])
            for item in self.rectification._parse_prevalidation_blocks(prevalidation)
        }
        record = ChartRecord.model_validate_json(chart_record_json)
        round_number = int(state.get("rectificationRound") or 0) + 1
        questions: list[RectificationQuestion] = []
        for anchor in parsed_anchors:
            supported = [
                str(candidate_id)
                for candidate_id in anchor.get("candidateIds", [])
                if str(candidate_id) in candidate_ids
            ]
            fields = [str(value) for value in anchor.get("unstableFields", [])]
            if not supported or not fields:
                continue
            index = int(anchor["index"])
            contradicted = [
                candidate_id for candidate_id in candidate_ids if candidate_id not in supported
            ]
            questions.append(
                RectificationQuestion(
                    question_id=f"rectification.r{round_number}.q{index}",
                    prompt=self.rectification._statement_from_anchor_block(blocks.get(index, "")),
                    answer_kind="single_choice",
                    discriminating_fact_ids=[
                        self._discriminating_fact_id(field) for field in fields
                    ],
                    candidate_ids=candidate_ids,
                    options=[
                        DiscriminatorOption(
                            option_id="accurate",
                            label="准确",
                            supports_candidate_ids=supported,
                            contradicts_candidate_ids=contradicted,
                        ),
                        DiscriminatorOption(
                            option_id="partly",
                            label="部分准确",
                        ),
                        DiscriminatorOption(
                            option_id="inaccurate",
                            label="不准确",
                            supports_candidate_ids=contradicted,
                            contradicts_candidate_ids=supported,
                        ),
                        DiscriminatorOption(
                            option_id="unknown",
                            label="不确定",
                        ),
                    ],
                    why_asked=(
                        "This answer distinguishes chart candidates that differ on "
                        + ", ".join(fields)
                        + "."
                    ),
                    prohibited_inference=(
                        "The answer may score only the supplied candidates and cannot create "
                        "a chart fact."
                    ),
                )
            )
        if not questions:
            return
        question_set = RectificationQuestionSet(
            chart_record_id=record.chart_record_id,
            round=round_number,
            questions=questions[:5],
            completion_condition=(
                "Submit one observable answer per question, including unknown when memory "
                "is insufficient; the backend then reevaluates all candidates."
            ),
        )
        self.workspace.write_artifact(
            session_id,
            "rectification_question_set.json",
            question_set.model_dump_json(by_alias=True, indent=2) + "\n",
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            "rectification_question_set.json",
            producer="vedicdust-rectification-dialogue",
        )

    def _write_rectification_answer_batch(
        self,
        session_id: str,
        feedback_markdown: str,
    ) -> None:
        read_artifact_text = getattr(self.workspace, "read_artifact_text", None)
        if not callable(read_artifact_text):
            return
        question_set_json = read_artifact_text(session_id, "rectification_question_set.json")
        if not question_set_json:
            return
        question_set = RectificationQuestionSet.model_validate_json(question_set_json)
        feedback = self._parse_prevalidation_feedback(feedback_markdown)
        answers: list[RectificationAnswer] = []
        for question in question_set.questions:
            match = re.search(r"\.q(\d+)$", question.question_id)
            if match is None:
                continue
            normalized = feedback.get(int(match.group(1)), "recorded")
            selected = (
                normalized if normalized in {"accurate", "partly", "inaccurate"} else "unknown"
            )
            answers.append(
                RectificationAnswer(
                    question_id=question.question_id,
                    selected_option_ids=[selected],
                    confidence=(
                        "uncertain" if selected in {"partly", "unknown"} else "fairly_certain"
                    ),
                )
            )
        if not answers:
            return
        batch = RectificationAnswerBatch(
            chart_record_id=question_set.chart_record_id,
            round=question_set.round,
            answers=answers,
        )
        self.workspace.write_artifact(
            session_id,
            "rectification_answer_batch.json",
            batch.model_dump_json(by_alias=True, indent=2) + "\n",
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            "rectification_answer_batch.json",
            producer="vedicdust-rectification-feedback",
        )

    @staticmethod
    def _discriminating_fact_id(field: str) -> str:
        match = re.fullmatch(r"d(\d+)Lagna", field)
        if match:
            return f"fact.D{match.group(1)}.Lagna.position"
        if field in {"moonSign", "moonNakshatra", "moonPada", "currentDasha"}:
            return "fact.D1.Moon.position"
        return "fact.D1.Lagna.position"

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
        reliable_source = bool(
            re.search(r"出生证|医院|birth certificate|hospital", time_source, re.I)
        )
        approximate_source = bool(
            re.search(r"大概|估计|记忆|回忆|未追问|unknown|approx", time_source, re.I)
        )
        time_reliability = (
            "reliable_exact"
            if time_precision == "exact" and reliable_source and not approximate_source
            else "uncertain"
        )
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
        reliable_exact = time_reliability == "reliable_exact"
        if mode == "rectification_required" and not reliable_exact:
            return {
                "nextStep": "candidate_confirmation_or_rectifier",
                "timeConfidence": "low",
                "reportAllowed": False,
                "reportScope": scope,
                "inputRiskLevel": input_risk_level,
                "llmContract": llm_contract,
                "reason": (
                    "Input sensitivity scan found chart-changing candidates. "
                    "Run candidate confirmation or rectifier before full report."
                ),
            }
        if reliable_exact:
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
                    "Reliable exact time source. Low prevalidation score is recorded as signal or expression limitation."
                    if total_score <= 2
                    else "Reliable exact time source and validation feedback recorded."
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
                "nextStep": "report_allowed_with_limits",
                "timeConfidence": "medium",
                "reportAllowed": input_risk_level == "low",
                "reportScope": "guarded_full_report" if input_risk_level == "low" else scope,
                "inputRiskLevel": input_risk_level,
                "llmContract": llm_contract,
                "reason": (
                    "Medium validation score is enough only for low input-risk sessions; "
                    "medium/high risk sessions need stronger feedback or rectification."
                ),
            }
        return {
            "nextStep": "boundary_scan_or_rectifier",
            "timeConfidence": "low",
            "reportAllowed": False,
            "reportScope": scope,
            "inputRiskLevel": input_risk_level,
            "llmContract": llm_contract,
            "reason": "Uncertain time and low validation score; run boundary correction or rectifier before full report.",
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
  - Output 3 to 5 numbered items only.
  - Each item uses a bold markdown number followed by one direct, user-answerable lived-experience question in Chinese, e.g. **1.** 2018年前后，您是否经历过一次工作方向的明显变化？
  - The visible question must describe exactly one concrete family, education, relocation, career, relationship, or dated life-event fact. Prefer a dated major event when evidence supports one.
  - Keep the visible question to one short sentence, ideally no more than 45 Chinese characters, and end it with ？.
  - Never put planets, signs, houses, degrees, Yoga, Nakshatra, Dasha, Sanskrit terms, candidate IDs, field IDs, scores, or astrological reasoning in the visible numbered question.
  - Do not ask flattering personality generalities, leading questions, or bundle multiple unrelated events in one item.
  - For a minor, never ask about adult marriage, career, or childbirth; use already-observable family, development, education, or care facts.
  - Each item is followed by one blank line and a quoted derivation line: > 推导：...
  - Do not add signal tables, Yoga tables, 综合轮廓, advice, disclaimers, or app-specific explanation.
  - If sensitivity_scan.reportReadiness.mode=rectification_required, each item must distinguish candidate signatures or unstable fields through a lived-experience difference; keep all candidate and field terminology out of the visible question.
  - For rectification_required anchors, add quoted machine lines after 推导 using exactly: > Candidate: A, > Field: d9Lagna, and when rectificationPlan.lifeEventFocus is non-empty, > Event: evt_1_201810_marriage. Use candidate IDs, fields, and event IDs from chart_rectification_state.json.
  - End with: 请逐条回复：**准 / 不准 / 部分准**"""
        if locale == "ja":
            return """- Chat response should be only the original short progress / next-step message and ask the user to reply 正確 / 不正確 / 一部正確.
- reader_prevalidation.md must follow the original Step 5 output template:
  - Start with: 完全な分析に入る前に、出生データの精度を確認するため、いくつかの時間アンカーを検証します——
  - Output 3 to 5 numbered items only.
  - Each item uses a bold markdown number followed by one short, direct lived-experience question in Japanese, ending with ？.
  - The visible question must cover exactly one concrete or dated fact and must not expose planets, signs, houses, degrees, Yoga, Nakshatra, Dasha, Sanskrit terms, candidate IDs, field IDs, scores, or astrological reasoning.
  - Do not ask flattering personality generalities or bundle unrelated events. For a minor, do not ask adult marriage, career, or childbirth questions.
  - Each item is followed by one blank line and a quoted derivation line: > 根拠：...
  - Do not add signal tables, Yoga tables, synthesis profile, advice, disclaimers, or app-specific explanation.
  - If sensitivity_scan.reportReadiness.mode=rectification_required, distinguish candidates through a lived-experience difference while keeping candidate and field terminology out of the visible question.
  - For rectification_required anchors, add quoted machine lines after 根拠 using exactly: > Candidate: A, > Field: d9Lagna, and when rectificationPlan.lifeEventFocus is non-empty, > Event: evt_1_201810_marriage. Use candidate IDs, fields, and event IDs from chart_rectification_state.json.
  - End with: 各項目に返信してください：**正確 / 不正確 / 一部正確**"""
        return """- Chat response should be only the original short progress / next-step message and ask the user to reply Accurate / Not accurate / Partly accurate.
- reader_prevalidation.md must follow the original Step 5 output template:
  - Start with: Before entering the full analysis, I will first validate several timing anchors to check the precision of the birth data—
  - Output 3 to 5 numbered items only.
  - Each item uses a bold markdown number followed by one direct, user-answerable lived-experience question, e.g. **1.** Around 2018, did you make one major change in your work direction?
  - The visible question must describe exactly one concrete family, education, relocation, career, relationship, or dated life-event fact. Keep it to one short sentence, ideally no more than 35 words.
  - Never put planets, signs, houses, degrees, Yoga, Nakshatra, Dasha, Sanskrit terms, candidate IDs, field IDs, scores, or astrological reasoning in the visible question.
  - Do not ask flattering personality generalities, leading questions, or bundle unrelated events. For a minor, do not ask about adult marriage, career, or childbirth.
  - Each item is followed by one blank line and a quoted derivation line: > Derivation: ...
  - Do not add signal tables, Yoga tables, synthesis profile, advice, disclaimers, or app-specific explanation.
  - If sensitivity_scan.reportReadiness.mode=rectification_required, distinguish candidates through a lived-experience difference while keeping candidate and field terminology out of the visible question.
  - For rectification_required anchors, add quoted machine lines after Derivation using exactly: > Candidate: A, > Field: d9Lagna, and when rectificationPlan.lifeEventFocus is non-empty, > Event: evt_1_201810_marriage. Use candidate IDs, fields, and event IDs from chart_rectification_state.json.
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
        existing = {
            artifact.path: artifact.content
            for artifact in self.workspace.read_artifacts(session_id)
        }
        state = self._json_dict(existing.get("chart_rectification_state.json", ""))
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
        if skill == "vedic-career":
            return {"career_report.md"}
        if skill == "vedic-love":
            return {"love_report.md"}
        if skill == "vedic-rectifier":
            return {"rectification_report.md"}
        return None

    def _prompt_for(self, input_data: SkillRunInput) -> str:
        locale = self._run_locale(input_data)
        if input_data.skill == "vedic-reader":
            return self._reader_prompt(input_data.user_message, locale)
        if input_data.skill == "vedic-core":
            raise ValueError("vedic-core must run through the native core job")
        if input_data.skill == "vedic-career":
            return self._career_prompt(input_data.user_message, locale)
        if input_data.skill == "vedic-love":
            return self._love_prompt(input_data.user_message, locale)
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
        base_prompt = self._prompt_for(input_data)
        return self._artifact_prompt(base_prompt, artifacts)

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
                "id": "vedicdust_judgement",
                "label": "VedicDust 证据判断",
                "files": [CLAIM_GRAPH_JSON],
                "dependencies": [],
                "active": "reader_prevalidation.md",
                "progress_message": "盘面证据判断已完成。",
                "task_name": "vedicdust-judgement",
                "skills": ["vedicdust-judgement"],
                "prompt": f"""Build the native VedicDust Claim Graph for this reading.

Read exactly these authoritative inputs:
- chart_record.json: deterministic Jyotish facts and timing periods;
- chart_audit.json: calculation and release permissions;
- judgement_context.json: backend-selected topic evidence, allowed rules, eligible
  vargas, restricted facts, and restricted timing periods;
- prevalidation_result.json and chart_rectification_state.json: input confidence
  and unresolved rectification limits.

Use only the listed typed contracts. Do not use any prior prose as evidence.

{language_instruction}

Write exactly one file: {CLAIM_GRAPH_JSON}
The file must be valid camelCase JSON conforming to
vedicdust-claim-graph/1.1.0. Do not write Markdown or any other file.

Hard contract:
- Copy chartRecordId, chartRevision, and methodProfileId exactly.
- Every Claim must bind to exactly one backend-generated Judgement Unit using
  judgementUnitId. Copy judgementCode from that unit's allowedOutputCodes.
- Use only that unit's permittedRuleIds, allowed scopes, fact IDs, timing IDs,
  and timing period IDs. The unit's certaintyCap is an absolute maximum.
- Copy every limitation carried by the Judgement Unit into a released Claim.
- Use only topic IDs, fact IDs, timingPeriodIds, and rule IDs exposed by
  judgement_context.json. A rule is usable only when evaluationStatus is
  eligible; matchedFactIds and the topic evidence lists are hard boundaries.
- Every Claim must use its topic's eligible judgement rule. Workflow gates may
  be added only when they are eligible and their required evidence is cited.
- Use 5 to 10 synthesis Claims. Include chart foundation, the user's requested
  topics, and only the highest-priority remaining topics. Do not produce one
  Claim per planet, house, or varga.
- Each released Claim requires D1 natal promise and capacity evidence. Eligible
  varga evidence may confirm; it may never create the promise.
- A timing Claim requires a domain judgement rule,
  judge.timing.vimshottari-activation, sop.promise-capacity-before-timing, an
  exact timeScope, and exact timingPeriodIds.
- Never use restrictedFactIds as supportingFactIds. Never use
  restrictedTimingPeriodIds. Ineligible D60 cannot support a Claim.
- Record counter-evidence, conditions, and limitations before certainty.
- Use high only for convergent evidence with no material unresolved input risk;
  otherwise use moderate, low/tentative, or withheld.
- User testimony may explain relevance but cannot become a chart promise.
- Health Claims describe wellbeing patterns only; no diagnosis. Finance Claims
  describe conditions only; no promised return. No fatalistic event certainty.
- For omitted requested topics, add an explicit omittedTopics reason.

Each Claim must contain:
claimId, topic, judgementUnitId, judgementCode, title, plainStatement, technicalStatement,
realWorldExpressions, userRelevance, conditions, supportingFactIds,
counterFactIds, timingFactIds, timingPeriodIds, ruleIds, certainty, scope,
status, timeScope, practicalImplications, limitations.

User request:
{user_line}""",
            },
            {
                "id": "vedicdust_consultation",
                "label": "VedicDust 专业咨询档案",
                "files": [CONSULTATION_DOSSIER_JSON],
                "dependencies": ["vedicdust_judgement"],
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
- chart_foundation and decision_support each require their own assigned Claim.
  technical_evidence must keep claimIds empty.
- A Timing Window may use only a timing Claim and its exact fact and period IDs.
  State opportunities, pressures, conditions, and limits; never a guaranteed event.
- Organize priority domains by requested topic and judgementContext priority,
  not by the calculator's technical order.
- Confidence must reflect Birth Assertion, rectification result, Claim
  certainty, and residual uncertainty. Do not invent percentages.
- Preserve child/adult life-stage and reader-relationship framing from the Chart Record.
- releaseStatus may be approved only when chart_audit permits judgement, all
  released Claims are accounted for, and dossier qualityChecks pass. Otherwise
  block and explain unresolvedQuestions.

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
        if batch_id == "vedicdust_judgement":
            return [JUDGEMENT_CONTEXT_JSON]
        if batch_id == "vedicdust_consultation":
            return [JUDGEMENT_CONTEXT_JSON, CLAIM_GRAPH_JSON]
        return []

    def _session_paths(self, session_dir: Path) -> set[str]:
        return {
            path.relative_to(session_dir).as_posix()
            for path in session_dir.rglob("*")
            if path.is_file()
        }

    def _validate_native_core_batch(self, session_id: str, batch_id: str) -> None:
        if batch_id != "vedicdust_judgement":
            return
        chart_record_json = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON)
        context_json = self.workspace.read_artifact_text(session_id, JUDGEMENT_CONTEXT_JSON)
        graph_json = self.workspace.read_artifact_text(session_id, CLAIM_GRAPH_JSON)
        if not chart_record_json or not context_json or not graph_json:
            raise ValueError("VedicDust judgement batch is missing a required contract")
        record = ChartRecord.model_validate_json(chart_record_json)
        context = JudgementContext.model_validate_json(context_json)
        graph = ClaimGraph.model_validate_json(graph_json)
        catalog = load_rule_catalog()
        validate_judgement_context(record, context, catalog)
        validate_claim_graph(record, graph, catalog, context)

    def _prepare_judgement_context(self, session_id: str, user_message: str = "") -> None:
        chart_record_json = self.workspace.read_artifact_text(session_id, CHART_RECORD_JSON)
        if not chart_record_json:
            raise ValueError("Session is missing chart_record.json")
        record = ChartRecord.model_validate_json(chart_record_json)
        sensitivity = self._json_dict(
            self.workspace.read_artifact_text(session_id, "sensitivity_scan.json") or ""
        )
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
        restricted: set[str] = set()
        restrict_timing = False

        for value in restrictions:
            normalized = value.strip()
            lagna_match = re.fullmatch(r"[dD](\d+)Lagna", normalized)
            varga_match = re.fullmatch(r"[dD](\d+)", normalized)
            if lagna_match:
                restricted.add(f"fact.D{lagna_match.group(1)}.Lagna.position")
            elif varga_match:
                prefix = f"fact.D{varga_match.group(1)}."
                restricted.update(
                    fact.fact_id for fact in record.facts if fact.fact_id.startswith(prefix)
                )
            elif normalized in {"lagna", "ascendant", "lagnaSign"}:
                restricted.add("fact.D1.Lagna.position")
            elif normalized in {"moonSign", "moonNakshatra", "moonPada"}:
                restricted.add("fact.D1.Moon.position")
            elif normalized in {"currentDasha", "dasha", "vimshottari"}:
                restrict_timing = True
        return restricted, restrict_timing

    def _finalize_consultation_artifacts(self, session_id: str) -> None:
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

        record = ChartRecord.model_validate_json(chart_record_json)
        context = JudgementContext.model_validate_json(judgement_context_json)
        graph = ClaimGraph.model_validate_json(claim_graph_json)
        dossier = ConsultationDossier.model_validate_json(dossier_json)
        catalog = load_rule_catalog()
        validate_judgement_context(record, context, catalog)
        validate_claim_graph(record, graph, catalog, context)
        validate_consultation_dossier(record, graph, dossier)
        if dossier.release_status != "approved":
            raise ValueError(
                "VedicDust consultation dossier did not pass its release gate: "
                f"{dossier.release_status}"
            )

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

Follow the original vedic-reader workflow exactly, but because this is a web adapter:
- {self._language_instruction(locale)}
- Do not ask for setup or dependency installation.
- Do not run shell commands.
- Treat chart_record.json as the authoritative deterministic record.
- Read birth_input_context.json, sensitivity_scan.json, and chart_rectification_state.json before writing anchors.
- If sensitivity_scan.reportReadiness.mode is rectification_required, make each anchor support one explicit candidate ID from chart_rectification_state.json and focus on unstableFields / changedFields. Do not imply the full report can proceed until feedback passes the backend gate.
- Use chart_rectification_state.rectificationPlan as the backend-owned next-round plan: targetCandidateIds, discriminatingFields, focusAxes, timeWindow, placeWindow, lifeEventFocus, eventCollectionRequired, and requiredAnchorCount are hard constraints.
- When rectificationPlan.lifeEventFocus is non-empty, build validation anchors from those dated events first. Each such anchor must include a machine-readable > Event: line using an eventId or category from chart_rectification_state.lifeEventLedger.
- When rectificationPlan.eventCollectionRequired is true and lifeEventFocus is empty, still produce candidate-bound anchors using available chart differences, but keep them low-confidence and do not claim complete birth-time rectification.
- If chart_rectification_state.status is needs_more_feedback or needs_candidate_bound_checks, generate a new rectification round from rectificationPlan. Use prior feedbackAnchors, roundHistory, and candidate scores to ask narrower candidate-discriminating anchors; do not repeat anchors that already failed to separate candidates.
- Stop analysis as soon as you have the required number of concrete, non-duplicative questions that satisfy the format contract. Do not keep expanding the visible reading after sufficient evidence exists.
- Do not invent candidate IDs, event IDs, times, coordinates, or fields outside chart_rectification_state.rectificationPlan.
- Execute Calc mode Stage 2 and Stage 3 only: signal pre-scan, Yoga scan, and pre-validation reading.
- Write the user-facing pre-validation output to reader_prevalidation.md.
{self._reader_prevalidation_format_instruction(locale)}
- Treat pre-validation as a scoring gate, not as performance writing: do not show the internal SOP, do not add full candidate tables, and do not reframe misses as hits.
- Do not generate core report, career report, love report, daily note, or app-specific claims.
- The backend will deterministically create prevalidation_result.json and update chart_rectification_state.json from reader_prevalidation.md and user feedback; do not hand-write those artifacts.

User message:
{user_message or self._reader_default_user_message(locale)}"""

    def _career_prompt(self, user_message: str, locale: str) -> str:
        return f"""Run the VedicDust career consultation skill.

Workspace contains chart_record.json, claim_graph.json, consultation_dossier.json,
agent_context.json, and consultation_report.md.

Rules:
- {self._language_instruction(locale)}
- Use agent_context.json as the released consultation context and chart_record.json only to
  verify cited fact IDs. Do not introduce a chart judgement absent from claim_graph.json.
- Write career_report.md with conclusions, evidence, counter-evidence, timing limits,
  decision support, and follow-up questions.
- Chat response should only report progress/completion and file paths.

User message:
{user_message or "分析事业"}"""

    def _love_prompt(self, user_message: str, locale: str) -> str:
        return f"""Run the VedicDust relationship consultation skill.

Workspace contains chart_record.json, claim_graph.json, consultation_dossier.json,
agent_context.json, and consultation_report.md.

Rules:
- {self._language_instruction(locale)}
- Use agent_context.json as the released consultation context and chart_record.json only to
  verify cited fact IDs. Do not introduce a chart judgement absent from claim_graph.json.
- Write love_report.md with conclusions, evidence, counter-evidence, timing limits,
  decision support, and follow-up questions.
- Chat response should only report progress/completion and file paths.
- Do not output app cards, claims, daily notes, or JSON.

User message:
{user_message or "分析感情"}"""

    def _rectifier_prompt(self, user_message: str, locale: str) -> str:
        return f"""Run vedic-rectifier exactly as the original skill.

Workspace contains chart_record.json, chart_rectification_state.json,
rectification_question_set.json, prevalidation_result.json, and user_context.md when feedback exists.

Rules:
- {self._language_instruction(locale)}
- This skill is interactive.
- Use chart_record.json and its RectificationRecord as the deterministic boundary.
- Write rectification_report.md.
- If the birth time should be changed, clearly state the candidate time and what needs confirmation.
- Do not run shell commands. If recalculation is needed, request recalculation as the next backend step.
- Do not output app cards, claims, daily notes, or JSON.

User message:
{user_message or "校准时间"}"""

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
            "vedic-career": 8,
            "vedic-love": 8,
            "vedic-rectifier": 6,
            "vedic-synastry": 8,
            "vedicdust-judgement": 12,
            "vedicdust-consultation": 12,
            "bazi-calculator": 6,
            "bazi-classics-core": 12,
        }[skill]

    def _stage_for(self, skill: str) -> str:
        return {
            "vedic-reader": "reader_validation",
            "vedic-core": "core_complete",
            "vedic-career": "career_complete",
            "vedic-love": "love_complete",
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
            "vedic-career": "career_report.md",
            "vedic-love": "love_report.md",
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
