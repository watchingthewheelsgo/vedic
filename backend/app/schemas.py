from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.vedicdust.rectification_policy import RECTIFICATION_EVENT_SUBTYPES


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


BirthTimePrecision = Literal["exact", "approximate", "part_of_day", "unknown"]
AppLocale = Literal["zh", "en", "ja"]
ReaderRelationship = Literal["self", "parent", "partner", "family", "professional"]
LifeEventCategory = Literal[
    "education",
    "career",
    "relationship",
    "relocation",
    "child",
    "health",
    "family",
    "finance",
    "property",
    "legal",
    "loss",
    "spiritual",
]
SkillName = Literal[
    "vedic-reader",
    "vedic-core",
    "vedic-rectifier",
    "vedic-synastry",
    "bazi-calculator",
    "bazi-classics-core",
]


class ReportedTimeWindow(ApiModel):
    minutes_before: int = Field(alias="minutesBefore", ge=0, le=720)
    minutes_after: int = Field(alias="minutesAfter", ge=0, le=720)
    basis: Literal["user_certainty_choice", "user_custom_range"] = Field(
        default="user_certainty_choice"
    )

    @model_validator(mode="after")
    def validate_span(self) -> ReportedTimeWindow:
        if self.minutes_before + self.minutes_after > 1439:
            raise ValueError("reported birth-time window cannot exceed one civil day")
        return self


class BirthInput(ApiModel):
    birth_date: str = Field(alias="birthDate", min_length=8, max_length=20)
    birth_time: str = Field(default="", alias="birthTime", max_length=20)
    birth_place: str = Field(alias="birthPlace", min_length=2, max_length=160)
    birth_time_precision: BirthTimePrecision = Field(alias="birthTimePrecision")
    reported_time_window: ReportedTimeWindow | None = Field(
        default=None,
        alias="reportedTimeWindow",
    )
    gender: str = Field(default="[待填]", max_length=80)
    relationship: str = Field(default="[待填]", max_length=120)
    time_source: str = Field(default="未追问", alias="timeSource", max_length=120)
    reading_focus: str = Field(default="", alias="readingFocus", max_length=1000)
    life_events: str = Field(default="", alias="lifeEvents", max_length=4000)
    life_event_facts: str = Field(default="", alias="lifeEventFacts", max_length=16000)
    reader_relationship: ReaderRelationship = Field(
        default="self",
        alias="readerRelationship",
    )
    utc_offset_seconds: int | None = Field(
        default=None,
        alias="utcOffsetSeconds",
        ge=-50400,
        le=50400,
    )
    locale: AppLocale = "en"


class SkillBirthInput(BirthInput):
    pass


class RectificationLifeEventInput(ApiModel):
    question_id: str | None = Field(
        default=None,
        alias="questionId",
        pattern=r"^rectify\.r\d+\.q\d+\.[a-z]+$",
    )
    date: str = Field(
        pattern=r"^(?:19|20)\d{2}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)?$"
    )
    category: LifeEventCategory
    event_subtype: str = Field(
        alias="eventSubtype",
        pattern=r"^[a-z][a-z0-9_]{1,39}$",
    )
    description: str = Field(min_length=3, max_length=240)

    @model_validator(mode="after")
    def validate_event_subtype(self) -> RectificationLifeEventInput:
        allowed = RECTIFICATION_EVENT_SUBTYPES.get(self.category, ())
        if self.event_subtype not in allowed:
            raise ValueError(
                f"event subtype {self.event_subtype!r} is not valid for category {self.category!r}"
            )
        return self


class RectificationLifeEventsInput(ApiModel):
    session_id: str = Field(alias="sessionId", min_length=1)
    expected_chart_revision: int | None = Field(
        default=None,
        alias="expectedChartRevision",
        ge=1,
    )
    idempotency_key: str | None = Field(
        default=None,
        alias="idempotencyKey",
        min_length=8,
        max_length=160,
    )
    # Evidence is recalculated after every accepted answer. The release gate still
    # requires the configured calibration set before a chart can be published.
    events: list[RectificationLifeEventInput] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def validate_independent_events(self) -> RectificationLifeEventsInput:
        fingerprints = [
            (
                event.date,
                event.category,
                event.event_subtype,
                " ".join(event.description.casefold().split()),
            )
            for event in self.events
        ]
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError("rectification life events must be distinct")
        return self

    def ledger_text(self) -> str:
        return "\n".join(
            f"{event.date} {event.category}: {event.description.strip()}" for event in self.events
        )


class RectificationLifeEventsResetInput(ApiModel):
    session_id: str = Field(alias="sessionId", min_length=1)
    expected_chart_revision: int | None = Field(
        default=None,
        alias="expectedChartRevision",
        ge=1,
    )


