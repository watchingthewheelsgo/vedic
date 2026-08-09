from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .fact_catalog import FactType, validate_fact_payload
from .rectification_policy import (
    RECTIFICATION_CONVERGENCE_COMPONENTS,
    RECTIFICATION_SCORING_POLICY,
    RECTIFICATION_SELECTION_COMPONENTS,
)
from .varga_policy import INDEPENDENT_REFERENCE_VARGA_IDS


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

    @property
    def rank(self) -> int:
        return {
            ConfidenceGrade.UNAVAILABLE: 0,
            ConfidenceGrade.DISPUTED: 1,
            ConfidenceGrade.PROVISIONAL: 2,
            ConfidenceGrade.CORROBORATED: 3,
            ConfidenceGrade.VERIFIED: 4,
        }[self]


class SourceReference(ContractModel):
    source_id: str = Field(min_length=3)
    evidence_class: EvidenceClass
    title: str = Field(min_length=3)
    locator: str | None = None
    edition: str | None = None
    url: str | None = None
    citation_status: Literal["pinned", "pending-edition-pin", "informational"]

    @model_validator(mode="after")
    def validate_pinned_citation(self) -> SourceReference:
        if self.citation_status != "pinned":
            return self
        if not self.locator or not self.locator.strip():
            raise ValueError("pinned source requires a reproducible locator")
        if self.evidence_class in {
            EvidenceClass.ASTRONOMICAL_AUTHORITY,
            EvidenceClass.CLASSICAL_TEXT,
            EvidenceClass.LINEAGE_COMMENTARY,
        } and (not self.url or not self.url.strip()):
            raise ValueError("pinned external source requires a retrievable URL")
        if self.evidence_class in {
            EvidenceClass.CLASSICAL_TEXT,
            EvidenceClass.LINEAGE_COMMENTARY,
        } and (not self.edition or not self.edition.strip()):
            raise ValueError("pinned textual source requires an edition")
        return self


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
    gender_context: str | None = None
    relationship_status: str | None = None
    consultation_topics: list[str] = Field(default_factory=list)


class AyanamsaSetting(ContractModel):
    model: Literal["lahiri", "true_chitra", "raman", "krishnamurti", "custom"]
    value_deg: float | None = Field(default=None, ge=0, lt=30)
    implementation: str


class VargaMethodSetting(ContractModel):
    factor: int = Field(ge=1, le=360)
    algorithm_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    provider: str = Field(min_length=3)
    provider_method: int | None = Field(default=None, ge=1)


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
    varga_methods: list[VargaMethodSetting]
    aspect_model: str
    dasha_model: str
    dasha_year_days: float = Field(gt=300, lt=400)
    coordinate_datum: Literal["WGS84"] = "WGS84"
    ephemeris_provider: str
    planet_position_model: Literal["geocentric_apparent"]
    ephemeris_flags: list[str] = Field(min_length=1)
    rule_pack_version: str
    source_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_varga_methods(self) -> CalculationProfile:
        factors = [setting.factor for setting in self.varga_methods]
        if len(factors) != len(set(factors)):
            raise ValueError("varga methods cannot contain duplicate factors")
        if set(factors) != set(self.supported_vargas):
            raise ValueError("varga methods must cover every supported varga exactly once")
        return self


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
    provider_versions: dict[str, str]
    timezone_database_version: str
    ephemeris_data_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
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


class VargaHouseLord(ContractModel):
    house: int = Field(ge=1, le=12)
    sign: str
    sign_index: int = Field(ge=0, le=11)
    lord: Literal["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
    lord_house: int | None = Field(default=None, ge=1, le=12)


class VargaChart(ContractModel):
    varga_id: str = Field(pattern=r"^D\d+$")
    factor: int = Field(ge=1, le=360)
    method: str
    lagna: ChartPlacement
    placements: list[ChartPlacement]
    house_lords: list[VargaHouseLord] = Field(min_length=12, max_length=12)
    input_stability: ConfidenceGrade
    calculation_assurance: Literal[
        "astronomical_authority",
        "internal_provider_regression",
        "independent_external_match",
    ]
    confidence: ConfidenceGrade
    eligible_as_primary_evidence: bool

    @model_validator(mode="after")
    def validate_factor(self) -> VargaChart:
        if self.varga_id != f"D{self.factor}":
            raise ValueError("varga id must match its factor")
        object_ids = [placement.object_id for placement in self.placements]
        if len(object_ids) != len(set(object_ids)):
            raise ValueError("varga chart cannot contain duplicate placements")
        houses = [entry.house for entry in self.house_lords]
        if sorted(houses) != list(range(1, 13)):
            raise ValueError("varga chart requires exactly one lord entry for each house")
        if self.factor == 1 and self.calculation_assurance != "astronomical_authority":
            raise ValueError("D1 calculation assurance must be astronomical authority")
        if self.factor != 1 and self.calculation_assurance == "astronomical_authority":
            raise ValueError("non-D1 varga calculation assurance cannot be astronomical authority")
        calculation_confidence = (
            ConfidenceGrade.CORROBORATED
            if self.calculation_assurance == "internal_provider_regression"
            else ConfidenceGrade.VERIFIED
        )
        expected_confidence = min(
            self.input_stability,
            calculation_confidence,
            key=lambda value: value.rank,
        )
        if self.confidence != expected_confidence:
            raise ValueError(
                "varga confidence must be the lower of calculation assurance and input stability"
            )
        return self


class JyotishFact(ContractModel):
    fact_id: str
    fact_type: FactType
    subject_ref: str
    value: Any
    unit: str | None = None
    provenance: RuleProvenance
    input_stability: ConfidenceGrade = ConfidenceGrade.VERIFIED
    sensitivity_dependencies: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_catalog_contract(self) -> JyotishFact:
        validate_fact_payload(self.fact_type, self.subject_ref, self.value)
        if len(self.sensitivity_dependencies) != len(set(self.sensitivity_dependencies)):
            raise ValueError("fact sensitivity dependencies must be unique")
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
    judgement_use: Literal["context_only", "traditional_tendency", "directional"] = "context_only"
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


class ValidationFixtureReference(ContractModel):
    fixture_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    fixture_kind: Literal[
        "contract",
        "invariant",
        "same_provider_regression",
        "independent_external",
        "professional_review",
        "rectification_benchmark",
    ]
    test_nodes: list[str] = Field(min_length=1)
    description: str = Field(min_length=3)
    evidence_artifact_path: str | None = Field(default=None, min_length=1)
    evidence_artifact_sha256: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    review_protocol_id: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9][a-z0-9._/-]+$",
    )
    reviewed_by: str | None = Field(default=None, min_length=3)
    reviewed_at: datetime | None = None
    reviewed_case_ids: list[str] = Field(default_factory=list)
    review_scope: Literal["calculation_and_judgement", "rectification", "end_to_end"] | None = None

    @model_validator(mode="after")
    def validate_test_nodes(self) -> ValidationFixtureReference:
        if len(self.test_nodes) != len(set(self.test_nodes)):
            raise ValueError("validation fixture cannot contain duplicate test nodes")
        if any("::test_" not in node for node in self.test_nodes):
            raise ValueError("validation fixture test nodes must name an explicit pytest test")
        if len(self.reviewed_case_ids) != len(set(self.reviewed_case_ids)) or any(
            not case_id.strip() for case_id in self.reviewed_case_ids
        ):
            raise ValueError("reviewed case ids must be unique and non-empty")
        evidence_backed = self.fixture_kind in {
            "independent_external",
            "professional_review",
            "rectification_benchmark",
        }
        evidence_fields = (self.evidence_artifact_path, self.evidence_artifact_sha256)
        if evidence_backed and not all(evidence_fields):
            raise ValueError(
                f"{self.fixture_kind} fixture requires an evidence artifact path and SHA-256"
            )
        if self.fixture_kind == "professional_review":
            required_review_fields = (
                self.review_protocol_id,
                self.reviewed_by,
                self.reviewed_at,
                self.review_scope,
            )
            if not all(required_review_fields) or not self.reviewed_case_ids:
                raise ValueError(
                    "professional review fixture requires protocol, reviewer, timestamp, "
                    "scope, and reviewed case ids"
                )
            if self.reviewed_at is not None and (
                self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None
            ):
                raise ValueError("professional review timestamp must include a UTC offset")
        elif (
            any(
                value is not None
                for value in (
                    self.review_protocol_id,
                    self.reviewed_by,
                    self.reviewed_at,
                    self.review_scope,
                )
            )
            or self.reviewed_case_ids
        ):
            raise ValueError("review metadata is reserved for professional review fixtures")
        return self


