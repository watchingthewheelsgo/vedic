from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from app.schemas import SkillRunInput, SkillSessionResponse
from app.services.core_job_runtime import CoreJobRuntime


class FakeWorkspace:
    def __init__(self, root: Path) -> None:
        self.root = root

    def require_session_dir(self, session_id: str) -> Path:
        path = self.session_dir(session_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def session_dir(self, session_id: str) -> Path:
        return self.root / session_id

    def write_artifact(self, session_id: str, path: str, content: str) -> None:
        target = self.require_session_dir(session_id) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def mark_artifact_checkpoint(self, session_id: str, path: str, *, producer: str) -> None:
        target = self.require_session_dir(session_id) / path
        metadata_path = self._metadata_path(session_id, path)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            json.dumps(
                {
                    "sessionId": session_id,
                    "artifactPath": path,
                    "producer": producer,
                    "artifactSha256": self._file_hash(target),
                }
            ),
            encoding="utf-8",
        )

    def artifact_checkpoint_valid(
        self,
        session_id: str,
        path: str,
        *,
        producer: str | None = None,
    ) -> bool:
        target = self.require_session_dir(session_id) / path
        metadata_path = self._metadata_path(session_id, path)
        if not target.exists() or not metadata_path.exists():
            return False
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        return (
            payload.get("sessionId") == session_id
            and payload.get("artifactPath") == path
            and (producer is None or payload.get("producer") == producer)
            and payload.get("artifactSha256") == self._file_hash(target)
        )

    def _metadata_path(self, session_id: str, path: str) -> Path:
        digest = hashlib.sha256(path.encode("utf-8")).hexdigest()
        return self.require_session_dir(session_id) / ".meta" / "artifacts" / f"{digest}.json"

    def _file_hash(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def read_artifacts(self, session_id: str) -> list[object]:
        self.require_session_dir(session_id)
        return []

    def read_session_locale(self, session_id: str) -> str:
        self.require_session_dir(session_id)
        return "en"


class FakeSkillRuntime:
    def __init__(self, workspace: FakeWorkspace, batches: list[dict[str, Any]]) -> None:
        self.workspace = workspace
        self.batches = batches
        self.calls: list[tuple[str, bool]] = []

    def core_batches(self, user_message: str, locale: str = "en") -> list[dict[str, Any]]:
        return self.batches

    def core_batch_files(self, batch: dict[str, Any]) -> list[str]:
        return [str(path) for path in batch["files"]]

    def core_batch_resume_valid(self, session_id: str, batch: dict[str, Any]) -> bool:
        return all(
            self.workspace.artifact_checkpoint_valid(
                session_id,
                path,
                producer=f"vedic-core:{batch['id']}",
            )
            for path in self.core_batch_files(batch)
        )

    def core_progress_response(
        self,
        session_id: str,
        chat_message: str,
        *,
        stage: str = "core_in_progress",
        active_artifact: str | None = None,
    ) -> SkillSessionResponse:
        return SkillSessionResponse(
            session_id=session_id,
            stage=stage,
            chat_message=chat_message,
            artifacts=[],
            active_artifact=active_artifact,
        )

    async def run_core_batch(
        self,
        input_data: SkillRunInput,
        batch: dict[str, Any],
        *,
        batches: list[dict[str, Any]] | None = None,
        force: bool = False,
        owner_user_id: str | None = None,
    ) -> SkillSessionResponse:
        self.calls.append((str(batch["id"]), force))
        for path in self.core_batch_files(batch):
            self.workspace.write_artifact(input_data.session_id, path, f"# {batch['id']}\n")
            self.workspace.mark_artifact_checkpoint(
                input_data.session_id,
                path,
                producer=f"vedic-core:{batch['id']}",
            )
        return self.core_progress_response(input_data.session_id, "running")


def batch(
    batch_id: str,
    file_name: str,
    dependencies: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": batch_id,
        "label": batch_id,
        "files": [file_name],
        "dependencies": dependencies or [],
        "prompt": batch_id,
    }


def wait_for_job(runtime: CoreJobRuntime, job_id: str):
    async def _wait():
        for _ in range(100):
            response = await runtime.get(job_id)
            if response.status in {"completed", "failed"}:
                return response
            await asyncio.sleep(0.01)
        raise AssertionError("job did not finish")

    return _wait()


def test_resume_skips_completed_nodes_and_reruns_failed_artifacts(tmp_path: Path) -> None:
    async def run() -> None:
        session_id = "resume-session"
        workspace = FakeWorkspace(tmp_path)
        runtime_dir = workspace.require_session_dir(session_id)
        workspace.write_artifact(session_id, "claim_graph.json", '{"claims":[]}\n')
        workspace.mark_artifact_checkpoint(
            session_id, "claim_graph.json", producer="vedic-core:vedicdust_judgement"
        )
        workspace.write_artifact(session_id, "consultation_dossier.json", '{"sections":[]}\n')
        (runtime_dir / "run_metrics.json").write_text(
            json.dumps(
                {
                    "nodes": [
                        {
                            "id": "vedicdust_judgement",
                            "status": "completed",
                            "files": ["claim_graph.json"],
                        },
                        {
                            "id": "vedicdust_consultation",
                            "status": "failed",
                            "files": ["consultation_dossier.json"],
                            "error": "API Error: Connection closed mid-response.",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

        skill_runtime = FakeSkillRuntime(
            workspace,
            [
                batch("vedicdust_judgement", "claim_graph.json"),
                batch(
                    "vedicdust_consultation",
                    "consultation_dossier.json",
                    ["vedicdust_judgement"],
                ),
            ],
        )
        runtime = CoreJobRuntime(skill_runtime)  # type: ignore[arg-type]
        started = await runtime.start(
            SkillRunInput(sessionId=session_id, skill="vedic-core", userMessage="")
        )
        finished = await wait_for_job(runtime, started.job_id)

        assert finished.status == "completed"
        assert skill_runtime.calls == [("vedicdust_consultation", True)]
        nodes = {node.id: node for node in finished.nodes}
        assert nodes["vedicdust_judgement"].status == "skipped"
        assert nodes["vedicdust_consultation"].status == "completed"
        assert (runtime_dir / "consultation_dossier.json").read_text(
            encoding="utf-8"
        ) == "# vedicdust_consultation\n"

    asyncio.run(run())


def test_resume_reruns_completed_file_without_session_checkpoint(tmp_path: Path) -> None:
    async def run() -> None:
        session_id = "untrusted-session"
        workspace = FakeWorkspace(tmp_path)
        runtime_dir = workspace.require_session_dir(session_id)
        workspace.write_artifact(session_id, "claim_graph.json", '{"claims":[]}\n')
        (runtime_dir / "run_metrics.json").write_text(
            json.dumps(
                {
                    "nodes": [
                        {
                            "id": "vedicdust_judgement",
                            "status": "completed",
                            "files": ["claim_graph.json"],
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

        skill_runtime = FakeSkillRuntime(
            workspace, [batch("vedicdust_judgement", "claim_graph.json")]
        )
        runtime = CoreJobRuntime(skill_runtime)  # type: ignore[arg-type]
        started = await runtime.start(
            SkillRunInput(sessionId=session_id, skill="vedic-core", userMessage="")
        )
        finished = await wait_for_job(runtime, started.job_id)

        assert finished.status == "completed"
        assert skill_runtime.calls == [("vedicdust_judgement", True)]
        nodes = {node.id: node for node in finished.nodes}
        assert nodes["vedicdust_judgement"].status == "completed"
        assert (runtime_dir / "claim_graph.json").read_text(
            encoding="utf-8"
        ) == "# vedicdust_judgement\n"

    asyncio.run(run())


def test_failed_parallel_wave_waits_for_siblings_before_checkpoint(tmp_path: Path) -> None:
    class ParallelFakeSkillRuntime(FakeSkillRuntime):
        async def run_core_batch(
            self,
            input_data: SkillRunInput,
            batch: dict[str, Any],
            *,
            batches: list[dict[str, Any]] | None = None,
            force: bool = False,
            owner_user_id: str | None = None,
        ) -> SkillSessionResponse:
            self.calls.append((str(batch["id"]), force))
            if batch["id"] == "fast_fail":
                await asyncio.sleep(0.01)
                raise RuntimeError("API Error: Connection closed mid-response.")
            await asyncio.sleep(0.05)
            path = str(batch["files"][0])
            self.workspace.write_artifact(input_data.session_id, path, "# slow ok\n")
            self.workspace.mark_artifact_checkpoint(
                input_data.session_id,
                path,
                producer=f"vedic-core:{batch['id']}",
            )
            return self.core_progress_response(input_data.session_id, "running")

    async def run() -> None:
        session_id = "parallel-session"
        workspace = FakeWorkspace(tmp_path)
        workspace.require_session_dir(session_id)
        skill_runtime = ParallelFakeSkillRuntime(
            workspace,
            [
                batch("slow_ok", "slow_ok.md"),
                batch("fast_fail", "fast_fail.md"),
            ],
        )
        runtime = CoreJobRuntime(skill_runtime)  # type: ignore[arg-type]
        started = await runtime.start(
            SkillRunInput(sessionId=session_id, skill="vedic-core", userMessage="")
        )
        finished = await wait_for_job(runtime, started.job_id)

        assert finished.status == "failed"
        assert finished.message == CoreJobRuntime.USER_INTERRUPTED_MESSAGE
        assert "fast_fail" not in finished.message
        assert "API Error" not in finished.message
        nodes = {node.id: node for node in finished.nodes}
        assert nodes["slow_ok"].status == "completed"
        assert nodes["fast_fail"].status == "failed"
        metrics = json.loads(
            (workspace.session_dir(session_id) / "run_metrics.json").read_text(encoding="utf-8")
        )
        metric_nodes = {node["id"]: node for node in metrics["nodes"]}
        assert metric_nodes["slow_ok"]["status"] == "completed"
        assert metric_nodes["fast_fail"]["status"] == "failed"

    asyncio.run(run())
