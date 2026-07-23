from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.db.engine import close_db, database_diagnostic_context, init_db, normalize_database_url
from app.schemas import SkillSessionResponse
from app.services.admin_sessions import AdminSessionsService
from app.services.metadata_store import MetadataStore
from app.services.skill_workspace import SkillWorkspace
from app.settings import Settings


class FakeSkillRuntime:
    def __init__(self, workspace: SkillWorkspace) -> None:
        self.workspace = workspace

    def load_session(self, session_id: str) -> SkillSessionResponse:
        return SkillSessionResponse(
            session_id=session_id,
            stage="core_complete",
            chat_message="loaded",
            artifacts=self.workspace.read_artifacts(session_id),
            active_artifact="run_metrics.json",
        )


def test_admin_sessions_lists_database_metadata_and_local_paths(tmp_path: Path) -> None:
    async def run() -> None:
        await init_db(
            SimpleNamespace(
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'vedic.db'}",
                database_echo=False,
            )
        )
        try:
            workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
            session_id = workspace.create_session()
            workspace.write_artifact(
                session_id,
                "birth_chart_facts.json",
                json.dumps(
                    {
                        "subject": {
                            "birthDate": "2024-08-02",
                            "birthTime": "20:57",
                            "birthPlace": "Pudong, Shanghai, China",
                            "timePrecision": "精确到分钟",
                            "timeSource": "出生证/医院记录",
                            "timezone": "Asia/Shanghai",
                            "gender": "男",
                            "relationship": "单身",
                        }
                    }
                ),
            )
            workspace.write_artifact(session_id, "structured_data.md", "# data\n")
            workspace.write_artifact(session_id, "appendix.md", "# appendix\n")
            workspace.write_artifact(
                session_id,
                "run_metrics.json",
                json.dumps(
                    {
                        "jobId": "job-1",
                        "status": "completed",
                        "durationSeconds": 12.5,
                        "nodes": [
                            {"id": "p1", "label": "P1", "status": "completed"},
                            {"id": "p2", "label": "P2", "status": "skipped"},
                        ],
                    }
                ),
            )
            workspace.write_artifact(session_id, "exports/report.pdf", "pdf")

            metadata_store = MetadataStore(workspace)
            await metadata_store.sync_session_from_files(session_id)
            service = AdminSessionsService(
                workspace,
                FakeSkillRuntime(workspace),  # type: ignore[arg-type]
                metadata_store,
            )
            listing = await service.list_sessions()
            detail = await service.get_session(session_id)

            assert listing.total == 1
            assert listing.completed == 1
            assert listing.sessions[0].session_id == session_id
            assert listing.sessions[0].status == "completed"
            assert listing.sessions[0].progress.percent == 100
            assert listing.sessions[0].has_pdf is True
            assert listing.sessions[0].subject
            assert listing.sessions[0].subject.birth_place == "Pudong, Shanghai, China"
            assert detail.summary.job_id == "job-1"
            assert [item.path for item in detail.exports] == ["exports/report.pdf"]
            assert "run_metrics.json" in [item.path for item in detail.artifacts]
        finally:
            await close_db()

    asyncio.run(run())


def test_plain_postgres_url_uses_asyncpg_and_ssl() -> None:
    url = normalize_database_url(
        "postgresql://postgres:dummy-password@db.example.supabase.co:5432/postgres"
    )

    assert url.drivername == "postgresql+asyncpg"
    assert url.host == "db.example.supabase.co"
    assert url.query["ssl"] == "require"


def test_supabase_project_ref_and_password_build_direct_database_url() -> None:
    settings = Settings(
        _env_file=None,
        SUPABASE_PROJECT_REF="pkjtffyirhjpfpbyrfmu",
        SUPABASE_DB_PASSWORD="dummy password",
    )

    context = database_diagnostic_context(settings)

    assert settings.resolved_database_url() == (
        "postgresql://postgres:dummy%20password@"
        "db.pkjtffyirhjpfpbyrfmu.supabase.co:5432/postgres?sslmode=require"
    )
    assert context["source"] == "supabase"
    assert context["driver"] == "postgresql+asyncpg"
    assert context["host"] == "db.pkjtffyirhjpfpbyrfmu.supabase.co"
    assert context["supabaseDirect"] is True


def test_supabase_settings_take_over_example_sqlite_database_url() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="sqlite+aiosqlite:///./backend/data/vedic.db",
        SUPABASE_PROJECT_REF="pkjtffyirhjpfpbyrfmu",
        SUPABASE_DB_PASSWORD="dummy-password",
    )

    assert settings.database_source() == "supabase"
    assert normalize_database_url(settings.resolved_database_url()).host == (
        "db.pkjtffyirhjpfpbyrfmu.supabase.co"
    )


def test_metadata_store_filters_sessions_by_owner(tmp_path: Path) -> None:
    async def run() -> None:
        await init_db(
            SimpleNamespace(
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'vedic.db'}",
                database_echo=False,
            )
        )
        try:
            workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
            session_a = workspace.create_session()
            workspace.write_artifact(session_a, "structured_data.md", "# user a\n")
            session_b = workspace.create_session()
            workspace.write_artifact(session_b, "structured_data.md", "# user b\n")

            metadata_store = MetadataStore(workspace)
            await metadata_store.sync_session_from_files(session_a, owner_user_id="user_a")
            await metadata_store.sync_session_from_files(session_b, owner_user_id="user_b")

            user_a_sessions = await metadata_store.list_session_summaries("user_a")
            user_b_sessions = await metadata_store.list_session_summaries("user_b")
            local_sessions = await metadata_store.list_session_summaries()

            assert [item.session_id for item in user_a_sessions] == [session_a]
            assert [item.session_id for item in user_b_sessions] == [session_b]
            assert {item.session_id for item in local_sessions} == {session_a, session_b}
            await metadata_store.assert_session_access(session_a, "user_a")
            with pytest.raises(PermissionError):
                await metadata_store.assert_session_access(session_a, "user_b")
        finally:
            await close_db()

    asyncio.run(run())


def test_metadata_store_claims_anonymous_session_for_clerk_user(tmp_path: Path) -> None:
    async def run() -> None:
        await init_db(
            SimpleNamespace(
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'vedic.db'}",
                database_echo=False,
            )
        )
        try:
            workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
            session_id = workspace.create_session()
            workspace.write_artifact(session_id, "structured_data.md", "# anonymous\n")

            metadata_store = MetadataStore(workspace)
            await metadata_store.sync_session_from_files(
                session_id,
                owner_user_id="anonym_abc12345",
            )

            await metadata_store.claim_session_owner(
                session_id,
                from_owner_user_id="anonym_abc12345",
                to_owner_user_id="user_clerk123",
            )

            assert await metadata_store.list_session_summaries("anonym_abc12345") == []
            claimed = await metadata_store.list_session_summaries("user_clerk123")
            assert [item.session_id for item in claimed] == [session_id]
            with pytest.raises(PermissionError):
                await metadata_store.claim_session_owner(
                    session_id,
                    from_owner_user_id="anonym_other123",
                    to_owner_user_id="user_other123",
                )
        finally:
            await close_db()

    asyncio.run(run())
