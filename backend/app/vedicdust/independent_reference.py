from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from .models import ContractModel, IndependentReferenceSnapshot
from .profiles import parashari_lahiri_profile


DEFAULT_CERTIFICATION_MINIMUM_CASES = 12
DEFAULT_CERTIFICATION_COVERAGE_TAGS = frozenset(
    {
        "ordinary",
        "varga-boundary",
        "dasha-boundary",
        "dst-or-offset-edge",
        "southern-hemisphere",
    }
)


class IndependentReferenceSelector(ContractModel):
    local_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    local_time: str = Field(pattern=r"^\d{2}:\d{2}(?::\d{2})?$")
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone_id: str = Field(min_length=1)
    utc_offset_seconds: int | None = Field(default=None, ge=-50400, le=50400)
    method_profile_id: str
    coordinate_tolerance_deg: float = Field(default=0.0001, gt=0, le=0.01)


class RegisteredIndependentReference(ContractModel):
    case_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")
    coverage_tags: list[str] = Field(default_factory=list)
    selector: IndependentReferenceSelector
    reference: IndependentReferenceSnapshot
    source_artifact_path: str = Field(min_length=1)
    normalization_protocol: str = Field(
        default="dual-entry-manual-v1",
        pattern=r"^dual-entry-manual-v1$",
    )
    normalized_by: str = Field(min_length=3)
    reviewed_by: str = Field(min_length=3)
    reviewed_at: datetime

    @model_validator(mode="after")
    def validate_profile_alignment(self) -> RegisteredIndependentReference:
        if self.selector.method_profile_id != self.reference.method_profile_id:
            raise ValueError("selector and reference method profiles must match")
        if self.normalized_by.casefold() == self.reviewed_by.casefold():
            raise ValueError("independent reference requires a distinct reviewer")
        normalized_tags = [tag.strip() for tag in self.coverage_tags]
        if any(not tag for tag in normalized_tags):
            raise ValueError("independent reference coverage tags must be non-empty")
        if len(normalized_tags) != len(set(normalized_tags)):
            raise ValueError("independent reference coverage tags must be unique")
        self.coverage_tags = normalized_tags
        return self


