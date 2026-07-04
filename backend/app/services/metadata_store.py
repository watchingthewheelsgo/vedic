from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session_factory
from app.db.models import (
    VedicArtifactRecord,
    VedicCoreJobNodeRecord,
    VedicCoreJobRecord,
    VedicExportRecord,
    VedicSessionRecord,
)
from app.schemas import (
    AdminArtifactSummary,
    AdminExportSummary,
    AdminSessionProgress,
    AdminSessionStatus,
    AdminSessionSummary,
    CoreJobResponse,
)
from app.services.skill_workspace import SkillWorkspace


class MetadataStore:
    """Database index for local Vedic runtime files and long-running jobs."""

    def __init__(self, workspace: SkillWorkspace) -> None:
        self.workspace = workspace

    async def backfill_all_sessions(self) -> None:
        if not self.workspace.root.exists():
            return
        for session_dir in sorted(path for path in self.workspace.root.iterdir() if path.is_dir()):
            await self.sync_session_from_files(session_dir.name)

    async def sync_session_from_files(
        self,
        session_id: str,
        *,
        stage: str | None = None,
        status: str | None = None,
        active_job_id: str | None = None,
        active_node: str | None = None,
        error: str | None = None,
    ) -> None:
        session_dir = self.workspace.require_session_dir(session_id)
        files = self._session_files(session_dir)
        checkpoints = self._checkpoint_metadata(session_dir)
        metrics = self._read_json(session_dir / "run_metrics.json")
        exports = [path for path in files if path.relative_to(session_dir).as_posix().startswith("exports/")]
        artifacts = [path for path in files if not path.relative_to(session_dir).as_posix().startswith(".meta/")]
        subject = self._subject_json(session_dir)
        derived_status = status or self._derive_status(files, metrics)
        derived_stage = stage or self._derive_stage(files, metrics, derived_status)
        progress = self._progress(metrics)

        async with self._session() as db:
            record = await self._get_session_record(db, session_id)
            if record is None:
                record = VedicSessionRecord(
                    session_id=session_id,
                    storage_root=str(session_dir),
                    created_at=self._created_at(files, session_dir),
                )
                db.add(record)
            record.status = derived_status
            record.stage = derived_stage
            record.storage_backend = "local"
            record.storage_root = str(session_dir)
            record.subject_json = subject
            record.artifact_count = len(artifacts)
            record.export_count = len(exports)
            record.has_pdf = (session_dir / "exports" / "report.pdf").exists()
            record.progress_total = progress.total
            record.progress_completed = progress.completed
            record.progress_running = progress.running
            record.progress_failed = progress.failed
            record.progress_percent = progress.percent
            record.active_job_id = active_job_id or self._string(metrics, "jobId")
            record.active_node = active_node or self._active_node(metrics)
            record.duration_seconds = self._duration(metrics)
            record.error = error or self._error(metrics)
            record.updated_at = self._updated_at(files, session_dir)

            await self._replace_artifacts(db, session_id, session_dir, artifacts, checkpoints)
            await self._replace_exports(db, session_id, session_dir, exports)

            # Keep progress-derived failed state even when only files exist and
            # the caller did not supply a status.
            if record.status != "failed" and progress.failed > 0:
                record.status = "failed"
            await db.commit()

    async def upsert_core_job(
        self,
        job: CoreJobResponse,
        *,
        user_message: str = "",
    ) -> None:
        async with self._session() as db:
            record = await self._get_job_record(db, job.job_id)
            if record is None:
                record = VedicCoreJobRecord(
                    job_id=job.job_id,
                    session_id=job.session_id,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(record)
            record.session_id = job.session_id
            record.status = job.status
            record.message = job.message
            record.user_message = user_message
            record.started_at = self._parse_dt(job.started_at)
            record.finished_at = self._parse_dt(job.finished_at)
            record.duration_seconds = job.duration_seconds
            record.progress_total = job.progress.total
            record.progress_completed = job.progress.completed
            record.progress_running = job.progress.running
            record.progress_failed = job.progress.failed
            record.progress_percent = job.progress.percent
            record.error = next((node.error for node in job.nodes if node.error), None)
            record.updated_at = datetime.now(timezone.utc)

            seen: set[str] = set()
            for node in job.nodes:
                seen.add(node.id)
                node_record = await self._get_job_node_record(db, job.job_id, node.id)
                if node_record is None:
                    node_record = VedicCoreJobNodeRecord(
                        job_id=job.job_id,
                        session_id=job.session_id,
                        node_id=node.id,
                    )
                    db.add(node_record)
                node_record.session_id = job.session_id
                node_record.label = node.label
                node_record.wave = node.wave
                node_record.status = node.status
                node_record.files = node.files
                node_record.dependencies = node.dependencies
                node_record.started_at = self._parse_dt(node.started_at)
                node_record.finished_at = self._parse_dt(node.finished_at)
                node_record.duration_seconds = node.duration_seconds
                node_record.error = node.error
                node_record.updated_at = datetime.now(timezone.utc)

            await db.execute(
                delete(VedicCoreJobNodeRecord).where(
                    VedicCoreJobNodeRecord.job_id == job.job_id,
                    VedicCoreJobNodeRecord.node_id.not_in(seen),
                )
            )
            await db.commit()

    async def list_session_summaries(self) -> list[AdminSessionSummary]:
        async with self._session() as db:
            result = await db.execute(
                select(VedicSessionRecord).order_by(VedicSessionRecord.updated_at.desc())
            )
            records = list(result.scalars().all())
            return [self._summary_from_record(record) for record in records]

    async def get_session_summary(self, session_id: str) -> AdminSessionSummary:
        async with self._session() as db:
            record = await self._get_session_record(db, session_id)
            if record is None:
                raise LookupError("Skill session not found")
            return self._summary_from_record(record)

    async def list_artifacts(self, session_id: str) -> list[AdminArtifactSummary]:
        async with self._session() as db:
            result = await db.execute(
                select(VedicArtifactRecord)
                .where(VedicArtifactRecord.session_id == session_id)
                .order_by(VedicArtifactRecord.path.asc())
            )
            return [self._artifact_summary(record) for record in result.scalars().all()]

    async def list_exports(self, session_id: str) -> list[AdminExportSummary]:
        async with self._session() as db:
            result = await db.execute(
                select(VedicExportRecord)
                .where(VedicExportRecord.session_id == session_id)
                .order_by(VedicExportRecord.path.asc())
            )
            return [self._export_summary(record) for record in result.scalars().all()]

    def _session(self):
        return get_session_factory()()

    async def _get_session_record(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> VedicSessionRecord | None:
        result = await db.execute(
            select(VedicSessionRecord).where(VedicSessionRecord.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def _get_job_record(
        self,
        db: AsyncSession,
        job_id: str,
    ) -> VedicCoreJobRecord | None:
        result = await db.execute(select(VedicCoreJobRecord).where(VedicCoreJobRecord.job_id == job_id))
        return result.scalar_one_or_none()

    async def _get_job_node_record(
        self,
        db: AsyncSession,
        job_id: str,
        node_id: str,
    ) -> VedicCoreJobNodeRecord | None:
        result = await db.execute(
            select(VedicCoreJobNodeRecord).where(
                VedicCoreJobNodeRecord.job_id == job_id,
                VedicCoreJobNodeRecord.node_id == node_id,
            )
        )
        return result.scalar_one_or_none()

    async def _replace_artifacts(
        self,
        db: AsyncSession,
        session_id: str,
        session_dir: Path,
        artifacts: list[Path],
        checkpoints: dict[str, dict[str, Any]],
    ) -> None:
        await db.execute(delete(VedicArtifactRecord).where(VedicArtifactRecord.session_id == session_id))
        for path in artifacts:
            relative = path.relative_to(session_dir).as_posix()
            checkpoint = checkpoints.get(relative, {})
            db.add(
                VedicArtifactRecord(
                    session_id=session_id,
                    path=relative,
                    kind=self._kind(path),
                    media_type=self._media_type(path),
                    storage_backend="local",
                    storage_path=str(path),
                    size_bytes=path.stat().st_size,
                    producer=self._optional_string(checkpoint, "producer"),
                    checkpointed=bool(checkpoint),
                    artifact_sha256=self._optional_string(checkpoint, "artifactSha256"),
                    structured_data_sha256=self._optional_string(
                        checkpoint,
                        "structuredDataSha256",
                    ),
                    created_at=self._mtime(path),
                    updated_at=self._mtime(path),
                )
            )

    async def _replace_exports(
        self,
        db: AsyncSession,
        session_id: str,
        session_dir: Path,
        exports: list[Path],
    ) -> None:
        await db.execute(delete(VedicExportRecord).where(VedicExportRecord.session_id == session_id))
        for path in exports:
            relative = path.relative_to(session_dir).as_posix()
            db.add(
                VedicExportRecord(
                    session_id=session_id,
                    name=path.name,
                    path=relative,
                    media_type=self._media_type(path),
                    storage_backend="local",
                    storage_path=str(path),
                    size_bytes=path.stat().st_size,
                    created_at=self._mtime(path),
                    updated_at=self._mtime(path),
                )
            )

    def _summary_from_record(self, record: VedicSessionRecord) -> AdminSessionSummary:
        progress = AdminSessionProgress(
            total=record.progress_total,
            completed=record.progress_completed,
            running=record.progress_running,
            failed=record.progress_failed,
            percent=record.progress_percent,
        )
        return AdminSessionSummary(
            sessionId=record.session_id,
            status=self._admin_status(record.status),
            stage=record.stage,
            createdAt=self._iso(record.created_at),
            updatedAt=self._iso(record.updated_at),
            subject=self._subject_summary(record.subject_json),
            progress=progress,
            artifactCount=record.artifact_count,
            exportCount=record.export_count,
            hasPdf=record.has_pdf,
            jobId=record.active_job_id,
            activeNode=record.active_node,
            durationSeconds=record.duration_seconds,
            error=record.error,
        )

    def _subject_summary(self, subject: dict[str, Any] | None):
        if not subject:
            return None
        from app.schemas import AdminSubjectSummary

        return AdminSubjectSummary(
            birthDate=self._optional_string(subject, "birthDate"),
            birthTime=self._optional_string(subject, "birthTime"),
            birthPlace=self._optional_string(subject, "birthPlace"),
            timePrecision=self._optional_string(subject, "timePrecision"),
            timeSource=self._optional_string(subject, "timeSource"),
            timezone=self._optional_string(subject, "timezone"),
            gender=self._optional_string(subject, "gender"),
            relationship=self._optional_string(subject, "relationship"),
        )

    def _artifact_summary(self, record: VedicArtifactRecord) -> AdminArtifactSummary:
        return AdminArtifactSummary(
            path=record.path,
            kind=record.kind,
            sizeBytes=record.size_bytes,
            updatedAt=self._iso(record.updated_at),
        )

    def _export_summary(self, record: VedicExportRecord) -> AdminExportSummary:
        return AdminExportSummary(
            name=record.name,
            path=record.path,
            mediaType=record.media_type,
            sizeBytes=record.size_bytes,
            updatedAt=self._iso(record.updated_at),
        )

    def _session_files(self, session_dir: Path) -> list[Path]:
        return sorted(path for path in session_dir.rglob("*") if path.is_file())

    def _checkpoint_metadata(self, session_dir: Path) -> dict[str, dict[str, Any]]:
        checkpoint_dir = session_dir / ".meta" / "artifacts"
        if not checkpoint_dir.exists():
            return {}
        checkpoints: dict[str, dict[str, Any]] = {}
        for path in checkpoint_dir.glob("*.json"):
            payload = self._read_json(path)
            if not payload:
                continue
            artifact_path = self._optional_string(payload, "artifactPath")
            if artifact_path:
                checkpoints[artifact_path] = payload
        return checkpoints

    def _subject_json(self, session_dir: Path) -> dict[str, Any] | None:
        payload = self._read_json(session_dir / "structured_data.json")
        subject = payload.get("subject") if isinstance(payload, dict) else None
        return subject if isinstance(subject, dict) else None

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _derive_status(self, files: list[Path], metrics: dict[str, Any] | None) -> str:
        names = {path.name for path in files}
        metric_status = self._string(metrics, "status")
        if metric_status in {"queued", "running", "completed", "failed"}:
            return metric_status
        if "appendix.md" in names:
            return "completed"
        if metric_status == "calculator_complete":
            return "draft"
        if "reader_prevalidation.md" in names and "user_context.md" not in names:
            return "validation"
        return "draft"

    def _derive_stage(self, files: list[Path], metrics: dict[str, Any] | None, status: str) -> str:
        names = {path.name for path in files}
        if status == "failed":
            return "error"
        if "appendix.md" in names:
            return "core_complete"
        if "user_context.md" in names or "reader_prevalidation.md" in names:
            return "reader_validation"
        if "structured_data.md" in names:
            return "reader_ready"
        return self._string(metrics, "stage") or "draft"

    def _progress(self, metrics: dict[str, Any] | None) -> AdminSessionProgress:
        nodes = metrics.get("nodes") if isinstance(metrics, dict) else None
        if isinstance(nodes, list) and nodes:
            total = len(nodes)
            completed = sum(
                1
                for node in nodes
                if isinstance(node, dict) and str(node.get("status")) in {"completed", "skipped"}
            )
            running = sum(
                1 for node in nodes if isinstance(node, dict) and str(node.get("status")) == "running"
            )
            failed = sum(
                1 for node in nodes if isinstance(node, dict) and str(node.get("status")) == "failed"
            )
            return AdminSessionProgress(
                total=total,
                completed=completed,
                running=running,
                failed=failed,
                percent=int(round((completed / total) * 100)) if total else 0,
            )
        return AdminSessionProgress()

    def _active_node(self, metrics: dict[str, Any] | None) -> str | None:
        nodes = metrics.get("nodes") if isinstance(metrics, dict) else None
        if not isinstance(nodes, list):
            return None
        for node in nodes:
            if isinstance(node, dict) and str(node.get("status")) in {"running", "failed"}:
                return self._optional_string(node, "label") or self._optional_string(node, "id")
        return None

    def _duration(self, metrics: dict[str, Any] | None) -> float | None:
        value = metrics.get("durationSeconds") if isinstance(metrics, dict) else None
        return float(value) if isinstance(value, (int, float)) else None

    def _error(self, metrics: dict[str, Any] | None) -> str | None:
        nodes = metrics.get("nodes") if isinstance(metrics, dict) else None
        if not isinstance(nodes, list):
            return None
        for node in nodes:
            if isinstance(node, dict):
                error = self._optional_string(node, "error")
                if error:
                    return error
        return None

    def _created_at(self, files: list[Path], session_dir: Path) -> datetime:
        if not files:
            return self._mtime(session_dir)
        return self._mtime(min(files, key=lambda path: path.stat().st_mtime))

    def _updated_at(self, files: list[Path], session_dir: Path) -> datetime:
        if not files:
            return self._mtime(session_dir)
        return self._mtime(max(files, key=lambda path: path.stat().st_mtime))

    def _kind(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".md":
            return "markdown"
        if suffix == ".json":
            return "json"
        if suffix == ".txt":
            return "text"
        if suffix == ".html":
            return "html"
        if suffix == ".pdf":
            return "pdf"
        return "other"

    def _media_type(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return "application/pdf"
        if suffix == ".html":
            return "text/html"
        if suffix == ".json":
            return "application/json"
        if suffix == ".md":
            return "text/markdown"
        if suffix == ".txt":
            return "text/plain"
        return "application/octet-stream"

    def _admin_status(self, status: str) -> AdminSessionStatus:
        if status in {"draft", "validation", "queued", "running", "completed", "failed", "stalled"}:
            return status  # type: ignore[return-value]
        return "draft"

    def _mtime(self, path: Path) -> datetime:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)

    def _parse_dt(self, value: str | None) -> datetime | None:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None

    def _iso(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()

    def _string(self, payload: dict[str, Any] | None, key: str) -> str | None:
        value = payload.get(key) if isinstance(payload, dict) else None
        return value if isinstance(value, str) and value else None

    def _optional_string(self, payload: dict[str, Any], key: str) -> str | None:
        value = payload.get(key)
        return str(value) if value is not None and str(value) else None
