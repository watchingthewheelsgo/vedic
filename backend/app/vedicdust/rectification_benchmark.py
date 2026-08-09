from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from .event_time import event_utc_envelope
from .models import ChartRecord, ContractModel, TimeRange, ValidationFixtureReference
from .rectification_policy import (
    RECTIFICATION_EVENT_MAPPING_ID,
    RECTIFICATION_HOLDOUT_POLICY_ID,
    RECTIFICATION_SCORING_POLICY_ID,
)


RECTIFICATION_BENCHMARK_PROTOCOL_ID = "vedicdust-source-blind-rectification/1.1.0"
RECTIFICATION_BENCHMARK_ACCEPTANCE_POLICY_ID = (
    "vedicdust-rectification-benchmark-release-gate/1.1.0"
)
RECTIFICATION_BENCHMARK_RUN_RECEIPT_SCHEMA_VERSION = "vedicdust-rectification-run-receipt/1.0.0"
RECTIFICATION_BENCHMARK_BLIND_INPUT_SCHEMA_VERSION = "vedicdust-rectification-blind-input/1.0.0"
RECTIFICATION_BENCHMARK_RUNNER_ID = "vedicdust-production-runtime/1.0.0"
MINIMUM_PRIMARY_BENCHMARK_CASES = 30
MINIMUM_DECISIVE_RATE = 0.50
MINIMUM_FULL_COVERAGE_RATE = 0.90
MAXIMUM_FALSE_EXCLUSION_RATE = 0.10
MAXIMUM_MEDIAN_NARROWING_RATIO = 0.50
MINIMUM_INDEPENDENT_RECALL_CASES = 10
MINIMUM_DETERMINISTIC_MASK_CASES = 10
MINIMUM_SUBJECT_INTERVIEW_CASES = 10
MINIMUM_PRODUCT_LIKE_CASES = 10
DETERMINISTIC_WINDOW_MASK_PROTOCOL_ID = "vedicdust-deterministic-window-mask/1.0.0"


