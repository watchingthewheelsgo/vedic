from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

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
        started = datetime.now(timezone.utc)
        calculation = self.calculator.calculate(input_data)
        finished = datetime.now(timezone.utc)
        self.workspace.write_artifact(session_id, "structured_data.md", calculation.structured_data)
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

    def load_session(self, session_id: str) -> SkillSessionResponse:
        artifacts = self.workspace.read_artifacts(session_id)
        paths = {artifact.path for artifact in artifacts}
        if "appendix.md" in paths and "run_metrics.json" in paths:
            stage = "core_complete"
            active = "run_metrics.json"
            message = "已载入完整 core 报告和运行耗时统计。"
        elif "structured_data.md" in paths:
            stage = "reader_ready"
            active = "structured_data.md"
            message = "已载入 structured_data.md。"
        else:
            stage = "reader_ready"
            active = artifacts[0].path if artifacts else None
            message = "已载入 session。"
        return SkillSessionResponse(
            session_id=session_id,
            stage=stage,
            chat_message=message,
            artifacts=artifacts,
            active_artifact=active,
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
        session_dir = self.workspace.require_session_dir(input_data.session_id)
        batches = self.core_batches(input_data.user_message)
        existing_paths = self._session_paths(session_dir)
        batch = next(
            (
                item
                for item in batches
                if not set(self.core_batch_files(item)).issubset(existing_paths)
            ),
            None,
        )
        if batch is None:
            return self.core_progress_response(
                session_id=input_data.session_id,
                stage="core_complete",
                chat_message="vedic-core 已完成。可继续运行 vedic-career、vedic-love，或进行追问。",
            )

        return await self.run_core_batch(input_data, batch, batches=batches)

    def core_batches(self, user_message: str) -> list[dict[str, object]]:
        return self._core_batches(user_message)

    def core_batch_files(self, batch: dict[str, object]) -> list[str]:
        return self._batch_files(batch)

    def core_batch_complete(self, session_id: str, batch: dict[str, object]) -> bool:
        session_dir = self.workspace.require_session_dir(session_id)
        existing_paths = self._session_paths(session_dir)
        return set(self.core_batch_files(batch)).issubset(existing_paths)

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
    ) -> SkillSessionResponse:
        session_dir = self.workspace.require_session_dir(input_data.session_id)
        batches = batches or self.core_batches(input_data.user_message)
        expected = set(self.core_batch_files(batch))
        if expected.issubset(self._session_paths(session_dir)):
            self._compose_core_outputs(session_dir)
            artifacts = self.workspace.read_artifacts(input_data.session_id)
            return SkillSessionResponse(
                session_id=input_data.session_id,
                stage="core_in_progress",
                chat_message=f"{self._chat_message_for_batch(batch, '')}\n\n该批次已存在，已跳过。",
                artifacts=artifacts,
                active_artifact=self._active_artifact_for_batch(batch, artifacts),
            )

        result = await self.agent_runtime.run_skill_task(
            input_data.skill,
            str(batch["prompt"]),
            cwd=session_dir,
            skills=[input_data.skill],
            max_turns=self._max_turns_for(input_data.skill),
        )
        missing = [path for path in expected if not (session_dir / path).exists()]
        if missing:
            raise ValueError(
                "vedic-core did not create expected artifact(s): "
                + ", ".join(missing)
                + f"\nAgent output:\n{result.raw_text[:2000]}"
            )

        self._compose_core_outputs(session_dir)
        artifacts = self.workspace.read_artifacts(input_data.session_id)
        completed_paths = self._session_paths(session_dir)
        core_complete = all(
            set(self.core_batch_files(item)).issubset(completed_paths) for item in batches
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
            ),
            self._core_batch(
                "p2_yoga",
                "P2 Yoga/NBRY 预扫描",
                ".runtime/p2/yoga.md",
                "Run only the original Step 1 Yoga pre-scan before planet audit. Read structured_data.md and resources/yogas.md. Check every listed Yoga/NBRY condition. Write the content that belongs at the top of p2a_planets.md: the opening framework note plus 已确认格局 / 待验证格局 / 落陷星NBRY状态. Do not audit Sun or Moon in this batch.",
                user_line,
                active="p1_overview.md",
                progress_message="P2 Yoga/NBRY 预扫描已完成。",
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
                        "D9 quality/兑现率 logic, and the original markdown style. "
                        f"Write only the complete D9 section for {planet}; do not audit other planets."
                    ),
                    user_line,
                    dependencies=p2_node_ids,
                    active="p2a_planets.md",
                    progress_message=f"P3A D9 {planet} 审计已完成。",
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
            )
        )

        life_blocks = [
            (1, "人格核心", "Use p1_overview.md, p2 Sun/Moon findings, p3a Sun/Moon D9 settlement, Lagna, Moon, Sun, and AK. Write block 1 only."),
            (2, "财富潜力", "Use house 2 and house 11 diagnoses, D4 data, p2 money-relevant planet audits, and Dasha review. Write block 2 only."),
            (3, "事业方向", "Use house 10 diagnosis, D10 data, L10/AmK audits, Yoga activation, and Dasha review. Write block 3 only."),
            (4, "感情/婚姻", "Use house 7 diagnosis, D9, Venus/Jupiter/DK/UL signals, and Dasha review. Write block 4 only."),
            (5, "健康提醒", "Use house 1 and house 6 diagnoses, Mars/Saturn audits, Maraka context, and Dasha review. Write block 5 only."),
            (6, "教育/学习", "Use house 4 and house 5 diagnoses, D5 data, Mercury/Jupiter/Moon signals, and Dasha review. Write block 6 only."),
            (7, "家庭/居住", "Use house 4 and house 9 diagnoses, D4 data, parental/home indicators, and Dasha review. Write block 7 only."),
            (8, "社交/声誉", "Use AL data from structured_data.md, house 11 diagnosis, relevant p2/p4 signals, and Dasha review. Write block 8 only."),
            (9, "灵性/成长", "Use AK, house 9 and house 12 diagnoses, AK planet D9 settlement, and Dasha review. Write block 9 only."),
            (10, "赛道优势地图", "Use all p2 Yoga findings, p3a D9 settlements, p4 house conclusions, and dasha_review.md. Translate Yoga into supported tracks, business/wealth paths, and timing. Write block 10 only."),
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
                        "chart. No data tables except where the original block explicitly allows it. "
                        f"{instruction}"
                    ),
                    user_line,
                    dependencies=["p4_parivartana", "dasha_review"],
                    active="p4b_houses.md",
                    progress_message=f"P5 板块{number} {title} 已完成。",
                )
            )

        batches.append(
            self._core_batch(
                "appendix",
                "Step 5 技术附录",
                "appendix.md",
                (
                    "Run the original Step 5 technical appendix only. Read structured_data.md, "
                    "p2a-p2d, p3a/p3b, p4a/p4b, p5a/p5b, and .runtime/dasha_review.md. "
                    "Include the P1-P12 parameter table, divisional data overview, validation "
                    "report, Dasha timeline, and the Dasha回顾速查表 if available."
                ),
                user_line,
                dependencies=life_node_ids,
                active="p5a_life.md",
                progress_message="Step 5 技术附录已完成。",
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
            ),
        }

    def _core_batch_prompt(
        self, batch_name: str, files: list[str], instruction: str, user_message: str
    ) -> str:
        file_list = ", ".join(files)
        return f"""Run vedic-core exactly as the original skill, but only for this backend batch: {batch_name}.

Batch instruction:
{instruction}

Write exactly these batch file names in the current workspace and no others:
{file_list}

Rules:
- Preserve the original vedic-core phase order, terminology, markdown style, evidence weighting, and QA/report rules.
- Use structured_data.md as the calculation source of truth.
- Do not summarize with app-specific sections, cards, claims, daily notes, or JSON.
- Each requested file must be complete markdown, not a placeholder and not "see previous".
- If the requested file is under .runtime/, treat it as an internal shard; do not write the public composed files such as p2a_planets.md, p3a_d9.md, p4a_houses.md, p4b_houses.md, p5a_life.md, or p5b_life.md.
- Do not create, edit, or rename any file outside the exact requested batch file name(s).
- Do not return JSON for this batch. Write the markdown file directly, then state the batch is complete and list the file generated.

User message:
{user_message}"""

    def _batch_files(self, batch: dict[str, object]) -> list[str]:
        return [str(path) for path in batch["files"]]

    def _session_paths(self, session_dir: Path) -> set[str]:
        return {
            path.relative_to(session_dir).as_posix()
            for path in session_dir.rglob("*")
            if path.is_file()
        }

    def _compose_core_outputs(self, session_dir: Path) -> None:
        p2a_parts = [
            session_dir / ".runtime" / "p2" / "yoga.md",
            session_dir / ".runtime" / "p2" / "sun.md",
            session_dir / ".runtime" / "p2" / "moon.md",
        ]
        self._compose_parts(session_dir / "p2a_planets.md", p2a_parts)

        p2b_parts = [
            session_dir / ".runtime" / "p2" / "mars.md",
            session_dir / ".runtime" / "p2" / "mercury.md",
        ]
        self._compose_parts(session_dir / "p2b_planets.md", p2b_parts)

        p2c_parts = [
            session_dir / ".runtime" / "p2" / "jupiter.md",
            session_dir / ".runtime" / "p2" / "venus.md",
        ]
        self._compose_parts(session_dir / "p2c_planets.md", p2c_parts)

        p2d_parts = [
            session_dir / ".runtime" / "p2" / "saturn.md",
            session_dir / ".runtime" / "p2" / "rahu.md",
            session_dir / ".runtime" / "p2" / "ketu.md",
        ]
        self._compose_parts(session_dir / "p2d_planets.md", p2d_parts)

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
        self._compose_parts(session_dir / "p3a_d9.md", p3a_parts)

        p3b_parts = [
            session_dir / ".runtime" / "p3" / "d10.md",
            session_dir / ".runtime" / "p3" / "d4.md",
            session_dir / ".runtime" / "p3" / "d5.md",
        ]
        self._compose_parts(session_dir / "p3b_divisional.md", p3b_parts)

        p4a_parts = [
            session_dir / ".runtime" / "houses" / f"house_{number:02d}.md"
            for number in range(1, 7)
        ]
        self._compose_parts(session_dir / "p4a_houses.md", p4a_parts)

        p4b_parts = [
            *[
                session_dir / ".runtime" / "houses" / f"house_{number:02d}.md"
                for number in range(7, 13)
            ],
            session_dir / ".runtime" / "houses" / "parivartana.md",
        ]
        self._compose_parts(session_dir / "p4b_houses.md", p4b_parts)

        p5a_parts = [
            session_dir / ".runtime" / "life" / f"block_{number:02d}.md"
            for number in range(1, 6)
        ]
        self._compose_parts(session_dir / "p5a_life.md", p5a_parts)

        p5b_parts = [
            session_dir / ".runtime" / "life" / f"block_{number:02d}.md"
            for number in range(6, 11)
        ]
        self._compose_parts(session_dir / "p5b_life.md", p5b_parts)

    def _compose_parts(self, target: Path, parts: list[Path]) -> None:
        if all(path.exists() for path in parts):
            target.write_text(
                "\n\n".join(path.read_text(encoding="utf-8").strip() for path in parts) + "\n",
                encoding="utf-8",
            )

    def _active_artifact_for_batch(self, batch: dict[str, object], artifacts: list[object]) -> str:
        paths = {str(getattr(artifact, "path")) for artifact in artifacts}
        active = str(batch.get("active") or self._batch_files(batch)[0])
        if active in paths:
            return active
        for fallback in [
            "p5a_life.md",
            "p5b_life.md",
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
            # vedic-core batches still need several tool turns to load skill
            # resources, inspect prior artifacts, and write the target report.
            "vedic-core": 40,
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
