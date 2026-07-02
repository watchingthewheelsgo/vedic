from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


BirthTimePrecision = Literal["exact", "approximate", "part_of_day", "unknown"]
SkillName = Literal[
    "vedic-reader",
    "vedic-core",
    "vedic-career",
    "vedic-love",
    "vedic-rectifier",
    "vedic-synastry",
]


class BirthInput(ApiModel):
    birth_date: str = Field(alias="birthDate", min_length=8, max_length=20)
    birth_time: str = Field(default="", alias="birthTime", max_length=20)
    birth_place: str = Field(alias="birthPlace", min_length=2, max_length=160)
    birth_time_precision: BirthTimePrecision = Field(alias="birthTimePrecision")
    gender: str = Field(default="[待填]", max_length=80)
    relationship: str = Field(default="[待填]", max_length=120)
    time_source: str = Field(default="未追问", alias="timeSource", max_length=120)


class SkillBirthInput(BirthInput):
    pass


class SynastryBirthInput(ApiModel):
    session_id: str = Field(alias="sessionId", min_length=1)
    label: str = Field(default="B", max_length=80)
    relationship_type: str = Field(default="", alias="relationshipType", max_length=120)
    current_stage: str = Field(default="", alias="currentStage", max_length=160)
    question: str = Field(default="", max_length=1000)
    birth: BirthInput


class PlaceOption(ApiModel):
    id: str
    label: str
    value: str
    meta: str | None = None
    country: str | None = None
    region: str | None = None
    birth_place: str | None = Field(default=None, alias="birthPlace")


class PlaceSearchResponse(ApiModel):
    options: list[PlaceOption]


class SkillArtifact(ApiModel):
    path: str
    title: str
    content: str
    kind: Literal["markdown", "text", "json"] = "markdown"
    updated_at: str = Field(alias="updatedAt")


class SkillSessionResponse(ApiModel):
    session_id: str = Field(alias="sessionId")
    stage: Literal[
        "reader_ready",
        "reader_validation",
        "core_in_progress",
        "core_complete",
        "career_complete",
        "love_complete",
        "rectifier_complete",
        "synastry_ready",
        "synastry_complete",
        "qa_complete",
        "error",
    ]
    chat_message: str = Field(alias="chatMessage")
    artifacts: list[SkillArtifact]
    active_artifact: str | None = Field(default=None, alias="activeArtifact")
    access_token: str | None = Field(default=None, alias="accessToken")


class SkillRunInput(ApiModel):
    session_id: str = Field(alias="sessionId", min_length=1)
    skill: SkillName
    user_message: str = Field(default="", alias="userMessage", max_length=4000)


CoreJobStatus = Literal["queued", "running", "completed", "failed"]
CoreJobNodeStatus = Literal["pending", "running", "completed", "skipped", "failed"]


class CoreJobNode(ApiModel):
    id: str
    label: str
    files: list[str]
    dependencies: list[str] = Field(default_factory=list)
    wave: int
    status: CoreJobNodeStatus
    started_at: str | None = Field(default=None, alias="startedAt")
    finished_at: str | None = Field(default=None, alias="finishedAt")
    duration_seconds: float | None = Field(default=None, alias="durationSeconds")
    error: str | None = None


class CoreJobProgress(ApiModel):
    total: int
    completed: int
    running: int
    failed: int
    percent: int


class CoreJobWave(ApiModel):
    wave: int
    total: int
    completed: int
    running: int
    failed: int
    duration_seconds: float | None = Field(default=None, alias="durationSeconds")


class CoreJobResponse(ApiModel):
    job_id: str = Field(alias="jobId")
    session_id: str = Field(alias="sessionId")
    status: CoreJobStatus
    message: str
    started_at: str | None = Field(default=None, alias="startedAt")
    finished_at: str | None = Field(default=None, alias="finishedAt")
    duration_seconds: float | None = Field(default=None, alias="durationSeconds")
    progress: CoreJobProgress
    waves: list[CoreJobWave] = Field(default_factory=list)
    nodes: list[CoreJobNode]
    session: SkillSessionResponse | None = None


class SkillFeedbackInput(ApiModel):
    session_id: str = Field(alias="sessionId", min_length=1)
    feedback_markdown: str = Field(alias="feedbackMarkdown", min_length=1, max_length=8000)


class PlanetFact(ApiModel):
    sign: str | None = None
    house: int | None = None
    degree: float | None = None
    nakshatra: str | None = None
    nakshatra_lord: str | None = None
    retrograde: bool | None = None


class StrengthFact(ApiModel):
    planet: str
    rupas: float
    strength_pct: float = Field(alias="strengthPct")


class LagnaFact(ApiModel):
    sign: str | None = None
    degree: float | None = None
    nakshatra: str | None = None
    nakshatra_lord: str | None = None


class CurrentDasha(ApiModel):
    mahadasha: str | None = None
    mahadasha_start: str | None = None
    mahadasha_end: str | None = None
    antardasha: str | None = None
    antardasha_start: str | None = None
    antardasha_end: str | None = None


class Karakas(ApiModel):
    ak: str | None = None
    amk: str | None = None
    dk_7k: str | None = None
    dk_8k: str | None = None


class ChartFacts(ApiModel):
    lagna: LagnaFact
    moon: PlanetFact
    sun: PlanetFact
    current_dasha: CurrentDasha = Field(alias="currentDasha")
    sav_total: int = Field(alias="savTotal")
    strongest_planet: StrengthFact | None = Field(default=None, alias="strongestPlanet")
    weakest_planet: StrengthFact | None = Field(default=None, alias="weakestPlanet")
    karakas: Karakas
    planets: dict[str, PlanetFact]


class CalculationSnapshot(ApiModel):
    snapshot_id: str = Field(alias="snapshotId")
    engine: Literal["real_vedic"]
    calculation_version: str = Field(alias="calculationVersion")
    ayanamsa: str
    house_system: str = Field(alias="houseSystem")
    ephemeris_version: str = Field(alias="ephemerisVersion")
    timezone_source: str = Field(alias="timezoneSource")
    geo_source: str = Field(alias="geoSource")
    input_precision: BirthTimePrecision = Field(alias="inputPrecision")
    validation_status: Literal["passed", "degraded", "limited"] = Field(alias="validationStatus")
    structured_data: str = Field(alias="structuredData")
    structured_data_json: str = Field(alias="structuredDataJson")
    facts: ChartFacts
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(), alias="generatedAt"
    )
