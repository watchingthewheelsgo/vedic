from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone

from app.agents.claude_runtime import ClaudeRuntime
from app.schemas import SkillBirthInput, SkillRunInput, SkillSessionResponse, SynastryBirthInput
from app.services.skill_workspace import SkillWorkspace
from app.services.vedic_calculator import VedicCalculator


class SkillRuntime:
    """Faithful web adapter for the original vedic-astro-skills file workflow."""

    def __init__(
        self,
        calculator: VedicCalculator,
        workspace: SkillWorkspace,
        agent_runtime: ClaudeRuntime,
    ) -> None:
        self.calculator = calculator
        self.workspace = workspace
        self.agent_runtime = agent_runtime

    async def create_reader_session(self, input_data: SkillBirthInput) -> SkillSessionResponse:
        session_id = self.workspace.create_session()
        calculation = self.calculator.calculate(input_data)
        self.workspace.write_artifact(session_id, "structured_data.md", calculation.structured_data)

        chat_message = (
            "读盘基础数据已生成。\n\n"
            "已生成: structured_data.md\n"
            "下一步按原 vedic-reader 流程运行验前事：点击「运行读盘验前事」。"
        )
        return SkillSessionResponse(
            session_id=session_id,
            stage="reader_ready",
            chat_message=chat_message,
            artifacts=self.workspace.read_artifacts(session_id),
            active_artifact="structured_data.md",
        )

    async def create_synastry_subject(
        self, input_data: SynastryBirthInput
    ) -> SkillSessionResponse:
        session_dir = self.workspace.require_session_dir(input_data.session_id)
        if not (session_dir / "structured_data.md").exists():
            raise ValueError("A structured_data.md is required before synastry")

        folder = self._synastry_folder(input_data.label)
        calculation = self.calculator.calculate(input_data.birth)
        b_path = f"{folder}/structured_data_B.md"
        self.workspace.write_artifact(input_data.session_id, b_path, calculation.structured_data)

        intake = self._synastry_intake(input_data)
        self.workspace.write_artifact(input_data.session_id, f"{folder}/intake.md", intake)

        synastry_dir = session_dir / folder
        validate_output = self._run_synastry_script(
            "validate_synastry_data.py",
            [
                str(session_dir / "structured_data.md"),
                str(synastry_dir / "structured_data_B.md"),
            ],
        )
        build_output = self._run_synastry_script(
            "build_synastry_data.py",
            [
                str(session_dir / "structured_data.md"),
                str(synastry_dir / "structured_data_B.md"),
                str(synastry_dir),
                "--a",
                "A",
                "--b",
                input_data.label or "B",
            ],
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

    async def run_skill(self, input_data: SkillRunInput) -> SkillSessionResponse:
        self.workspace.require_session_dir(input_data.session_id)
        if input_data.skill == "vedic-core":
            return await self._run_core(input_data)

        prompt = self._artifact_prompt_for(input_data)
        result = await self.agent_runtime.run_skill_prompt_task(
            input_data.skill,
            prompt,
            skills=[input_data.skill],
            max_turns=self._max_turns_for(input_data.skill),
        )
        parsed = self._parse_artifact_response(result.raw_text)
        for artifact in parsed["artifacts"]:
            self.workspace.write_artifact(
                input_data.session_id,
                str(artifact["path"]),
                str(artifact["content"]),
            )
        stage = self._stage_for(input_data.skill)
        artifacts = self.workspace.read_artifacts(input_data.session_id)
        return SkillSessionResponse(
            session_id=input_data.session_id,
            stage=stage,
            chat_message=str(parsed["chatMessage"]),
            artifacts=artifacts,
            active_artifact=self._preferred_artifact(input_data.skill, artifacts),
        )

    async def _run_core(self, input_data: SkillRunInput) -> SkillSessionResponse:
        batches = self._core_batches(input_data.user_message)
        existing_paths = {artifact.path for artifact in self.workspace.read_artifacts(input_data.session_id)}
        batch = next(
            (
                item
                for item in batches
                if not set(self._batch_files(item)).issubset(existing_paths)
            ),
            None,
        )
        if batch is None:
            artifacts = self.workspace.read_artifacts(input_data.session_id)
            return SkillSessionResponse(
                session_id=input_data.session_id,
                stage="core_complete",
                chat_message="vedic-core 已完成。可继续运行 vedic-career、vedic-love，或进行追问。",
                artifacts=artifacts,
                active_artifact=self._preferred_artifact(input_data.skill, artifacts),
            )

        artifacts_for_prompt = self._artifacts_for_skill(
            input_data.skill,
            self.workspace.read_artifacts(input_data.session_id),
        )
        prompt = self._artifact_prompt(str(batch["prompt"]), artifacts_for_prompt)
        result = await self.agent_runtime.run_skill_prompt_task(
            input_data.skill,
            prompt,
            skills=[input_data.skill],
            max_turns=self._max_turns_for(input_data.skill),
        )
        parsed = self._parse_artifact_response(result.raw_text)
        expected = set(self._batch_files(batch))
        for artifact in parsed["artifacts"]:
            path = str(artifact["path"])
            if path not in expected:
                raise ValueError(f"vedic-core returned unexpected artifact: {path}")
            self.workspace.write_artifact(
                input_data.session_id,
                path,
                str(artifact["content"]),
            )

        artifacts = self.workspace.read_artifacts(input_data.session_id)
        completed_paths = {artifact.path for artifact in artifacts}
        core_complete = all(
            set(self._batch_files(item)).issubset(completed_paths) for item in batches
        )
        next_message = (
            "vedic-core 全部批次已完成。"
            if core_complete
            else "继续点击 vedic-core，可按原流程生成下一批文件。"
        )
        return SkillSessionResponse(
            session_id=input_data.session_id,
            stage="core_complete" if core_complete else "core_in_progress",
            chat_message=f"{parsed['chatMessage']}\n\n{next_message}",
            artifacts=artifacts,
            active_artifact=self._batch_files(batch)[0],
        )

    async def record_reader_feedback(
        self, session_id: str, feedback_markdown: str
    ) -> SkillSessionResponse:
        existing = ""
        artifacts = {artifact.path: artifact.content for artifact in self.workspace.read_artifacts(session_id)}
        if "user_context.md" in artifacts:
            existing = artifacts["user_context.md"].rstrip() + "\n\n"
        content = (
            f"{existing}"
            "## 验前事反馈\n\n"
            f"{feedback_markdown.strip()}\n\n"
            f"_updated_at: {datetime.now(timezone.utc).isoformat()}_\n"
        )
        self.workspace.write_artifact(session_id, "user_context.md", content)
        return SkillSessionResponse(
            session_id=session_id,
            stage="reader_validation",
            chat_message=(
                "反馈已写入 user_context.md。按原流程，下一步可以运行 vedic-core 开始完整分析。"
            ),
            artifacts=self.workspace.read_artifacts(session_id),
            active_artifact="user_context.md",
        )

    def _prompt_for(self, input_data: SkillRunInput) -> str:
        if input_data.skill == "vedic-reader":
            return self._reader_prompt(input_data.user_message)
        if input_data.skill == "vedic-core":
            return self._core_prompt(input_data.user_message)
        if input_data.skill == "vedic-career":
            return self._career_prompt(input_data.user_message)
        if input_data.skill == "vedic-love":
            return self._love_prompt(input_data.user_message)
        if input_data.skill == "vedic-rectifier":
            return self._rectifier_prompt(input_data.user_message)
        if input_data.skill == "vedic-synastry":
            return self._synastry_prompt(input_data.user_message)
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
- Preserve the selected skill's original output file names and markdown style.
- Do not omit important sections with phrases like see above.
- Do not include any artifact outside the original skill's expected file set.
- The JSON wrapper is only for the backend; the user sees the markdown artifacts."""

    def _core_batches(self, user_message: str) -> list[dict[str, object]]:
        user_line = user_message or "开始分析"
        return [
            {
                "files": ["p1_overview.md"],
                "prompt": self._core_batch_prompt(
                    "P1 身份总览",
                    ["p1_overview.md"],
                    "Run vedic-core Step 0 and P1 only. Use structured_data.md. Do not use user_context.md in this batch.",
                    user_line,
                ),
            },
            self._core_batch(
                "P2A 行星审计 Sun/Moon",
                "p2a_planets.md",
                "Run the original Step 1 Group 1 only: Sun and Moon. Include the Yoga pre-scan at the beginning as specified by vedic-core. Preserve the blind-audit rule: do not use user_context.md in this batch.",
                user_line,
            ),
            self._core_batch(
                "P2B 行星审计 Mars/Mercury",
                "p2b_planets.md",
                "Run the original Step 1 Group 2 only: Mars and Mercury. Preserve the blind-audit rule: do not use user_context.md in this batch.",
                user_line,
            ),
            self._core_batch(
                "P2C 行星审计 Jupiter/Venus",
                "p2c_planets.md",
                "Run the original Step 1 Group 3 only: Jupiter and Venus. Preserve the blind-audit rule: do not use user_context.md in this batch.",
                user_line,
            ),
            self._core_batch(
                "P2D 行星审计 Saturn/Rahu/Ketu",
                "p2d_planets.md",
                "Run the original Step 1 Group 4 only: Saturn, Rahu, and Ketu. Preserve the blind-audit rule: do not use user_context.md in this batch.",
                user_line,
            ),
            self._core_batch(
                "P3A D9 逐星深度审计",
                "p3a_d9.md",
                "Run the original Step 2.1 D9 audit only. Use completed p2a-p2d artifacts and structured_data.md. Preserve the blind-audit rule: do not use user_context.md in this batch.",
                user_line,
            ),
            self._core_batch(
                "P3B D10/D4/D5 分盘交叉",
                "p3b_divisional.md",
                "Run the original Step 2.2-2.4 D10/D4/D5 overview only. Use structured_data.md and completed P2/P3A artifacts.",
                user_line,
            ),
            self._core_batch(
                "P4A 宫位诊断 1-6宫",
                "p4a_houses.md",
                "Run the original Step 3 house diagnosis for houses 1-6 only. Use existing P1-P3 artifacts as prior audit context.",
                user_line,
            ),
            self._core_batch(
                "P4B 宫位诊断 7-12宫",
                "p4b_houses.md",
                "Run the original Step 3 house diagnosis for houses 7-12 only, including the Parivartana scan at the end as required by vedic-core. Use existing P1-P4A artifacts as prior audit context.",
                user_line,
            ),
            self._core_batch(
                "P5A 十大板块 1-5",
                "p5a_life.md",
                "Run the original Step 4 life synthesis blocks 1-5 only. Use existing P1-P4 artifacts and structured_data.md. If user_context.md exists, use it only for the original contextual calibration stage.",
                user_line,
            ),
            self._core_batch(
                "P5B 十大板块 6-10",
                "p5b_life.md",
                "Run the original Step 4 life synthesis blocks 6-10 only. Use existing P1-P4 artifacts and structured_data.md. If user_context.md exists, use it only for the original contextual calibration stage.",
                user_line,
            ),
            self._core_batch(
                "Step 5 技术附录",
                "appendix.md",
                "Run the original Step 5 technical appendix only, including the P1-P12 parameter table, divisional data overview, validation report, and Dasha timeline.",
                user_line,
            ),
        ]

    def _core_batch(
        self, batch_name: str, file_name: str, instruction: str, user_message: str
    ) -> dict[str, object]:
        return {
            "files": [file_name],
            "prompt": self._core_batch_prompt(
                batch_name,
                [file_name],
                instruction,
                user_message,
            ),
        }

    def _core_batch_prompt(
        self, batch_name: str, files: list[str], instruction: str, user_message: str
    ) -> str:
        file_list = ", ".join(files)
        return f"""Run vedic-core exactly as the original skill, but only for this backend batch: {batch_name}.

Batch instruction:
{instruction}

Output exactly these original file names and no others:
{file_list}

Rules:
- Preserve the original vedic-core phase order, terminology, markdown style, evidence weighting, and QA/report rules.
- Use structured_data.md as the calculation source of truth.
- Do not summarize with app-specific sections, cards, claims, daily notes, or JSON.
- Each requested file must be complete markdown, not a placeholder and not "see previous".
- The chat response should only state this batch is complete and list the files generated.

User message:
{user_message}"""

    def _batch_files(self, batch: dict[str, object]) -> list[str]:
        return [str(path) for path in batch["files"]]

    def _artifacts_for_skill(self, skill: str, artifacts: list[object]) -> dict[str, str]:
        selected: dict[str, str] = {}
        for artifact in artifacts:
            path = str(getattr(artifact, "path"))
            content = str(getattr(artifact, "content"))
            if skill == "vedic-synastry":
                if path == "structured_data.md" or path.startswith("synastry_"):
                    selected[path] = content
                continue
            if "/" not in path:
                selected[path] = content
        return selected

    def _reader_prompt(self, user_message: str) -> str:
        return f"""Run vedic-reader in Calc mode.

Workspace already contains structured_data.md generated by vedic-calculator.

Follow the original vedic-reader workflow exactly, but because this is a web adapter:
- Do not ask for setup or dependency installation.
- Do not run shell commands.
- Use the provided structured_data.md content.
- Execute Calc mode Stage 2 and Stage 3 only: signal pre-scan, Yoga scan, and pre-validation reading.
- Write the user-facing pre-validation output to reader_prevalidation.md.
- Chat response should be only the original short progress / next-step message and ask the user to reply 准 / 不准 / 部分准.
- reader_prevalidation.md must follow the original Step 5 output template:
  - Start with: 在进入完整分析之前，我先验证几个时间锚点来确认出生数据的精度——
  - Output 3 to 5 numbered items only.
  - Each item uses bold markdown number, e.g. **1.** 推断正文.
  - Each item is followed by one blank line and a quoted derivation line: > 推导：...
  - Do not add signal tables, Yoga tables, 综合轮廓, advice, disclaimers, or app-specific explanation.
  - End with: 请逐条回复：**准 / 不准 / 部分准**
- Do not generate core report, career report, love report, daily note, app-specific claims, or JSON.

User message:
{user_message or "开始读盘验前事"}"""

    def _core_prompt(self, user_message: str) -> str:
        return f"""Run vedic-core exactly as the original skill.

Workspace contains structured_data.md and may contain user_context.md / reader_prevalidation.md.

Rules:
- Follow vedic-core Step 0 through Step 5.
- Preserve blind-audit rules: Step 1-3 must not use user_context.md.
- Write the original expected markdown files: p1_overview.md, p2a_planets.md, p2b_planets.md, p2c_planets.md, p2d_planets.md, p3a_d9.md, p3b_divisional.md, p4a_houses.md, p4b_houses.md, p5a_life.md, p5b_life.md, appendix.md.
- Chat response should only report completion and available next actions, matching the skill style.
- Do not compress the report into app-specific sections, claims, daily notes, or JSON.

User message:
{user_message or "开始分析"}"""

    def _career_prompt(self, user_message: str) -> str:
        return f"""Run vedic-career exactly as the original skill.

Workspace contains structured_data.md and may contain the core report files.

Rules:
- Use only structured_data.md and core report files as allowed by the skill.
- Follow all four career phases.
- Write the original expected markdown outputs, including career_phase4a.md, career_phase4b.md, and career_phase4c.md when Phase 4 is reached.
- Chat response should only report progress/completion and file paths.
- Do not output app cards, claims, daily notes, or JSON.

User message:
{user_message or "分析事业"}"""

    def _love_prompt(self, user_message: str) -> str:
        return f"""Run vedic-love exactly as the original skill.

Workspace contains structured_data.md and may contain the core report files.

Rules:
- Use only structured_data.md and allowed report files.
- Follow the original love timing workflow and output file rules.
- Chat response should only report progress/completion and file paths.
- Do not output app cards, claims, daily notes, or JSON.

User message:
{user_message or "分析感情"}"""

    def _rectifier_prompt(self, user_message: str) -> str:
        return f"""Run vedic-rectifier exactly as the original skill.

Workspace contains structured_data.md and user_context.md if feedback/events exist.

Rules:
- This skill is interactive.
- Write rectification_report.md.
- If the birth time should be changed, clearly state the candidate time and what needs confirmation.
- Do not run shell commands. If recalculation is needed, request recalculation as the next backend step.
- Do not output app cards, claims, daily notes, or JSON.

User message:
{user_message or "校准时间"}"""

    def _synastry_prompt(self, user_message: str) -> str:
        return f"""Run vedic-synastry exactly as the original skill.

Workspace contains A's structured_data.md and a synastry_<B>_<YYYYMMDD> folder with:
- intake.md
- structured_data_B.md
- synastry_data.md

Rules:
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

    def _max_turns_for(self, skill: str) -> int:
        return {
            "vedic-reader": 6,
            "vedic-core": 10,
            "vedic-career": 8,
            "vedic-love": 8,
            "vedic-rectifier": 6,
            "vedic-synastry": 8,
        }[skill]

    def _stage_for(self, skill: str) -> str:
        return {
            "vedic-reader": "reader_validation",
            "vedic-core": "core_complete",
            "vedic-career": "career_complete",
            "vedic-love": "love_complete",
            "vedic-rectifier": "rectifier_complete",
            "vedic-synastry": "synastry_complete",
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

    def _run_synastry_script(self, script_name: str, args: list[str]) -> str:
        script = self.workspace.settings.skills_root / "vedic-synastry" / "scripts" / script_name
        if not script.exists():
            raise RuntimeError(f"Synastry script not found: {script}")
        result = subprocess.run(
            [sys.executable, str(script), *args],
            check=False,
            text=True,
            capture_output=True,
        )
        output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
        if result.returncode != 0:
            raise RuntimeError(output or f"{script_name} failed")
        return output

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
            if not isinstance(artifact, dict) or not artifact.get("path") or not artifact.get("content"):
                raise ValueError("Artifact response contains an invalid artifact")
        return payload
