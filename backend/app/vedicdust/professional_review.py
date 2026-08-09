from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .models import ContractModel, ValidationFixtureReference


MINIMUM_RECTIFICATION_REVIEW_CASES = 5


class RetainedReviewArtifact(ContractModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ProfessionalReviewAssessment(ContractModel):
    method_fidelity: Literal["accepted", "reservation", "rejected", "not_applicable"]
    evidence_traceability: Literal["accepted", "reservation", "rejected"]
    uncertainty_calibration: Literal["accepted", "reservation", "rejected"]
    reader_comprehensibility: Literal["accepted", "reservation", "rejected"]


class ProfessionalRectificationAssessment(ContractModel):
    candidate_construction: Literal["accepted", "reservation", "rejected"]
    event_method_fidelity: Literal["accepted", "reservation", "rejected"]
    holdout_independence: Literal["accepted", "reservation", "rejected"]
    stopping_and_abstention: Literal["accepted", "reservation", "rejected"]
    uncertainty_communication: Literal["accepted", "reservation", "rejected"]


class ProfessionalReviewCase(ContractModel):
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")
    chart_record: RetainedReviewArtifact
    claim_graph: RetainedReviewArtifact
    consultation_dossier: RetainedReviewArtifact
    rectification_state: RetainedReviewArtifact | None = None
    expected_disposition: Literal["publish", "withhold"]
    observed_disposition: Literal["publish", "withhold"]
    decision: Literal["accepted", "accepted_with_reservations", "rejected"]
    assessment: ProfessionalReviewAssessment
    rectification_assessment: ProfessionalRectificationAssessment | None = None
    disagreements: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=20)

    @model_validator(mode="after")
    def validate_disagreements(self) -> ProfessionalReviewCase:
        normalized = [item.strip() for item in self.disagreements]
        if any(not item for item in normalized) or len(normalized) != len(set(normalized)):
            raise ValueError("professional review disagreements must be unique and non-empty")
        self.disagreements = normalized
        return self


