from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.container import get_container
from app.schemas import (
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
    get_container()
    yield


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
        "agent": container.agent_runtime.config_summary(),
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


@app.post("/api/skill-sessions", response_model=SkillSessionResponse)
async def create_skill_session(input_data: SkillBirthInput) -> SkillSessionResponse:
    try:
        return await get_container().skill_runtime.create_reader_session(input_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/skill-sessions/{session_id}", response_model=SkillSessionResponse)
async def get_skill_session(session_id: str) -> SkillSessionResponse:
    try:
        return get_container().skill_runtime.load_session(session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/skill-synastry-subject", response_model=SkillSessionResponse)
async def create_synastry_subject(input_data: SynastryBirthInput) -> SkillSessionResponse:
    try:
        return await get_container().skill_runtime.create_synastry_subject(input_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/skill-runs", response_model=SkillSessionResponse)
async def run_skill(input_data: SkillRunInput) -> SkillSessionResponse:
    try:
        return await get_container().skill_runtime.run_skill(input_data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
async def start_core_job(input_data: SkillRunInput) -> CoreJobResponse:
    try:
        return await get_container().core_job_runtime.start(input_data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/core-jobs/{job_id}", response_model=CoreJobResponse)
async def get_core_job(job_id: str) -> CoreJobResponse:
    try:
        return await get_container().core_job_runtime.get(job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/skill-feedback", response_model=SkillSessionResponse)
async def record_skill_feedback(input_data: SkillFeedbackInput) -> SkillSessionResponse:
    try:
        return await get_container().skill_runtime.record_reader_feedback(
            input_data.session_id,
            input_data.feedback_markdown,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
