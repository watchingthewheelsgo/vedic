from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from app.schemas import SkillArtifact
from app.settings import Settings
from app.utils.ids import make_id


class SkillWorkspace:
    """File-backed workspace that mirrors the original skill artifact model."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self.settings.project_root / "backend" / "data" / "sessions"

    def create_session(self) -> str:
        session_id = make_id("skill")
        self.session_dir(session_id).mkdir(parents=True, exist_ok=False)
        return session_id

    def create_session_access_token(self, session_id: str) -> str:
        token = secrets.token_urlsafe(32)
        meta_dir = self.require_session_dir(session_id) / ".meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "session.json").write_text(
            json.dumps(
                {
                    "accessToken": token,
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return token

    def session_dir(self, session_id: str) -> Path:
        if "/" in session_id or "\\" in session_id or ".." in session_id:
            raise ValueError("Invalid session id")
        return self.root / session_id

    def require_session_dir(self, session_id: str) -> Path:
        path = self.session_dir(session_id)
        if not path.exists():
            raise LookupError("Skill session not found")
        return path

    def validate_session_access(self, session_id: str, token: str | None) -> None:
        expected = self.session_access_token(session_id)
        if not expected:
            return
        if not token or not secrets.compare_digest(token, expected):
            raise PermissionError("This session is private to the browser that created it.")

    def session_access_token(self, session_id: str) -> str | None:
        meta_path = self.require_session_dir(session_id) / ".meta" / "session.json"
        if not meta_path.exists():
            return None
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        token = payload.get("accessToken") if isinstance(payload, dict) else None
        return token if isinstance(token, str) and token else None

    def write_artifact(self, session_id: str, path: str, content: str) -> SkillArtifact:
        session_dir = self.require_session_dir(session_id)
        target = self._safe_artifact_path(session_dir, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return self._artifact_from_path(session_dir, target)

    def read_artifacts(self, session_id: str) -> list[SkillArtifact]:
        session_dir = self.require_session_dir(session_id)
        files = [
            path
            for path in session_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in [".md", ".txt", ".json"]
            and not any(part.startswith(".") for part in path.relative_to(session_dir).parts)
        ]
        files.sort(key=lambda path: (self._artifact_rank(path.name), path.name))
        return [self._artifact_from_path(session_dir, path) for path in files]

    def _safe_artifact_path(self, session_dir: Path, relative_path: str) -> Path:
        target = (session_dir / relative_path).resolve()
        if session_dir.resolve() not in [target, *target.parents]:
            raise ValueError("Artifact path escapes session directory")
        return target

    def _artifact_from_path(self, session_dir: Path, path: Path) -> SkillArtifact:
        relative = path.relative_to(session_dir).as_posix()
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
            "structured_data.md",
            "structured_data.json",
            "user_context.md",
            "reader_prevalidation.md",
            "p1_overview.md",
            "p2a_planets.md",
            "p2b_planets.md",
            "p2c_planets.md",
            "p2d_planets.md",
            "p3a_d9.md",
            "p3b_divisional.md",
            "p4a_houses.md",
            "p4b_houses.md",
            "p5a_life.md",
            "p5b_life.md",
            "appendix.md",
            "run_metrics.json",
        ]
        return order.index(name) if name in order else 999
