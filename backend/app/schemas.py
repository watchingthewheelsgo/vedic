from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


BirthTimePrecision = Literal["exact", "approximate", "part_of_day", "unknown"]
AppLocale = Literal["zh", "en", "ja"]
SkillName = Literal[
    "vedic-reader",
    "vedic-core",
    "vedic-career",
    "vedic-love",
    "vedic-rectifier",
    "vedic-synastry",
    "bazi-calculator",
    "bazi-classics-core",
]


class BirthInput(ApiModel):
    birth_date: str = Field(alias="birthDate", min_length=8, max_length=20)
    birth_time: str = Field(default="", alias="birthTime", max_length=20)
    birth_place: str = Field(alias="birthPlace", min_length=2, max_length=160)
    birth_time_precision: BirthTimePrecision = Field(alias="birthTimePrecision")
    gender: str = Field(default="[待填]", max_length=80)
    relationship: str = Field(default="[待填]", max_length=120)
    time_source: str = Field(default="未追问", alias="timeSource", max_length=120)
    locale: AppLocale = "en"


class SkillBirthInput(BirthInput):
    pass


BaziCalendarType = Literal["solar", "lunar"]


class BaziSessionInput(BirthInput):
    calendar_type: BaziCalendarType = Field(default="solar", alias="calendarType")
    current_date: str = Field(
        default_factory=lambda: date.today().isoformat(),
        alias="currentDate",
        min_length=8,
        max_length=20,
    )
    audience: str = Field(default="self", max_length=80)
    topic: str = Field(default="[not provided]", max_length=1000)


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


BillingPlanKey = Literal["pro_monthly", "pro_yearly", "single_report"]


class BillingPlanResponse(ApiModel):
    key: BillingPlanKey
    name: str
    billing_period: str = Field(alias="billingPeriod")
    product_id_configured: bool = Field(alias="productIdConfigured")


class BillingSubscriptionResponse(ApiModel):
    plan_key: str = Field(alias="planKey")
    status: str
    is_active: bool = Field(alias="isActive")
    current_period_start: str | None = Field(default=None, alias="currentPeriodStart")
    current_period_end: str | None = Field(default=None, alias="currentPeriodEnd")
    cancel_at_period_end: bool = Field(default=False, alias="cancelAtPeriodEnd")
    creem_customer_id: str | None = Field(default=None, alias="creemCustomerId")
    creem_subscription_id: str | None = Field(default=None, alias="creemSubscriptionId")


class BillingAccountResponse(ApiModel):
    provider: Literal["creem"] = "creem"
    configured: bool
    test_mode: bool = Field(alias="testMode")
    entitlement: Literal["admin", "paid", "free"]
    has_active_entitlement: bool = Field(alias="hasActiveEntitlement")
    can_manage_billing: bool = Field(alias="canManageBilling")
    subscription: BillingSubscriptionResponse | None = None
    plans: list[BillingPlanResponse]


class BillingCheckoutInput(ApiModel):
    plan_key: BillingPlanKey = Field(alias="planKey")
    success_url: str | None = Field(default=None, alias="successUrl", max_length=500)


class BillingCheckoutResponse(ApiModel):
    checkout_url: str = Field(alias="checkoutUrl")
    checkout_id: str | None = Field(default=None, alias="checkoutId")
    request_id: str = Field(alias="requestId")


class BillingPortalResponse(ApiModel):
    portal_url: str = Field(alias="portalUrl")


class CreemWebhookResponse(ApiModel):
    ok: bool
    processed: bool
    duplicate: bool = False
    event_id: str | None = Field(default=None, alias="eventId")
    event_type: str | None = Field(default=None, alias="eventType")
    owner_user_id: str | None = Field(default=None, alias="ownerUserId")


class AccountProfileResponse(ApiModel):
    user_id: str = Field(alias="userId")
    auth_mode: str = Field(alias="authMode")
    email: str | None = None
    role: str = "user"
    is_admin: bool = Field(default=False, alias="isAdmin")
    anonymous_user_id: str | None = Field(default=None, alias="anonymousUserId")


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
        "bazi_ready",
        "bazi_complete",
        "qa_complete",
        "error",
    ]
    chat_message: str = Field(alias="chatMessage")
    artifacts: list[SkillArtifact]
    active_artifact: str | None = Field(default=None, alias="activeArtifact")


class SkillRunInput(ApiModel):
    session_id: str = Field(alias="sessionId", min_length=1)
    skill: SkillName
    user_message: str = Field(default="", alias="userMessage", max_length=4000)
    locale: AppLocale | None = None


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


AdminSessionStatus = Literal[
    "draft",
    "validation",
    "queued",
    "running",
    "completed",
    "failed",
    "stalled",
]


class AdminSessionProgress(ApiModel):
    total: int = 0
    completed: int = 0
    running: int = 0
    failed: int = 0
    percent: int = 0


class AdminArtifactSummary(ApiModel):
    path: str
    kind: Literal["markdown", "json", "text", "html", "pdf", "other"]
    size_bytes: int = Field(alias="sizeBytes")
    updated_at: str = Field(alias="updatedAt")


class AdminExportSummary(ApiModel):
    name: str
    path: str
    media_type: str = Field(alias="mediaType")
    size_bytes: int = Field(alias="sizeBytes")
    updated_at: str = Field(alias="updatedAt")


class AdminSubjectSummary(ApiModel):
    birth_date: str | None = Field(default=None, alias="birthDate")
    birth_time: str | None = Field(default=None, alias="birthTime")
    birth_place: str | None = Field(default=None, alias="birthPlace")
    time_precision: str | None = Field(default=None, alias="timePrecision")
    time_source: str | None = Field(default=None, alias="timeSource")
    timezone: str | None = None
    gender: str | None = None
    relationship: str | None = None


class AdminSessionSummary(ApiModel):
    session_id: str = Field(alias="sessionId")
    status: AdminSessionStatus
    stage: str
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")
    subject: AdminSubjectSummary | None = None
    progress: AdminSessionProgress
    artifact_count: int = Field(alias="artifactCount")
    export_count: int = Field(alias="exportCount")
    has_pdf: bool = Field(alias="hasPdf")
    job_id: str | None = Field(default=None, alias="jobId")
    active_node: str | None = Field(default=None, alias="activeNode")
    duration_seconds: float | None = Field(default=None, alias="durationSeconds")
    error: str | None = None


class AdminSessionListResponse(ApiModel):
    sessions: list[AdminSessionSummary]
    total: int
    running: int
    completed: int
    failed: int


class AdminSessionDetailResponse(ApiModel):
    summary: AdminSessionSummary
    session: SkillSessionResponse
    artifacts: list[AdminArtifactSummary]
    exports: list[AdminExportSummary]
    run_metrics: dict[str, Any] | None = Field(default=None, alias="runMetrics")
    manifest: dict[str, Any] | None = None
    active_job: CoreJobResponse | None = Field(default=None, alias="activeJob")


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
