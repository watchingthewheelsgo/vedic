from __future__ import annotations

import json
import re
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
from app.services.vedic_calculator import VedicCalculator
from app.tools.registry import BackendToolRunner


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
        calculation = self.calculator.calculate(input_data)
        finished = datetime.now(timezone.utc)
        self.workspace.write_artifact(session_id, "structured_data.md", calculation.structured_data)
        self.workspace.write_artifact(
            session_id,
            "structured_data.json",
            calculation.structured_data_json,
        )
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
            session_id, "structured_data.md", producer="calculator"
        )
        self.workspace.mark_artifact_checkpoint(
            session_id, "structured_data.json", producer="calculator"
        )
        self.workspace.mark_artifact_checkpoint(
            session_id, "birth_input_context.json", producer="calculator"
        )
        self.workspace.mark_artifact_checkpoint(
            session_id, "sensitivity_scan.json", producer="calculator"
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
            active_artifact="structured_data.md",
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
                                "bazi_structured_data.json",
                                "bazi_structured_data.md",
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
            "bazi_structured_data.json",
            "bazi_structured_data.md",
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
            active_artifact="bazi_structured_data.md",
        )

    def load_session(self, session_id: str) -> SkillSessionResponse:
        artifacts = self.workspace.read_artifacts(session_id)
        paths = {artifact.path for artifact in artifacts}
        if "bazi_life_report.md" in paths:
            stage = "bazi_complete"
            active = "bazi_life_report.md"
            message = "Your BaZi classical report is ready."
        elif "bazi_structured_data.md" in paths:
            stage = "bazi_ready"
            active = "bazi_structured_data.md"
            message = "Your BaZi chart facts are ready."
        elif "appendix.md" in paths and "run_metrics.json" in paths:
            stage = "core_complete"
            active = "run_metrics.json"
            message = "Your full reading is ready."
        elif "structured_data.md" in paths:
            stage = "reader_ready"
            active = "structured_data.md"
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
        if not (session_dir / "structured_data.md").exists():
            raise ValueError("A structured_data.md is required before synastry")

        folder = self._synastry_folder(input_data.label)
        calculation = self.calculator.calculate(input_data.birth)
        b_path = f"{folder}/structured_data_B.md"
        self.workspace.write_artifact(input_data.session_id, b_path, calculation.structured_data)
        self.workspace.write_artifact(
            input_data.session_id,
            f"{folder}/structured_data_B.json",
            calculation.structured_data_json,
        )

        intake = self._synastry_intake(input_data)
        self.workspace.write_artifact(input_data.session_id, f"{folder}/intake.md", intake)

        synastry_dir = session_dir / folder
        validate_output = self.tools.validate_synastry_data(
            session_dir / "structured_data.md",
            synastry_dir / "structured_data_B.md",
        ).output
        build_output = self.tools.build_synastry_data(
            session_dir / "structured_data.md",
            synastry_dir / "structured_data_B.md",
            synastry_dir,
            a_label="A",
            b_label=input_data.label or "B",
        ).output
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
                "合盘前置数据已生成。\n\n"
                f"已生成: {b_path}\n"
                f"已生成: {folder}/synastry_data.md\n\n"
                "下一步按原 vedic-synastry 流程运行 Layer 0.5。\n\n"
                f"{validate_output.strip()}\n{build_output.strip()}"
            ),
            artifacts=self.workspace.read_artifacts(input_data.session_id),
            active_artifact=f"{folder}/synastry_data.md",
        )

    async def run_skill(
        self, input_data: SkillRunInput, *, owner_user_id: str | None = None
    ) -> SkillSessionResponse:
        self.workspace.require_session_dir(input_data.session_id)
        if input_data.skill == "vedic-core":
            return await self._run_core(input_data, owner_user_id=owner_user_id)

        prompt = self._artifact_prompt_for(input_data)
        result = await self.agent_runtime.run_skill_prompt_task(
            input_data.skill,
            prompt,
            skills=[input_data.skill],
            max_turns=self._max_turns_for(input_data.skill),
        )
        parsed = self._parse_artifact_response(result.raw_text)
        self._validate_skill_artifacts(input_data.session_id, input_data.skill, parsed)
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
        self.assert_core_readiness(input_data.session_id)
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

    def assert_core_readiness(self, session_id: str) -> None:
        session_dir = self.workspace.require_session_dir(session_id)
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
        return all(
            self.workspace.artifact_checkpoint_valid(session_id, path, producer=producer)
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
            self._compose_core_outputs(input_data.session_id, session_dir)
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
        result = await self.agent_runtime.run_skill_task(
            input_data.skill,
            str(batch["prompt"]),
            cwd=session_dir,
            skills=[input_data.skill],
            max_turns=self._max_turns_for(input_data.skill),
        )
        self.workspace.assert_no_project_runtime_artifacts()
        missing = [path for path in expected if not (session_dir / path).exists()]
        if missing:
            raise ValueError(
                "vedic-core did not create expected artifact(s): "
                + ", ".join(missing)
                + f"\nAgent output:\n{result.raw_text[:2000]}"
            )
        producer = self._batch_producer(batch)
        for path in expected:
            self.workspace.mark_artifact_checkpoint(
                input_data.session_id,
                path,
                producer=producer,
            )

        self._compose_core_outputs(input_data.session_id, session_dir)
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
            for artifact in self.workspace.read_artifacts(session_id)
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
            artifacts.get("structured_data.json", ""),
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
                self._json_dict(artifacts.get("structured_data.json", "")),
            )
            if rectified_input is not None:
                chart_revision = self._next_chart_revision(updated_state)
                self._archive_current_chart_artifacts(session_id, chart_revision - 1, artifacts)
                calculation = self.calculator.calculate(rectified_input)
                self._write_chart_calculation(
                    session_id,
                    calculation.structured_data,
                    calculation.structured_data_json,
                    calculation.birth_input_context_json,
                    calculation.sensitivity_scan_json,
                    producer="calculator:rectification",
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
        structured_data: str,
        structured_data_json: str,
        birth_input_context_json: str,
        sensitivity_scan_json: str,
        *,
        producer: str,
    ) -> None:
        chart_artifacts = {
            "structured_data.md": structured_data,
            "structured_data.json": structured_data_json,
            "birth_input_context.json": birth_input_context_json,
            "sensitivity_scan.json": sensitivity_scan_json,
        }
        for path, content in chart_artifacts.items():
            self.workspace.write_artifact(session_id, path, content)
            self.workspace.mark_artifact_checkpoint(session_id, path, producer=producer)

    def _archive_current_chart_artifacts(
        self,
        session_id: str,
        revision: int,
        artifacts: dict[str, str],
    ) -> None:
        for path in [
            "structured_data.md",
            "structured_data.json",
            "birth_input_context.json",
            "sensitivity_scan.json",
        ]:
            content = artifacts.get(path)
            if content is None:
                continue
            self.workspace.write_artifact(
                session_id,
                f".runtime/chart_revisions/rev_{revision}/{path}",
                content,
            )

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
        structured_data_json: str,
    ) -> dict[str, object]:
        anchors = self._parse_prevalidation_anchors(prevalidation_markdown)
        answers = self._parse_prevalidation_feedback(feedback_markdown)
        subject = self._prevalidation_subject_context(structured_data_json)
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

    def _prevalidation_subject_context(self, structured_data_json: str) -> dict[str, object]:
        try:
            payload = json.loads(structured_data_json) if structured_data_json.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        subject = payload.get("subject") if isinstance(payload, dict) else {}
        if not isinstance(subject, dict):
            subject = {}
        sensitivity = payload.get("sensitivityScan") if isinstance(payload, dict) else {}
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
        time_precision = str(subject.get("timePrecision") or "")
        time_source = str(subject.get("timeSource") or "")
        reliable_source = bool(
            re.search(r"出生证|医院|birth certificate|hospital", time_source, re.I)
        )
        approximate_source = bool(
            re.search(r"大概|估计|记忆|回忆|未追问|unknown|approx", time_source, re.I)
        )
        time_reliability = (
            "reliable_exact"
            if time_precision == "精确到分钟" and reliable_source and not approximate_source
            else "uncertain"
        )
        return {
            "birthDate": subject.get("birthDate"),
            "birthTime": subject.get("birthTime"),
            "birthPlace": subject.get("birthPlace"),
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
  - Each item uses bold markdown number, e.g. **1.** 推断正文.
  - Each item is followed by one blank line and a quoted derivation line: > 推导：...
  - Do not add signal tables, Yoga tables, 综合轮廓, advice, disclaimers, or app-specific explanation.
  - If sensitivity_scan.reportReadiness.mode=rectification_required, each item must distinguish candidate signatures or unstable fields rather than validate generic personality.
  - For rectification_required anchors, add quoted machine lines after 推导 using exactly: > Candidate: A, > Field: d9Lagna, and when rectificationPlan.lifeEventFocus is non-empty, > Event: evt_1_201810_marriage. Use candidate IDs, fields, and event IDs from chart_rectification_state.json.
  - End with: 请逐条回复：**准 / 不准 / 部分准**"""
        if locale == "ja":
            return """- Chat response should be only the original short progress / next-step message and ask the user to reply 正確 / 不正確 / 一部正確.
- reader_prevalidation.md must follow the original Step 5 output template:
  - Start with: 完全な分析に入る前に、出生データの精度を確認するため、いくつかの時間アンカーを検証します——
  - Output 3 to 5 numbered items only.
  - Each item uses bold markdown number, e.g. **1.** 推論本文.
  - Each item is followed by one blank line and a quoted derivation line: > 根拠：...
  - Do not add signal tables, Yoga tables, synthesis profile, advice, disclaimers, or app-specific explanation.
  - If sensitivity_scan.reportReadiness.mode=rectification_required, each item must distinguish candidate signatures or unstable fields rather than validate generic personality.
  - For rectification_required anchors, add quoted machine lines after 根拠 using exactly: > Candidate: A, > Field: d9Lagna, and when rectificationPlan.lifeEventFocus is non-empty, > Event: evt_1_201810_marriage. Use candidate IDs, fields, and event IDs from chart_rectification_state.json.
  - End with: 各項目に返信してください：**正確 / 不正確 / 一部正確**"""
        return """- Chat response should be only the original short progress / next-step message and ask the user to reply Accurate / Not accurate / Partly accurate.
- reader_prevalidation.md must follow the original Step 5 output template:
  - Start with: Before entering the full analysis, I will first validate several timing anchors to check the precision of the birth data—
  - Output 3 to 5 numbered items only.
  - Each item uses bold markdown number, e.g. **1.** Inference text.
  - Each item is followed by one blank line and a quoted derivation line: > Derivation: ...
  - Do not add signal tables, Yoga tables, synthesis profile, advice, disclaimers, or app-specific explanation.
  - If sensitivity_scan.reportReadiness.mode=rectification_required, each item must distinguish candidate signatures or unstable fields rather than validate generic personality.
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
        errors = self.rectification.validate_prevalidation_contract(state, prevalidation)
        if errors:
            raise ValueError(
                "vedic-reader output failed candidate-bound validation: " + "; ".join(errors[:4])
            )

    @staticmethod
    def _allowed_output_artifacts(skill: str) -> set[str] | None:
        if skill == "vedic-reader":
            return {"reader_prevalidation.md"}
        return None

    def _prompt_for(self, input_data: SkillRunInput) -> str:
        locale = self._run_locale(input_data)
        if input_data.skill == "vedic-reader":
            return self._reader_prompt(input_data.user_message, locale)
        if input_data.skill == "vedic-core":
            return self._core_prompt(input_data.user_message, locale)
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
            self.workspace.read_artifacts(input_data.session_id),
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
        user_line = user_message or "开始分析"
        language_instruction = self._language_instruction(locale)
        planets = [
            ("sun", "Sun", "太阳"),
            ("moon", "Moon", "月亮"),
            ("mars", "Mars", "火星"),
            ("mercury", "Mercury", "水星"),
            ("jupiter", "Jupiter", "木星"),
            ("venus", "Venus", "金星"),
            ("saturn", "Saturn", "土星"),
            ("rahu", "Rahu", "罗睺"),
            ("ketu", "Ketu", "计都"),
        ]
        p2_node_ids = [f"p2_{slug}" for slug, _, _ in planets]
        d9_node_ids = [f"p3a_d9_{slug}" for slug, _, _ in planets]
        divisional_node_ids = ["p3b_d10", "p3b_d4", "p3b_d5"]
        p3_done = [*d9_node_ids, *divisional_node_ids]
        house_node_ids = [f"p4_house_{number:02d}" for number in range(1, 13)]
        life_node_ids = [f"p5_block_{number:02d}" for number in range(1, 11)]

        batches: list[dict[str, object]] = [
            self._core_batch(
                "p1",
                "P1 身份总览",
                "p1_overview.md",
                "Run vedic-core Step 0 and P1 only. Use structured_data.md. Do not use user_context.md in this batch.",
                user_line,
                language_instruction=language_instruction,
            ),
            self._core_batch(
                "p2_yoga",
                "P2 Yoga/NBRY 预扫描",
                ".runtime/p2/yoga.md",
                "Run only the original Step 1 Yoga pre-scan before planet audit. Read structured_data.md and resources/yogas.md. Check every listed Yoga/NBRY condition. Write the content that belongs at the top of p2a_planets.md: the opening framework note plus 已确认格局 / 待验证格局 / 落陷星NBRY状态. Do not audit Sun or Moon in this batch.",
                user_line,
                active="p1_overview.md",
                progress_message="P2 Yoga/NBRY 预扫描已完成。",
                language_instruction=language_instruction,
            ),
        ]

        for slug, planet, chinese_name in planets:
            others = ", ".join(item[1] for item in planets if item[0] != slug)
            batches.append(
                self._core_batch(
                    f"p2_{slug}",
                    f"P2 {planet} 行星审计",
                    f".runtime/p2/{slug}.md",
                    (
                        f"Run only the original Step 1 P1-P12 planet audit for {planet} "
                        f"({chinese_name}). Read structured_data.md, resources/p1_p12.md, "
                        "and .runtime/p2/yoga.md for Yoga/NBRY labels. Preserve the "
                        "P1-P12 framework, PAC联合判定, SAV读取铁规, 美贴标注, and confidence "
                        f"rules. Write only the complete {planet} section. Do not audit or "
                        f"summarize these other planets: {others}."
                    ),
                    user_line,
                    dependencies=["p2_yoga"],
                    active="p1_overview.md",
                    progress_message=f"P2 {planet} 审计已完成。",
                    language_instruction=language_instruction,
                )
            )

        for slug, planet, chinese_name in planets:
            batches.append(
                self._core_batch(
                    f"p3a_d9_{slug}",
                    f"P3A D9 {planet} 审计",
                    f".runtime/p3/d9_{slug}.md",
                    (
                        f"Run only the original Step 2.1 D9 audit for {planet} ({chinese_name}). "
                        "Use structured_data.md and the completed p2a_planets.md, "
                        "p2b_planets.md, p2c_planets.md, p2d_planets.md artifacts as prior "
                        "blind-audit context. Preserve the D9三条铁律, 身份继承矩阵, "
                        "D9 quality/兑现率 logic, and the current concise evidence style. "
                        f"Write only the complete D9 section for {planet}; do not audit other planets."
                    ),
                    user_line,
                    dependencies=p2_node_ids,
                    active="p2a_planets.md",
                    progress_message=f"P3A D9 {planet} 审计已完成。",
                    language_instruction=language_instruction,
                )
            )

        divisional_batches = [
            (
                "p3b_d10",
                "P3B D10 事业概述",
                ".runtime/p3/d10.md",
                "Run only original Step 2.2 D10 career overview. Read structured_data.md and completed P2 artifacts. Cover D10 Lagna, strong D10 planets, D10 10th lord position, career direction clues, and confidence. Do not write D4/D5.",
            ),
            (
                "p3b_d4",
                "P3B D4 财产概述",
                ".runtime/p3/d4.md",
                "Run only original Step 2.3 D4 property/comfort overview. Read structured_data.md and completed P2 artifacts. Cover D4 Lagna, D4 4th lord/Venus, D1 4th vs D4 cross-check, and property/vehicle indications. Do not write D10/D5.",
            ),
            (
                "p3b_d5",
                "P3B D5 权力概述",
                ".runtime/p3/d5.md",
                "Run only original Step 2.4 D5 authority/creative power overview. Read structured_data.md and completed P2 artifacts. Cover D5 Sun/Jupiter, authority/influence, and creative potential. Do not write D10/D4.",
            ),
        ]
        for node_id, label, file_name, instruction in divisional_batches:
            batches.append(
                self._core_batch(
                    node_id,
                    label,
                    file_name,
                    instruction,
                    user_line,
                    dependencies=p2_node_ids,
                    active="p2a_planets.md",
                    progress_message=f"{label} 已完成。",
                    language_instruction=language_instruction,
                )
            )

        for number in range(1, 13):
            batches.append(
                self._core_batch(
                    f"p4_house_{number:02d}",
                    f"P4 第{number}宫诊断",
                    f".runtime/houses/house_{number:02d}.md",
                    (
                        f"Run only the original Step 3 house diagnosis for house {number}. "
                        "Before writing, read structured_data.md, p2a_planets.md, p2b_planets.md, "
                        "p2c_planets.md, p2d_planets.md, p3a_d9.md, and p3b_divisional.md. "
                        "Preserve the four-dimensional house framework: manager/house lord, tenant "
                        "planets, aspects, SAV hardware, divisional cross-checks, Dasha event "
                        "association, evidence weighting, and markdown style. Write only this one "
                        "house section. Do not diagnose other houses and do not run the Parivartana scan."
                    ),
                    user_line,
                    dependencies=p3_done,
                    active="p3a_d9.md",
                    progress_message=f"P4 第{number}宫诊断已完成。",
                    language_instruction=language_instruction,
                )
            )

        batches.append(
            self._core_batch(
                "p4_parivartana",
                "P4 Parivartana 互溶扫描",
                ".runtime/houses/parivartana.md",
                (
                    "Run only the original Step 3 Parivartana scan required after all 12 house "
                    "diagnoses. Read structured_data.md, p2a-p2d, p3a/p3b, and all "
                    ".runtime/houses/house_01.md through .runtime/houses/house_12.md. Include "
                    "the original exchange-check logic, confirmed/excluded exchange pairs, final "
                    "house-diagnosis synthesis for houses 7-12, and the Step 3 completion marker. "
                    "Do not repeat the full 12 house diagnoses."
                ),
                user_line,
                dependencies=house_node_ids,
                active="p4a_houses.md",
                progress_message="P4 Parivartana 互溶扫描已完成。",
                language_instruction=language_instruction,
            )
        )

        batches.append(
            self._core_batch(
                "dasha_review",
                "Step 4 Dasha速查与格局激活",
                ".runtime/dasha_review.md",
                (
                    "Run only the original Step 4 prerequisite: Dasha回顾速查表 and Yoga x "
                    "Dasha x D9 activation validation. Read structured_data.md, completed "
                    "p2a-p2d artifacts, p3a_d9.md, and p3b_divisional.md. Produce a reusable "
                    "markdown reference for later life blocks. Do not write any life synthesis blocks."
                ),
                user_line,
                dependencies=p3_done,
                active="p3a_d9.md",
                progress_message="Dasha速查与格局激活验证已完成。",
                language_instruction=language_instruction,
            )
        )

        life_blocks = [
            (
                1,
                "人格核心",
                "Use p1_overview.md, p2 Sun/Moon findings, p3a Sun/Moon D9 settlement, Lagna, Moon, Sun, and AK. Write block 1 only.",
            ),
            (
                2,
                "财富潜力",
                "Use house 2 and house 11 diagnoses, D4 data, p2 money-relevant planet audits, and Dasha review. Write block 2 only.",
            ),
            (
                3,
                "事业方向",
                "Use house 10 diagnosis, D10 data, L10/AmK audits, Yoga activation, and Dasha review. Write block 3 only.",
            ),
            (
                4,
                "感情/婚姻",
                "Use house 7 diagnosis, D9, Venus/Jupiter/DK/UL signals, and Dasha review. Write block 4 only.",
            ),
            (
                5,
                "健康提醒",
                "Use house 1 and house 6 diagnoses, Mars/Saturn audits, Maraka context, and Dasha review. Write block 5 only.",
            ),
            (
                6,
                "教育/学习",
                "Use house 4 and house 5 diagnoses, D5 data, Mercury/Jupiter/Moon signals, and Dasha review. Write block 6 only.",
            ),
            (
                7,
                "家庭/居住",
                "Use house 4 and house 9 diagnoses, D4 data, parental/home indicators, and Dasha review. Write block 7 only.",
            ),
            (
                8,
                "社交/声誉",
                "Use AL data from structured_data.md, house 11 diagnosis, relevant p2/p4 signals, and Dasha review. Write block 8 only.",
            ),
            (
                9,
                "长期成长",
                "Use AK, house 9 and house 12 diagnoses, AK planet D9 settlement, and Dasha review. Write block 9 only.",
            ),
            (
                10,
                "赛道优势地图",
                "Use all p2 Yoga findings, p3a D9 settlements, p4 house conclusions, and dasha_review.md. Translate Yoga into capability tracks, business/wealth paths, compounding conditions, and timing. Write block 10 only.",
            ),
        ]
        for number, title, instruction in life_blocks:
            batches.append(
                self._core_batch(
                    f"p5_block_{number:02d}",
                    f"P5 板块{number} {title}",
                    f".runtime/life/block_{number:02d}.md",
                    (
                        "Run only the original Step 4 life synthesis block requested below. "
                        "Before writing, read p1_overview.md, p2a-p2d, p3a_d9.md, "
                        "p3b_divisional.md, p4a_houses.md, p4b_houses.md, and "
                        ".runtime/dasha_review.md. Follow the Step 4 context rule: you may use "
                        "confirmed facts only as supporting evidence, never to reverse-infer the "
                        "chart. Write for a human reader using what/why/limit/next-step structure; "
                        "translate naked technical labels on first use; avoid florid persona, filler, "
                        "and word-count padding. No data tables except where the original block "
                        "explicitly allows it. "
                        f"{instruction}"
                    ),
                    user_line,
                    dependencies=["p4_parivartana", "dasha_review"],
                    active="p4b_houses.md",
                    progress_message=f"P5 板块{number} {title} 已完成。",
                    language_instruction=language_instruction,
                )
            )

        batches.append(
            self._core_batch(
                "appendix",
                "Step 5 技术附录",
                "appendix.md",
                (
                    "Run the original Step 5 technical appendix only. Read structured_data.md, "
                    "birth_input_context.json, sensitivity_scan.json, "
                    "chart_rectification_state.json, prevalidation_result.json "
                    "if present, p2a-p2d, p3a/p3b, p4a/p4b, p5a/p5b, and "
                    ".runtime/dasha_review.md. Include the P1-P12 parameter table, divisional "
                    "data overview, input confidence / report readiness summary, validation "
                    "report, Dasha timeline, and the Dasha回顾速查表 if available."
                ),
                user_line,
                dependencies=life_node_ids,
                active="p5a_life.md",
                progress_message="Step 5 技术附录已完成。",
                language_instruction=language_instruction,
            )
        )

        batches.append(
            self._core_batch(
                "report_quality_audit",
                "Step 6 最终报告质量审计",
                "report_quality_audit.md",
                (
                    "Run the current vedic-core Step 6 final report quality audit only. "
                    "Read birth_input_context.json, sensitivity_scan.json, "
                    "chart_rectification_state.json, prevalidation_result.json "
                    "if present, structured_data.md, p5a_life.md, p5b_life.md, and appendix.md. "
                    "Do not rewrite the report body. Write a clear PASS / NEEDS_REVISION audit "
                    "with blocking issues, evidence, and exact fixes. Fail the audit if "
                    "prevalidation_result.decision.reportAllowed is false, "
                    "sensitivity_scan.reportReadiness.mode is rectification_required but the report "
                    "is written as a deterministic full report, any "
                    "llmContract.mustNotUseAsPrimaryEvidence field is used as a primary conclusion "
                    "anchor, time confidence is inconsistent, missed validation anchors are "
                    "reinterpreted as hits, child/adult framing is wrong, Dasha ages are incoherent, "
                    "or the main report contains raw technical-label paragraphs."
                ),
                user_line,
                dependencies=["appendix"],
                active="report_quality_audit.md",
                progress_message="Step 6 最终报告质量审计已完成。",
                language_instruction=language_instruction,
            )
        )

        return batches

    def _core_batch(
        self,
        batch_id: str,
        batch_name: str,
        file_name: str | list[str],
        instruction: str,
        user_message: str,
        *,
        dependencies: list[str] | None = None,
        active: str | None = None,
        progress_message: str | None = None,
        language_instruction: str,
    ) -> dict[str, object]:
        files = [file_name] if isinstance(file_name, str) else file_name
        return {
            "id": batch_id,
            "label": batch_name,
            "files": files,
            "dependencies": dependencies or [],
            "active": active or files[0],
            "progress_message": progress_message,
            "prompt": self._core_batch_prompt(
                batch_name,
                files,
                instruction,
                user_message,
                language_instruction,
            ),
        }

    def _core_batch_prompt(
        self,
        batch_name: str,
        files: list[str],
        instruction: str,
        user_message: str,
        language_instruction: str,
    ) -> str:
        file_list = ", ".join(files)
        return f"""Run vedic-core exactly as the original skill, but only for this backend batch: {batch_name}.

Batch instruction:
{instruction}

Write exactly these batch file names in the current workspace and no others:
{file_list}

Rules:
- Preserve the vedic-core phase order, source-of-truth boundaries, evidence weighting, and QA/report rules.
- Follow the current report quality rules: user-facing life blocks prioritize plain conclusions, concise evidence, limitations, and actionable guidance; technical detail belongs in appendix.
- Do not inherit old persona language, florid metaphors, raw technical-label paragraphs, or fixed word-count padding.
- {language_instruction}
- Use structured_data.md as the calculation source of truth.
- Read birth_input_context.json, sensitivity_scan.json, and chart_rectification_state.json when present; use them only as the input-confidence, active chart revision, and report-readiness gate.
- Obey sensitivity_scan.reportReadiness.llmContract: never use mustNotUseAsPrimaryEvidence fields as primary conclusion anchors, and downgrade or omit unstable divisional/timing claims.
- Obey chart_rectification_state.rectificationPlan.advancedVargaPolicy: D16/D20/D24/D27/D30 are corroboration-only until the time window is narrow; D60 is final-confirmation-only, never a first-pass report anchor.
- If sensitivity_scan.reportReadiness.mode is rectification_required, write only candidate-discriminating or clearly low-confidence/D1-only content unless prevalidation_result.json explicitly allows the full report.
- Do not summarize with app-specific sections, cards, claims, daily notes, or JSON.
- Each requested file must be complete markdown, not a placeholder and not "see previous".
- If the requested file is under .runtime/, treat it as an internal shard; do not write the public composed files such as p2a_planets.md, p3a_d9.md, p4a_houses.md, p4b_houses.md, p5a_life.md, or p5b_life.md.
- Do not create, edit, or rename any file outside the exact requested batch file name(s).
- All requested paths are relative to the current working directory, which is the only valid user session workspace.
- Do not read from or write to ../ paths, absolute paths, the project root .runtime directory, or any other session directory.
- Do not return JSON for this batch. Write the markdown file directly, then state the batch is complete and list the file generated.

User message:
{user_message}"""

    def _batch_files(self, batch: dict[str, object]) -> list[str]:
        return [str(path) for path in batch["files"]]

    def _batch_producer(self, batch: dict[str, object]) -> str:
        return f"vedic-core:{batch.get('id') or 'unknown'}"

    def _session_paths(self, session_dir: Path) -> set[str]:
        return {
            path.relative_to(session_dir).as_posix()
            for path in session_dir.rglob("*")
            if path.is_file()
        }

    def _compose_core_outputs(self, session_id: str, session_dir: Path) -> None:
        p2a_parts = [
            session_dir / ".runtime" / "p2" / "yoga.md",
            session_dir / ".runtime" / "p2" / "sun.md",
            session_dir / ".runtime" / "p2" / "moon.md",
        ]
        self._compose_parts(
            session_id, session_dir / "p2a_planets.md", p2a_parts, "vedic-core:compose:p2a"
        )

        p2b_parts = [
            session_dir / ".runtime" / "p2" / "mars.md",
            session_dir / ".runtime" / "p2" / "mercury.md",
        ]
        self._compose_parts(
            session_id, session_dir / "p2b_planets.md", p2b_parts, "vedic-core:compose:p2b"
        )

        p2c_parts = [
            session_dir / ".runtime" / "p2" / "jupiter.md",
            session_dir / ".runtime" / "p2" / "venus.md",
        ]
        self._compose_parts(
            session_id, session_dir / "p2c_planets.md", p2c_parts, "vedic-core:compose:p2c"
        )

        p2d_parts = [
            session_dir / ".runtime" / "p2" / "saturn.md",
            session_dir / ".runtime" / "p2" / "rahu.md",
            session_dir / ".runtime" / "p2" / "ketu.md",
        ]
        self._compose_parts(
            session_id, session_dir / "p2d_planets.md", p2d_parts, "vedic-core:compose:p2d"
        )

        p3a_parts = [
            session_dir / ".runtime" / "p3" / f"d9_{planet}.md"
            for planet in [
                "sun",
                "moon",
                "mars",
                "mercury",
                "jupiter",
                "venus",
                "saturn",
                "rahu",
                "ketu",
            ]
        ]
        self._compose_parts(
            session_id, session_dir / "p3a_d9.md", p3a_parts, "vedic-core:compose:p3a"
        )

        p3b_parts = [
            session_dir / ".runtime" / "p3" / "d10.md",
            session_dir / ".runtime" / "p3" / "d4.md",
            session_dir / ".runtime" / "p3" / "d5.md",
        ]
        self._compose_parts(
            session_id, session_dir / "p3b_divisional.md", p3b_parts, "vedic-core:compose:p3b"
        )

        p4a_parts = [
            session_dir / ".runtime" / "houses" / f"house_{number:02d}.md" for number in range(1, 7)
        ]
        self._compose_parts(
            session_id, session_dir / "p4a_houses.md", p4a_parts, "vedic-core:compose:p4a"
        )

        p4b_parts = [
            *[
                session_dir / ".runtime" / "houses" / f"house_{number:02d}.md"
                for number in range(7, 13)
            ],
            session_dir / ".runtime" / "houses" / "parivartana.md",
        ]
        self._compose_parts(
            session_id, session_dir / "p4b_houses.md", p4b_parts, "vedic-core:compose:p4b"
        )

        p5a_parts = [
            session_dir / ".runtime" / "life" / f"block_{number:02d}.md" for number in range(1, 6)
        ]
        self._compose_parts(
            session_id, session_dir / "p5a_life.md", p5a_parts, "vedic-core:compose:p5a"
        )

        p5b_parts = [
            session_dir / ".runtime" / "life" / f"block_{number:02d}.md" for number in range(6, 11)
        ]
        self._compose_parts(
            session_id, session_dir / "p5b_life.md", p5b_parts, "vedic-core:compose:p5b"
        )

    def _compose_parts(
        self,
        session_id: str,
        target: Path,
        parts: list[Path],
        producer: str,
    ) -> None:
        session_dir = self.workspace.require_session_dir(session_id)
        if not all(path.exists() for path in parts):
            return
        relative_parts = [path.relative_to(session_dir).as_posix() for path in parts]
        if not all(
            self.workspace.artifact_checkpoint_valid(
                session_id,
                relative_path,
                producer=self._producer_for_core_file(relative_path),
            )
            for relative_path in relative_parts
        ):
            return
        target.write_text(
            "\n\n".join(path.read_text(encoding="utf-8").strip() for path in parts) + "\n",
            encoding="utf-8",
        )
        self.workspace.mark_artifact_checkpoint(
            session_id,
            target.relative_to(session_dir).as_posix(),
            producer=producer,
        )

    def _producer_for_core_file(self, relative_path: str) -> str:
        for batch in self.core_batches(""):
            if relative_path in self.core_batch_files(batch):
                return self._batch_producer(batch)
        return ""

    def _active_artifact_for_batch(self, batch: dict[str, object], artifacts: list[object]) -> str:
        paths = {str(getattr(artifact, "path")) for artifact in artifacts}
        active = str(batch.get("active") or self._batch_files(batch)[0])
        if active in paths:
            return active
        for fallback in [
            "p5a_life.md",
            "p5b_life.md",
            "report_quality_audit.md",
            "p4b_houses.md",
            "p4a_houses.md",
            "p3a_d9.md",
            "p2a_planets.md",
            "p1_overview.md",
            "reader_prevalidation.md",
            "structured_data.md",
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
            if path in {"structured_data.json"} or path.endswith("/structured_data_B.json"):
                continue
            if skill == "vedic-synastry":
                if path == "structured_data.md" or path.startswith("synastry_"):
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

Workspace already contains structured_data.md generated by vedic-calculator.

Follow the original vedic-reader workflow exactly, but because this is a web adapter:
- {self._language_instruction(locale)}
- Do not ask for setup or dependency installation.
- Do not run shell commands.
- Use the provided structured_data.md content.
- Read birth_input_context.json, sensitivity_scan.json, and chart_rectification_state.json before writing anchors.
- If sensitivity_scan.reportReadiness.mode is rectification_required, make each anchor support one explicit candidate ID from chart_rectification_state.json and focus on unstableFields / changedFields. Do not imply the full report can proceed until feedback passes the backend gate.
- Use chart_rectification_state.rectificationPlan as the backend-owned next-round plan: targetCandidateIds, discriminatingFields, focusAxes, timeWindow, placeWindow, lifeEventFocus, eventCollectionRequired, and requiredAnchorCount are hard constraints.
- When rectificationPlan.lifeEventFocus is non-empty, build validation anchors from those dated events first. Each such anchor must include a machine-readable > Event: line using an eventId or category from chart_rectification_state.lifeEventLedger.
- When rectificationPlan.eventCollectionRequired is true and lifeEventFocus is empty, still produce candidate-bound anchors using available chart differences, but keep them low-confidence and do not claim complete birth-time rectification.
- If chart_rectification_state.status is needs_more_feedback or needs_candidate_bound_checks, generate a new rectification round from rectificationPlan. Use prior feedbackAnchors, roundHistory, and candidate scores to ask narrower candidate-discriminating anchors; do not repeat anchors that already failed to separate candidates.
- Do not invent candidate IDs, event IDs, times, coordinates, or fields outside chart_rectification_state.rectificationPlan.
- Execute Calc mode Stage 2 and Stage 3 only: signal pre-scan, Yoga scan, and pre-validation reading.
- Write the user-facing pre-validation output to reader_prevalidation.md.
{self._reader_prevalidation_format_instruction(locale)}
- Treat pre-validation as a scoring gate, not as performance writing: do not show the internal SOP, do not add full candidate tables, and do not reframe misses as hits.
- Do not generate core report, career report, love report, daily note, or app-specific claims.
- The backend will deterministically create prevalidation_result.json and update chart_rectification_state.json from reader_prevalidation.md and user feedback; do not hand-write those artifacts.

User message:
{user_message or self._reader_default_user_message(locale)}"""

    def _core_prompt(self, user_message: str, locale: str) -> str:
        return f"""Run vedic-core exactly as the original skill.

Workspace contains structured_data.md, birth_input_context.json, sensitivity_scan.json,
chart_rectification_state.json, and may contain user_context.md / reader_prevalidation.md.

Rules:
- {self._language_instruction(locale)}
- Follow vedic-core Step 0 through Step 5.
- Preserve blind-audit rules: Step 1-3 must not use user_context.md.
- Use prevalidation_result.json and chart_rectification_state.json, when present, as the structured source for validation score, active chart revision, time confidence, and report gating. Do not reinterpret missed anchors as hits.
- Obey sensitivity_scan.reportReadiness.llmContract: do not use restricted evidence as a primary conclusion anchor, and downgrade or omit unstable divisional/timing claims.
- Follow the current report quality rules: main report sections use plain conclusions, concise evidence, limitations, and actionable guidance; technical detail belongs in appendix.
- Do not use old persona language, florid metaphors, raw technical-label paragraphs, or fixed word-count padding.
- Write the original expected markdown files: p1_overview.md, p2a_planets.md, p2b_planets.md, p2c_planets.md, p2d_planets.md, p3a_d9.md, p3b_divisional.md, p4a_houses.md, p4b_houses.md, p5a_life.md, p5b_life.md, appendix.md.
- Chat response should only report completion and available next actions, matching the skill style.
- Do not compress the report into app-specific sections, claims, daily notes, or JSON.

User message:
{user_message or "开始分析"}"""

    def _career_prompt(self, user_message: str, locale: str) -> str:
        return f"""Run vedic-career exactly as the original skill.

Workspace contains structured_data.md and may contain the core report files.

Rules:
- {self._language_instruction(locale)}
- Use only structured_data.md and core report files as allowed by the skill.
- Follow all four career phases.
- Follow the current report quality rules: plain career conclusions, concise evidence, limitations/risks, and actionable guidance. Do not use old persona language, florid metaphors, raw technical-label paragraphs, or fixed word-count padding.
- Write the original expected markdown outputs, including career_phase4a.md, career_phase4b.md, and career_phase4c.md when Phase 4 is reached.
- Chat response should only report progress/completion and file paths.
- Do not output app cards, claims, daily notes, or JSON.

User message:
{user_message or "分析事业"}"""

    def _love_prompt(self, user_message: str, locale: str) -> str:
        return f"""Run vedic-love exactly as the original skill.

Workspace contains structured_data.md and may contain the core report files.

Rules:
- {self._language_instruction(locale)}
- Use only structured_data.md and allowed report files.
- Follow the original love timing workflow and output file rules.
- Follow the current report quality rules: plain relationship conclusions, concise evidence, limitations/risks, and actionable guidance. Do not use old persona language, florid metaphors, raw technical-label paragraphs, or fixed word-count padding.
- Chat response should only report progress/completion and file paths.
- Do not output app cards, claims, daily notes, or JSON.

User message:
{user_message or "分析感情"}"""

    def _rectifier_prompt(self, user_message: str, locale: str) -> str:
        return f"""Run vedic-rectifier exactly as the original skill.

Workspace contains structured_data.md and user_context.md if feedback/events exist.

Rules:
- {self._language_instruction(locale)}
- This skill is interactive.
- Write rectification_report.md.
- If the birth time should be changed, clearly state the candidate time and what needs confirmation.
- Do not run shell commands. If recalculation is needed, request recalculation as the next backend step.
- Do not output app cards, claims, daily notes, or JSON.

User message:
{user_message or "校准时间"}"""

    def _synastry_prompt(self, user_message: str, locale: str) -> str:
        return f"""Run vedic-synastry exactly as the original skill.

Workspace contains A's structured_data.md and a synastry_<B>_<YYYYMMDD> folder with:
- intake.md
- structured_data_B.md
- synastry_data.md

Rules:
- {self._language_instruction(locale)}
- Do not read user_context.md.
- Use synastry_data.md as the cross-chart calculation source of truth.
- If reports/00_signal_triage.md does not exist, run Layer 0.5 only, write reports/00_signal_triage.md, then stop and ask the original intake question:
  ① 就到这
  ② 深入分析，但不用贴标签（通用深析）
  ③ 告诉我现实关系类型，我做对应专属解读
- If reports/00_signal_triage.md exists and the user requests deeper analysis, continue with the original selected layer/framework rules.
- Preserve original nested paths under the existing synastry folder.
- Artifact JSON paths must include the synastry_<B>_<YYYYMMDD>/ prefix, for example synastry_B_20260630/reports/00_signal_triage.md.
- Chat response should only report progress/completion and next intake choice.
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
  bazi_structured_data.json, bazi_structured_data.md, bazi_report_context.md.
- Chat response should say the BaZi chart data is ready, mention any warning count or key boundary warning, and recommend bazi-classics-core for the classical report.
- Do not create bazi_life_report.md or any classics interpretation in this skill.

User message:
{user_message or "计算八字排盘数据"}"""

    def _bazi_prompt(self, user_message: str, locale: str) -> str:
        return f"""Run bazi-classics-core exactly as the repo-local skill.

Workspace must contain:
- bazi_structured_data.md or bazi_structured_data.json
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
        if skill == "vedic-synastry" and artifacts:
            for artifact in artifacts:
                path = getattr(artifact, "path", "")
                if path.endswith("/reports/00_signal_triage.md"):
                    return path
                if path.endswith("/reports/04_guidance.md"):
                    return path
        return {
            "vedic-reader": "reader_prevalidation.md",
            "vedic-core": "p1_overview.md",
            "vedic-career": "career_phase4a.md",
            "vedic-love": "love_report.md",
            "vedic-rectifier": "rectification_report.md",
            "vedic-synastry": "reports/00_signal_triage.md",
            "bazi-calculator": "bazi_structured_data.md",
            "bazi-classics-core": "bazi_life_report.md",
        }[skill]

    def _synastry_folder(self, label: str) -> str:
        slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", label.strip() or "B").strip("_")
        slug = slug[:40] or "B"
        return f"synastry_{slug}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"

    def _synastry_intake(self, input_data: SynastryBirthInput) -> str:
        lines = [
            "# intake.md",
            "",
            f"- B label: {input_data.label or 'B'}",
            f"- relationship type: {input_data.relationship_type or '未指定'}",
            f"- current stage: {input_data.current_stage or '未指定'}",
            f"- question: {input_data.question or '未指定'}",
        ]
        return "\n".join(lines).strip() + "\n"

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
