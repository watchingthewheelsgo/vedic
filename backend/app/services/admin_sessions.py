from __future__ import annotations

from typing import Any

from app.schemas import (
    AdminSessionDetailResponse,
    AdminSessionListResponse,
    AdminSessionProgress,
    AdminSessionSummary,
    CoreJobResponse,
)
from app.services.metadata_store import MetadataStore
from app.services.skill_runtime import SkillRuntime
from app.services.skill_workspace import SkillWorkspace


class AdminSessionsService:
    """Read-only admin projection over database metadata and live jobs."""

    def __init__(
        self,
        workspace: SkillWorkspace,
        skill_runtime: SkillRuntime,
        metadata_store: MetadataStore,
    ) -> None:
        self.workspace = workspace
        self.skill_runtime = skill_runtime
        self.metadata_store = metadata_store

    async def list_sessions(
        self,
        live_jobs: list[CoreJobResponse] | None = None,
    ) -> AdminSessionListResponse:
        live_by_session = self._latest_job_by_session(live_jobs or [])
        summaries = await self.metadata_store.list_session_summaries()
        sessions = [
            self._overlay_live_job(item, live_by_session.get(item.session_id)) for item in summaries
        ]
        sessions.sort(key=lambda item: item.updated_at or item.created_at or "", reverse=True)
        return AdminSessionListResponse(
            sessions=sessions,
            total=len(sessions),
            running=sum(1 for item in sessions if item.status in {"queued", "running", "stalled"}),
            completed=sum(1 for item in sessions if item.status == "completed"),
            failed=sum(1 for item in sessions if item.status == "failed"),
        )

    async def get_session(
        self,
        session_id: str,
        live_jobs: list[CoreJobResponse] | None = None,
    ) -> AdminSessionDetailResponse:
        self.workspace.require_session_dir(session_id)
        live_job = self._latest_job_by_session(live_jobs or []).get(session_id)
        summary = await self.metadata_store.get_session_summary(session_id)
        return AdminSessionDetailResponse(
            summary=self._overlay_live_job(summary, live_job),
            session=self.skill_runtime.load_session(session_id),
            artifacts=await self.metadata_store.list_artifacts(session_id),
            exports=await self.metadata_store.list_exports(session_id),
            runMetrics=self._read_json_artifact(session_id, "run_metrics.json"),
            manifest=self._read_json_artifact(session_id, ".meta/session.json"),
            activeJob=live_job,
        )

    def _overlay_live_job(
        self,
        summary: AdminSessionSummary,
        live_job: CoreJobResponse | None,
    ) -> AdminSessionSummary:
        if live_job is None:
            return summary
        active_node = next(
            (node.label for node in live_job.nodes if node.status == "running"), None
        )
        failed_node = next((node for node in live_job.nodes if node.status == "failed"), None)
        return summary.model_copy(
            update={
                "status": live_job.status,
                "stage": "core_complete" if live_job.status == "completed" else "core_in_progress",
                "progress": AdminSessionProgress(
                    total=live_job.progress.total,
                    completed=live_job.progress.completed,
                    running=live_job.progress.running,
                    failed=live_job.progress.failed,
                    percent=live_job.progress.percent,
                ),
                "job_id": live_job.job_id,
                "active_node": active_node
                or (failed_node.label if failed_node else summary.active_node),
                "duration_seconds": live_job.duration_seconds,
                "error": failed_node.error if failed_node else summary.error,
            }
        )

    def _latest_job_by_session(self, jobs: list[CoreJobResponse]) -> dict[str, CoreJobResponse]:
        latest: dict[str, CoreJobResponse] = {}
        for job in jobs:
            previous = latest.get(job.session_id)
            if previous is None or (job.started_at or "") >= (previous.started_at or ""):
                latest[job.session_id] = job
        return latest

    def _read_json_artifact(self, session_id: str, relative_path: str) -> dict[str, Any] | None:
        path = self.workspace.session_dir(session_id) / relative_path
        if not path.exists():
            return None
        try:
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None
