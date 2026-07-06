from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.schemas import BaziSessionInput
from app.services.skill_runtime import SkillRuntime
from app.services.skill_workspace import SkillWorkspace
from app.tools.bazi.calculate_chart import BaziInput, calculate_bazi, write_artifacts
from app.tools.registry import BackendToolRunner


def sample_input(**overrides: object) -> BaziInput:
    data = {
        "birth_date": date(2005, 12, 23),
        "birth_time": "08:37",
        "birth_place": "Shanghai",
        "gender": "male",
        "calendar_type": "solar",
        "time_precision": "exact",
        "timezone_name": "Asia/Shanghai",
        "latitude": None,
        "longitude": None,
        "current_date": date(2026, 7, 5),
        "audience": "self",
        "relationship": "[not provided]",
        "topic": "[not provided]",
        "day_boundary_sect": 2,
        "luck_sect": 2,
        "solar_time_policy": "civil",
    }
    data.update(overrides)
    return BaziInput(**data)


def test_calculate_bazi_matches_lunar_python_golden_chart() -> None:
    payload = calculate_bazi(sample_input())

    assert payload["pillars"]["year"]["ganZhi"] == "乙酉"
    assert payload["pillars"]["month"]["ganZhi"] == "戊子"
    assert payload["pillars"]["day"]["ganZhi"] == "辛巳"
    assert payload["pillars"]["hour"]["ganZhi"] == "壬辰"
    assert payload["dayMaster"] == {"stem": "辛", "element": "金", "yinYang": "阴"}
    assert payload["luck"]["direction"] == "reverse"
    assert payload["luck"]["majorLuck"][0]["pillar"] == "丁亥"
    assert payload["luck"]["currentLuck"]["pillar"] == "丙戌"


def test_write_bazi_artifacts(tmp_path: Path) -> None:
    payload = calculate_bazi(sample_input())
    written = write_artifacts(payload, tmp_path)

    assert set(written) == {
        "bazi_structured_data.json",
        "bazi_structured_data.md",
        "bazi_report_context.md",
    }
    structured = json.loads((tmp_path / "bazi_structured_data.json").read_text())
    assert structured["schemaVersion"] == "bazi-chart-facts/v1"
    assert "## Four Pillars" in (tmp_path / "bazi_structured_data.md").read_text()
    assert "Major Luck True Ages" in (tmp_path / "bazi_report_context.md").read_text()


def test_backend_runner_calculates_bazi_chart_artifacts(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    runner = BackendToolRunner(SimpleNamespace(project_root=project_root))  # type: ignore[arg-type]
    result = runner.calculate_bazi_chart(
        birth_date="2005-12-23",
        birth_time="08:37",
        birth_place="Shanghai",
        gender="male",
        current_date="2026-07-05",
        out_dir=tmp_path,
    )

    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert (tmp_path / "bazi_structured_data.json").exists()
    assert (tmp_path / "bazi_structured_data.md").exists()
    assert (tmp_path / "bazi_report_context.md").exists()


def test_skill_runtime_creates_bazi_session(tmp_path: Path) -> None:
    class FakeBaziTools:
        def calculate_bazi_chart(self, *, out_dir: Path, **_: object) -> object:
            payload = calculate_bazi(sample_input())
            write_artifacts(payload, out_dir)
            return SimpleNamespace(output=json.dumps({"ok": True}))

    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    runtime = SkillRuntime(
        calculator=None,  # type: ignore[arg-type]
        workspace=workspace,
        agent_runtime=None,  # type: ignore[arg-type]
    )
    runtime.tools = FakeBaziTools()  # type: ignore[assignment]

    async def run() -> None:
        session = await runtime.create_bazi_session(
            BaziSessionInput(
                birthDate="2005-12-23",
                birthTime="08:37",
                birthPlace="Shanghai",
                birthTimePrecision="exact",
                gender="male",
                relationship="self",
                timeSource="user-provided",
                calendarType="solar",
                currentDate="2026-07-05",
                audience="self",
                topic="general",
            )
        )
        assert session.stage == "bazi_ready"
        assert session.active_artifact == "bazi_structured_data.md"
        paths = {artifact.path for artifact in session.artifacts}
        assert "bazi_structured_data.md" in paths
        assert "bazi_structured_data.json" in paths
        assert "bazi_report_context.md" in paths

        loaded = runtime.load_session(session.session_id)
        assert loaded.stage == "bazi_ready"
        assert loaded.active_artifact == "bazi_structured_data.md"

    asyncio.run(run())