class RetainedBenchmarkArtifact(ContractModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    retained_at: datetime

    @model_validator(mode="after")
    def validate_retained_timestamp(self) -> RetainedBenchmarkArtifact:
        if self.retained_at.tzinfo is None or self.retained_at.utcoffset() is None:
            raise ValueError("retained benchmark artifact timestamp must include a UTC offset")
        return self


class RectificationBenchmarkBlindInput(ContractModel):
    """The complete evidence package visible to the source-blind run operator."""

    schema_version: Literal["vedicdust-rectification-blind-input/1.0.0"] = (
        RECTIFICATION_BENCHMARK_BLIND_INPUT_SCHEMA_VERSION
    )
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")
    birth_input: dict[str, object]
    life_events: list[dict[str, object]] = Field(min_length=4, max_length=5)
    reported_window: TimeRange
    reported_window_origin: Literal[
        "independent_subject_recall",
        "deterministic_truth_mask",
    ]
    event_evidence_origin: Literal["subject_interview", "public_documentary_record"]
    candidate_contrasts_exposed: bool = False

    @model_validator(mode="after")
    def validate_blind_payload(self) -> RectificationBenchmarkBlindInput:
        forbidden = _forbidden_truth_fields(
            {"birthInput": self.birth_input, "lifeEvents": self.life_events}
        )
        if forbidden:
            raise ValueError(
                "blind input contains target-bearing field(s): " + ", ".join(forbidden)
            )
        if self.candidate_contrasts_exposed:
            raise ValueError("blind input cannot expose candidate contrasts")
        required_birth_fields = {
            "birthDate",
            "birthTime",
            "birthPlace",
            "birthTimePrecision",
        }
        missing_birth_fields = sorted(required_birth_fields - self.birth_input.keys())
        if missing_birth_fields:
            raise ValueError(
                "blind input is missing birth field(s): " + ", ".join(missing_birth_fields)
            )
        if not str(self.birth_input.get("birthPlace") or "").strip():
            raise ValueError("blind input birth place cannot be empty")
        try:
            datetime.strptime(str(self.birth_input.get("birthDate") or ""), "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("blind input birth date must use YYYY-MM-DD") from exc
        if self.birth_input.get("birthTimePrecision") not in {
            "exact",
            "approximate",
            "part_of_day",
            "unknown",
        }:
            raise ValueError("blind input has an invalid birth-time precision")
        event_ids = [str(item.get("eventId") or "").strip() for item in self.life_events]
        if any(not event_id for event_id in event_ids):
            raise ValueError("every blind input life event must retain its eventId")
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("blind input contains duplicate life event ids")
        for item in self.life_events:
            missing_event_fields = [
                field
                for field in ("date", "category", "eventSubtype", "description")
                if not str(item.get(field) or "").strip()
            ]
            if missing_event_fields:
                raise ValueError(
                    f"blind input event {item.get('eventId')} is missing field(s): "
                    + ", ".join(missing_event_fields)
                )
            _blind_event_interval(item)
        return self


class RectificationBenchmarkRunReceipt(ContractModel):
    """Machine-produced binding between one blind input and one runtime output."""

    schema_version: Literal["vedicdust-rectification-run-receipt/1.0.0"] = (
        RECTIFICATION_BENCHMARK_RUN_RECEIPT_SCHEMA_VERSION
    )
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")
    runner_id: Literal["vedicdust-production-runtime/1.0.0"] = RECTIFICATION_BENCHMARK_RUNNER_ID
    engine_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    engine_source_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    working_tree_clean: bool
    run_operator_id: str = Field(min_length=3)
    run_started_at: datetime
    run_completed_at: datetime
    blind_input_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    chart_record_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    selection_policy_id: str
    event_mapping_id: str
    holdout_policy_id: str

    @model_validator(mode="after")
    def validate_run_timestamps(self) -> RectificationBenchmarkRunReceipt:
        for moment in (self.run_started_at, self.run_completed_at):
            if moment.tzinfo is None or moment.utcoffset() is None:
                raise ValueError("rectification run receipt timestamps must include UTC offsets")
        if self.run_completed_at < self.run_started_at:
            raise ValueError("rectification run receipt completed before it started")
        return self


class RectificationBenchmarkCase(ContractModel):
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")
    chart_record: RetainedBenchmarkArtifact
    blind_input: RetainedBenchmarkArtifact
    run_receipt: RetainedBenchmarkArtifact
    truth_interval: TimeRange
    truth_source_rating: Literal["AA", "A", "B", "C", "DD"]
    truth_source_reference: str = Field(min_length=3)
    truth_source_url: str | None = None
    truth_source_artifact: RetainedBenchmarkArtifact
    truth_commitment_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    truth_commitment_salt: str = Field(min_length=16)
    truth_committed_at: datetime
    run_started_at: datetime
    run_completed_at: datetime
    truth_revealed_at: datetime
    truth_custodian_id: str = Field(min_length=3)
    run_operator_id: str = Field(min_length=3)
    target_hidden_during_run: bool
    reported_window_origin: Literal[
        "independent_subject_recall",
        "deterministic_truth_mask",
    ]
    independent_recall_attested: bool = False
    masking_protocol_id: Literal["vedicdust-deterministic-window-mask/1.0.0"] | None = None
    masking_seed: str | None = Field(default=None, min_length=16)
    masking_window_minutes: Literal[120, 240] | None = None
    event_evidence_origin: Literal["subject_interview", "public_documentary_record"]
    events_collected_without_candidate_contrast: bool

    @model_validator(mode="after")
    def validate_blind_run_timeline(self) -> RectificationBenchmarkCase:
        moments = (
            self.truth_committed_at,
            self.run_started_at,
            self.run_completed_at,
            self.truth_revealed_at,
            self.truth_interval.start,
            self.truth_interval.end,
        )
        if any(moment.tzinfo is None or moment.utcoffset() is None for moment in moments):
            raise ValueError("rectification benchmark timestamps must include UTC offsets")
        if not (
            self.truth_source_artifact.retained_at
            <= self.truth_committed_at
            <= self.blind_input.retained_at
            <= self.run_started_at
            <= self.chart_record.retained_at
            <= self.run_receipt.retained_at
            <= self.run_completed_at
            <= self.truth_revealed_at
        ):
            raise ValueError("rectification benchmark blind-run timestamps are out of order")
        if self.truth_custodian_id == self.run_operator_id:
            raise ValueError("truth custodian and source-blind run operator must be distinct")
        if self.reported_window_origin == "independent_subject_recall":
            if not self.independent_recall_attested:
                raise ValueError("independent recall case requires a no-record-access attestation")
            if any(
                value is not None
                for value in (
                    self.masking_protocol_id,
                    self.masking_seed,
                    self.masking_window_minutes,
                )
            ):
                raise ValueError("independent recall case cannot carry deterministic mask fields")
        else:
            if self.independent_recall_attested:
                raise ValueError("deterministic mask cannot claim independent subject recall")
            if (
                self.masking_protocol_id != DETERMINISTIC_WINDOW_MASK_PROTOCOL_ID
                or self.masking_seed is None
                or self.masking_window_minutes is None
            ):
                raise ValueError("deterministic mask case requires its versioned mask contract")
        expected_commitment = rectification_truth_commitment(
            self.case_id,
            self.truth_interval,
            self.truth_source_rating,
            self.truth_source_reference,
            self.truth_source_artifact.sha256,
            self.reported_window_origin,
            self.independent_recall_attested,
            self.masking_protocol_id,
            self.masking_seed,
            self.masking_window_minutes,
            self.event_evidence_origin,
            self.truth_commitment_salt,
        )
        if self.truth_commitment_sha256 != expected_commitment:
            raise ValueError("rectification benchmark truth commitment does not match the reveal")
        return self


class RectificationBenchmarkArtifact(ContractModel):
    schema_version: Literal["vedicdust-rectification-benchmark/1.1.0"] = (
        "vedicdust-rectification-benchmark/1.1.0"
    )
    benchmark_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._/-]+$")
    protocol_id: Literal["vedicdust-source-blind-rectification/1.1.0"] = (
        RECTIFICATION_BENCHMARK_PROTOCOL_ID
    )
    created_at: datetime
    cases: list[RectificationBenchmarkCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cases(self) -> RectificationBenchmarkArtifact:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("rectification benchmark timestamp must include a UTC offset")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("rectification benchmark contains duplicate case ids")
        return self


class RectificationBenchmarkCaseResult(ContractModel):
    case_id: str
    chart_record_id: str | None = None
    source_rating: str
    reported_window_origin: str
    event_evidence_origin: str
    primary_eligible: bool
    protocol_failures: list[str] = Field(default_factory=list)
    output_failures: list[str] = Field(default_factory=list)
    decision_status: str | None = None
    outcome: Literal["hit", "partial", "miss", "abstained", "invalid"]
    truth_coverage: Literal["full", "partial", "none", "not_applicable"]
    predicted_intervals: list[TimeRange] = Field(default_factory=list)
    reported_window_minutes: float | None = Field(default=None, ge=0)
    predicted_union_minutes: float | None = Field(default=None, ge=0)
    narrowing_ratio: float | None = Field(default=None, ge=0)


class RectificationBenchmarkCohortMetrics(ContractModel):
    case_count: int = Field(ge=0)
    decisive_case_count: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    partial_count: int = Field(ge=0)
    miss_count: int = Field(ge=0)
    abstained_count: int = Field(ge=0)
    invalid_count: int = Field(ge=0)
    decisive_rate: float | None = Field(default=None, ge=0, le=1)
    full_coverage_rate: float | None = Field(default=None, ge=0, le=1)
    false_exclusion_rate: float | None = Field(default=None, ge=0, le=1)
    median_narrowing_ratio: float | None = Field(default=None, ge=0)


class RectificationBenchmarkReport(ContractModel):
    schema_version: Literal["vedicdust-rectification-benchmark-report/1.1.0"] = (
        "vedicdust-rectification-benchmark-report/1.1.0"
    )
    benchmark_id: str
    protocol_id: str
    acceptance_policy_id: Literal["vedicdust-rectification-benchmark-release-gate/1.1.0"] = (
        RECTIFICATION_BENCHMARK_ACCEPTANCE_POLICY_ID
    )
    evaluated_at: datetime
    cases: list[RectificationBenchmarkCaseResult]
    primary_case_count: int = Field(ge=0)
    primary_case_count_by_window_origin: dict[str, int]
    primary_case_count_by_event_origin: dict[str, int]
    cohort_metrics: dict[str, RectificationBenchmarkCohortMetrics]
    decisive_case_count: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    partial_count: int = Field(ge=0)
    miss_count: int = Field(ge=0)
    abstained_count: int = Field(ge=0)
    invalid_count: int = Field(ge=0)
    decisive_rate: float | None = Field(default=None, ge=0, le=1)
    full_coverage_rate: float | None = Field(default=None, ge=0, le=1)
    false_exclusion_rate: float | None = Field(default=None, ge=0, le=1)
    median_narrowing_ratio: float | None = Field(default=None, ge=0)
    release_gate_passed: bool
    release_gate_failures: list[str] = Field(default_factory=list)


def rectification_truth_commitment(
    case_id: str,
    interval: TimeRange,
    source_rating: str,
    source_reference: str,
    source_artifact_sha256: str,
    reported_window_origin: str,
    independent_recall_attested: bool,
    masking_protocol_id: str | None,
    masking_seed: str | None,
    masking_window_minutes: int | None,
    event_evidence_origin: str,
    salt: str,
) -> str:
    payload = {
        "caseId": case_id,
        "truthStartUtc": interval.start.astimezone(timezone.utc).isoformat(),
        "truthEndUtc": interval.end.astimezone(timezone.utc).isoformat(),
        "truthSourceRating": source_rating,
        "truthSourceReference": source_reference,
        "truthSourceArtifactSha256": source_artifact_sha256,
        "reportedWindowOrigin": reported_window_origin,
        "independentRecallAttested": independent_recall_attested,
        "maskingProtocolId": masking_protocol_id,
        "maskingSeed": masking_seed,
        "maskingWindowMinutes": masking_window_minutes,
        "eventEvidenceOrigin": event_evidence_origin,
        "salt": salt,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _forbidden_truth_fields(value: object, *, path: str = "$") -> list[str]:
    """Reject target-bearing fields from the package visible to the run operator."""

    forbidden_names = {
        "groundtruth",
        "knownbirthtime",
        "knownbirthinterval",
        "maskingseed",
        "targetbirthtime",
        "targetinterval",
        "truthinterval",
        "truthsource",
        "truthsourcesha256",
    }
    found: list[str] = []
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = str(raw_key)
            normalized = "".join(character for character in key.casefold() if character.isalnum())
            next_path = f"{path}.{key}"
            if normalized in forbidden_names:
                found.append(next_path)
            found.extend(_forbidden_truth_fields(item, path=next_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_forbidden_truth_fields(item, path=f"{path}[{index}]"))
    return found


def rectification_blind_input_binding_failures(
    blind_input: RectificationBenchmarkBlindInput,
    record: ChartRecord,
) -> list[str]:
    """Verify that a terminal record was built from the retained blind facts."""

    failures: list[str] = []
    birth = blind_input.birth_input
    assertion = record.birth_assertion
    expected_precision = {
        "exact": "reported_exact",
        "approximate": "approximate",
        "part_of_day": "broad_window",
        "unknown": "unknown",
    }[str(birth["birthTimePrecision"])]
    expected_time = str(birth.get("birthTime") or "").strip() or None
    if assertion.local_date != str(birth["birthDate"]):
        failures.append("runtime Chart Record uses a different reported birth date")
    if assertion.reported_local_time != expected_time:
        failures.append("runtime Chart Record uses a different reported birth time")
    if " ".join(assertion.reported_place.split()) != " ".join(str(birth["birthPlace"]).split()):
        failures.append("runtime Chart Record uses a different reported birth place")
    if assertion.time_certainty != expected_precision:
        failures.append("runtime Chart Record uses a different birth-time precision")
    if assertion.reported_time_window != blind_input.reported_window:
        failures.append("runtime Chart Record does not preserve the blinded reported window")

    rectification = record.rectification
    if rectification is None:
        failures.append("runtime Chart Record has no rectification evidence")
        return failures
    record_events = {event.event_id: event for event in rectification.life_events}
    blind_event_ids = {str(item["eventId"]) for item in blind_input.life_events}
    if blind_event_ids != set(record_events):
        failures.append("runtime Chart Record does not preserve the blinded life-event set")
        return failures
    for item in blind_input.life_events:
        event_id = str(item["eventId"])
        event = record_events[event_id]
        expected_interval, expected_date_precision = _blind_event_interval(item)
        if event.category != str(item["category"]):
            failures.append(f"runtime Chart Record changed category for event {event_id}")
        if event.event_subtype != str(item["eventSubtype"]):
            failures.append(f"runtime Chart Record changed subtype for event {event_id}")
        if event.date_precision != expected_date_precision or event.interval != expected_interval:
            failures.append(f"runtime Chart Record changed date for event {event_id}")
        expected_description = _normalized_event_description(
            str(item["description"]),
            str(item["date"]),
            str(item["category"]),
        )
        actual_description = _normalized_event_description(
            event.description,
            str(item["date"]),
            str(item["category"]),
        )
        if actual_description != expected_description:
            failures.append(f"runtime Chart Record changed description for event {event_id}")
    return failures


def _blind_event_interval(item: dict[str, object]) -> tuple[TimeRange, str]:
    raw_date = str(item.get("date") or "")
    try:
        if len(raw_date) == 4:
            year = int(raw_date)
            start = datetime(year, 1, 1)
            end = datetime(year + 1, 1, 1) - timedelta(seconds=1)
            precision = "year"
        elif len(raw_date) == 7:
            start = datetime.strptime(raw_date, "%Y-%m")
            end = (
                datetime(start.year + 1, 1, 1)
                if start.month == 12
                else datetime(start.year, start.month + 1, 1)
            ) - timedelta(seconds=1)
            precision = "month"
        elif len(raw_date) == 10:
            start = datetime.strptime(raw_date, "%Y-%m-%d")
            end = start + timedelta(days=1) - timedelta(seconds=1)
            precision = "day"
        else:
            raise ValueError
    except ValueError as exc:
        raise ValueError(f"blind input event date is invalid: {raw_date!r}") from exc
    event_start, event_end = event_utc_envelope(start, end)
    return TimeRange(start=event_start, end=event_end), precision


def _normalized_event_description(value: str, date_value: str, category: str) -> str:
    normalized = " ".join(value.split())
    prefix = f"{date_value} {category}:"
    if normalized.casefold().startswith(prefix.casefold()):
        normalized = normalized[len(prefix) :].strip()
    return normalized.casefold()


def evaluate_rectification_benchmark(
    artifact: RectificationBenchmarkArtifact,
    artifact_path: Path,
    *,
    evaluated_at: datetime | None = None,
) -> RectificationBenchmarkReport:
    results = [_evaluate_case(case, artifact_path.parent) for case in artifact.cases]
    primary = [case for case in results if case.primary_eligible]
    window_origin_counts = _counts(primary, "reported_window_origin")
    event_origin_counts = _counts(primary, "event_evidence_origin")
    cohort_metrics = {
        "window:independent_subject_recall": _cohort_metrics(
            [
                case
                for case in primary
                if case.reported_window_origin == "independent_subject_recall"
            ]
        ),
        "window:deterministic_truth_mask": _cohort_metrics(
            [case for case in primary if case.reported_window_origin == "deterministic_truth_mask"]
        ),
        "event:subject_interview": _cohort_metrics(
            [case for case in primary if case.event_evidence_origin == "subject_interview"]
        ),
        "event:public_documentary_record": _cohort_metrics(
            [case for case in primary if case.event_evidence_origin == "public_documentary_record"]
        ),
        "product:independent_recall_subject_interview": _cohort_metrics(
            [
                case
                for case in primary
                if case.reported_window_origin == "independent_subject_recall"
                and case.event_evidence_origin == "subject_interview"
            ]
        ),
    }
    decisive = [case for case in primary if case.outcome in {"hit", "partial", "miss"}]
    hits = [case for case in primary if case.outcome == "hit"]
    partials = [case for case in primary if case.outcome == "partial"]
    misses = [case for case in primary if case.outcome == "miss"]
    abstained = [case for case in primary if case.outcome == "abstained"]
    invalid = [case for case in primary if case.outcome == "invalid"]
    decisive_rate = _rate(len(decisive), len(primary))
    full_coverage_rate = _rate(len(hits), len(decisive))
    false_exclusion_rate = _rate(len(partials) + len(misses), len(decisive))
    narrowing_values = [
        case.narrowing_ratio for case in decisive if case.narrowing_ratio is not None
    ]
    release_failures: list[str] = []
    if len(primary) < MINIMUM_PRIMARY_BENCHMARK_CASES:
        release_failures.append(
            f"requires at least {MINIMUM_PRIMARY_BENCHMARK_CASES} source-blind AA cases"
        )
    if window_origin_counts.get("independent_subject_recall", 0) < MINIMUM_INDEPENDENT_RECALL_CASES:
        release_failures.append(
            f"requires at least {MINIMUM_INDEPENDENT_RECALL_CASES} independent-recall cases"
        )
    if window_origin_counts.get("deterministic_truth_mask", 0) < MINIMUM_DETERMINISTIC_MASK_CASES:
        release_failures.append(
            f"requires at least {MINIMUM_DETERMINISTIC_MASK_CASES} deterministic-mask cases"
        )
    if event_origin_counts.get("subject_interview", 0) < MINIMUM_SUBJECT_INTERVIEW_CASES:
        release_failures.append(
            f"requires at least {MINIMUM_SUBJECT_INTERVIEW_CASES} subject-interview cases"
        )
    product_like_case_count = cohort_metrics[
        "product:independent_recall_subject_interview"
    ].case_count
    if product_like_case_count < MINIMUM_PRODUCT_LIKE_CASES:
        release_failures.append(
            f"requires at least {MINIMUM_PRODUCT_LIKE_CASES} end-to-end product-like cases"
        )
    for cohort_name in (
        "window:independent_subject_recall",
        "window:deterministic_truth_mask",
        "event:subject_interview",
        "product:independent_recall_subject_interview",
    ):
        _append_cohort_release_failures(
            release_failures,
            cohort_name,
            cohort_metrics[cohort_name],
        )
    if decisive_rate is None or decisive_rate < MINIMUM_DECISIVE_RATE:
        release_failures.append(f"decisive rate must be at least {MINIMUM_DECISIVE_RATE:.0%}")
    if full_coverage_rate is None or full_coverage_rate < MINIMUM_FULL_COVERAGE_RATE:
        release_failures.append(
            f"full truth-coverage rate must be at least {MINIMUM_FULL_COVERAGE_RATE:.0%}"
        )
    if false_exclusion_rate is None or false_exclusion_rate > MAXIMUM_FALSE_EXCLUSION_RATE:
        release_failures.append(
            f"false-exclusion rate must be at most {MAXIMUM_FALSE_EXCLUSION_RATE:.0%}"
        )
    if invalid:
        release_failures.append("primary benchmark cannot contain invalid runtime outcomes")
    if not narrowing_values or median(narrowing_values) > MAXIMUM_MEDIAN_NARROWING_RATIO:
        release_failures.append(
            "median retained interval must be at most 50% of the reported window"
        )
    return RectificationBenchmarkReport(
        benchmarkId=artifact.benchmark_id,
        protocolId=artifact.protocol_id,
        evaluatedAt=evaluated_at or datetime.now(timezone.utc),
        cases=results,
        primaryCaseCount=len(primary),
        primaryCaseCountByWindowOrigin=window_origin_counts,
        primaryCaseCountByEventOrigin=event_origin_counts,
        cohortMetrics=cohort_metrics,
        decisiveCaseCount=len(decisive),
        hitCount=len(hits),
        partialCount=len(partials),
        missCount=len(misses),
        abstainedCount=len(abstained),
        invalidCount=len(invalid),
        decisiveRate=decisive_rate,
        fullCoverageRate=full_coverage_rate,
        falseExclusionRate=false_exclusion_rate,
        medianNarrowingRatio=median(narrowing_values) if narrowing_values else None,
        releaseGatePassed=not release_failures,
        releaseGateFailures=release_failures,
    )


def validate_rectification_benchmark_fixture(
    fixture: ValidationFixtureReference,
    evidence_path: Path,
    *,
    require_release_gate: bool = True,
) -> RectificationBenchmarkReport:
    if fixture.fixture_kind != "rectification_benchmark":
        raise ValueError("fixture is not a rectification benchmark")
    artifact = RectificationBenchmarkArtifact.model_validate_json(
        evidence_path.read_text(encoding="utf-8")
    )
    report = evaluate_rectification_benchmark(artifact, evidence_path)
    if require_release_gate and not report.release_gate_passed:
        raise ValueError(
            "rectification benchmark release gate failed: "
            + "; ".join(report.release_gate_failures)
        )
    return report


def _evaluate_case(
    case: RectificationBenchmarkCase,
    benchmark_dir: Path,
) -> RectificationBenchmarkCaseResult:
    protocol_failures: list[str] = []
    output_failures: list[str] = []
    if case.truth_source_rating != "AA":
        protocol_failures.append("primary metrics require an AA-rated recorded birth time")
    if not case.target_hidden_during_run:
        protocol_failures.append("known birth time was not hidden during the engine run")
    if (
        case.reported_window_origin == "independent_subject_recall"
        and not case.independent_recall_attested
    ):
        protocol_failures.append("independent recall lacks a no-record-access attestation")
    if not case.events_collected_without_candidate_contrast:
        protocol_failures.append("event evidence was exposed to candidate contrast")

    _verify_retained_artifact(benchmark_dir, case.truth_source_artifact)
    blind_input_path = _verify_retained_artifact(benchmark_dir, case.blind_input)
    run_receipt_path = _verify_retained_artifact(benchmark_dir, case.run_receipt)
    record_path = _verify_retained_artifact(benchmark_dir, case.chart_record)
    try:
        blind_input = RectificationBenchmarkBlindInput.model_validate_json(
            blind_input_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        protocol_failures.append(f"blind input contract is invalid: {type(exc).__name__}")
        blind_input = None
    try:
        run_receipt = RectificationBenchmarkRunReceipt.model_validate_json(
            run_receipt_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        protocol_failures.append(f"runtime receipt contract is invalid: {type(exc).__name__}")
        run_receipt = None
    try:
        record = ChartRecord.model_validate_json(record_path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        return _invalid_case_result(
            case,
            None,
            protocol_failures,
            [f"terminal Chart Record contract is invalid: {type(exc).__name__}"],
        )
    rectification = record.rectification
    if rectification is None or rectification.reported_window is None:
        return _invalid_case_result(
            case,
            record.chart_record_id,
            protocol_failures,
            ["terminal Chart Record has no rectification evidence"],
        )
    expected_record_status = {
        "bounded_interval": "rectified",
        "multiple_equivalent": "ready_for_judgement",
        "not_required": "ready_for_judgement",
        "underdetermined": "rectification_required",
        "calculation_failed": "blocked",
        "input_resolution_required": "blocked",
    }.get(rectification.decision.status)
    if expected_record_status is None or record.status != expected_record_status:
        output_failures.append(
            "Chart Record is not a terminal output for its rectification decision"
        )
    if record.astronomy is None or record.astronomy.status != "complete":
        output_failures.append("terminal output requires a complete astronomy snapshot")
    if record.input_sensitivity is None or record.input_sensitivity.scan_status != "complete":
        output_failures.append("terminal output requires a complete input-sensitivity scan")
    protocol_failures.extend(
        _runtime_binding_failures(
            case,
            blind_input,
            run_receipt,
            record,
        )
    )
    if case.reported_window_origin == "deterministic_truth_mask":
        expected_window = deterministic_masked_window(
            case.case_id,
            case.truth_interval,
            case.masking_seed or "",
            case.masking_window_minutes or 0,
        )
        if rectification.reported_window != expected_window:
            protocol_failures.append(
                "reported window does not match the committed deterministic mask"
            )
    if not _contains(rectification.reported_window, case.truth_interval):
        protocol_failures.append("hidden truth is outside the declared reported window")
    if rectification.selection_policy_id != RECTIFICATION_SCORING_POLICY_ID:
        protocol_failures.append("Chart Record uses a different scoring policy")
    if rectification.event_mapping_id != RECTIFICATION_EVENT_MAPPING_ID:
        protocol_failures.append("Chart Record uses a different event mapping")
    if rectification.holdout_policy_id != RECTIFICATION_HOLDOUT_POLICY_ID:
        protocol_failures.append("Chart Record uses a different holdout policy")
    calibration_episodes = {
        event.episode_id for event in rectification.life_events if event.role == "calibration"
    }
    holdout_episodes = {
        event.episode_id for event in rectification.life_events if event.role == "holdout"
    }
    if len(calibration_episodes) < 3 or len(holdout_episodes) != 1:
        protocol_failures.append(
            "primary benchmark requires three calibration episodes and one blind holdout"
        )

    decision = rectification.decision
    predicted, valid_prediction = _prediction_intervals(record)
    primary_eligible = not protocol_failures
    prediction_escapes_window = any(
        not _contains(rectification.reported_window, interval) for interval in predicted
    )
    if output_failures or not valid_prediction or prediction_escapes_window:
        outcome: Literal["hit", "partial", "miss", "abstained", "invalid"] = "invalid"
        coverage: Literal["full", "partial", "none", "not_applicable"] = "not_applicable"
    elif not predicted:
        outcome = "abstained"
        coverage = "not_applicable"
    elif _union_contains(predicted, case.truth_interval):
        outcome = "hit"
        coverage = "full"
    elif any(_overlaps(interval, case.truth_interval) for interval in predicted):
        outcome = "partial"
        coverage = "partial"
    else:
        outcome = "miss"
        coverage = "none"

    reported_minutes = _duration_minutes(rectification.reported_window)
    predicted_minutes = sum(_duration_minutes(interval) for interval in _merge_ranges(predicted))
    return RectificationBenchmarkCaseResult(
        caseId=case.case_id,
        chartRecordId=record.chart_record_id,
        sourceRating=case.truth_source_rating,
        reportedWindowOrigin=case.reported_window_origin,
        eventEvidenceOrigin=case.event_evidence_origin,
        primaryEligible=primary_eligible,
        protocolFailures=protocol_failures,
        outputFailures=output_failures,
        decisionStatus=decision.status,
        outcome=outcome,
        truthCoverage=coverage,
        predictedIntervals=predicted,
        reportedWindowMinutes=reported_minutes,
        predictedUnionMinutes=predicted_minutes,
        narrowingRatio=(predicted_minutes / reported_minutes) if reported_minutes else None,
    )


def _runtime_binding_failures(
    case: RectificationBenchmarkCase,
    blind_input: RectificationBenchmarkBlindInput | None,
    receipt: RectificationBenchmarkRunReceipt | None,
    record: ChartRecord,
) -> list[str]:
    failures: list[str] = []
    rectification = record.rectification
    if blind_input is None or receipt is None or rectification is None:
        return failures
    if blind_input.case_id != case.case_id or receipt.case_id != case.case_id:
        failures.append("blind input or runtime receipt belongs to a different case")
    if blind_input.reported_window_origin != case.reported_window_origin:
        failures.append("blind input uses a different reported-window origin")
    if blind_input.event_evidence_origin != case.event_evidence_origin:
        failures.append("blind input uses a different event-evidence origin")
    failures.extend(rectification_blind_input_binding_failures(blind_input, record))
    if receipt.run_operator_id != case.run_operator_id:
        failures.append("runtime receipt identifies a different run operator")
    if (
        receipt.run_started_at != case.run_started_at
        or receipt.run_completed_at != case.run_completed_at
    ):
        failures.append("runtime receipt timestamps do not match the benchmark case")
    if receipt.blind_input_sha256 != case.blind_input.sha256:
        failures.append("runtime receipt is not bound to the retained blind input")
    if receipt.chart_record_sha256 != case.chart_record.sha256:
        failures.append("runtime receipt is not bound to the terminal Chart Record")
    if not receipt.working_tree_clean:
        failures.append("primary metrics require a clean, revision-pinned engine run")
    if receipt.selection_policy_id != RECTIFICATION_SCORING_POLICY_ID:
        failures.append("runtime receipt uses a different scoring policy")
    if receipt.event_mapping_id != RECTIFICATION_EVENT_MAPPING_ID:
        failures.append("runtime receipt uses a different event mapping")
    if receipt.holdout_policy_id != RECTIFICATION_HOLDOUT_POLICY_ID:
        failures.append("runtime receipt uses a different holdout policy")
    return failures


def _prediction_intervals(record: ChartRecord) -> tuple[list[TimeRange], bool]:
    rectification = record.rectification
    if rectification is None or rectification.reported_window is None:
        return [], False
    decision = rectification.decision
    if decision.status == "bounded_interval" and decision.resulting_interval is not None:
        return [decision.resulting_interval], True
    if decision.status == "multiple_equivalent" and decision.resulting_intervals:
        return list(decision.resulting_intervals), True
    if decision.status == "not_required":
        # A source-blind rectification benchmark measures useful narrowing. Keeping
        # the complete input window is an abstention, not a successful prediction.
        return [], True
    if decision.status == "underdetermined":
        return [], True
    return [], False


def _invalid_case_result(
    case: RectificationBenchmarkCase,
    chart_record_id: str | None,
    protocol_failures: list[str],
    output_failures: list[str],
) -> RectificationBenchmarkCaseResult:
    return RectificationBenchmarkCaseResult(
        caseId=case.case_id,
        chartRecordId=chart_record_id,
        sourceRating=case.truth_source_rating,
        reportedWindowOrigin=case.reported_window_origin,
        eventEvidenceOrigin=case.event_evidence_origin,
        primaryEligible=not protocol_failures,
        protocolFailures=protocol_failures,
        outputFailures=output_failures,
        outcome="invalid",
        truthCoverage="not_applicable",
    )


def _verify_retained_artifact(
    benchmark_dir: Path,
    retained: RetainedBenchmarkArtifact,
) -> Path:
    path = Path(retained.path).expanduser()
    if not path.is_absolute():
        path = benchmark_dir / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"rectification benchmark artifact not found: {path}")
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != retained.sha256:
        raise ValueError(f"rectification benchmark artifact hash mismatch: {path}")
    return path


def _contains(container: TimeRange, value: TimeRange) -> bool:
    return container.start <= value.start and value.end <= container.end


def _overlaps(left: TimeRange, right: TimeRange) -> bool:
    return left.start < right.end and right.start < left.end


def _union_contains(intervals: list[TimeRange], truth: TimeRange) -> bool:
    return any(_contains(interval, truth) for interval in _merge_ranges(intervals))


def _merge_ranges(intervals: list[TimeRange]) -> list[TimeRange]:
    merged: list[TimeRange] = []
    for interval in sorted(intervals, key=lambda item: item.start):
        if not merged or interval.start > merged[-1].end:
            merged.append(interval)
            continue
        merged[-1] = TimeRange(
            start=merged[-1].start,
            end=max(merged[-1].end, interval.end),
        )
    return merged


def _duration_minutes(interval: TimeRange) -> float:
    return (interval.end - interval.start).total_seconds() / 60.0


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def deterministic_masked_window(
    case_id: str,
    truth_interval: TimeRange,
    seed: str,
    window_minutes: int,
) -> TimeRange:
    if window_minutes not in {120, 240}:
        raise ValueError("deterministic mask window must be 120 or 240 minutes")
    if len(seed) < 16:
        raise ValueError("deterministic mask seed must contain at least 16 characters")
    truth_start_floor = truth_interval.start.replace(second=0, microsecond=0)
    truth_span_seconds = (truth_interval.end - truth_start_floor).total_seconds()
    available_seconds = window_minutes * 60 - truth_span_seconds
    if available_seconds < 0:
        raise ValueError("deterministic mask window cannot contain the truth interval")
    maximum_offset_minutes = int(available_seconds // 60)
    if maximum_offset_minutes < 2:
        raise ValueError("deterministic mask requires one minute of margin on both sides")
    digest = hashlib.sha256(
        f"{DETERMINISTIC_WINDOW_MASK_PROTOCOL_ID}|{case_id}|{seed}".encode()
    ).digest()
    offset_minutes = 1 + int.from_bytes(digest[:8], "big") % (maximum_offset_minutes - 1)
    start = truth_start_floor - timedelta(minutes=offset_minutes)
    return TimeRange(start=start, end=start + timedelta(minutes=window_minutes))


def _counts(
    cases: list[RectificationBenchmarkCaseResult],
    field_name: Literal["reported_window_origin", "event_evidence_origin"],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        value = str(getattr(case, field_name))
        counts[value] = counts.get(value, 0) + 1
    return counts


def _cohort_metrics(
    cases: list[RectificationBenchmarkCaseResult],
) -> RectificationBenchmarkCohortMetrics:
    decisive = [case for case in cases if case.outcome in {"hit", "partial", "miss"}]
    hits = [case for case in decisive if case.outcome == "hit"]
    partials = [case for case in decisive if case.outcome == "partial"]
    misses = [case for case in decisive if case.outcome == "miss"]
    abstained = [case for case in cases if case.outcome == "abstained"]
    invalid = [case for case in cases if case.outcome == "invalid"]
    narrowing_values = [
        case.narrowing_ratio for case in decisive if case.narrowing_ratio is not None
    ]
    return RectificationBenchmarkCohortMetrics(
        caseCount=len(cases),
        decisiveCaseCount=len(decisive),
        hitCount=len(hits),
        partialCount=len(partials),
        missCount=len(misses),
        abstainedCount=len(abstained),
        invalidCount=len(invalid),
        decisiveRate=_rate(len(decisive), len(cases)),
        fullCoverageRate=_rate(len(hits), len(decisive)),
        falseExclusionRate=_rate(len(partials) + len(misses), len(decisive)),
        medianNarrowingRatio=median(narrowing_values) if narrowing_values else None,
    )


def _append_cohort_release_failures(
    failures: list[str],
    cohort_name: str,
    metrics: RectificationBenchmarkCohortMetrics,
) -> None:
    if metrics.decisive_rate is None or metrics.decisive_rate < MINIMUM_DECISIVE_RATE:
        failures.append(f"{cohort_name} decisive rate must be at least {MINIMUM_DECISIVE_RATE:.0%}")
    if (
        metrics.full_coverage_rate is None
        or metrics.full_coverage_rate < MINIMUM_FULL_COVERAGE_RATE
    ):
        failures.append(
            f"{cohort_name} full truth-coverage rate must be at least "
            f"{MINIMUM_FULL_COVERAGE_RATE:.0%}"
        )
    if (
        metrics.false_exclusion_rate is None
        or metrics.false_exclusion_rate > MAXIMUM_FALSE_EXCLUSION_RATE
    ):
        failures.append(
            f"{cohort_name} false-exclusion rate must be at most {MAXIMUM_FALSE_EXCLUSION_RATE:.0%}"
        )
    if (
        metrics.median_narrowing_ratio is None
        or metrics.median_narrowing_ratio > MAXIMUM_MEDIAN_NARROWING_RATIO
    ):
        failures.append(
            f"{cohort_name} median retained interval must be at most 50% of the reported window"
        )