class RectificationInterviewInput(ApiModel):
    session_id: str = Field(alias="sessionId", min_length=1)
    locale: AppLocale = "en"
    current_question_id: str | None = Field(
        default=None,
        alias="currentQuestionId",
        pattern=r"^rectify\.r\d+\.q\d+\.[a-z]+$",
    )
    skipped_category: LifeEventCategory | None = Field(default=None, alias="skippedCategory")
    reset_skipped: bool = Field(default=False, alias="resetSkipped")
    available_categories: list[LifeEventCategory] | None = Field(
        default=None,
        alias="availableCategories",
        min_length=1,
        max_length=12,
    )

    @model_validator(mode="after")
    def validate_available_categories(self) -> RectificationInterviewInput:
        if self.available_categories is not None and len(self.available_categories) != len(
            set(self.available_categories)
        ):
            raise ValueError("available rectification categories must be distinct")
        return self


RectificationConfirmationAnswer = Literal["accurate", "partly", "inaccurate"]


class RectificationConfirmationResponse(ApiModel):
    example_id: str = Field(alias="exampleId", min_length=1, max_length=80)
    answer: RectificationConfirmationAnswer
    note: str = Field(default="", max_length=400)


class RectificationConfirmationInput(ApiModel):
    session_id: str = Field(alias="sessionId", min_length=1)
    expected_chart_revision: int | None = Field(
        default=None,
        alias="expectedChartRevision",
        ge=1,
    )
    responses: list[RectificationConfirmationResponse] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def validate_unique_examples(self) -> RectificationConfirmationInput:
        example_ids = [response.example_id for response in self.responses]
        if len(example_ids) != len(set(example_ids)):
            raise ValueError("rectification confirmation responses must be distinct")
        return self


class ConsultationQuestionInput(ApiModel):
    session_id: str = Field(alias="sessionId", min_length=1)
    question: str = Field(min_length=3, max_length=1200)


class ConsultationAnswerResponse(ApiModel):
    answerability: Literal["answered", "insufficient_evidence"]
    answer: str
    supporting_claim_ids: list[str] = Field(alias="supportingClaimIds", max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=5)
    follow_up_questions: list[str] = Field(
        default_factory=list,
        alias="followUpQuestions",
        max_length=3,
    )


class ConsultationExchangeResponse(ConsultationAnswerResponse):
    asked_at: datetime = Field(alias="askedAt")
    question: str


class ConsultationConversationResponse(ApiModel):
    schema_version: Literal["vedicdust-consultation-conversation/1.0.0"] = Field(
        default="vedicdust-consultation-conversation/1.0.0",
        alias="schemaVersion",
    )
    session_id: str = Field(alias="sessionId")
    exchanges: list[ConsultationExchangeResponse] = Field(default_factory=list, max_length=20)


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
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None


class PlaceSearchResponse(ApiModel):
    options: list[PlaceOption]


class PrecisePlaceOption(ApiModel):
    id: str
    label: str
    address: str | None = None
    meta: str | None = None
    source: Literal["geonames-local", "amap", "agent", "manual"]
    accuracy: Literal["city", "poi", "address", "district", "coordinate"]
    coordinate_system: str = Field(alias="coordinateSystem")
    latitude: float
    longitude: float
    birth_place: str = Field(alias="birthPlace")
    verification_status: Literal["verified", "city-fallback", "unverified", "manual"] = Field(
        default="unverified", alias="verificationStatus"
    )
    verification_reason: str | None = Field(default=None, alias="verificationReason")
    distance_from_city_km: float | None = Field(default=None, alias="distanceFromCityKm")
    city_label: str | None = Field(default=None, alias="cityLabel")
    source_url: str | None = Field(default=None, alias="sourceUrl")
    raw_evidence: str | None = Field(default=None, alias="rawEvidence")


class PrecisePlaceSearchResponse(ApiModel):
    options: list[PrecisePlaceOption]
    local_count: int = Field(default=0, alias="localCount")
    fallback_source: str | None = Field(default=None, alias="fallbackSource")
    fallback_enabled: bool = Field(default=False, alias="fallbackEnabled")
    agent_fallback_enabled: bool = Field(default=False, alias="agentFallbackEnabled")
    agent_attempted: bool = Field(default=False, alias="agentAttempted")
    agent_error: str | None = Field(default=None, alias="agentError")
    agent_search_queries: list[str] = Field(default_factory=list, alias="agentSearchQueries")
    verification_base: str | None = Field(default=None, alias="verificationBase")
    rejected_count: int = Field(default=0, alias="rejectedCount")
    attempted_sources: list[str] = Field(default_factory=list, alias="attemptedSources")


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
    provider_versions: dict[str, str] = Field(alias="providerVersions")
    timezone_database_version: str = Field(alias="timezoneDatabaseVersion")
    ephemeris_data_fingerprint: str = Field(alias="ephemerisDataFingerprint")
    timezone_source: str = Field(alias="timezoneSource")
    geo_source: str = Field(alias="geoSource")
    input_precision: BirthTimePrecision = Field(alias="inputPrecision")
    validation_status: Literal["passed", "degraded", "limited"] = Field(alias="validationStatus")
    birth_input_context_json: str = Field(alias="birthInputContextJson")
    sensitivity_scan_json: str = Field(alias="sensitivityScanJson")
    chart_record_json: str = Field(alias="chartRecordJson")
    facts: ChartFacts
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(), alias="generatedAt"
    )
