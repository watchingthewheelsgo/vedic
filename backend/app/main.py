from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.auth import AuthenticatedUser, require_user, resolve_session_user
from app.container import get_container
from app.db.engine import close_db, database_diagnostic_context, init_db
from app.schemas import (
    AdminSessionDetailResponse,
    AdminSessionListResponse,
    CoreJobResponse,
    PlaceSearchResponse,
    SkillBirthInput,
    SkillFeedbackInput,
    SkillRunInput,
    SkillSessionResponse,
    SynastryBirthInput,
)
from app.settings import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    await init_db(settings)
    container = get_container()
    await container.metadata_store.backfill_all_sessions()
    try:
        yield
    finally:
        await close_db()


app = FastAPI(title="Vedic Skills Runtime API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, object]:
    container = get_container()
    settings = container.settings
    return {
        "ok": True,
        "service": "vedic-skills-runtime",
        "backend": "python-fastapi",
        "calculationMode": "real_vedic",
        "calculatorRoot": str(settings.calculator_root),
        "skillsRoot": str(settings.skills_root),
        "runtimeSitePackages": str(settings.calculator_site_packages()),
        "runtimePreflight": {
            "dependencies": container.runtime_preflight.dependencies,
            "ephemerisFiles": container.runtime_preflight.ephemeris_files,
            "geonamesPath": container.runtime_preflight.geonames_path,
        },
        "startupConfig": {
            "envFile": container.startup_config_preflight.env_file,
            "agentMode": container.startup_config_preflight.agent_mode,
            "baseUrl": container.startup_config_preflight.base_url,
            "model": container.startup_config_preflight.model,
        },
        "agent": container.agent_runtime.config_summary(),
        "auth": settings.auth_config_summary(),
        "database": database_diagnostic_context(settings),
    }


@app.get("/api/places", response_model=PlaceSearchResponse)
async def places(
    level: Literal["country", "region", "city"],
    q: str = Query(default=""),
    country: str | None = Query(default=None),
    region: str | None = Query(default=None),
    limit: int = Query(default=30, ge=5, le=80),
) -> PlaceSearchResponse:
    try:
        return get_container().place_service.search(
            level=level,
            query=q,
            country=country,
            region=region,
            limit=limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/sessions", response_model=AdminSessionListResponse)
async def list_admin_sessions(
    current_user: AuthenticatedUser = Depends(require_user),
) -> AdminSessionListResponse:
    try:
        container = get_container()
        owner_user_id = current_user.owner_user_id
        return await container.admin_sessions.list_sessions(
            owner_user_id,
            container.core_job_runtime.list_jobs(owner_user_id=owner_user_id),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/sessions/{session_id}", response_model=AdminSessionDetailResponse)
async def get_admin_session(
    session_id: str,
    current_user: AuthenticatedUser = Depends(require_user),
) -> AdminSessionDetailResponse:
    try:
        container = get_container()
        owner_user_id = current_user.owner_user_id
        return await container.admin_sessions.get_session(
            session_id,
            owner_user_id,
            container.core_job_runtime.list_jobs(owner_user_id=owner_user_id),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/skill-sessions", response_model=SkillSessionResponse)
async def create_skill_session(
    input_data: SkillBirthInput,
    current_user: AuthenticatedUser = Depends(resolve_session_user),
) -> SkillSessionResponse:
    try:
        return await get_container().skill_runtime.create_reader_session(
            input_data,
            owner_user_id=current_user.owner_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/skill-sessions/{session_id}", response_model=SkillSessionResponse)
async def get_skill_session(
    session_id: str,
    current_user: AuthenticatedUser = Depends(resolve_session_user),
) -> SkillSessionResponse:
    try:
        container = get_container()
        await _claim_or_assert_session_access(container, session_id, current_user)
        return container.skill_runtime.load_session(session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/skill-sessions/{session_id}/report.pdf")
async def download_skill_session_report_pdf(
    session_id: str,
    current_user: AuthenticatedUser = Depends(require_user),
) -> FileResponse:
    try:
        container = get_container()
        await _claim_or_assert_session_access(container, session_id, current_user)
        result = container.report_exporter.export_session(session_id)
        await container.metadata_store.sync_session_from_files(
            session_id,
            owner_user_id=current_user.owner_user_id,
        )
        return FileResponse(
            result.pdf_path,
            media_type="application/pdf",
            filename=f"vedic-report-{session_id}.pdf",
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/skill-synastry-subject", response_model=SkillSessionResponse)
async def create_synastry_subject(
    input_data: SynastryBirthInput,
    current_user: AuthenticatedUser = Depends(require_user),
) -> SkillSessionResponse:
    try:
        container = get_container()
        await _claim_or_assert_session_access(container, input_data.session_id, current_user)
        return await container.skill_runtime.create_synastry_subject(
            input_data,
            owner_user_id=current_user.owner_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/skill-runs", response_model=SkillSessionResponse)
async def run_skill(
    input_data: SkillRunInput,
    current_user: AuthenticatedUser = Depends(resolve_session_user),
) -> SkillSessionResponse:
    try:
        container = get_container()
        if input_data.skill != "vedic-reader" and not current_user.is_clerk:
            raise HTTPException(status_code=401, detail="Sign in to continue")
        await _claim_or_assert_session_access(container, input_data.session_id, current_user)
        return await container.skill_runtime.run_skill(
            input_data,
            owner_user_id=current_user.owner_user_id,
        )
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TimeoutError as exc:
        # asyncio.timeout raises a builtin TimeoutError whose str() is empty,
        # which previously surfaced as a 500 with no detail. Report it clearly
        # so the caller knows to retry or reduce the batch context.
        raise HTTPException(
            status_code=504,
            detail=(
                f"{input_data.skill} 运行超时（>{get_settings().agent_timeout_ms} ms）。"
                "请重试；若反复超时，请减少该批次的上下文或调大 AGENT_TIMEOUT_MS。"
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/core-jobs", response_model=CoreJobResponse)
async def start_core_job(
    input_data: SkillRunInput,
    current_user: AuthenticatedUser = Depends(require_user),
) -> CoreJobResponse:
    try:
        container = get_container()
        await _claim_or_assert_session_access(container, input_data.session_id, current_user)
        return await container.core_job_runtime.start(
            input_data,
            owner_user_id=current_user.owner_user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/core-jobs/{job_id}", response_model=CoreJobResponse)
async def get_core_job(
    job_id: str,
    current_user: AuthenticatedUser = Depends(require_user),
) -> CoreJobResponse:
    try:
        return await get_container().core_job_runtime.get(
            job_id,
            owner_user_id=current_user.owner_user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/skill-feedback", response_model=SkillSessionResponse)
async def record_skill_feedback(
    input_data: SkillFeedbackInput,
    current_user: AuthenticatedUser = Depends(require_user),
) -> SkillSessionResponse:
    try:
        container = get_container()
        await _claim_or_assert_session_access(container, input_data.session_id, current_user)
        return await container.skill_runtime.record_reader_feedback(
            input_data.session_id,
            input_data.feedback_markdown,
            owner_user_id=current_user.owner_user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def _claim_or_assert_session_access(
    container,
    session_id: str,
    current_user: AuthenticatedUser,
) -> None:
    if current_user.is_clerk and current_user.anonymous_user_id:
        try:
            await container.metadata_store.claim_session_owner(
                session_id,
                from_owner_user_id=current_user.anonymous_user_id,
                to_owner_user_id=current_user.user_id,
            )
            return
        except PermissionError:
            pass
    await container.metadata_store.assert_session_access(session_id, current_user.owner_user_id)


def start() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    start()
