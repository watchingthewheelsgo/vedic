from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.report_exporter import ReportExporter
from app.services.skill_workspace import SkillWorkspace


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
