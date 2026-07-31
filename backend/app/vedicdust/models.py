from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .fact_catalog import FactType, validate_fact_payload


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class EvidenceClass(StrEnum):
    ASTRONOMICAL_AUTHORITY = "astronomical_authority"
    CLASSICAL_TEXT = "classical_text"
    LINEAGE_COMMENTARY = "lineage_commentary"
    SOFTWARE_REFERENCE = "software_reference"
    PRODUCT_HYPOTHESIS = "product_hypothesis"
    USER_TESTIMONY = "user_testimony"


class ConfidenceGrade(StrEnum):
    VERIFIED = "verified"
    CORROBORATED = "corroborated"
    PROVISIONAL = "provisional"
    DISPUTED = "disputed"
    UNAVAILABLE = "unavailable"


class SourceReference(ContractModel):
    source_id: str = Field(min_length=3)
    evidence_class: EvidenceClass
    title: str = Field(min_length=3)
    locator: str | None = None
    edition: str | None = None
    url: str | None = None
    citation_status: Literal["pinned", "pending-edition-pin", "informational"]


class RuleProvenance(ContractModel):
    rule_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    rule_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    method_profile_id: str
    evidence_class: EvidenceClass
    source_ids: list[str] = Field(min_length=1)
    confidence: ConfidenceGrade
    implementation_note: str | None = None


class GeoPoint(ContractModel):
    latitude_deg: float = Field(ge=-90, le=90)
    longitude_deg: float = Field(ge=-180, le=180)
    datum: Literal["WGS84"] = "WGS84"


class TimeRange(ContractModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_order(self) -> TimeRange:
        if self.end <= self.start:
            raise ValueError("time range end must be after start")
        return self


class EvidenceItem(ContractModel):
    evidence_id: str
    evidence_class: EvidenceClass
    source_label: str
    observed_value: str
    confidence: ConfidenceGrade
    source_url: str | None = None
    notes: str | None = None


class BirthAssertion(ContractModel):
    local_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    reported_local_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}(:\d{2})?$")
    reported_place: str = Field(min_length=2)
    time_certainty: Literal[
        "documented", "reported_exact", "approximate", "broad_window", "unknown", "rectified"
    ]
    reported_time_window: TimeRange | None = None
    evidence: list[EvidenceItem] = Field(min_length=1)


class PlaceResolution(ContractModel):
    label: str
    point: GeoPoint
    precision: Literal["coordinate", "poi", "address", "district", "city"]
    timezone_id: str
    evidence: list[EvidenceItem] = Field(min_length=1)


class CanonicalBirthMoment(ContractModel):
    local_datetime: datetime
    utc_datetime: datetime
    timezone_id: str
    utc_offset_seconds: int = Field(ge=-50400, le=50400)
    historical_offset_status: Literal["resolved", "ambiguous", "nonexistent", "unresolved"]
    place: PlaceResolution
    resolution_confidence: ConfidenceGrade

    @model_validator(mode="after")
    def require_resolved_offset_for_verified_moment(self) -> CanonicalBirthMoment:
        if (
            self.resolution_confidence == ConfidenceGrade.VERIFIED
            and self.historical_offset_status != "resolved"
        ):
            raise ValueError("verified canonical moment requires a resolved historical offset")
        return self


class SubjectContext(ContractModel):
    subject_id: str
    display_name: str | None = None
    locale: Literal["zh", "en", "ja"] = "en"
    current_age: int | None = Field(default=None, ge=0, le=130)
    life_stage: Literal["child", "teen", "young_adult", "adult", "elder"] | None = None
    reader_relationship: Literal["self", "parent", "partner", "family", "professional"] = "self"
    consultation_topics: list[str] = Field(default_factory=list)


class AyanamsaSetting(ContractModel):
    model: Literal["lahiri", "true_chitra", "raman", "krishnamurti", "custom"]
    value_deg: float | None = Field(default=None, ge=0, lt=30)
    implementation: str