class IndependentReferenceRegistry(ContractModel):
    schema_version: str = Field(
        default="vedicdust-independent-reference-registry/1.1.0",
        pattern=r"^vedicdust-independent-reference-registry/1\.1\.0$",
    )
    entries: list[RegisteredIndependentReference]

    @model_validator(mode="after")
    def validate_unique_selectors(self) -> IndependentReferenceRegistry:
        keys = [
            (
                entry.selector.local_date,
                _exact_time(entry.selector.local_time),
                entry.selector.latitude,
                entry.selector.longitude,
                entry.selector.timezone_id,
                entry.selector.utc_offset_seconds,
                entry.selector.method_profile_id,
            )
            for entry in self.entries
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("independent reference registry contains duplicate selectors")
        case_ids = [entry.case_id for entry in self.entries if entry.case_id is not None]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("independent reference registry contains duplicate case IDs")
        return self


class IndependentReferenceCertificationCase(ContractModel):
    case_id: str
    selector: IndependentReferenceSelector
    source_system: str
    source_version: str
    source_artifact_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    coverage_tags: list[str]
    status: Literal["passed", "failed"]
    issues: list[dict[str, Any]] = Field(default_factory=list)


class IndependentReferenceCertificationReport(ContractModel):
    schema_version: str = Field(
        default="vedicdust-independent-reference-certification/1.0.0",
        pattern=r"^vedicdust-independent-reference-certification/1\.0\.0$",
    )
    generated_at: datetime
    method_profile_id: str
    minimum_cases: int = Field(ge=1)
    required_coverage_tags: list[str]
    observed_coverage_tags: list[str]
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    policy_failures: list[str] = Field(default_factory=list)
    cases: list[IndependentReferenceCertificationCase]
    status: Literal["passed", "failed"]


def find_independent_reference(
    registry_path: Path | None,
    *,
    local_date: str,
    local_time: str,
    latitude: float,
    longitude: float,
    timezone_id: str,
    utc_offset_seconds: int | None = None,
) -> IndependentReferenceSnapshot | None:
    """Return an exact-profile external snapshot for the active birth assertion."""

    if registry_path is None:
        return None
    resolved = registry_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Independent reference registry not found: {resolved}")
    registry = load_independent_reference_registry(resolved)
    profile_id = parashari_lahiri_profile().profile_id
    normalized_time = _exact_time(local_time)
    matches = []
    for entry in registry.entries:
        selector = entry.selector
        if (
            selector.local_date == local_date
            and _exact_time(selector.local_time) == normalized_time
            and selector.timezone_id == timezone_id
            and selector.utc_offset_seconds == utc_offset_seconds
            and selector.method_profile_id == profile_id
            and abs(selector.latitude - latitude) <= selector.coordinate_tolerance_deg
            and abs(selector.longitude - longitude) <= selector.coordinate_tolerance_deg
        ):
            matches.append(entry.reference)
    if len(matches) > 1:
        raise ValueError("multiple independent reference snapshots match this birth assertion")
    return matches[0] if matches else None


def load_independent_reference_registry(path: Path) -> IndependentReferenceRegistry:
    """Load a registry and verify every retained source artifact."""

    registry = IndependentReferenceRegistry.model_validate_json(path.read_text(encoding="utf-8"))
    for entry in registry.entries:
        artifact_path = Path(entry.source_artifact_path).expanduser()
        if not artifact_path.is_absolute():
            artifact_path = path.parent / artifact_path
        artifact_path = artifact_path.resolve()
        if not artifact_path.is_file():
            raise FileNotFoundError(f"Independent reference artifact not found: {artifact_path}")
        digest = "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if digest != entry.reference.source_artifact_sha256:
            raise ValueError(
                "independent reference artifact hash mismatch for "
                f"{entry.reference.source_system} {entry.reference.source_version}"
            )
    return registry


def certify_independent_reference_registry(
    registry_path: Path,
    *,
    minimum_cases: int,
    required_coverage_tags: set[str] | None = None,
    calculate_chart: Callable[[IndependentReferenceSelector], Mapping[str, Any]] | None = None,
) -> IndependentReferenceCertificationReport:
    """Recalculate and compare every registered external reference.

    Passing this contract proves agreement for the declared corpus only. It does not
    promote interpretation rules or establish universal software equivalence.
    """

    if minimum_cases < 1:
        raise ValueError("minimum_cases must be at least one")
    registry = load_independent_reference_registry(registry_path.expanduser().resolve())
    calculator = calculate_chart or _calculate_selector_chart
    required_tags = sorted(required_coverage_tags or set())
    observed_tags = sorted(
        {tag for entry in registry.entries for tag in entry.coverage_tags if tag.strip()}
    )
    policy_failures: list[str] = []
    if len(registry.entries) < minimum_cases:
        policy_failures.append(
            f"corpus has {len(registry.entries)} cases; minimum is {minimum_cases}"
        )
    missing_tags = sorted(set(required_tags) - set(observed_tags))
    if missing_tags:
        policy_failures.append("missing required coverage tags: " + ", ".join(missing_tags))

    cases: list[IndependentReferenceCertificationCase] = []
    for index, entry in enumerate(registry.entries, start=1):
        case_id = entry.case_id or f"unidentified-entry-{index}"
        issues: list[dict[str, Any]] = []
        if entry.case_id is None:
            issues.append({"reason": "missing-case-id"})
        if not entry.coverage_tags:
            issues.append({"reason": "missing-coverage-tags"})
        try:
            chart = calculator(entry.selector)
            from .chart_record_builder import independent_reference_quality_check

            check = independent_reference_quality_check(chart, entry.reference)
            if check.status != "passed":
                observed = check.observed
                if isinstance(observed, list):
                    issues.extend(item for item in observed if isinstance(item, dict))
                else:
                    issues.append({"reason": "comparison-failed", "observed": observed})
        except Exception as exc:
            issues.append(
                {
                    "reason": "calculation-failed",
                    "errorType": type(exc).__name__,
                    "message": str(exc),
                }
            )
        cases.append(
            IndependentReferenceCertificationCase(
                caseId=case_id,
                selector=entry.selector,
                sourceSystem=entry.reference.source_system,
                sourceVersion=entry.reference.source_version,
                sourceArtifactSha256=entry.reference.source_artifact_sha256,
                coverageTags=sorted(set(entry.coverage_tags)),
                status="failed" if issues else "passed",
                issues=issues,
            )
        )

    failed_cases = sum(case.status == "failed" for case in cases)
    passed_cases = len(cases) - failed_cases
    return IndependentReferenceCertificationReport(
        generatedAt=datetime.now(timezone.utc),
        methodProfileId=parashari_lahiri_profile().profile_id,
        minimumCases=minimum_cases,
        requiredCoverageTags=required_tags,
        observedCoverageTags=observed_tags,
        totalCases=len(cases),
        passedCases=passed_cases,
        failedCases=failed_cases,
        policyFailures=policy_failures,
        cases=cases,
        status="passed" if not policy_failures and failed_cases == 0 else "failed",
    )


def _calculate_selector_chart(selector: IndependentReferenceSelector) -> Mapping[str, Any]:
    from app.calculator.engine import calculate_full_chart

    date_parts = [int(part) for part in selector.local_date.split("-")]
    time_parts = [int(part) for part in _exact_time(selector.local_time).split(":")]
    with redirect_stdout(StringIO()):
        return calculate_full_chart(
            year=date_parts[0],
            month=date_parts[1],
            day=date_parts[2],
            hour=time_parts[0],
            minute=time_parts[1],
            second=time_parts[2],
            lat=selector.latitude,
            lon=selector.longitude,
            tz_str=selector.timezone_id,
            utc_offset_seconds=selector.utc_offset_seconds,
            transit_as_of=datetime(2000, 1, 1, tzinfo=timezone.utc),
            calculation_as_of=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )


def _exact_time(value: str) -> str:
    parts = value.split(":")
    return ":".join([*parts[:2], parts[2] if len(parts) > 2 else "00"])
