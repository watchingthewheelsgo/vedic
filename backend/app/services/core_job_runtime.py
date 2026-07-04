from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.schemas import (
    CoreJobNode,
    CoreJobProgress,
    CoreJobResponse,
    CoreJobStatus,
    SkillRunInput,
    SkillSessionResponse,
)
from app.services.skill_runtime import SkillRuntime


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CoreNodeState:
    id: str
    label: str
    files: list[str]
    dependencies: list[str]
    wave: int
    batch: dict[str, object]
    status: str = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    started_perf: float | None = None
    finished_perf: float | None = None
    error: str | None = None


@dataclass
class CoreJobState:
    job_id: str
    session_id: str
    user_message: str
    nodes: list[CoreNodeState]
    batches: list[dict[str, object]]
    status: CoreJobStatus = "queued"
    message: str = "vedic-core 完整报告任务已排队。"
    started_at: str | None = None
    finished_at: str | None = None
    started_perf: float | None = None
    finished_perf: float | None = None
    session: SkillSessionResponse | None = None
    task: asyncio.Task[None] | None = field(default=None, repr=False)


class CoreJobRuntime:
    """In-memory DAG runner for full vedic-core report generation."""

    MAX_CONCURRENCY = 10
    USER_RUNNING_MESSAGE = (
        "Your full report is being generated. Completed sections are saved automatically."
    )
    USER_INTERRUPTED_MESSAGE = "Generation was interrupted. Completed sections are saved; retry will resume from unfinished steps."

    def __init__(self, skill_runtime: SkillRuntime) -> None:
        self.skill_runtime = skill_runtime
        self._jobs: dict[str, CoreJobState] = {}
        self._active_by_session: dict[str, str] = {}
        self._registry_lock = asyncio.Lock()

    async def start(self, input_data: SkillRunInput) -> CoreJobResponse:
        if input_data.skill != "vedic-core":
            raise ValueError("Core jobs only support vedic-core")
        self.skill_runtime.workspace.require_session_dir(input_data.session_id)

        async with self._registry_lock:
            active_job_id = self._active_by_session.get(input_data.session_id)
            if active_job_id:
                active_job = self._jobs.get(active_job_id)
                if active_job and active_job.status in {"queued", "running"}:
                    return self._to_response(active_job)

            job = self._create_job(input_data)
            self._jobs[job.job_id] = job
            self._active_by_session[job.session_id] = job.job_id
            await self._persist_job_metadata(job)
            job.task = asyncio.create_task(self._run_job(job))
            return self._to_response(job)

    async def get(self, job_id: str) -> CoreJobResponse:
        job = self._jobs.get(job_id)
        if job is None:
            raise LookupError(f"Core job not found: {job_id}")
        return self._to_response(job)

    def list_jobs(self) -> list[CoreJobResponse]:
        jobs = sorted(
            self._jobs.values(),
            key=lambda job: job.started_at or "",
            reverse=True,
        )
        return [self._to_response(job) for job in jobs]

    def _create_job(self, input_data: SkillRunInput) -> CoreJobState:
        batches = self.skill_runtime.core_batches(input_data.user_message)
        batch_ids = [str(batch.get("id") or "") for batch in batches]
        duplicate_ids = sorted({node_id for node_id in batch_ids if batch_ids.count(node_id) > 1})
        if duplicate_ids:
            raise RuntimeError(
                f"vedic-core batch graph has duplicate id(s): {', '.join(duplicate_ids)}"
            )

        known_ids = set(batch_ids)
        missing_dependencies = sorted(
            {
                str(dep)
                for batch in batches
                for dep in batch.get("dependencies", [])
                if str(dep) not in known_ids
            }
        )
        if missing_dependencies:
            raise RuntimeError(
                "vedic-core batch graph has missing dependency id(s): "
                + ", ".join(missing_dependencies)
            )

        nodes: list[CoreNodeState] = []
        wave_by_id: dict[str, int] = {}
        for batch in batches:
            node_id = str(batch.get("id") or "")
            if not node_id:
                raise RuntimeError("vedic-core batch is missing an id")
            dependencies = [str(dep) for dep in batch.get("dependencies", [])]
            wave = 1 + max((wave_by_id[dep] for dep in dependencies), default=0)
            wave_by_id[node_id] = wave
            nodes.append(
                CoreNodeState(
                    id=node_id,
                    label=str(batch.get("label") or node_id),
                    dependencies=dependencies,
                    wave=wave,
                    batch=batch,
                    files=self.skill_runtime.core_batch_files(batch),
                )
            )

        self._apply_resume_checkpoints(input_data.session_id, nodes)

        session = self.skill_runtime.core_progress_response(
            input_data.session_id,
            self.USER_RUNNING_MESSAGE,
        )
        return CoreJobState(
            job_id=str(uuid.uuid4()),
            session_id=input_data.session_id,
            user_message=input_data.user_message,
            nodes=nodes,
            batches=batches,
            session=session,
        )

    async def _run_job(self, job: CoreJobState) -> None:
        job.status = "running"
        job.message = self.USER_RUNNING_MESSAGE
        job.started_at = _now()
        job.started_perf = time.perf_counter()
        try:
            pending = {node.id for node in job.nodes if node.status not in {"completed", "skipped"}}
            while pending:
                ready = [
                    node
                    for node in job.nodes
                    if node.id in pending and self._dependencies_complete(job, node)
                ]
                if not ready:
                    blocked = ", ".join(sorted(pending))
                    raise RuntimeError(f"Core job graph is blocked: {blocked}")

                for start in range(0, len(ready), self.MAX_CONCURRENCY):
                    group = ready[start : start + self.MAX_CONCURRENCY]
                    results = await asyncio.gather(
                        *(self._run_node(job, node) for node in group),
                        return_exceptions=True,
                    )
                    for node in group:
                        pending.remove(node.id)
                    failures = [result for result in results if isinstance(result, Exception)]
                    if failures:
                        raise failures[0]

            job.status = "completed"
            job.message = "Your full report is ready."
            job.finished_at = _now()
            job.finished_perf = time.perf_counter()
            await self._write_metrics(job)
            job.session = self.skill_runtime.core_progress_response(
                job.session_id,
                job.message,
                stage="core_complete",
            )
        except Exception as exc:
            job.status = "failed"
            job.message = self.USER_INTERRUPTED_MESSAGE
            job.finished_at = _now()
            job.finished_perf = time.perf_counter()
            await self._write_metrics(job)
            if job.session is None:
                job.session = self.skill_runtime.core_progress_response(
                    job.session_id,
                    job.message,
                    stage="error",
                )
        finally:
            async with self._registry_lock:
                if self._active_by_session.get(job.session_id) == job.job_id:
                    self._active_by_session.pop(job.session_id, None)

    async def _run_node(self, job: CoreJobState, node: CoreNodeState) -> None:
        input_data = SkillRunInput(
            sessionId=job.session_id,
            skill="vedic-core",
            userMessage=job.user_message,
        )

        node.status = "running"
        node.started_at = _now()
        node.started_perf = time.perf_counter()
        job.message = self.USER_RUNNING_MESSAGE
        await self._write_metrics(job)
        try:
            job.session = await self.skill_runtime.run_core_batch(
                input_data,
                node.batch,
                batches=job.batches,
                force=True,
            )
            job.session.chat_message = self.USER_RUNNING_MESSAGE
            node.status = "completed"
            node.finished_at = _now()
            node.finished_perf = time.perf_counter()
            node.error = None
            job.message = self.USER_RUNNING_MESSAGE
            await self._write_metrics(job)
        except Exception as exc:
            node.status = "failed"
            node.error = str(exc) or "Node failed"
            node.finished_at = _now()
            node.finished_perf = time.perf_counter()
            job.message = self.USER_INTERRUPTED_MESSAGE
            await self._write_metrics(job)
            raise

    def _dependencies_complete(self, job: CoreJobState, node: CoreNodeState) -> bool:
        statuses = {item.id: item.status for item in job.nodes}
        return all(statuses.get(dep) in {"completed", "skipped"} for dep in node.dependencies)

    def _to_response(self, job: CoreJobState) -> CoreJobResponse:
        completed = sum(1 for node in job.nodes if node.status in {"completed", "skipped"})
        running = sum(1 for node in job.nodes if node.status == "running")
        failed = sum(1 for node in job.nodes if node.status == "failed")
        total = len(job.nodes)
        percent = int(round((completed / total) * 100)) if total else 0
        return CoreJobResponse(
            jobId=job.job_id,
            sessionId=job.session_id,
            status=job.status,
            message=job.message,
            startedAt=job.started_at,
            finishedAt=job.finished_at,
            durationSeconds=self._duration_seconds(job.started_perf, job.finished_perf),
            progress=CoreJobProgress(
                total=total,
                completed=completed,
                running=running,
                failed=failed,
                percent=percent,
            ),
            waves=self._wave_metrics(job),
            nodes=[
                CoreJobNode(
                    id=node.id,
                    label=node.label,
                    files=node.files,
                    dependencies=node.dependencies,
                    wave=node.wave,
                    status=node.status,
                    startedAt=node.started_at,
                    finishedAt=node.finished_at,
                    durationSeconds=self._duration_seconds(node.started_perf, node.finished_perf),
                    error=node.error,
                )
                for node in job.nodes
            ],
            session=job.session,
        )

    async def _write_metrics(self, job: CoreJobState) -> None:
        """Persist timing data as a session artifact for test and UI review."""

        existing = self._read_existing_metrics(job.session_id)
        payload = {
            "jobId": job.job_id,
            "sessionId": job.session_id,
            "status": job.status,
            "message": job.message,
            "calculator": existing.get("calculator"),
            "startedAt": job.started_at,
            "finishedAt": job.finished_at,
            "durationSeconds": self._duration_seconds(job.started_perf, job.finished_perf),
            "progress": {
                "total": len(job.nodes),
                "completed": sum(
                    1 for node in job.nodes if node.status in {"completed", "skipped"}
                ),
                "failed": sum(1 for node in job.nodes if node.status == "failed"),
            },
            "waves": self._wave_metrics(job),
            "nodes": [
                {
                    "id": node.id,
                    "label": node.label,
                    "wave": node.wave,
                    "files": node.files,
                    "dependencies": node.dependencies,
                    "status": node.status,
                    "startedAt": node.started_at,
                    "finishedAt": node.finished_at,
                    "durationSeconds": self._duration_seconds(
                        node.started_perf, node.finished_perf
                    ),
                    "error": node.error,
                }
                for node in job.nodes
            ],
        }
        self.skill_runtime.workspace.write_artifact(
            job.session_id,
            "run_metrics.json",
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        )
        await self._persist_job_metadata(job)

    async def _persist_job_metadata(self, job: CoreJobState) -> None:
        metadata_store = getattr(self.skill_runtime, "metadata_store", None)
        if metadata_store is None:
            return
        response = self._to_response(job)
        running = [node.label for node in response.nodes if node.status == "running"]
        failed = next((node for node in response.nodes if node.status == "failed"), None)
        await metadata_store.upsert_core_job(response, user_message=job.user_message)
        await metadata_store.sync_session_from_files(
            job.session_id,
            stage="core_complete" if job.status == "completed" else "core_in_progress",
            status=job.status,
            active_job_id=job.job_id,
            active_node=", ".join(running[:3]) if running else failed.label if failed else None,
            error=failed.error if failed else None,
        )

    def _read_existing_metrics(self, session_id: str) -> dict[str, object]:
        path = self.skill_runtime.workspace.session_dir(session_id) / "run_metrics.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _apply_resume_checkpoints(self, session_id: str, nodes: list[CoreNodeState]) -> None:
        """Mark previously completed nodes as skipped for a new retry/resume job.

        A file left behind by a failed Claude response is not enough to count as
        complete when run_metrics.json explicitly says that node failed.
        """

        session_dir = self.skill_runtime.workspace.session_dir(session_id)
        existing = {
            path.relative_to(session_dir).as_posix()
            for path in session_dir.rglob("*")
            if path.is_file()
        }
        metrics = self._read_existing_metrics(session_id)
        metric_nodes = {
            str(item.get("id")): item
            for item in metrics.get("nodes", [])
            if isinstance(item, dict) and item.get("id")
        }
        has_node_metrics = bool(metric_nodes)

        for node in nodes:
            files_exist = set(node.files).issubset(existing)
            resume_valid = self.skill_runtime.core_batch_resume_valid(session_id, node.batch)
            metric = metric_nodes.get(node.id)
            metric_status = str(metric.get("status")) if metric else None
            if (
                files_exist
                and resume_valid
                and (
                    metric_status in {"completed", "skipped"}
                    or (metric is None and not has_node_metrics)
                )
            ):
                node.status = "skipped"
                node.started_at = (
                    str(metric.get("startedAt")) if metric and metric.get("startedAt") else None
                )
                node.finished_at = (
                    str(metric.get("finishedAt")) if metric and metric.get("finishedAt") else _now()
                )
                node.error = None

    def _wave_metrics(self, job: CoreJobState) -> list[dict[str, object]]:
        waves = sorted({node.wave for node in job.nodes})
        metrics: list[dict[str, object]] = []
        for wave in waves:
            nodes = [node for node in job.nodes if node.wave == wave]
            starts = [node.started_perf for node in nodes if node.started_perf is not None]
            finishes = [node.finished_perf for node in nodes if node.finished_perf is not None]
            metrics.append(
                {
                    "wave": wave,
                    "total": len(nodes),
                    "completed": sum(
                        1 for node in nodes if node.status in {"completed", "skipped"}
                    ),
                    "running": sum(1 for node in nodes if node.status == "running"),
                    "failed": sum(1 for node in nodes if node.status == "failed"),
                    "durationSeconds": (
                        round(max(finishes) - min(starts), 3) if starts and finishes else None
                    ),
                }
            )
        return metrics

    def _duration_seconds(self, started: float | None, finished: float | None) -> float | None:
        if started is None:
            return None
        end = finished if finished is not None else time.perf_counter()
        return round(max(0.0, end - started), 3)