class CalculationProfile(ContractModel):
    profile_id: str
    profile_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    tradition: str
    zodiac: Literal["sidereal", "tropical"]
    ayanamsa: AyanamsaSetting
    node_model: Literal["mean", "true"]
    rashi_house_model: Literal["whole_sign"]
    bhava_cusp_model: str | None = None
    varga_scheme: str
    supported_vargas: list[int]
    aspect_model: str
    dasha_model: str
    dasha_year_days: float = Field(gt=300, lt=400)
    coordinate_datum: Literal["WGS84"] = "WGS84"
    ephemeris_provider: str
    rule_pack_version: str
    source_ids: list[str] = Field(min_length=1)


class NakshatraPosition(ContractModel):
    name: str
    index: int = Field(ge=0, le=26)
    pada: int = Field(ge=1, le=4)
    lord: str


class ZodiacPosition(ContractModel):
    longitude_deg: float = Field(ge=0, lt=360)
    sign: str
    sign_index: int = Field(ge=0, le=11)
    degree_in_sign: float = Field(ge=0, lt=30)
    nakshatra: NakshatraPosition | None = None


class GrahaPosition(ContractModel):
    graha: Literal["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
    position: ZodiacPosition
    speed_deg_per_day: float | None = None
    motion: Literal["direct", "retrograde", "stationary", "not_applicable"]


class AstronomySnapshot(ContractModel):
    snapshot_id: str
    calculated_at: datetime
    julian_day_ut: float
    calculation_provider: str
    calculation_adapter_version: str
    ephemeris_version: str
    ayanamsa_value_deg: float = Field(ge=0, lt=30)
    ascendant: ZodiacPosition
    grahas: list[GrahaPosition]
    status: Literal["complete", "partial", "failed"]

    @model_validator(mode="after")
    def validate_graha_completeness(self) -> AstronomySnapshot:
        names = [graha.graha for graha in self.grahas]
        if len(names) != len(set(names)):
            raise ValueError("astronomy snapshot cannot contain duplicate grahas")
        if self.status == "complete" and set(names) != {
            "Sun",
            "Moon",
            "Mars",
            "Mercury",
            "Jupiter",
            "Venus",
            "Saturn",
            "Rahu",
            "Ketu",
        }:
            raise ValueError("complete astronomy snapshot requires all nine grahas")
        return self


class ChartPlacement(ContractModel):
    object_id: str
    position: ZodiacPosition
    house: int = Field(ge=1, le=12)


class VargaChart(ContractModel):
    varga_id: str = Field(pattern=r"^D\d+$")
    factor: int = Field(ge=1, le=360)
    method: str
    lagna: ChartPlacement
    placements: list[ChartPlacement]
    confidence: ConfidenceGrade
    eligible_as_primary_evidence: bool

    @model_validator(mode="after")
    def validate_factor(self) -> VargaChart:
        if self.varga_id != f"D{self.factor}":
            raise ValueError("varga id must match its factor")
        object_ids = [placement.object_id for placement in self.placements]
        if len(object_ids) != len(set(object_ids)):
            raise ValueError("varga chart cannot contain duplicate placements")
        return self


class JyotishFact(ContractModel):
    fact_id: str
    fact_type: FactType
    subject_ref: str
    value: Any
    unit: str | None = None
    provenance: RuleProvenance

    @model_validator(mode="after")
    def validate_catalog_contract(self) -> JyotishFact:
        validate_fact_payload(self.fact_type, self.subject_ref, self.value)
        return self


class RulePredicate(ContractModel):
    fact_type: str
    subject_selector: str
    operator: Literal[
        "equals",
        "not_equals",
        "greater_than",
        "less_than",
        "contains",
        "exists",
        "not_exists",
    ]
    expected: Any | None = None


class MethodRule(ContractModel):
    rule_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    rule_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    title: str
    rule_kind: Literal["derivation", "judgement", "workflow_gate"]
    method_profile_ids: list[str] = Field(min_length=1)
    topic: str
    required_evidence_layers: list[
        Literal["natal_promise", "capacity", "varga_confirmation", "timing", "user_testimony"]
    ] = Field(default_factory=list)
    all_of: list[RulePredicate] = Field(default_factory=list)
    any_of: list[RulePredicate] = Field(default_factory=list)
    none_of: list[RulePredicate] = Field(default_factory=list)
    output_code: str
    evidence_class: EvidenceClass
    source_ids: list[str] = Field(min_length=1)
    status: Literal["draft", "provisional", "validated", "retired"]
    validation_fixture_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class RuleCatalog(ContractModel):
    schema_version: Literal["vedicdust-rule-catalog/1.0.0"] = "vedicdust-rule-catalog/1.0.0"
    catalog_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    rules: list[MethodRule]

    @model_validator(mode="after")
    def validate_unique_rule_ids(self) -> RuleCatalog:
        rule_ids = [rule.rule_id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("rule catalog contains duplicate rule ids")
        return self


class TimingPeriod(ContractModel):
    period_id: str
    system: str
    level: Literal["mahadasha", "antardasha", "pratyantardasha", "other"]
    lords: list[str] = Field(min_length=1)
    interval: TimeRange
    provenance: RuleProvenance


class QualityCheck(ContractModel):
    check_id: str
    status: Literal["passed", "warning", "failed", "not_run"]
    expected: Any | None = None
    observed: Any | None = None
    message: str


class SensitivityBoundary(ContractModel):
    boundary_id: str
    axis: Literal["time", "place", "method_profile"]
    at: datetime | None = None
    changed_fact_ids: list[str] = Field(min_length=1)
    before_fingerprint: str
    after_fingerprint: str


class LifeEvent(ContractModel):
    event_id: str
    category: str
    interval: TimeRange
    date_precision: Literal["day", "month", "year", "range"]
    description: str
    role: Literal["calibration", "holdout"]
    evidence: EvidenceItem


class CandidateEvidenceScore(ContractModel):
    event_id: str
    score: float = Field(ge=-1, le=1)
    supporting_fact_ids: list[str] = Field(default_factory=list)
    contradicting_fact_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    explanation: str


class CandidateInterval(ContractModel):
    candidate_id: str
    interval: TimeRange
    representative_moment: datetime
    fingerprint: str
    evidence_scores: list[CandidateEvidenceScore] = Field(default_factory=list)
    aggregate_score: float | None = None
    eligible: bool = True
    exclusion_reason: str | None = None

    @model_validator(mode="after")
    def validate_representative_moment(self) -> CandidateInterval:
        if not self.interval.start <= self.representative_moment < self.interval.end:
            raise ValueError("representative moment must be inside the candidate interval")
        return self


class RectificationDecision(ContractModel):
    status: Literal[
        "not_required",
        "collecting_evidence",
        "comparing_candidates",
        "bounded_interval",
        "multiple_equivalent",
        "underdetermined",
    ]
    selected_candidate_ids: list[str] = Field(default_factory=list)
    resulting_interval: TimeRange | None = None
    confidence: ConfidenceGrade
    reasons: list[str] = Field(default_factory=list)
    holdout_result: Literal["passed", "failed", "not_run"] = "not_run"
    unresolved_questions: list[str] = Field(default_factory=list)


class RectificationRecord(ContractModel):
    schema_version: Literal["vedicdust-rectification/1.0.0"] = "vedicdust-rectification/1.0.0"
    reported_window: TimeRange | None = None
    life_events: list[LifeEvent] = Field(default_factory=list)
    candidates: list[CandidateInterval] = Field(default_factory=list)
    decision: RectificationDecision


class ChartRecord(ContractModel):
    schema_version: Literal["vedicdust-chart-record/1.0.0"] = "vedicdust-chart-record/1.0.0"
    chart_record_id: str
    reading_session_id: str
    revision: int = Field(ge=1)
    created_at: datetime
    subject: SubjectContext
    birth_assertion: BirthAssertion
    canonical_moment: CanonicalBirthMoment | None = None
    calculation_profile: CalculationProfile
    astronomy: AstronomySnapshot | None = None
    charts: list[VargaChart] = Field(default_factory=list)
    facts: list[JyotishFact] = Field(default_factory=list)
    timing_periods: list[TimingPeriod] = Field(default_factory=list)
    quality_checks: list[QualityCheck] = Field(default_factory=list)
    sensitivity_boundaries: list[SensitivityBoundary] = Field(default_factory=list)
    rectification: RectificationRecord | None = None
    status: Literal[
        "intake",
        "canonicalized",
        "calculated",
        "rectification_required",
        "rectified",
        "ready_for_judgement",
        "blocked",
    ]

    @model_validator(mode="after")
    def validate_record_state(self) -> ChartRecord:
        calculated_states = {
            "calculated",
            "rectification_required",
            "rectified",
            "ready_for_judgement",
        }
        if self.status in calculated_states and (
            self.canonical_moment is None or self.astronomy is None
        ):
            raise ValueError("calculated chart records require canonical moment and astronomy")
        if self.status == "ready_for_judgement" and any(
            check.status == "failed" for check in self.quality_checks
        ):
            raise ValueError(
                "chart record with failed quality checks cannot be ready for judgement"
            )
        return self


class ReadingSession(ContractModel):
    schema_version: Literal["vedicdust-reading-session/1.0.0"] = "vedicdust-reading-session/1.0.0"
    reading_session_id: str
    subject_id: str
    chart_record_id: str
    active_chart_revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    locale: Literal["zh", "en", "ja"] = "en"
    stage: Literal[
        "intake",
        "chart_ready",
        "rectification",
        "ready_for_judgement",
        "report_in_progress",
        "report_ready",
        "blocked",
    ]
    rectification_status: Literal[
        "not_required",
        "collecting_evidence",
        "comparing_candidates",
        "bounded_interval",
        "multiple_equivalent",
        "underdetermined",
    ]
    report_status: Literal["not_started", "in_progress", "ready", "blocked"] = "not_started"


class DiscriminatorOption(ContractModel):
    option_id: str
    label: str
    supports_candidate_ids: list[str] = Field(default_factory=list)
    contradicts_candidate_ids: list[str] = Field(default_factory=list)


class RectificationQuestion(ContractModel):
    question_id: str
    prompt: str
    answer_kind: Literal["single_choice", "multiple_choice", "date", "short_text"]
    discriminating_fact_ids: list[str] = Field(min_length=1)
    candidate_ids: list[str] = Field(min_length=2)
    options: list[DiscriminatorOption] = Field(default_factory=list)
    why_asked: str
    prohibited_inference: str | None = None


class RectificationQuestionSet(ContractModel):
    schema_version: Literal["vedicdust-question-set/1.0.0"] = "vedicdust-question-set/1.0.0"
    chart_record_id: str
    round: int = Field(ge=1)
    questions: list[RectificationQuestion] = Field(min_length=1, max_length=5)
    completion_condition: str


class RectificationAnswer(ContractModel):
    question_id: str
    selected_option_ids: list[str] = Field(default_factory=list)
    text: str | None = None
    event_interval: TimeRange | None = None
    confidence: Literal["certain", "fairly_certain", "uncertain", "unknown"]


class RectificationAnswerBatch(ContractModel):
    schema_version: Literal["vedicdust-answer-batch/1.0.0"] = "vedicdust-answer-batch/1.0.0"
    chart_record_id: str
    round: int = Field(ge=1)
    answers: list[RectificationAnswer] = Field(min_length=1, max_length=5)


class AuditFinding(ContractModel):
    finding_id: str
    severity: Literal["blocking", "warning", "information"]
    category: Literal[
        "birth_evidence",
        "civil_time",
        "place",
        "calculation_profile",
        "calculation",
        "sensitivity",
        "rectification",
        "provenance",
        "audience",
    ]
    field_refs: list[str] = Field(default_factory=list)
    message: str
    required_action: str | None = None


class ChartAudit(ContractModel):
    schema_version: Literal["vedicdust-chart-audit/1.0.0"] = "vedicdust-chart-audit/1.0.0"
    chart_record_id: str
    audited_at: datetime
    status: Literal["passed", "passed_with_limits", "blocked"]
    findings: list[AuditFinding] = Field(default_factory=list)
    permitted_next_steps: list[
        Literal["canonicalize", "calculate", "rectify", "judge", "render_report", "collect_input"]
    ] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_blocking_status(self) -> ChartAudit:
        has_blocker = any(finding.severity == "blocking" for finding in self.findings)
        if has_blocker != (self.status == "blocked"):
            raise ValueError("audit status must agree with blocking findings")
        return self


class Claim(ContractModel):
    claim_id: str
    topic: str
    title: str | None = None
    plain_statement: str
    technical_statement: str
    real_world_expressions: list[str] = Field(default_factory=list)
    user_relevance: str | None = None
    conditions: list[str] = Field(default_factory=list)
    supporting_fact_ids: list[str] = Field(min_length=1)
    counter_fact_ids: list[str] = Field(default_factory=list)
    timing_fact_ids: list[str] = Field(default_factory=list)
    timing_period_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(min_length=1)
    certainty: Literal["high", "moderate", "low", "withheld"]
    scope: Literal["natal_promise", "capacity", "timing", "rectification", "context"]
    status: Literal["supported", "tentative", "withheld"] = "supported"
    time_scope: TimeRange | None = None
    practical_implications: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_claim_state(self) -> Claim:
        if (self.certainty == "withheld") != (self.status == "withheld"):
            raise ValueError("withheld claim status and certainty must agree")
        if self.scope == "timing":
            if self.time_scope is None:
                raise ValueError("timing claim requires a time scope")
            if not self.timing_fact_ids and not self.timing_period_ids:
                raise ValueError("timing claim requires timing evidence")
        for label, values in (
            ("supporting facts", self.supporting_fact_ids),
            ("counter facts", self.counter_fact_ids),
            ("timing facts", self.timing_fact_ids),
            ("timing periods", self.timing_period_ids),
            ("rules", self.rule_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"claim contains duplicate {label}")
        return self


class ClaimGraph(ContractModel):
    schema_version: Literal["vedicdust-claim-graph/1.0.0"] = "vedicdust-claim-graph/1.0.0"
    chart_record_id: str
    chart_revision: int = Field(default=1, ge=1)
    method_profile_id: str
    rule_pack_version: str
    generated_at: datetime
    claims: list[Claim] = Field(min_length=1, max_length=12)
    omitted_topics: dict[str, str] = Field(default_factory=dict)
    quality_checks: list[QualityCheck] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_claim_ids(self) -> ClaimGraph:
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim graph contains duplicate claim ids")
        return self


class JudgementRuleContext(ContractModel):
    rule_id: str
    title: str
    topic: str
    required_evidence_layers: list[
        Literal["natal_promise", "capacity", "varga_confirmation", "timing", "user_testimony"]
    ] = Field(default_factory=list)
    status: Literal["draft", "provisional", "validated"]
    limitations: list[str] = Field(default_factory=list)


class JudgementTopicContext(ContractModel):
    topic_id: str
    title: str
    purpose: str
    requested: bool = False
    priority_score: int = Field(ge=0, le=100)
    rule_ids: list[str] = Field(min_length=1)
    natal_fact_ids: list[str] = Field(default_factory=list)
    capacity_fact_ids: list[str] = Field(default_factory=list)
    varga_fact_ids: list[str] = Field(default_factory=list)
    timing_period_ids: list[str] = Field(default_factory=list)
    eligible_vargas: list[str] = Field(default_factory=list)
    evidence_layers: list[Literal["natal_promise", "capacity", "varga_confirmation", "timing"]] = (
        Field(default_factory=list)
    )
    limitations: list[str] = Field(default_factory=list)


class JudgementContext(ContractModel):
    schema_version: Literal["vedicdust-judgement-context/1.0.0"] = (
        "vedicdust-judgement-context/1.0.0"
    )
    chart_record_id: str
    chart_revision: int = Field(ge=1)
    method_profile_id: str
    generated_at: datetime
    requested_topics: list[str] = Field(default_factory=list)
    rule_pack_version: str
    rules: list[JudgementRuleContext] = Field(min_length=1)
    global_gate_rule_ids: list[str] = Field(default_factory=list)
    topics: list[JudgementTopicContext] = Field(min_length=1)
    restricted_fact_ids: list[str] = Field(default_factory=list)
    restricted_timing_period_ids: list[str] = Field(default_factory=list)
    quality_checks: list[QualityCheck] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> JudgementContext:
        rule_ids = {rule.rule_id for rule in self.rules}
        unknown = sorted(
            {
                rule_id
                for topic in self.topics
                for rule_id in topic.rule_ids
                if rule_id not in rule_ids
            }
            | {rule_id for rule_id in self.global_gate_rule_ids if rule_id not in rule_ids}
        )
        if unknown:
            raise ValueError("judgement context references unknown rules: " + ", ".join(unknown))
        return self


class TimingWindow(ContractModel):
    timing_window_id: str
    title: str
    horizon: Literal["historical", "current", "near_term", "strategic"]
    interval: TimeRange
    claim_ids: list[str] = Field(min_length=1)
    activation_fact_ids: list[str] = Field(default_factory=list)
    activation_period_ids: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    pressures: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    confidence: Literal["high", "moderate", "low"]
    limitations: list[str] = Field(default_factory=list)


class ConsultationScope(ContractModel):
    requested_topics: list[str] = Field(default_factory=list)
    user_questions: list[str] = Field(default_factory=list)
    included_topics: list[str] = Field(default_factory=list)
    omitted_topics: dict[str, str] = Field(default_factory=dict)
    report_depth: Literal["standard", "professional"] = "standard"
    residual_uncertainties: list[str] = Field(default_factory=list)


class ConsultationConfidence(ContractModel):
    overall: Literal["high", "moderate", "low", "blocked"]
    input_confidence: ConfidenceGrade
    rectification_confidence: ConfidenceGrade
    judgement_confidence: Literal["high", "moderate", "low", "blocked"]
    rationale: list[str] = Field(min_length=1)


class ReportSection(ContractModel):
    section_id: str
    section_kind: Literal[
        "scope",
        "executive_synthesis",
        "chart_foundation",
        "core_architecture",
        "priority_domain",
        "timing_outlook",
        "decision_support",
        "follow_up",
        "technical_evidence",
    ]
    title: str
    purpose: str
    claim_ids: list[str] = Field(default_factory=list)
    timing_window_ids: list[str] = Field(default_factory=list)
    visual_refs: list[str] = Field(default_factory=list)
    priority: int = Field(default=100, ge=0)
    confidence_disclosure_required: bool = False


class ConsultationReportManifest(ContractModel):
    schema_version: Literal["vedicdust-report-manifest/1.0.0"] = "vedicdust-report-manifest/1.0.0"
    dossier_id: str | None = None
    chart_record_id: str
    chart_revision: int = Field(default=1, ge=1)
    claim_graph_version: Literal["vedicdust-claim-graph/1.0.0"]
    generated_at: datetime | None = None
    locale: Literal["zh", "en", "ja"]
    audience: Literal["self", "parent", "partner", "family", "professional"]
    sections: list[ReportSection]
    omitted_claim_ids: dict[str, str] = Field(default_factory=dict)
    release_status: Literal["draft", "approved", "blocked"]


class ConsultationDossier(ContractModel):
    schema_version: Literal["vedicdust-consultation-dossier/1.0.0"] = (
        "vedicdust-consultation-dossier/1.0.0"
    )
    dossier_id: str
    chart_record_id: str
    chart_revision: int = Field(ge=1)
    method_profile_id: str
    claim_graph_version: Literal["vedicdust-claim-graph/1.0.0"]
    generated_at: datetime
    locale: Literal["zh", "en", "ja"]
    audience: Literal["self", "parent", "partner", "family", "professional"]
    scope: ConsultationScope
    confidence: ConsultationConfidence
    executive_claim_ids: list[str] = Field(default_factory=list, max_length=5)
    sections: list[ReportSection] = Field(min_length=1)
    timing_windows: list[TimingWindow] = Field(default_factory=list)
    omitted_claim_ids: dict[str, str] = Field(default_factory=dict)
    unresolved_questions: list[str] = Field(default_factory=list)
    release_status: Literal["draft", "approved", "blocked"]
    quality_checks: list[QualityCheck] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dossier_shape(self) -> ConsultationDossier:
        section_ids = [section.section_id for section in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("consultation dossier contains duplicate section ids")
        fixed_kinds = [
            section.section_kind
            for section in self.sections
            if section.section_kind != "priority_domain"
        ]
        duplicate_kinds = sorted({kind for kind in fixed_kinds if fixed_kinds.count(kind) > 1})
        if duplicate_kinds:
            raise ValueError(
                "consultation dossier contains duplicate fixed section kinds: "
                + ", ".join(duplicate_kinds)
            )
        timing_ids = [window.timing_window_id for window in self.timing_windows]
        if len(timing_ids) != len(set(timing_ids)):
            raise ValueError("consultation dossier contains duplicate timing window ids")
        if len(self.executive_claim_ids) != len(set(self.executive_claim_ids)):
            raise ValueError("consultation dossier contains duplicate executive claim ids")
        if self.release_status == "approved":
            required = {
                "scope",
                "executive_synthesis",
                "chart_foundation",
                "timing_outlook",
                "decision_support",
                "follow_up",
                "technical_evidence",
            }
            present = {section.section_kind for section in self.sections}
            missing = sorted(required - present)
            if missing:
                raise ValueError(
                    "approved consultation dossier is missing section kinds: " + ", ".join(missing)
                )
            if not 3 <= len(self.executive_claim_ids) <= 5:
                raise ValueError(
                    "approved consultation dossier requires three to five executive claims"
                )
            sections_by_kind = {section.section_kind: section for section in self.sections}
            for section_kind in (
                "executive_synthesis",
                "chart_foundation",
                "decision_support",
            ):
                if not sections_by_kind[section_kind].claim_ids:
                    raise ValueError(
                        f"approved consultation dossier requires claims in {section_kind}"
                    )
        return self


class AgentClaimContext(ContractModel):
    claim_id: str
    topic: str
    statement: str
    user_relevance: str | None = None
    certainty: Literal["high", "moderate", "low"]
    supporting_fact_ids: list[str] = Field(default_factory=list)
    counter_fact_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    practical_implications: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    time_scope: TimeRange | None = None
    timing_window_ids: list[str] = Field(default_factory=list)


class AgentFactContext(ContractModel):
    fact_id: str
    fact_type: FactType
    subject_ref: str
    value: Any
    unit: str | None = None
    confidence: ConfidenceGrade


class AgentContext(ContractModel):
    schema_version: Literal["vedicdust-agent-context/1.0.0"] = "vedicdust-agent-context/1.0.0"
    dossier_id: str
    chart_record_id: str
    chart_revision: int = Field(ge=1)
    generated_at: datetime
    locale: Literal["zh", "en", "ja"]
    stable_fact_ids: list[str] = Field(default_factory=list)
    stable_facts: list[AgentFactContext] = Field(default_factory=list)
    approved_claims: list[AgentClaimContext] = Field(default_factory=list)
    withheld_claim_ids: list[str] = Field(default_factory=list)
    timing_windows: list[TimingWindow] = Field(default_factory=list)
    user_confirmed_event_ids: list[str] = Field(default_factory=list)
    rejected_hypotheses: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    topic_index: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_topic_index(self) -> AgentContext:
        known_claim_ids = {claim.claim_id for claim in self.approved_claims}
        unknown = sorted(
            {
                claim_id
                for claim_ids in self.topic_index.values()
                for claim_id in claim_ids
                if claim_id not in known_claim_ids
            }
        )
        if unknown:
            raise ValueError(
                "agent context topic index references unknown claims: " + ", ".join(unknown)
            )
        return self
