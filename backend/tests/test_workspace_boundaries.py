from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.services.report_exporter import ReportExporter
from app.services.chart_rectification import ChartRectificationService
from app.services.skill_runtime import SkillRuntime
from app.services.skill_workspace import SkillWorkspace
from app.vedicdust.models import (
    BirthAssertion,
    ChartRecord,
    EvidenceItem,
    SubjectContext,
)
from app.vedicdust.profiles import parashari_lahiri_profile


def test_workspace_rejects_project_root_runtime_artifacts(tmp_path: Path) -> None:
    runtime_file = tmp_path / ".runtime" / "p2" / "yoga.md"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text("# stale root runtime\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Root \\.runtime contains generated artifacts"):
        SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]


def test_report_export_defaults_to_session_exports_directory(tmp_path: Path) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    workspace.write_artifact(session_id, "structured_data.md", "# structured\n")
    workspace.write_session_manifest(session_id)
    workspace.write_artifact(session_id, "p1_overview.md", "# Overview\n\nBody")

    exporter = ReportExporter(workspace)

    def fake_render_pdf(**kwargs) -> None:
        kwargs["pdf_path"].write_text("pdf", encoding="utf-8")

    exporter._render_pdf_with_playwright = fake_render_pdf  # type: ignore[method-assign]
    result = exporter.export_session(session_id)

    session_dir = workspace.session_dir(session_id)
    assert result.html_path == session_dir / "exports" / "report.html"
    assert result.pdf_path == session_dir / "exports" / "report.pdf"
    assert result.html_path.exists()
    assert result.pdf_path.exists()


def test_chart_record_is_internal_but_available_to_the_runtime(tmp_path: Path) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    workspace.write_artifact(session_id, "structured_data.md", "# legacy view\n")
    workspace.write_artifact(
        session_id,
        "chart_record.json",
        '{"schemaVersion":"vedicdust-chart-record/1.0.0","chartRecordId":"chart-1"}\n',
    )

    public_artifacts = workspace.read_artifacts(session_id)
    runtime_artifacts = workspace.read_artifacts(session_id, include_internal=True)

    assert [artifact.path for artifact in public_artifacts] == ["structured_data.md"]
    assert runtime_artifacts[0].path == "chart_record.json"
    assert runtime_artifacts[0].kind == "json"
    assert runtime_artifacts[1].path == "structured_data.md"


def test_reading_session_keeps_chart_identity_across_revisions(tmp_path: Path) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    record = ChartRecord(
        chart_record_id="chart-stable",
        reading_session_id=session_id,
        revision=1,
        created_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        subject=SubjectContext(subject_id="subject-stable"),
        birth_assertion=BirthAssertion(
            local_date="1990-01-01",
            reported_local_time="08:00",
            reported_place="Shanghai, China",
            time_certainty="reported_exact",
            evidence=[
                EvidenceItem(
                    evidence_id="birth-input",
                    evidence_class="user_testimony",
                    source_label="user",
                    observed_value="1990-01-01 08:00",
                    confidence="corroborated",
                )
            ],
        ),
        calculation_profile=parashari_lahiri_profile(),
        status="intake",
    )
    workspace.write_artifact(
        session_id,
        "chart_record.json",
        record.model_dump_json(by_alias=True),
    )
    runtime = cast(Any, SkillRuntime.__new__(SkillRuntime))
    runtime.workspace = workspace

    revision = runtime._chart_record_identity(session_id, revision=2)

    assert revision.reading_session_id == session_id
    assert revision.chart_record_id == "chart-stable"
    assert revision.subject_id == "subject-stable"
    assert revision.revision == 2
    reading = workspace.read_artifact_text(session_id, "reading_session.json")
    assert reading is not None


def test_rectification_cards_are_persisted_as_typed_question_and_answer_artifacts(
    tmp_path: Path,
) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    record = ChartRecord(
        chart_record_id="chart-questions",
        reading_session_id=session_id,
        revision=1,
        created_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        subject=SubjectContext(subject_id="subject-questions"),
        birth_assertion=BirthAssertion(
            local_date="1990-01-01",
            reported_local_time="08:00",
            reported_place="Shanghai, China",
            time_certainty="approximate",
            evidence=[
                EvidenceItem(
                    evidence_id="birth-input",
                    evidence_class="user_testimony",
                    source_label="user",
                    observed_value="1990-01-01 around 08:00",
                    confidence="provisional",
                )
            ],
        ),
        calculation_profile=parashari_lahiri_profile(),
        status="intake",
    )
    workspace.write_artifact(
        session_id,
        "chart_record.json",
        record.model_dump_json(by_alias=True),
    )
    workspace.write_artifact(
        session_id,
        "chart_rectification_state.json",
        '{"rectificationRound":0,"candidates":[{"candidateId":"A"},{"candidateId":"B"}]}',
    )
    workspace.write_artifact(
        session_id,
        "reader_prevalidation.md",
        (
            "**1.** 2018 至 2020 年间，你是否经历过一次明确的搬迁？\n\n"
            "> Derivation: Candidate split\n"
            "> Candidate: A\n"
            "> Field: d9Lagna\n"
        ),
    )
    runtime = cast(Any, SkillRuntime.__new__(SkillRuntime))
    runtime.workspace = workspace
    runtime.rectification = ChartRectificationService()

    runtime._write_rectification_question_set(session_id)
    runtime._write_rectification_answer_batch(
        session_id,
        "#### Anchor 1\n- User answer: 准 (accurate)\n",
    )

    questions = workspace.read_artifact_text(session_id, "rectification_question_set.json")
    answers = workspace.read_artifact_text(session_id, "rectification_answer_batch.json")
    assert questions is not None
    assert answers is not None
    assert '"chartRecordId": "chart-questions"' in questions
    assert '"questionId": "rectification.r1.q1"' in questions
    assert '"selectedOptionIds": [\n        "accurate"\n      ]' in answers
    assert "rectification_question_set.json" not in {
        artifact.path for artifact in workspace.read_artifacts(session_id)
    }
