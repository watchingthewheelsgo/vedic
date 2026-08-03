from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from app.schemas import SkillArtifact
from app.settings import Settings
from app.utils.ids import make_id


class SkillWorkspace:
    """File-backed workspace for the current VedicDust and BaZi contracts."""

    ROOT_ARTIFACTS = {
        "birth_input_context.json",
        "sensitivity_scan.json",
        "active_chart_sensitivity.json",
        "chart_record.json",
        "reading_session.json",
        "chart_audit.json",
        "chart_rectification_state.json",
        "rectification_interview.json",
        "life_event_evidence_validation.json",
        "reader_prevalidation.md",
        "prevalidation_result.json",
        "user_context.md",
        "judgement_context.json",
        "claim_graph.json",
        "consultation_dossier.json",
        "consultation_report_manifest.json",
        "agent_context.json",
        "consultation_report.md",
        "consultation_conversation.json",
        "consultation_grounding_audit.json",
        "life_event_evidence_validation.json",
        "rectification_report.md",
        "run_metrics.json",
    }

    BAZI_ARTIFACTS = {
        "bazi_chart_record.json",
        "bazi_chart_foundation.md",
        "bazi_report_context.md",
        "bazi_overview.md",
        "bazi_life_report.md",
        "bazi_timing_report.md",
        "bazi_appendix.md",
        "bazi_data_audit.md",
        "bazi_classics_audit.md",
    }

    INTERNAL_ARTIFACTS = {
        "reading_session.json",
        "chart_audit.json",
        "judgement_context.json",
        "claim_graph.json",
        "consultation_dossier.json",
        "consultation_report_manifest.json",
        "agent_context.json",
        "active_chart_sensitivity.json",
        "consultation_conversation.json",
        "consultation_grounding_audit.json",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.assert_no_project_runtime_artifacts()
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self.settings.project_root / "backend" / "data" / "sessions"

    def create_session(self, session_id: str | None = None) -> str:
        session_id = session_id or make_id("session")
        self.session_dir(session_id).mkdir(parents=True, exist_ok=False)
        return session_id

    def session_dir(self, session_id: str) -> Path:
        if "/" in session_id or "\\" in session_id or ".." in session_id:
            raise ValueError("Invalid session id")
        return self.root / session_id

    def require_session_dir(self, session_id: str) -> Path:
        path = self.session_dir(session_id)
        if not path.exists():
            raise LookupError("Skill session not found")
        return path

    def write_artifact(self, session_id: str, path: str, content: str) -> SkillArtifact:
        session_dir = self.require_session_dir(session_id)
        target = self._safe_artifact_path(session_dir, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return self._artifact_from_path(session_dir, target)

    def read_artifacts(
        self,
        session_id: str,
        *,
        include_internal: bool = False,
    ) -> list[SkillArtifact]:
        session_dir = self.require_session_dir(session_id)
        files = [
            path
            for path in session_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in [".md", ".txt", ".json"]
            and not any(part.startswith(".") for part in path.relative_to(session_dir).parts)
            and self.is_current_runtime_file(path.relative_to(session_dir).as_posix())
            and (
                include_internal
                or path.relative_to(session_dir).as_posix() not in self.INTERNAL_ARTIFACTS
            )
        ]
        files.sort(key=lambda path: (self._artifact_rank(path.name), path.name))
        return [self._artifact_from_path(session_dir, path) for path in files]

    @staticmethod
    def is_current_runtime_file(relative_path: str) -> bool:
        if relative_path in SkillWorkspace.ROOT_ARTIFACTS:
            return True
        if relative_path in SkillWorkspace.BAZI_ARTIFACTS:
            return True
        if relative_path.startswith(".meta/") or relative_path.startswith("exports/"):
            return True
        if relative_path.startswith("synastry_"):
            suffix = relative_path.split("/", 1)[1] if "/" in relative_path else ""
            return suffix in {
                "chart_record_B.json",
                "synastry_context.json",
                "reports/relationship_consultation.md",
            }
        return False

    def read_artifact_text(self, session_id: str, path: str) -> str | None:
        session_dir = self.require_session_dir(session_id)
        target = self._safe_artifact_path(session_dir, path)
        if not target.exists() or not target.is_file():
            return None
        return target.read_text(encoding="utf-8")

    def write_session_manifest(self, session_id: str, *, locale: str = "en") -> None:
        session_dir = self.require_session_dir(session_id)
        manifest_path = session_dir / ".meta" / "session.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sessionId": session_id,
            "locale": locale,
            "chartRecordSha256": self.chart_record_sha256(session_id),
            "updatedAt": datetime.utcnow().isoformat() + "Z",
        }
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def read_session_locale(self, session_id: str) -> str:
        session_dir = self.require_session_dir(session_id)
        manifest_path = session_dir / ".meta" / "session.json"
        if not manifest_path.exists():
            return "en"
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return "en"
        locale = payload.get("locale") if isinstance(payload, dict) else None
        return locale if locale in {"zh", "en", "ja"} else "en"

    def mark_artifact_checkpoint(
        self,
        session_id: str,
        relative_path: str,
        *,
        producer: str,
        dependency_paths: list[str] | None = None,
    ) -> None:
        session_dir = self.require_session_dir(session_id)
        target = self._safe_artifact_path(session_dir, relative_path)
        if not target.exists() or not target.is_file():
            raise ValueError(f"Cannot checkpoint missing artifact: {relative_path}")
        metadata_path = self._artifact_checkpoint_path(session_dir, relative_path)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sessionId": session_id,
            "artifactPath": relative_path,
            "producer": producer,
            "chartRecordSha256": self.chart_record_sha256(session_id),
            "artifactSha256": self._file_sha256(target),
            "dependencySha256": self._dependency_hashes(session_dir, dependency_paths or []),
            "updatedAt": datetime.utcnow().isoformat() + "Z",
        }
        metadata_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def artifact_checkpoint_valid(
        self,
        session_id: str,
        relative_path: str,
        *,
        producer: str | None = None,
        dependency_paths: list[str] | None = None,
    ) -> bool:
        session_dir = self.require_session_dir(session_id)
        target = self._safe_artifact_path(session_dir, relative_path)
        if not target.exists() or not target.is_file():
            return False
        metadata_path = self._artifact_checkpoint_path(session_dir, relative_path)
        if not metadata_path.exists():
            return False
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        if not isinstance(payload, dict):
            return False
        if payload.get("sessionId") != session_id:
            return False
        if payload.get("artifactPath") != relative_path:
            return False
        if producer is not None and payload.get("producer") != producer:
            return False
        if payload.get("chartRecordSha256") != self.chart_record_sha256(session_id):
            return False
        if payload.get("artifactSha256") != self._file_sha256(target):
            return False
        expected_dependencies = self._dependency_hashes(session_dir, dependency_paths or [])
        if payload.get("dependencySha256", {}) != expected_dependencies:
            return False
        return True

    def chart_record_sha256(self, session_id: str) -> str:
        session_dir = self.require_session_dir(session_id)
        chart_record_path = session_dir / "chart_record.json"
        if not chart_record_path.exists():
            return ""
        return self._file_sha256(chart_record_path)

    def assert_no_project_runtime_artifacts(self) -> None:
        runtime_dir = self.settings.project_root / ".runtime"
        if not runtime_dir.exists():
            return
        files = sorted(path for path in runtime_dir.rglob("*") if path.is_file())
        if not files:
            return
        examples = ", ".join(
            path.relative_to(self.settings.project_root).as_posix() for path in files[:3]
        )
        raise RuntimeError(
            "Root .runtime contains generated artifacts outside any session. "
            "Move or delete these files before starting the service: "
            f"{examples}"
        )

    def _safe_artifact_path(self, session_dir: Path, relative_path: str) -> Path:
        target = (session_dir / relative_path).resolve()
        if session_dir.resolve() not in [target, *target.parents]:
            raise ValueError("Artifact path escapes session directory")
        return target

    def _artifact_checkpoint_path(self, session_dir: Path, relative_path: str) -> Path:
        digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()
        return session_dir / ".meta" / "artifacts" / f"{digest}.json"

    def _file_sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _dependency_hashes(self, session_dir: Path, dependency_paths: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for relative_path in dependency_paths:
            target = self._safe_artifact_path(session_dir, relative_path)
            if not target.exists() or not target.is_file():
                result[relative_path] = ""
            else:
                result[relative_path] = self._file_sha256(target)
        return result

    def _artifact_from_path(self, session_dir: Path, path: Path) -> SkillArtifact:
        relative = path.resolve().relative_to(session_dir.resolve()).as_posix()
        kind = "json" if path.suffix == ".json" else "text" if path.suffix == ".txt" else "markdown"
        return SkillArtifact(
            path=relative,
            title=relative,
            content=path.read_text(encoding="utf-8"),
            kind=kind,
            updated_at=datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
        )

    def _artifact_rank(self, name: str) -> int:
        order = [
            "chart_record.json",
            "birth_input_context.json",
            "sensitivity_scan.json",
            "chart_rectification_state.json",
            "judgement_context.json",
            "user_context.md",
            "reader_prevalidation.md",
            "prevalidation_result.json",
            "consultation_report.md",
            "run_metrics.json",
        ]
        return order.index(name) if name in order else 999