class ValidationFixtureRegistry(ContractModel):
    schema_version: Literal["vedicdust-validation-fixtures/1.2.0"] = (
        "vedicdust-validation-fixtures/1.2.0"
    )
    fixtures: list[ValidationFixtureReference]

    @model_validator(mode="before")
    @classmethod
    def migrate_additive_fixture_contract(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if payload.get("schemaVersion") in {
            "vedicdust-validation-fixtures/1.0.0",
            "vedicdust-validation-fixtures/1.1.0",
        }:
            payload["schemaVersion"] = "vedicdust-validation-fixtures/1.2.0"
        return payload

    @model_validator(mode="after")
    def validate_unique_fixture_ids(self) -> ValidationFixtureRegistry:
        fixture_ids = [fixture.fixture_id for fixture in self.fixtures]
        if len(fixture_ids) != len(set(fixture_ids)):
            raise ValueError("validation fixture registry contains duplicate fixture ids")
        return self


class TimingBoundaryEnvelope(ContractModel):
    earliest: datetime
    latest: datetime
    sampled_hypotheses: int = Field(ge=1)
    coverage: Literal[
        "reported_window_endpoints",
        "partial_window_sampling",
        "canonical_only",
    ]
    method_id: Literal["vedicdust-vimshottari-boundary-envelope/1.0.0"] = (
        "vedicdust-vimshottari-boundary-envelope/1.0.0"
    )

    @model_validator(mode="after")
    def validate_bounds(self) -> TimingBoundaryEnvelope:
        if self.earliest.tzinfo is None or self.latest.tzinfo is None:
            raise ValueError("timing boundary envelope must include UTC offsets")
        if self.latest < self.earliest:
            raise ValueError("timing boundary envelope latest must not precede earliest")
        return self


class TimingPeriod(ContractModel):
    period_id: str
    system: str
    level: Literal["mahadasha", "antardasha", "pratyantardasha", "other"]
    lords: list[str] = Field(min_length=1)
    interval: TimeRange
    provenance: RuleProvenance
    input_stability: ConfidenceGrade
    sensitivity_dependencies: list[str] = Field(min_length=1)
    start_boundary: TimingBoundaryEnvelope
    end_boundary: TimingBoundaryEnvelope

    @model_validator(mode="after")
    def validate_sensitivity_dependencies(self) -> TimingPeriod:
        if len(self.sensitivity_dependencies) != len(set(self.sensitivity_dependencies)):
            raise ValueError("timing sensitivity dependencies must be unique")
        if not self.start_boundary.earliest <= self.interval.start <= self.start_boundary.latest:
            raise ValueError("timing start boundary must contain the canonical period start")
        if not self.end_boundary.earliest <= self.interval.end <= self.end_boundary.latest:
            raise ValueError("timing end boundary must contain the canonical period end")
        return self


class IndependentReferencePosition(ContractModel):
    sign: str
    degree_in_sign: float = Field(ge=0, lt=30)


class IndependentReferenceDasha(ContractModel):
    lord: Literal["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_interval(self) -> IndependentReferenceDasha:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("independent Dasha boundaries must include UTC offsets")
        if self.end <= self.start:
            raise ValueError("independent Dasha end must be after its start")
        return self


class IndependentReferenceSnapshot(ContractModel):
    """Normalized output transcribed from software outside the active calculation chain."""

    source_system: str = Field(min_length=2)
    source_version: str = Field(min_length=1)
    source_artifact_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    method_profile_id: str
    d1_positions: dict[str, IndependentReferencePosition]
    varga_signs: dict[str, dict[str, str]]
    sav_by_sign: dict[str, int]
    shadbala_rupas: dict[str, float]
    mahadashas: list[IndependentReferenceDasha] = Field(min_length=9, max_length=9)

    @model_validator(mode="after")
    def validate_reference_coverage(self) -> IndependentReferenceSnapshot:
        supported_external_systems = {
            "jagannatha hora",
            "parashara's light",
        }
        if self.source_system.casefold() not in supported_external_systems:
            raise ValueError("independent reference uses an unsupported external source system")
        expected_bodies = {
            "Lagna",
            "Sun",
            "Moon",
            "Mars",
            "Mercury",
            "Jupiter",
            "Venus",
            "Saturn",
            "Rahu",
            "Ketu",
        }
        if set(self.d1_positions) != expected_bodies:
            raise ValueError("independent reference requires all D1 bodies")
        expected_vargas = set(INDEPENDENT_REFERENCE_VARGA_IDS)
        if set(self.varga_signs) != expected_vargas:
            raise ValueError("independent reference requires every supported non-D1 varga")
        if any(set(positions) != expected_bodies for positions in self.varga_signs.values()):
            raise ValueError("independent reference requires all bodies in every supported varga")
        if set(self.sav_by_sign) != set(
            [
                "Aries",
                "Taurus",
                "Gemini",
                "Cancer",
                "Leo",
                "Virgo",
                "Libra",
                "Scorpio",
                "Sagittarius",
                "Capricorn",
                "Aquarius",
                "Pisces",
            ]
        ):
            raise ValueError("independent reference requires SAV for all signs")
        if set(self.shadbala_rupas) != {
            "Sun",
            "Moon",
            "Mars",
            "Mercury",
            "Jupiter",
            "Venus",
            "Saturn",
        }:
            raise ValueError("independent reference requires seven-graha Shadbala")
        expected_dasha_lords = {
            "Sun",
            "Moon",
            "Mars",
            "Mercury",
            "Jupiter",
            "Venus",
            "Saturn",
            "Rahu",
            "Ketu",
        }
        if {period.lord for period in self.mahadashas} != expected_dasha_lords:
            raise ValueError("independent reference requires one complete nine-lord Dasha cycle")
        for current, following in zip(self.mahadashas, self.mahadashas[1:], strict=False):
            if current.end != following.start:
                raise ValueError("independent Mahadasha boundaries must be contiguous")
        return self


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
    uncertainty_interval: TimeRange | None = None
    resolution_seconds: int = Field(gt=0)
    changed_fields: list[str] = Field(min_length=1)
    before_fingerprint: str
    after_fingerprint: str


class InputSensitivityAssessment(ContractModel):
    schema_version: Literal["vedicdust-input-sensitivity/1.1.0"] = (
        "vedicdust-input-sensitivity/1.1.0"
    )
    policy_id: Literal["vedicdust-fact-sensitivity/1.0.0"] = "vedicdust-fact-sensitivity/1.0.0"
    scan_status: Literal["complete", "partial", "failed"]
    changed_fields: list[str] = Field(default_factory=list)
    scan_error_count: int = Field(default=0, ge=0)
    timing_boundary_scan_status: Literal["complete", "partial", "failed", "not_run"] = "not_run"
    timing_boundary_sample_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_scan_status(self) -> InputSensitivityAssessment:
        if len(self.changed_fields) != len(set(self.changed_fields)):
            raise ValueError("input sensitivity changed fields must be unique")
        if self.scan_status == "complete" and self.scan_error_count:
            raise ValueError("complete sensitivity assessment cannot contain scan errors")
        if self.scan_status == "failed" and self.scan_error_count == 0:
            raise ValueError("failed sensitivity assessment requires a scan error")
        if self.timing_boundary_scan_status == "complete" and self.timing_boundary_sample_count < 2:
            raise ValueError("complete timing boundary scan requires at least two hypotheses")
        if self.timing_boundary_scan_status in {"failed", "not_run"} and (
            self.timing_boundary_sample_count
        ):
            raise ValueError("failed or unrun timing boundary scan cannot claim samples")
        return self


class LifeEvent(ContractModel):
    event_id: str
    episode_id: str
    category: str
    event_subtype: str | None = None
    interval: TimeRange
    date_precision: Literal["day", "month", "year", "range"]
    event_timezone_basis: Literal["unknown_event_location_utc_offset_envelope"]
    description: str
    role: Literal["calibration", "holdout"]
    evidence: EvidenceItem


class RectificationEvidenceObservation(ContractModel):
    observation_id: str
    component: Literal[
        "natal_promise",
        "dasha",
        "varga",
        "double_transit",
        "node_transit",
        "sade_sati",
        "kp_sub_lord",
    ]
    outcome: Literal["support", "contradiction", "missing"]
    weight: float = Field(ge=0, le=1)
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_weight_semantics(self) -> RectificationEvidenceObservation:
        if self.outcome == "missing" and self.weight != 0:
            raise ValueError("missing rectification evidence must have zero weight")
        if self.outcome != "missing" and self.weight <= 0:
            raise ValueError("support or contradiction evidence must have positive weight")
        return self


class RectificationEventSemanticFacts(ContractModel):
    occurrence: Literal["occurred", "ongoing", "uncertain"] = "occurred"
    agency: Literal["active", "passive", "mixed", "unknown"] = "unknown"
    impact: Literal["major", "moderate", "minor", "unknown"] = "unknown"
    date_confidence: Literal["year", "month", "day", "unknown"] = "unknown"


class RectificationSemanticAdjustment(ContractModel):
    applied: bool = False
    component_multipliers: dict[str, float] = Field(default_factory=dict)
    used_fields: list[str] = Field(default_factory=list)
    context_only_fields: list[str] = Field(default_factory=list)
    reason: str = ""


class CandidateEvidenceScore(ContractModel):
    event_id: str
    episode_id: str
    event_fingerprint: str | None = None
    event_subtype: str | None = None
    semantic_facts: RectificationEventSemanticFacts | None = None
    semantic_adjustment: RectificationSemanticAdjustment | None = None
    role: Literal["calibration", "holdout"]
    score: float = Field(ge=-1, le=1)
    support_score: float = Field(ge=0, le=1)
    contradiction_score: float = Field(ge=0, le=1)
    selection_score: float = Field(ge=-1, le=1)
    selection_support_score: float = Field(ge=0, le=1)
    selection_contradiction_score: float = Field(ge=0, le=1)
    method_convergence_components: list[Literal["dasha", "varga"]] = Field(default_factory=list)
    method_convergence_layers: list[Literal["d1_period_activation", "domain_varga_activation"]] = (
        Field(default_factory=list)
    )
    method_convergence_count: int = Field(default=0, ge=0, le=2)
    method_convergence_met: bool = False
    observations: list[RectificationEvidenceObservation] = Field(min_length=1)
    rule_ids: list[str] = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)
    scoring_policy_id: str
    event_mapping_id: str
    event_timezone_basis: Literal["unknown_event_location_utc_offset_envelope"]
    explanation: str

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_selection_contract(cls, value: Any) -> Any:
        """Derive the selection contract when loading pre-1.20 Chart Records."""

        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        observations = data.get("observations") or []

        def observation_value(item: Any, snake_name: str, camel_name: str) -> Any:
            if isinstance(item, Mapping):
                if snake_name in item:
                    return item[snake_name]
                return item.get(camel_name)
            return getattr(item, snake_name, None)

        primary_components = RECTIFICATION_SELECTION_COMPONENTS
        if "selectionScore" not in data and "selection_score" not in data:
            support = round(
                min(
                    sum(
                        float(observation_value(item, "weight", "weight") or 0.0)
                        for item in observations
                        if observation_value(item, "outcome", "outcome") == "support"
                        and observation_value(item, "component", "component") in primary_components
                    ),
                    1,
                ),
                3,
            )
            contradiction = round(
                min(
                    sum(
                        float(observation_value(item, "weight", "weight") or 0.0)
                        for item in observations
                        if observation_value(item, "outcome", "outcome") == "contradiction"
                        and observation_value(item, "component", "component") in primary_components
                    ),
                    1,
                ),
                3,
            )
            data["selection_score"] = round(max(-1.0, min(1.0, support - contradiction)), 3)
            data["selection_support_score"] = support
            data["selection_contradiction_score"] = contradiction

        component_key = (
            "methodConvergenceComponents"
            if "methodConvergenceComponents" in data
            else "method_convergence_components"
        )
        if observations:
            raw_components = [
                component
                for component in ("dasha", "varga")
                if any(
                    observation_value(item, "outcome", "outcome") == "support"
                    and observation_value(item, "component", "component") == component
                    for item in observations
                )
            ]
        elif component_key in data:
            supplied_components = {str(component) for component in data.get(component_key) or []}
            raw_components = [
                component for component in ("dasha", "varga") if component in supplied_components
            ]
        else:
            raw_components = []
        components = raw_components
        layers = [
            layer
            for component, layer in (
                ("dasha", "d1_period_activation"),
                ("varga", "domain_varga_activation"),
            )
            if component in components
        ]
        data.pop("methodConvergenceFamilies", None)
        data.pop("method_convergence_families", None)
        data.pop("methodConvergenceComponents", None)
        data.pop("methodConvergenceLayers", None)
        data.pop("methodConvergenceCount", None)
        data.pop("methodConvergenceMet", None)
        data["method_convergence_components"] = components
        data["method_convergence_layers"] = layers
        data["method_convergence_count"] = len(layers)
        data["method_convergence_met"] = (
            "dasha" in components
            and len(layers) >= RECTIFICATION_SCORING_POLICY.minimum_evidence_layers_per_event
        )
        return data

    @model_validator(mode="after")
    def validate_score_reconciliation(self) -> CandidateEvidenceScore:
        observation_ids = [item.observation_id for item in self.observations]
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("rectification evidence contains duplicate observation ids")
        support = round(
            min(sum(item.weight for item in self.observations if item.outcome == "support"), 1),
            3,
        )
        contradiction = round(
            min(
                sum(item.weight for item in self.observations if item.outcome == "contradiction"),
                1,
            ),
            3,
        )
        expected_score = round(max(-1.0, min(1.0, support - contradiction)), 3)
        if self.support_score != support:
            raise ValueError("rectification support score does not match observations")
        if self.contradiction_score != contradiction:
            raise ValueError("rectification contradiction score does not match observations")
        if self.score != expected_score:
            raise ValueError("rectification net score does not match observations")
        selection_components = RECTIFICATION_SELECTION_COMPONENTS
        selection_support = round(
            min(
                sum(
                    item.weight
                    for item in self.observations
                    if item.outcome == "support" and item.component in selection_components
                ),
                1,
            ),
            3,
        )
        selection_contradiction = round(
            min(
                sum(
                    item.weight
                    for item in self.observations
                    if item.outcome == "contradiction" and item.component in selection_components
                ),
                1,
            ),
            3,
        )
        expected_selection_score = round(
            max(-1.0, min(1.0, selection_support - selection_contradiction)),
            3,
        )
        if self.selection_support_score != selection_support:
            raise ValueError("rectification selection support does not match primary observations")
        if self.selection_contradiction_score != selection_contradiction:
            raise ValueError(
                "rectification selection contradiction does not match primary observations"
            )
        if self.selection_score != expected_selection_score:
            raise ValueError("rectification selection score does not match primary observations")
        if len(self.method_convergence_components) != len(set(self.method_convergence_components)):
            raise ValueError("rectification method convergence components must be unique")
        if len(self.method_convergence_layers) != len(set(self.method_convergence_layers)):
            raise ValueError("rectification method convergence layers must be unique")
        expected_layers = []
        if "dasha" in self.method_convergence_components:
            expected_layers.append("d1_period_activation")
        if "varga" in self.method_convergence_components:
            expected_layers.append("domain_varga_activation")
        if self.method_convergence_layers != expected_layers:
            raise ValueError("rectification method convergence layers do not match components")
        if self.method_convergence_count != len(self.method_convergence_layers):
            raise ValueError("rectification method convergence count does not match layers")
        expected_convergence = (
            "dasha" in self.method_convergence_components
            and self.method_convergence_count
            >= RECTIFICATION_SCORING_POLICY.minimum_evidence_layers_per_event
        )
        if self.method_convergence_met != expected_convergence:
            raise ValueError("rectification method convergence flag does not match count")
        return self


class CandidatePlaceHypothesis(ContractModel):
    label: str | None = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone_id: str = Field(min_length=1)


class CandidateInterval(ContractModel):
    candidate_id: str
    interval: TimeRange
    representative_moment: datetime
    fingerprint: str
    hypothesis_axes: list[Literal["time", "place"]] = Field(default_factory=lambda: ["time"])
    place_hypothesis: CandidatePlaceHypothesis | None = None
    evidence_scores: list[CandidateEvidenceScore] = Field(default_factory=list)
    aggregate_score: float | None = None
    convergent_calibration_event_count: int = Field(default=0, ge=0)
    boundary_resolution_seconds: int = Field(default=60, gt=0)
    left_boundary_uncertainty: TimeRange | None = None
    eligible: bool = True
    exclusion_reason: str | None = None
    ayanamsa_risk: Literal["none", "medium", "high"] = "none"
    vimshottari_dasha_score: float | None = None
    chara_dasha_score: float | None = None
    dasha_system_agreement: Literal["agrees", "disagrees", "not_applicable"] = "not_applicable"
    holdout_period_boundary_checked: bool = False
    holdout_period_stable_within_interval: bool | None = None
    holdout_period_audit_resolution_seconds: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_representative_moment(self) -> CandidateInterval:
        if not self.interval.start <= self.representative_moment < self.interval.end:
            raise ValueError("representative moment must be inside the candidate interval")
        if len(self.hypothesis_axes) != len(set(self.hypothesis_axes)):
            raise ValueError("candidate hypothesis axes must be unique")
        if "place" in self.hypothesis_axes and self.place_hypothesis is None:
            raise ValueError("place-axis candidate requires a place hypothesis")
        if self.place_hypothesis is not None and "place" not in self.hypothesis_axes:
            raise ValueError("place hypothesis requires the place axis")
        if (
            self.holdout_period_boundary_checked
            and self.holdout_period_stable_within_interval is None
        ):
            raise ValueError("checked holdout period boundary requires a stability result")
        return self


class RectificationDecision(ContractModel):
    status: Literal[
        "not_required",
        "input_resolution_required",
        "calculation_failed",
        "collecting_evidence",
        "comparing_candidates",
        "bounded_interval",
        "multiple_equivalent",
        "underdetermined",
    ]
    selected_candidate_ids: list[str] = Field(default_factory=list)
    resulting_interval: TimeRange | None = None
    resulting_intervals: list[TimeRange] = Field(default_factory=list)
    confidence: ConfidenceGrade
    reasons: list[str] = Field(default_factory=list)
    holdout_result: Literal["passed", "failed", "inconclusive", "not_run"] = "not_run"
    unresolved_questions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result_shape(self) -> RectificationDecision:
        if len(self.selected_candidate_ids) != len(set(self.selected_candidate_ids)):
            raise ValueError("rectification decision candidate ids must be unique")
        if self.status == "bounded_interval":
            if len(self.selected_candidate_ids) != 1:
                raise ValueError("bounded-interval decision requires exactly one candidate")
            if self.resulting_interval is None:
                raise ValueError("bounded-interval decision requires a resulting interval")
            if self.resulting_intervals:
                raise ValueError("bounded-interval decision cannot contain multiple intervals")
            if self.holdout_result != "passed":
                raise ValueError("bounded-interval decision requires a passed holdout event")
        elif self.status == "multiple_equivalent":
            if len(self.selected_candidate_ids) < 2:
                raise ValueError("multiple-equivalent decision requires at least two candidates")
            if len(self.resulting_intervals) != len(self.selected_candidate_ids):
                raise ValueError("multiple-equivalent decision requires one interval per candidate")
            if self.resulting_interval is not None:
                raise ValueError("multiple-equivalent decision cannot claim one resulting interval")
            if self.holdout_result != "passed":
                raise ValueError("multiple-equivalent decision requires a passed holdout event")
        else:
            if self.selected_candidate_ids:
                raise ValueError(
                    "selected candidates are reserved for bounded or equivalent decisions"
                )
            if self.resulting_interval is not None:
                raise ValueError("only bounded-interval decisions can claim one resulting interval")
            if self.resulting_intervals:
                raise ValueError(
                    "resulting intervals are reserved for multiple-equivalent decisions"
                )
        return self


class RectificationRoundCandidateMetrics(ContractModel):
    candidate_interval_count: int = Field(ge=0)
    equivalence_class_count: int = Field(ge=0)
    leader_candidate_id: str | None = None
    leader_score: float | None = Field(default=None, ge=-1, le=1)
    leader_margin: float | None = Field(default=None, ge=0, le=2)


class RectificationRoundAnsweredEvent(ContractModel):
    question_id: str | None = None
    event_id: str | None = None
    episode_id: str | None = None
    episode_relation: Literal["primary", "corroborating"] | None = None
    event_fingerprint: str | None = None
    category: str | None = None
    event_subtype: str | None = None
    date: str | None = None
    date_precision: Literal["day", "month", "year", "range"] | None = None
    role: (
        Literal[
            "calibration",
            "holdout",
            "calibration_context",
            "holdout_context",
            "context_only",
        ]
        | None
    ) = None


class RectificationRoundEvidenceImpact(ContractModel):
    event_id: str | None = None
    role: Literal["calibration", "holdout"] | None = None
    scored_candidate_classes: int = Field(ge=0)
    minimum_score: float | None = Field(default=None, ge=-1, le=1)
    maximum_score: float | None = Field(default=None, ge=-1, le=1)
    score_spread: float | None = Field(default=None, ge=0, le=2)
    required_spread: float = Field(ge=0, le=2)
    discriminating: bool


class RectificationRoundDecisionSummary(ContractModel):
    outcome: Literal[
        "bounded_candidate_selected",
        "holdout_failed",
        "holdout_inconclusive",
        "candidate_scores_separated",
        "correlated_episode_recorded",
        "evidence_recorded_without_required_margin",
    ]
    status: str = Field(min_length=1)
    next_action: str | None = None
    selection_blockers: list[str] = Field(default_factory=list)
    holdout_result: Literal["passed", "failed", "inconclusive", "not_run"] = "not_run"
    selected_candidate_id: str | None = None
    equivalent_candidate_ids: list[str] = Field(default_factory=list)
    reason: str | None = None


class RectificationRoundRecord(ContractModel):
    schema_version: Literal["rectification-round-decision/v1"] = "rectification-round-decision/v1"
    round: int = Field(gt=0)
    chart_revision: int = Field(ge=0)
    answered_question: RectificationRoundAnsweredEvent
    candidate_state: dict[Literal["before", "after"], RectificationRoundCandidateMetrics]
    evidence_impact: RectificationRoundEvidenceImpact
    decision: RectificationRoundDecisionSummary

    @model_validator(mode="after")
    def validate_candidate_state(self) -> RectificationRoundRecord:
        if set(self.candidate_state) != {"before", "after"}:
            raise ValueError("rectification round requires before and after candidate metrics")
        return self


class RectificationRecord(ContractModel):
    schema_version: Literal["vedicdust-rectification/1.7.0"] = "vedicdust-rectification/1.7.0"
    selection_policy_id: str | None = None
    event_mapping_id: str | None = None
    holdout_policy_id: str | None = None
    method_maturity: Literal["product_hypothesis", "professionally_validated"] = (
        "product_hypothesis"
    )
    validation_status: Literal[
        "internal_regression_only",
        "independent_professional_review",
    ] = "internal_regression_only"
    source_ids: list[str] = Field(default_factory=list)
    professional_review_fixture_ids: list[str] = Field(default_factory=list)
    rectification_benchmark_fixture_ids: list[str] = Field(default_factory=list)
    reported_window: TimeRange | None = None
    life_events: list[LifeEvent] = Field(default_factory=list)
    candidates: list[CandidateInterval] = Field(default_factory=list)
    rounds: list[RectificationRoundRecord] = Field(default_factory=list)
    decision: RectificationDecision

    @model_validator(mode="after")
    def validate_method_assurance(self) -> RectificationRecord:
        event_ids = [event.event_id for event in self.life_events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("rectification life event ids must be unique")
        episode_ids = [event.episode_id for event in self.life_events]
        if len(episode_ids) != len(set(episode_ids)):
            raise ValueError(
                "rectification may retain only one scored life event per independent episode"
            )
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("rectification candidate ids must be unique")
        if self.reported_window is not None:
            escaped_candidates = [
                candidate.candidate_id
                for candidate in self.candidates
                if candidate.interval.start < self.reported_window.start
                or candidate.interval.end > self.reported_window.end
            ]
            if escaped_candidates:
                raise ValueError(
                    "rectification candidates must remain inside the reported window: "
                    + ", ".join(escaped_candidates)
                )
        candidates_by_id = {candidate.candidate_id: candidate for candidate in self.candidates}
        selected_ids = self.decision.selected_candidate_ids
        missing_selected_ids = [
            candidate_id for candidate_id in selected_ids if candidate_id not in candidates_by_id
        ]
        if missing_selected_ids:
            raise ValueError(
                "rectification decision references unknown candidate(s): "
                + ", ".join(missing_selected_ids)
            )
        if self.decision.status == "bounded_interval":
            selected = candidates_by_id[selected_ids[0]]
            if self.decision.resulting_interval != selected.interval:
                raise ValueError(
                    "bounded rectification interval must equal the selected candidate interval"
                )
        elif self.decision.status == "multiple_equivalent":
            expected_intervals = [
                candidates_by_id[candidate_id].interval for candidate_id in selected_ids
            ]
            if self.decision.resulting_intervals != expected_intervals:
                raise ValueError(
                    "equivalent rectification intervals must match selected candidates in order"
                )
        dasha_agreements = {candidate.dasha_system_agreement for candidate in self.candidates}
        if len(dasha_agreements) > 1:
            raise ValueError(
                "rectification candidates must share one scan-level dasha system agreement"
            )
        if len(self.professional_review_fixture_ids) != len(
            set(self.professional_review_fixture_ids)
        ):
            raise ValueError("rectification professional review fixtures must be unique")
        if len(self.rectification_benchmark_fixture_ids) != len(
            set(self.rectification_benchmark_fixture_ids)
        ):
            raise ValueError("rectification benchmark fixtures must be unique")
        professionally_reviewed = (
            self.method_maturity == "professionally_validated"
            and self.validation_status == "independent_professional_review"
        )
        if (self.method_maturity == "professionally_validated") != (
            self.validation_status == "independent_professional_review"
        ):
            raise ValueError(
                "professional rectification maturity requires independent professional review"
            )
        if professionally_reviewed and (
            not self.professional_review_fixture_ids or not self.rectification_benchmark_fixture_ids
        ):
            raise ValueError(
                "professionally reviewed rectification requires professional review and "
                "source-blind benchmark fixtures"
            )
        if not professionally_reviewed and (
            self.professional_review_fixture_ids or self.rectification_benchmark_fixture_ids
        ):
            raise ValueError(
                "professional review and benchmark fixtures are reserved for professionally "
                "reviewed rectification"
            )
        if (
            not professionally_reviewed
            and self.decision.status in {"bounded_interval", "multiple_equivalent"}
            and self.decision.confidence.rank > ConfidenceGrade.PROVISIONAL.rank
        ):
            raise ValueError(
                "internally validated rectification cannot exceed provisional confidence"
            )
        return self


class ChartRecord(ContractModel):
    schema_version: Literal["vedicdust-chart-record/1.6.0"] = "vedicdust-chart-record/1.6.0"
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
    input_sensitivity: InputSensitivityAssessment | None = None
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

    @model_validator(mode="before")
    @classmethod
    def migrate_supported_additive_versions(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if payload.get("schemaVersion") in {
            "vedicdust-chart-record/1.3.0",
            "vedicdust-chart-record/1.4.0",
            "vedicdust-chart-record/1.5.0",
        }:
            payload["schemaVersion"] = "vedicdust-chart-record/1.6.0"
        rectification = payload.get("rectification")
        if isinstance(rectification, dict) and rectification.get("schemaVersion") in {
            "vedicdust-rectification/1.1.0",
            "vedicdust-rectification/1.2.0",
            "vedicdust-rectification/1.3.0",
            "vedicdust-rectification/1.4.0",
            "vedicdust-rectification/1.5.0",
            "vedicdust-rectification/1.6.0",
        }:
            migrated_rectification = dict(rectification)
            migrated_rectification["schemaVersion"] = "vedicdust-rectification/1.7.0"
            migrated_rectification.setdefault("rectificationBenchmarkFixtureIds", [])
            migrated_events = []
            for raw_event in migrated_rectification.get("lifeEvents") or []:
                if not isinstance(raw_event, dict):
                    migrated_events.append(raw_event)
                    continue
                event = dict(raw_event)
                event.setdefault("episodeId", event.get("eventId"))
                event.setdefault(
                    "eventTimezoneBasis",
                    "unknown_event_location_utc_offset_envelope",
                )
                migrated_events.append(event)
            migrated_rectification["lifeEvents"] = migrated_events
            migrated_candidates = []
            for raw_candidate in migrated_rectification.get("candidates") or []:
                if not isinstance(raw_candidate, dict):
                    migrated_candidates.append(raw_candidate)
                    continue
                candidate = dict(raw_candidate)
                candidate["dashaSystemAgreement"] = "not_applicable"
                migrated_scores = []
                for raw_score in candidate.get("evidenceScores") or []:
                    if not isinstance(raw_score, dict):
                        migrated_scores.append(raw_score)
                        continue
                    score = dict(raw_score)
                    score.setdefault("episodeId", score.get("eventId"))
                    score.setdefault(
                        "eventTimezoneBasis",
                        "unknown_event_location_utc_offset_envelope",
                    )
                    migrated_scores.append(score)
                candidate["evidenceScores"] = migrated_scores
                migrated_candidates.append(candidate)
            migrated_rectification["candidates"] = migrated_candidates
            payload["rectification"] = migrated_rectification
        return payload

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
        if self.status in calculated_states and self.input_sensitivity is None:
            raise ValueError("calculated chart records require an input sensitivity assessment")
        if self.status == "ready_for_judgement" and any(
            check.status == "failed" for check in self.quality_checks
        ):
            raise ValueError(
                "chart record with failed quality checks cannot be ready for judgement"
            )
        return self


class SynastrySubject(ContractModel):
    role: Literal["A", "B"]
    label: str
    chart_record_id: str
    chart_revision: int = Field(ge=1)
    subject_id: str


class SynastryScope(ContractModel):
    relationship_type: str | None = None
    current_stage: str | None = None
    question: str | None = None


class SynastryOverlay(ContractModel):
    overlay_id: str
    source_role: Literal["A", "B"]
    source_object_id: str
    target_role: Literal["A", "B"]
    target_house: int = Field(ge=1, le=12)
    source_sign_index: int = Field(ge=0, le=11)
    target_lagna_sign_index: int = Field(ge=0, le=11)
    derivation_model: Literal["whole-sign-overlay"] = "whole-sign-overlay"


class SynastryContact(ContractModel):
    contact_id: str
    source_role: Literal["A", "B"]
    source_object_id: str
    target_role: Literal["A", "B"]
    target_object_id: str
    contact_type: Literal[
        "conjunction",
        "seventh_drishti",
        "mars_fourth_drishti",
        "mars_eighth_drishti",
        "jupiter_fifth_drishti",
        "jupiter_ninth_drishti",
        "saturn_third_drishti",
        "saturn_tenth_drishti",
    ]
    source_sign_index: int = Field(ge=0, le=11)
    target_sign_index: int = Field(ge=0, le=11)
    derivation_model: Literal["parashari-graha-drishti-1.0.0"] = "parashari-graha-drishti-1.0.0"


class SynastryContext(ContractModel):
    schema_version: Literal["vedicdust-synastry-context/1.0.0"] = "vedicdust-synastry-context/1.0.0"
    synastry_context_id: str
    reading_session_id: str
    generated_at: datetime
    method_profile_id: str
    subjects: list[SynastrySubject] = Field(min_length=2, max_length=2)
    scope: SynastryScope
    overlays: list[SynastryOverlay]
    contacts: list[SynastryContact]
    quality_checks: list[QualityCheck]
    limitations: list[str] = Field(default_factory=list)
    status: Literal["ready_for_judgement", "blocked"]

    @model_validator(mode="after")
    def validate_context(self) -> SynastryContext:
        roles = [subject.role for subject in self.subjects]
        if sorted(roles) != ["A", "B"]:
            raise ValueError("synastry context requires one A subject and one B subject")
        if len({overlay.overlay_id for overlay in self.overlays}) != len(self.overlays):
            raise ValueError("synastry context contains duplicate overlay ids")
        if len({contact.contact_id for contact in self.contacts}) != len(self.contacts):
            raise ValueError("synastry context contains duplicate contact ids")
        has_failure = any(check.status == "failed" for check in self.quality_checks)
        if has_failure != (self.status == "blocked"):
            raise ValueError("synastry status must agree with failed quality checks")
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
        "input_resolution_required",
        "calculation_failed",
        "collecting_evidence",
        "comparing_candidates",
        "bounded_interval",
        "multiple_equivalent",
        "underdetermined",
    ]
    report_status: Literal["not_started", "in_progress", "ready", "blocked"] = "not_started"


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
    judgement_unit_id: str
    conclusion_id: str
    judgement_code: str
    title: str
    plain_statement: str
    technical_statement: str
    real_world_expressions: list[str] = Field(default_factory=list)
    user_relevance: str | None = None
    conditions: list[str] = Field(default_factory=list)
    supporting_fact_ids: list[str] = Field(default_factory=list)
    context_fact_ids: list[str] = Field(default_factory=list)
    counter_fact_ids: list[str] = Field(default_factory=list)
    counter_statements: list[str] = Field(default_factory=list)
    timing_fact_ids: list[str] = Field(default_factory=list)
    timing_period_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(min_length=1)
    evidence_confidence: ConfidenceGrade
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
        if bool(self.counter_fact_ids) != bool(self.counter_statements):
            raise ValueError("counter facts and readable counter statements must agree")
        for label, values in (
            ("supporting facts", self.supporting_fact_ids),
            ("context facts", self.context_fact_ids),
            ("counter facts", self.counter_fact_ids),
            ("timing facts", self.timing_fact_ids),
            ("timing periods", self.timing_period_ids),
            ("rules", self.rule_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"claim contains duplicate {label}")
        evidence_sets = (
            set(self.supporting_fact_ids),
            set(self.context_fact_ids),
            set(self.counter_fact_ids),
        )
        if any(
            left & right
            for index, left in enumerate(evidence_sets)
            for right in evidence_sets[index + 1 :]
        ):
            raise ValueError("claim fact roles must be disjoint")
        if not any((self.supporting_fact_ids, self.context_fact_ids, self.timing_fact_ids)):
            raise ValueError("claim requires support, context, or timing facts")
        return self


class ClaimGraph(ContractModel):
    schema_version: Literal["vedicdust-claim-graph/1.6.0"] = "vedicdust-claim-graph/1.6.0"
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
        conclusion_ids = [claim.conclusion_id for claim in self.claims]
        if len(conclusion_ids) != len(set(conclusion_ids)):
            raise ValueError("claim graph cannot publish one conclusion more than once")
        return self


class JudgementRuleContext(ContractModel):
    rule_id: str
    title: str
    topic: str
    output_code: str
    evidence_class: EvidenceClass
    source_ids: list[str] = Field(min_length=1)
    required_evidence_layers: list[
        Literal["natal_promise", "capacity", "varga_confirmation", "timing", "user_testimony"]
    ] = Field(default_factory=list)
    status: Literal["draft", "provisional", "validated"]
    judgement_use: Literal["context_only", "traditional_tendency", "directional"]
    evaluation_status: Literal["eligible", "ineligible"]
    matched_fact_ids: list[str] = Field(default_factory=list)
    failed_predicates: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class PresentationPriorityReason(ContractModel):
    """Auditable contribution to report salience, never an astrological strength score."""

    reason_code: Literal[
        "baseline",
        "requested_topic",
        "sav_deviation_salience",
        "natal_aspect_salience",
        "eligible_varga",
    ]
    applied_points: int = Field(ge=0, le=100)
    evidence_fact_ids: list[str] = Field(default_factory=list)
    detail: str = Field(min_length=3)


class JudgementPresentationPolicy(ContractModel):
    """Versioned product policy controlling report breadth and ordering."""

    policy_id: Literal["vedicdust-presentation-selection/1.0.0"] = (
        "vedicdust-presentation-selection/1.0.0"
    )
    score_semantics: Literal["presentation_salience_not_astrological_strength"] = (
        "presentation_salience_not_astrological_strength"
    )
    foundation_always_included: Literal[True] = True
    requested_topics_first: Literal[True] = True
    timing_claims_for_requested_topics_only: Literal[True] = True
    structural_topic_limit: Literal[8] = 8
    total_claim_limit: Literal[10] = 10
    minimum_structural_coverage: Literal[5] = 5
    foundation_baseline: Literal[95] = 95
    domain_baseline: Literal[45] = 45
    requested_topic_target: Literal[100] = 100
    sav_neutral_reference: float = Field(default=28.0, ge=28.0, le=28.0)
    sav_deviation_multiplier: Literal[3] = 3
    sav_deviation_cap: Literal[24] = 24
    aspect_points_per_fact: Literal[2] = 2
    aspect_points_cap: Literal[12] = 12
    eligible_varga_boost: Literal[8] = 8


class JudgementTopicContext(ContractModel):
    topic_id: str
    title: str
    purpose: str
    requested: bool = False
    priority_score: int = Field(ge=0, le=100)
    priority_reasons: list[PresentationPriorityReason] = Field(min_length=1)
    rule_ids: list[str] = Field(min_length=1)
    natal_fact_ids: list[str] = Field(default_factory=list)
    capacity_fact_ids: list[str] = Field(default_factory=list)
    varga_fact_ids: list[str] = Field(default_factory=list)
    timing_fact_ids: list[str] = Field(default_factory=list)
    timing_period_ids: list[str] = Field(default_factory=list)
    eligible_vargas: list[str] = Field(default_factory=list)
    evidence_layers: list[Literal["natal_promise", "capacity", "varga_confirmation", "timing"]] = (
        Field(default_factory=list)
    )
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_presentation_priority(self) -> JudgementTopicContext:
        reason_codes = [reason.reason_code for reason in self.priority_reasons]
        if len(reason_codes) != len(set(reason_codes)):
            raise ValueError("topic presentation priority contains duplicate reason codes")
        if sum(reason.applied_points for reason in self.priority_reasons) != self.priority_score:
            raise ValueError("topic presentation priority reasons do not sum to priority score")
        topic_fact_ids = set(
            self.natal_fact_ids
            + self.capacity_fact_ids
            + self.varga_fact_ids
            + self.timing_fact_ids
        )
        unknown_reason_facts = sorted(
            {
                fact_id
                for reason in self.priority_reasons
                for fact_id in reason.evidence_fact_ids
                if fact_id not in topic_fact_ids
            }
        )
        if unknown_reason_facts:
            raise ValueError(
                "topic presentation priority references facts outside its evidence bundle: "
                + ", ".join(unknown_reason_facts)
            )
        return self


class JudgementFinding(ContractModel):
    """One deterministic, fact-bound observation produced by the judgement kernel."""

    finding_id: str = Field(pattern=r"^finding\.[a-z0-9._-]+$")
    finding_code: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    rule_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    polarity: Literal["supportive", "challenging", "context"]
    weight: float = Field(gt=0, le=1)
    fact_ids: list[str] = Field(min_length=1)
    timing_period_ids: list[str] = Field(default_factory=list)
    technical_statement: str = Field(min_length=3)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_finding_contract(self) -> JudgementFinding:
        if len(self.fact_ids) != len(set(self.fact_ids)):
            raise ValueError("judgement finding contains duplicate facts")
        if len(self.timing_period_ids) != len(set(self.timing_period_ids)):
            raise ValueError("judgement finding contains duplicate timing periods")
        return self


class JudgementConclusion(ContractModel):
    """Backend-owned semantic result that a claim may select but cannot rewrite."""

    conclusion_id: str = Field(pattern=r"^conclusion\.[a-z0-9._-]+$")
    conclusion_code: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    direction: Literal["supportive", "mixed", "challenging", "descriptive"]
    scope: Literal["natal_promise", "capacity", "timing", "rectification", "context"]
    title: str = Field(min_length=3)
    plain_statement: str = Field(min_length=3)
    technical_statement: str = Field(min_length=3)
    user_relevance: str | None = None
    finding_ids: list[str] = Field(min_length=1)
    supporting_fact_ids: list[str] = Field(default_factory=list)
    context_fact_ids: list[str] = Field(default_factory=list)
    counter_fact_ids: list[str] = Field(default_factory=list)
    counter_statements: list[str] = Field(default_factory=list)
    timing_fact_ids: list[str] = Field(default_factory=list)
    timing_period_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(min_length=1)
    time_scope: TimeRange | None = None
    real_world_expressions: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    practical_implications: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    certainty_cap: Literal["high", "moderate", "low"]

    @model_validator(mode="after")
    def validate_conclusion_contract(self) -> JudgementConclusion:
        for label, values in (
            ("findings", self.finding_ids),
            ("supporting facts", self.supporting_fact_ids),
            ("context facts", self.context_fact_ids),
            ("counter facts", self.counter_fact_ids),
            ("timing facts", self.timing_fact_ids),
            ("timing periods", self.timing_period_ids),
            ("rules", self.rule_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"judgement conclusion contains duplicate {label}")
        evidence_sets = (
            set(self.supporting_fact_ids),
            set(self.context_fact_ids),
            set(self.counter_fact_ids),
        )
        if any(
            left & right
            for index, left in enumerate(evidence_sets)
            for right in evidence_sets[index + 1 :]
        ):
            raise ValueError("judgement conclusion fact roles must be disjoint")
        if not any((self.supporting_fact_ids, self.context_fact_ids, self.timing_fact_ids)):
            raise ValueError("judgement conclusion requires support, context, or timing facts")
        if bool(self.counter_fact_ids) != bool(self.counter_statements):
            raise ValueError("counter facts and readable counter statements must agree")
        if self.scope == "timing":
            if self.time_scope is None or not self.timing_period_ids:
                raise ValueError("timing conclusion requires an exact period and time scope")
        elif self.time_scope is not None or self.timing_fact_ids or self.timing_period_ids:
            raise ValueError("non-timing conclusion cannot carry timing evidence")
        return self


class JudgementUnit(ContractModel):
    """Backend-owned semantic allowance for one consultation topic."""

    unit_id: str = Field(pattern=r"^unit\.[a-z0-9._-]+$")
    topic_id: str
    primary_rule_id: str
    permitted_rule_ids: list[str] = Field(min_length=1)
    allowed_output_codes: list[str] = Field(min_length=1)
    allowed_scopes: list[
        Literal["natal_promise", "capacity", "timing", "rectification", "context"]
    ] = Field(min_length=1)
    natal_fact_ids: list[str] = Field(default_factory=list)
    capacity_fact_ids: list[str] = Field(default_factory=list)
    varga_fact_ids: list[str] = Field(default_factory=list)
    timing_fact_ids: list[str] = Field(default_factory=list)
    timing_period_ids: list[str] = Field(default_factory=list)
    findings: list[JudgementFinding] = Field(min_length=1)
    conclusions: list[JudgementConclusion] = Field(min_length=1)
    certainty_cap: Literal["high", "moderate", "low"]
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unit_contract(self) -> JudgementUnit:
        if self.primary_rule_id not in self.permitted_rule_ids:
            raise ValueError("judgement unit must permit its primary rule")
        for label, values in (
            ("permitted rules", self.permitted_rule_ids),
            ("output codes", self.allowed_output_codes),
            ("scopes", self.allowed_scopes),
            ("natal facts", self.natal_fact_ids),
            ("capacity facts", self.capacity_fact_ids),
            ("varga facts", self.varga_fact_ids),
            ("timing facts", self.timing_fact_ids),
            ("timing periods", self.timing_period_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"judgement unit contains duplicate {label}")
        finding_ids = [finding.finding_id for finding in self.findings]
        conclusion_ids = [conclusion.conclusion_id for conclusion in self.conclusions]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("judgement unit contains duplicate finding ids")
        if len(conclusion_ids) != len(set(conclusion_ids)):
            raise ValueError("judgement unit contains duplicate conclusion ids")
        available_facts = set(
            self.natal_fact_ids
            + self.capacity_fact_ids
            + self.varga_fact_ids
            + self.timing_fact_ids
        )
        for finding in self.findings:
            if finding.rule_id not in self.permitted_rule_ids:
                raise ValueError("judgement finding uses a rule outside its unit")
            if not set(finding.fact_ids) <= available_facts:
                raise ValueError("judgement finding uses facts outside its unit")
        available_findings = set(finding_ids)
        available_periods = set(self.timing_period_ids)
        certainty_rank = {"low": 0, "moderate": 1, "high": 2}
        for conclusion in self.conclusions:
            if certainty_rank[conclusion.certainty_cap] > certainty_rank[self.certainty_cap]:
                raise ValueError("judgement conclusion exceeds its unit certainty cap")
            if not set(conclusion.finding_ids) <= available_findings:
                raise ValueError("judgement conclusion uses unknown findings")
            if (
                not set(
                    conclusion.supporting_fact_ids
                    + conclusion.context_fact_ids
                    + conclusion.counter_fact_ids
                )
                <= available_facts
            ):
                raise ValueError("judgement conclusion uses facts outside its unit")
            if not set(conclusion.timing_fact_ids) <= set(self.timing_fact_ids):
                raise ValueError("judgement conclusion uses timing facts outside its unit")
            if not set(conclusion.timing_period_ids) <= available_periods:
                raise ValueError("judgement conclusion uses timing periods outside its unit")
            if not set(conclusion.rule_ids) <= set(self.permitted_rule_ids):
                raise ValueError("judgement conclusion uses rules outside its unit")
            if conclusion.scope not in self.allowed_scopes:
                raise ValueError("judgement conclusion uses a scope outside its unit")
        if not self.natal_fact_ids or not self.capacity_fact_ids:
            raise ValueError("judgement unit requires natal-promise and capacity facts")
        if "timing" in self.allowed_scopes and not self.timing_period_ids:
            raise ValueError("timing-enabled judgement unit requires exact periods")
        return self


class JudgementContext(ContractModel):
    schema_version: Literal["vedicdust-judgement-context/1.6.0"] = (
        "vedicdust-judgement-context/1.6.0"
    )
    chart_record_id: str
    chart_revision: int = Field(ge=1)
    method_profile_id: str
    generated_at: datetime
    requested_topics: list[str] = Field(default_factory=list)
    rule_pack_version: str
    presentation_policy: JudgementPresentationPolicy
    rules: list[JudgementRuleContext] = Field(min_length=1)
    global_gate_rule_ids: list[str] = Field(default_factory=list)
    topics: list[JudgementTopicContext] = Field(min_length=1)
    units: list[JudgementUnit] = Field(min_length=1)
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
        topic_ids = {topic.topic_id for topic in self.topics}
        unit_ids = [unit.unit_id for unit in self.units]
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("judgement context contains duplicate unit ids")
        unknown_unit_topics = sorted({unit.topic_id for unit in self.units} - topic_ids)
        if unknown_unit_topics:
            raise ValueError(
                "judgement units reference unknown topics: " + ", ".join(unknown_unit_topics)
            )
        unknown_unit_rules = sorted(
            {
                rule_id
                for unit in self.units
                for rule_id in unit.permitted_rule_ids
                if rule_id not in rule_ids
            }
        )
        if unknown_unit_rules:
            raise ValueError(
                "judgement units reference unknown rules: " + ", ".join(unknown_unit_rules)
            )
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


class GroundedNarrative(ContractModel):
    narrative_id: str
    kind: Literal["synthesis", "integration", "reflection"]
    text: str = Field(min_length=20, max_length=900)
    claim_ids: list[str] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_claim_references(self) -> GroundedNarrative:
        if len(self.claim_ids) != len(set(self.claim_ids)):
            raise ValueError("grounded narrative claim ids must be unique")
        return self


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
    narratives: list[GroundedNarrative] = Field(default_factory=list, max_length=2)
    priority: int = Field(default=100, ge=0)
    confidence_disclosure_required: bool = False


class ConsultationReportManifest(ContractModel):
    schema_version: Literal["vedicdust-report-manifest/1.0.0"] = "vedicdust-report-manifest/1.0.0"
    dossier_id: str | None = None
    chart_record_id: str
    chart_revision: int = Field(default=1, ge=1)
    claim_graph_version: Literal["vedicdust-claim-graph/1.6.0"]
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
    claim_graph_version: Literal["vedicdust-claim-graph/1.6.0"]
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
    evidence_confidence: ConfidenceGrade
    certainty: Literal["high", "moderate", "low"]
    supporting_fact_ids: list[str] = Field(default_factory=list)
    context_fact_ids: list[str] = Field(default_factory=list)
    counter_fact_ids: list[str] = Field(default_factory=list)
    counter_statements: list[str] = Field(default_factory=list)
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
    calculation_confidence: ConfidenceGrade
    input_stability: ConfidenceGrade


class AgentContext(ContractModel):
    schema_version: Literal["vedicdust-agent-context/1.5.0"] = "vedicdust-agent-context/1.5.0"
    dossier_id: str
    chart_record_id: str
    chart_revision: int = Field(ge=1)
    generated_at: datetime
    locale: Literal["zh", "en", "ja"]
    subject: SubjectContext
    reported_birth_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
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