class ProfessionalReviewArtifact(ContractModel):
    schema_version: Literal["vedicdust-professional-review/1.1.0"] = (
        "vedicdust-professional-review/1.1.0"
    )
    protocol_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._/-]+$")
    review_scope: Literal["calculation_and_judgement", "rectification", "end_to_end"]
    reviewer_id: str = Field(min_length=3)
    reviewer_credentials: list[str] = Field(min_length=1)
    reviewed_at: datetime
    blinded_to_subject_identity: bool
    blinded_to_system_authorship: bool
    reviewer_independent_of_implementation: bool
    cases: list[ProfessionalReviewCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_review_contract(self) -> ProfessionalReviewArtifact:
        credentials = [item.strip() for item in self.reviewer_credentials]
        if any(not item for item in credentials) or len(credentials) != len(set(credentials)):
            raise ValueError("reviewer credentials must be unique and non-empty")
        self.reviewer_credentials = credentials
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("professional review timestamp must include a UTC offset")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("professional review contains duplicate case ids")
        if self.review_scope in {"rectification", "end_to_end"}:
            if len(self.cases) < MINIMUM_RECTIFICATION_REVIEW_CASES:
                raise ValueError(
                    "rectification professional review requires at least "
                    f"{MINIMUM_RECTIFICATION_REVIEW_CASES} blind cases"
                )
            dispositions = {case.expected_disposition for case in self.cases}
            if dispositions != {"publish", "withhold"}:
                raise ValueError(
                    "rectification professional review requires publish and withhold cases"
                )
            for case in self.cases:
                if case.rectification_state is None or case.rectification_assessment is None:
                    raise ValueError(
                        "rectification professional review cases require state evidence and "
                        "a rectification-specific assessment"
                    )
                if case.assessment.method_fidelity == "not_applicable":
                    raise ValueError(
                        "rectification professional review must assess method fidelity"
                    )
        return self


def validate_professional_review_fixture(
    fixture: ValidationFixtureReference,
    evidence_path: Path,
) -> ProfessionalReviewArtifact:
    """Validate that a professional-review fixture contains auditable blind review evidence."""

    if fixture.fixture_kind != "professional_review":
        raise ValueError("fixture is not a professional review")
    artifact = ProfessionalReviewArtifact.model_validate_json(
        evidence_path.read_text(encoding="utf-8")
    )
    if artifact.protocol_id != fixture.review_protocol_id:
        raise ValueError("professional review protocol does not match fixture metadata")
    if artifact.reviewer_id != fixture.reviewed_by:
        raise ValueError("professional review reviewer does not match fixture metadata")
    if artifact.reviewed_at != fixture.reviewed_at:
        raise ValueError("professional review timestamp does not match fixture metadata")
    if artifact.review_scope != fixture.review_scope:
        raise ValueError("professional review scope does not match fixture metadata")
    artifact_case_ids = {case.case_id for case in artifact.cases}
    if artifact_case_ids != set(fixture.reviewed_case_ids):
        raise ValueError("professional review case ids do not match fixture metadata")
    if not artifact.blinded_to_subject_identity:
        raise ValueError("professional review must blind subject identity")
    if not artifact.blinded_to_system_authorship:
        raise ValueError("professional review must blind system authorship")
    if not artifact.reviewer_independent_of_implementation:
        raise ValueError("professional reviewer must be independent of implementation")

    failures: list[str] = []
    for case in artifact.cases:
        _verify_retained_artifact(
            evidence_path.parent, case.case_id, "Chart Record", case.chart_record
        )
        _verify_retained_artifact(
            evidence_path.parent, case.case_id, "Claim Graph", case.claim_graph
        )
        _verify_retained_artifact(
            evidence_path.parent,
            case.case_id,
            "Consultation Dossier",
            case.consultation_dossier,
        )
        if case.rectification_state is not None:
            state_path = _verify_retained_artifact(
                evidence_path.parent,
                case.case_id,
                "Rectification State",
                case.rectification_state,
            )
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                failures.append(f"{case.case_id}: Rectification State is not valid JSON")
            else:
                if not isinstance(state, dict) or not state.get("status"):
                    failures.append(f"{case.case_id}: Rectification State has no terminal status")
                for field in ("selectionPolicyId", "eventMappingId", "holdoutPolicyId"):
                    if not state.get(field):
                        failures.append(f"{case.case_id}: Rectification State is missing {field}")
        if case.expected_disposition != case.observed_disposition:
            failures.append(f"{case.case_id}: publish/withhold disposition mismatch")
        if case.decision == "rejected":
            failures.append(f"{case.case_id}: professional review rejected the output")
        rejected_dimensions = [
            field_name
            for field_name, value in case.assessment.model_dump().items()
            if value == "rejected"
        ]
        if rejected_dimensions:
            failures.append(
                f"{case.case_id}: rejected assessment dimensions "
                + ", ".join(sorted(rejected_dimensions))
            )
        if case.rectification_assessment is not None:
            rejected_rectification_dimensions = [
                field_name
                for field_name, value in case.rectification_assessment.model_dump().items()
                if value == "rejected"
            ]
            if rejected_rectification_dimensions:
                failures.append(
                    f"{case.case_id}: rejected rectification dimensions "
                    + ", ".join(sorted(rejected_rectification_dimensions))
                )
    if failures:
        raise ValueError("professional review fixture failed: " + "; ".join(failures))
    return artifact


def _verify_retained_artifact(
    review_dir: Path,
    case_id: str,
    label: str,
    retained: RetainedReviewArtifact,
) -> Path:
    artifact_path = Path(retained.path).expanduser()
    if not artifact_path.is_absolute():
        artifact_path = review_dir / artifact_path
    artifact_path = artifact_path.resolve()
    if not artifact_path.is_file():
        raise FileNotFoundError(f"{label} artifact not found for {case_id}: {artifact_path}")
    digest = "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    if digest != retained.sha256:
        raise ValueError(f"{label} artifact hash mismatch for {case_id}")
    return artifact_path
