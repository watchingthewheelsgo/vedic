from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from typing import Literal

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.auth import AuthenticatedUser, require_user, resolve_session_user
from app.container import get_container
from app.db.engine import close_db, database_diagnostic_context, init_db
from app.schemas import (
    AccountProfileResponse,
    AdminSessionDetailResponse,
    AdminSessionListResponse,
    BillingAccountResponse,
    BillingCheckoutInput,
    BillingCheckoutResponse,
    BillingPortalResponse,
    BaziSessionInput,
    CoreJobResponse,
    CreemWebhookResponse,
    PlaceSearchResponse,
    SkillBirthInput,
    SkillFeedbackInput,
    SkillRunInput,
    SkillSessionResponse,
    SynastryBirthInput,
)
from app.settings import get_settings


logger = logging.getLogger(__name__)


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
        "billing": settings.billing_config_summary(),
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
        account_user = await _sync_account_user(container, current_user)
        _require_admin(account_user)
        return await container.admin_sessions.list_sessions(
            None,
            container.core_job_runtime.list_jobs(),
        )
    except HTTPException:
        raise
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
        account_user = await _sync_account_user(container, current_user)
        _require_admin(account_user)
        return await container.admin_sessions.get_session(
            session_id,
            None,
            container.core_job_runtime.list_jobs(),
        )
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/me", response_model=AccountProfileResponse)
async def get_account_profile(
    current_user: AuthenticatedUser = Depends(require_user),
) -> AccountProfileResponse:
    return await get_container().user_store.profile_for(current_user)


@app.get("/api/me/sessions", response_model=AdminSessionListResponse)
async def list_my_sessions(
    current_user: AuthenticatedUser = Depends(require_user),
) -> AdminSessionListResponse:
    try:
        container = get_container()
        account_user = await _sync_account_user(container, current_user)
        owner_user_id = account_user.owner_user_id
        return await container.admin_sessions.list_sessions(
            owner_user_id,
            container.core_job_runtime.list_jobs(owner_user_id=owner_user_id),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/billing/account", response_model=BillingAccountResponse)
async def get_billing_account(
    current_user: AuthenticatedUser = Depends(require_user),
) -> BillingAccountResponse:
    try:
        container = get_container()
        account_user = await _sync_account_user(container, current_user)
        return await container.billing.account_for_user(account_user)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/billing/checkout", response_model=BillingCheckoutResponse)
async def create_billing_checkout(
    input_data: BillingCheckoutInput,
    current_user: AuthenticatedUser = Depends(require_user),
) -> BillingCheckoutResponse:
    try:
        container = get_container()
        account_user = await _sync_account_user(container, current_user)
        return await container.billing.create_checkout(account_user, input_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/billing/portal", response_model=BillingPortalResponse)
async def create_billing_portal(
    current_user: AuthenticatedUser = Depends(require_user),
) -> BillingPortalResponse:
    try:
        container = get_container()
        account_user = await _sync_account_user(container, current_user)
        return await container.billing.create_portal(account_user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/webhooks/creem", response_model=CreemWebhookResponse)
async def receive_creem_webhook(
    request: Request,
    creem_signature: str | None = Header(default=None, alias="creem-signature"),
) -> CreemWebhookResponse:
    try:
        return await get_container().billing.handle_webhook(
            await request.body(),
            creem_signature,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/skill-sessions", response_model=SkillSessionResponse)
async def create_skill_session(
    input_data: SkillBirthInput,
    current_user: AuthenticatedUser = Depends(resolve_session_user),
) -> SkillSessionResponse:
    try:
        container = get_container()
        account_user = await _sync_account_user(container, current_user)
        return await container.skill_runtime.create_reader_session(
            input_data,
            owner_user_id=account_user.owner_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/bazi-sessions", response_model=SkillSessionResponse)
async def create_bazi_session(
    input_data: BaziSessionInput,
    current_user: AuthenticatedUser = Depends(resolve_session_user),
) -> SkillSessionResponse:
    try:
        container = get_container()
        account_user = await _sync_account_user(container, current_user)
        return await container.skill_runtime.create_bazi_session(
            input_data,
            owner_user_id=account_user.owner_user_id,
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
        account_user = await _sync_account_user(container, current_user)
        await _claim_or_assert_session_access(container, session_id, account_user)
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
        account_user = await _sync_account_user(container, current_user)
        await _claim_or_assert_session_access(container, session_id, account_user)
        await container.billing.assert_paid_access(account_user)
        result = container.report_exporter.export_session(session_id)
        await container.metadata_store.sync_session_from_files(
            session_id,
            owner_user_id=account_user.owner_user_id,
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
        account_user = await _sync_account_user(container, current_user)
        await _claim_or_assert_session_access(container, input_data.session_id, account_user)
        await container.billing.assert_paid_access(account_user)
        return await container.skill_runtime.create_synastry_subject(
            input_data,
            owner_user_id=account_user.owner_user_id,
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
        account_user = await _sync_account_user(container, current_user)
        if input_data.skill != "vedic-reader" and not account_user.is_clerk:
            raise HTTPException(
                status_code=401,
                detail=account_user.auth_error_detail or "Sign in to continue",
            )
        if input_data.skill != "vedic-reader":
            await container.billing.assert_paid_access(account_user)
        await _claim_or_assert_session_access(container, input_data.session_id, account_user)
        return await container.skill_runtime.run_skill(
            input_data,
            owner_user_id=account_user.owner_user_id,
        )
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        detail = str(exc)
        owner_user_id = account_user.owner_user_id if "account_user" in locals() else None
        logger.warning(
            "skill-runs rejected session_id=%s skill=%s owner_user_id=%s detail=%s",
            input_data.session_id,
            input_data.skill,
            owner_user_id,
            detail,
        )
        if "container" in locals():
            await _record_skill_run_failure(
                container,
                input_data,
                detail=detail,
                owner_user_id=owner_user_id,
            )
        raise HTTPException(status_code=400, detail=detail) from exc
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
        account_user = await _sync_account_user(container, current_user)
        await _claim_or_assert_session_access(container, input_data.session_id, account_user)
        await container.billing.assert_paid_access(account_user)
        return await container.core_job_runtime.start(
            input_data,
            owner_user_id=account_user.owner_user_id,
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
        container = get_container()
        account_user = await _sync_account_user(container, current_user)
        return await container.core_job_runtime.get(
            job_id,
            owner_user_id=account_user.owner_user_id,
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
        account_user = await _sync_account_user(container, current_user)
        await _claim_or_assert_session_access(container, input_data.session_id, account_user)
        return await container.skill_runtime.record_reader_feedback(
            input_data.session_id,
            input_data.feedback_markdown,
            owner_user_id=account_user.owner_user_id,
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


async def _sync_account_user(container, current_user: AuthenticatedUser) -> AuthenticatedUser:
    return await container.user_store.upsert_from_auth_user(current_user)


async def _record_skill_run_failure(
    container,
    input_data: SkillRunInput,
    *,
    detail: str,
    owner_user_id: str | None,
) -> None:
    try:
        await container.metadata_store.sync_session_from_files(
            input_data.session_id,
            stage="error",
            status="failed",
            owner_user_id=owner_user_id,
            error=detail,
        )
    except Exception:
        logger.exception(
            "failed to record skill-run failure session_id=%s skill=%s",
            input_data.session_id,
            input_data.skill,
        )


def _require_admin(current_user: AuthenticatedUser) -> None:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")


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
