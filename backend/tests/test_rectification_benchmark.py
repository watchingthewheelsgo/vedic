from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

from app.vedicdust.event_time import event_utc_envelope
from app.vedicdust.models import (
    AstronomySnapshot,
    BirthAssertion,
    CandidateInterval,
    CanonicalBirthMoment,
    ChartRecord,
    ConfidenceGrade,
    EvidenceItem,
    GeoPoint,
    GrahaPosition,
    InputSensitivityAssessment,
    LifeEvent,
    PlaceResolution,
    RectificationDecision,
    RectificationRecord,
    SubjectContext,
    TimeRange,
    ValidationFixtureReference,
    ZodiacPosition,
)
from app.vedicdust.profiles import parashari_lahiri_profile
from app.vedicdust.rectification_benchmark import (
    DETERMINISTIC_WINDOW_MASK_PROTOCOL_ID,
    RectificationBenchmarkArtifact,
    RectificationBenchmarkBlindInput,
    RectificationBenchmarkCase,
    RectificationBenchmarkRunReceipt,
    RetainedBenchmarkArtifact,
    deterministic_masked_window,
    evaluate_rectification_benchmark,
    rectification_truth_commitment,
    validate_rectification_benchmark_fixture,
)
from app.vedicdust.rectification_policy import (
    RECTIFICATION_EVENT_MAPPING_ID,
    RECTIFICATION_HOLDOUT_POLICY_ID,
    RECTIFICATION_SCORING_POLICY_ID,
)


UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]


def _interval(hour: int, minute: int, duration_minutes: int = 1) -> TimeRange:
    start = datetime(1990, 1, 1, hour, minute, tzinfo=UTC)
    return TimeRange(start=start, end=start + timedelta(minutes=duration_minutes))


def _event(index: int) -> LifeEvent:
    year = 2010 + index
    start, end = event_utc_envelope(
        datetime(year, 1, 1),
        datetime(year + 1, 1, 1) - timedelta(seconds=1),
    )
    evidence = EvidenceItem(
        evidenceId=f"event-evidence-{index}",
        evidenceClass="user_testimony",
        sourceLabel="source-blind interview",
        observedValue=f"Independent dated event {index}",
        confidence="corroborated",
    )
    return LifeEvent(
        eventId=f"event-{index}",
        episodeId=f"episode-{index}",
        category="career" if index < 3 else "relationship",
        eventSubtype="job_change" if index < 3 else "marriage",
        interval=TimeRange(start=start, end=end),
        datePrecision="year",
        eventTimezoneBasis="unknown_event_location_utc_offset_envelope",
        description=(
            f"{year} {'career' if index < 3 else 'relationship'}: Independent dated event {index}"
        ),
        role="holdout" if index == 3 else "calibration",
        evidence=evidence,
    )


def _write_chart_record(
    tmp_path: Path,
    *,
    decision: RectificationDecision,
    reported_window: TimeRange,
) -> RetainedBenchmarkArtifact:
    birth_evidence = EvidenceItem(
        evidenceId="reported-time",
        evidenceClass="user_testimony",
        sourceLabel="source-blind intake",
        observedValue=(
            f"between {reported_window.start.isoformat()} and {reported_window.end.isoformat()}"
        ),
        confidence="provisional",
    )
    candidate_intervals: list[CandidateInterval] = []
    if decision.status == "bounded_interval" and decision.resulting_interval is not None:
        candidate_intervals.append(
            CandidateInterval(
                candidateId=decision.selected_candidate_ids[0],
                interval=decision.resulting_interval,
                representativeMoment=decision.resulting_interval.start,
                fingerprint="benchmark-candidate-1-fingerprint",
            )
        )
    elif decision.status == "multiple_equivalent":
        candidate_intervals.extend(
            CandidateInterval(
                candidateId=candidate_id,
                interval=interval,
                representativeMoment=interval.start,
                fingerprint=f"benchmark-{candidate_id}-fingerprint",
            )
            for candidate_id, interval in zip(
                decision.selected_candidate_ids,
                decision.resulting_intervals,
                strict=True,
            )
        )
    calculation_moment = reported_window.start
    place_evidence = EvidenceItem(
        evidenceId="benchmark-place",
        evidenceClass="user_testimony",
        sourceLabel="source-blind intake",
        observedValue="Blind benchmark city",
        confidence="provisional",
    )
    zodiac = ZodiacPosition(
        longitudeDeg=0,
        sign="Aries",
        signIndex=0,
        degreeInSign=0,
    )
    astronomy = AstronomySnapshot(
        snapshotId="benchmark-astronomy-001",
        calculatedAt=datetime(2026, 8, 2, tzinfo=UTC),
        julianDayUt=2447892.5,
        calculationProvider="Swiss Ephemeris + PyJHora",
        calculationAdapterVersion="benchmark-runtime",
        ephemerisVersion="benchmark-pinned-runtime",
        providerVersions={"PyJHora": "4.8.6", "pysweph": "2.10.3.6"},
        timezoneDatabaseVersion="benchmark-tzdb",
        ephemerisDataFingerprint="sha256:" + "1" * 64,
        ayanamsaValueDeg=23.5,
        ascendant=zodiac,
        grahas=[
            GrahaPosition(
                graha=name,
                position=zodiac,
                motion="not_applicable" if name in {"Rahu", "Ketu"} else "direct",
            )
            for name in (
                "Sun",
                "Moon",
                "Mars",
                "Mercury",
                "Jupiter",
                "Venus",
                "Saturn",
                "Rahu",
                "Ketu",
            )
        ],
        status="complete",
    )
    terminal_status = {
        "bounded_interval": "rectified",
        "multiple_equivalent": "ready_for_judgement",
        "not_required": "ready_for_judgement",
        "underdetermined": "rectification_required",
        "calculation_failed": "blocked",
        "input_resolution_required": "blocked",
    }.get(decision.status, "rectification_required")
    record = ChartRecord(
        chartRecordId="benchmark-chart-001",
        readingSessionId="benchmark-session-001",
        revision=1,
        createdAt=datetime(2026, 8, 9, tzinfo=UTC),
        subject=SubjectContext(subjectId="benchmark-subject-001"),
        birthAssertion=BirthAssertion(
            localDate="1990-01-01",
            reportedLocalTime="09:00",
            reportedPlace="Blind benchmark city",
            timeCertainty="broad_window",
            reportedTimeWindow=reported_window,
            evidence=[birth_evidence],
        ),
        canonicalMoment=CanonicalBirthMoment(
            localDatetime=calculation_moment,
            utcDatetime=calculation_moment,
            timezoneId="UTC",
            utcOffsetSeconds=0,
            historicalOffsetStatus="resolved",
            place=PlaceResolution(
                label="Blind benchmark city",
                point=GeoPoint(latitudeDeg=0, longitudeDeg=0),
                precision="city",
                timezoneId="UTC",
                evidence=[place_evidence],
            ),
            resolutionConfidence="provisional",
        ),
        calculationProfile=parashari_lahiri_profile(),
        astronomy=astronomy,
        inputSensitivity=InputSensitivityAssessment(scanStatus="complete"),
        rectification=RectificationRecord(
            selectionPolicyId=RECTIFICATION_SCORING_POLICY_ID,
            eventMappingId=RECTIFICATION_EVENT_MAPPING_ID,
            holdoutPolicyId=RECTIFICATION_HOLDOUT_POLICY_ID,
            reportedWindow=reported_window,
            lifeEvents=[_event(index) for index in range(4)],
            candidates=candidate_intervals,
            decision=decision,
        ),
        status=terminal_status,
    )
    path = tmp_path / "chart-record.json"
    path.write_text(record.model_dump_json(by_alias=True, indent=2) + "\n", encoding="utf-8")
    return RetainedBenchmarkArtifact(
        path=path.name,
        sha256="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        retainedAt=datetime(2026, 8, 3, tzinfo=UTC),
    )


def _write_runtime_evidence(
    tmp_path: Path,
    *,
    case_id: str,
    chart_record: RetainedBenchmarkArtifact,
    reported_window: TimeRange,
    reported_window_origin: str,
    event_evidence_origin: str,
    run_operator_id: str,
) -> tuple[RetainedBenchmarkArtifact, RetainedBenchmarkArtifact]:
    blind_input = RectificationBenchmarkBlindInput(
        caseId=case_id,
        birthInput={
            "birthDate": "1990-01-01",
            "birthTime": "09:00",
            "birthPlace": "Blind benchmark city",
            "birthTimePrecision": "part_of_day",
        },
        lifeEvents=[
            {
                "eventId": f"event-{index}",
                "category": "career" if index < 3 else "relationship",
                "eventSubtype": "job_change" if index < 3 else "marriage",
                "date": str(2010 + index),
                "description": f"Independent dated event {index}",
            }
            for index in range(4)
        ],
        reportedWindow=reported_window,
        reportedWindowOrigin=reported_window_origin,
        eventEvidenceOrigin=event_evidence_origin,
    )
    blind_path = tmp_path / "blind-input.json"
    blind_path.write_text(
        blind_input.model_dump_json(by_alias=True, indent=2) + "\n",
        encoding="utf-8",
    )
    blind_retained = RetainedBenchmarkArtifact(
        path=blind_path.name,
        sha256="sha256:" + hashlib.sha256(blind_path.read_bytes()).hexdigest(),
        retainedAt=datetime(2026, 8, 1, 12, tzinfo=UTC),
    )
    receipt = RectificationBenchmarkRunReceipt(
        caseId=case_id,
        engineRevision="a" * 40,
        engineSourceSha256="sha256:" + "b" * 64,
        workingTreeClean=True,
        runOperatorId=run_operator_id,
        runStartedAt=datetime(2026, 8, 2, tzinfo=UTC),
        runCompletedAt=datetime(2026, 8, 3, tzinfo=UTC),
        blindInputSha256=blind_retained.sha256,
        chartRecordSha256=chart_record.sha256,
        selectionPolicyId=RECTIFICATION_SCORING_POLICY_ID,
        eventMappingId=RECTIFICATION_EVENT_MAPPING_ID,
        holdoutPolicyId=RECTIFICATION_HOLDOUT_POLICY_ID,
    )
    receipt_path = tmp_path / "run-receipt.json"
    receipt_path.write_text(
        receipt.model_dump_json(by_alias=True, indent=2) + "\n",
        encoding="utf-8",
    )
    receipt_retained = RetainedBenchmarkArtifact(
        path=receipt_path.name,
        sha256="sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        retainedAt=datetime(2026, 8, 3, tzinfo=UTC),
    )
    return blind_retained, receipt_retained


def _benchmark(
    tmp_path: Path,
    *,
    decision: RectificationDecision,
    truth: TimeRange | None = None,
    source_rating: Literal["AA", "A", "B", "C", "DD"] = "AA",
    reported_window_origin: Literal[
        "independent_subject_recall",
        "deterministic_truth_mask",
    ] = "independent_subject_recall",
    event_evidence_origin: Literal[
        "subject_interview",
        "public_documentary_record",
    ] = "subject_interview",
) -> RectificationBenchmarkArtifact:
    truth = truth or _interval(9, 0)
    salt = "benchmark-salt-00000001"
    truth_source_path = tmp_path / "truth-source-redacted.txt"
    truth_source_path.write_text(
        "Redacted civil birth record retained by the truth custodian.\n",
        encoding="utf-8",
    )
    source_reference = "retained civil birth record"
    truth_source = RetainedBenchmarkArtifact(
        path=truth_source_path.name,
        sha256="sha256:" + hashlib.sha256(truth_source_path.read_bytes()).hexdigest(),
        retainedAt=datetime(2026, 8, 1, tzinfo=UTC),
    )
    case_id = "blind-case-001"
    if reported_window_origin == "deterministic_truth_mask":
        masking_seed = "deterministic-mask-seed-0001"
        masking_window_minutes = 120
        masking_protocol_id = DETERMINISTIC_WINDOW_MASK_PROTOCOL_ID
        independent_recall_attested = False
        reported_window = deterministic_masked_window(
            case_id,
            truth,
            masking_seed,
            masking_window_minutes,
        )
    else:
        masking_seed = None
        masking_window_minutes = None
        masking_protocol_id = None
        independent_recall_attested = True
        reported_window = TimeRange(
            start=datetime(1990, 1, 1, 8, 0, tzinfo=UTC),
            end=datetime(1990, 1, 1, 10, 0, tzinfo=UTC),
        )
    run_operator_id = "source-blind-engine-runner"
    chart_record = _write_chart_record(
        tmp_path,
        decision=decision,
        reported_window=reported_window,
    )
    blind_input, run_receipt = _write_runtime_evidence(
        tmp_path,
        case_id=case_id,
        chart_record=chart_record,
        reported_window=reported_window,
        reported_window_origin=reported_window_origin,
        event_evidence_origin=event_evidence_origin,
        run_operator_id=run_operator_id,
    )
    case = RectificationBenchmarkCase(
        caseId=case_id,
        chartRecord=chart_record,
        blindInput=blind_input,
        runReceipt=run_receipt,
        truthInterval=truth,
        truthSourceRating=source_rating,
        truthSourceReference=source_reference,
        truthSourceArtifact=truth_source,
        truthCommitmentSha256=rectification_truth_commitment(
            case_id,
            truth,
            source_rating,
            source_reference,
            truth_source.sha256,
            reported_window_origin,
            independent_recall_attested,
            masking_protocol_id,
            masking_seed,
            masking_window_minutes,
            event_evidence_origin,
            salt,
        ),
        truthCommitmentSalt=salt,
        truthCommittedAt=datetime(2026, 8, 1, tzinfo=UTC),
        runStartedAt=datetime(2026, 8, 2, tzinfo=UTC),
        runCompletedAt=datetime(2026, 8, 3, tzinfo=UTC),
        truthRevealedAt=datetime(2026, 8, 4, tzinfo=UTC),
        truthCustodianId="independent-truth-custodian",
        runOperatorId=run_operator_id,
        targetHiddenDuringRun=True,
        reportedWindowOrigin=reported_window_origin,
        independentRecallAttested=independent_recall_attested,
        maskingProtocolId=masking_protocol_id,
        maskingSeed=masking_seed,
        maskingWindowMinutes=masking_window_minutes,
        eventEvidenceOrigin=event_evidence_origin,
        eventsCollectedWithoutCandidateContrast=True,
    )
    return RectificationBenchmarkArtifact(
        benchmarkId="vedicdust/blind-rectification-test",
        createdAt=datetime(2026, 8, 4, tzinfo=UTC),
        cases=[case],
    )


def _bounded(interval: TimeRange) -> RectificationDecision:
    return RectificationDecision(
        status="bounded_interval",
        selectedCandidateIds=["candidate-1"],
        resultingInterval=interval,
        confidence=ConfidenceGrade.PROVISIONAL,
        holdoutResult="passed",
    )


def test_benchmark_counts_full_truth_coverage_and_useful_narrowing(tmp_path: Path) -> None:
    artifact = _benchmark(tmp_path, decision=_bounded(_interval(8, 50, 20)))

    report = evaluate_rectification_benchmark(artifact, tmp_path / "benchmark.json")

    assert report.primary_case_count == 1
    assert report.hit_count == 1
    assert report.full_coverage_rate == 1
    assert report.false_exclusion_rate == 0
    assert report.median_narrowing_ratio == pytest.approx(1 / 6)
    assert report.cohort_metrics["product:independent_recall_subject_interview"].hit_count == 1
    assert report.release_gate_passed is False


def test_benchmark_counts_false_exclusion_in_primary_metrics(tmp_path: Path) -> None:
    artifact = _benchmark(tmp_path, decision=_bounded(_interval(8, 10, 10)))

    report = evaluate_rectification_benchmark(artifact, tmp_path / "benchmark.json")

    assert report.primary_case_count == 1
    assert report.miss_count == 1
    assert report.false_exclusion_rate == 1


def test_benchmark_treats_underdetermined_as_calibrated_abstention(tmp_path: Path) -> None:
    artifact = _benchmark(
        tmp_path,
        decision=RectificationDecision(
            status="underdetermined",
            confidence=ConfidenceGrade.UNAVAILABLE,
        ),
    )

    report = evaluate_rectification_benchmark(artifact, tmp_path / "benchmark.json")

    assert report.primary_case_count == 1
    assert report.abstained_count == 1
    assert report.decisive_case_count == 0


def test_benchmark_invalid_terminal_state_cannot_disappear_from_primary_metrics(
    tmp_path: Path,
) -> None:
    artifact = _benchmark(
        tmp_path,
        decision=RectificationDecision(
            status="collecting_evidence",
            confidence=ConfidenceGrade.UNAVAILABLE,
        ),
    )

    report = evaluate_rectification_benchmark(artifact, tmp_path / "benchmark.json")

    assert report.primary_case_count == 1
    assert report.invalid_count == 1
    assert "not a terminal output" in " ".join(report.cases[0].output_failures)
    assert "invalid runtime outcomes" in " ".join(report.release_gate_failures)


def test_non_aa_truth_is_reported_but_excluded_from_primary_metrics(tmp_path: Path) -> None:
    artifact = _benchmark(
        tmp_path,
        decision=_bounded(_interval(8, 50, 20)),
        source_rating="A",
    )

    report = evaluate_rectification_benchmark(artifact, tmp_path / "benchmark.json")

    assert report.primary_case_count == 0
    assert report.cases[0].primary_eligible is False
    assert "AA-rated" in " ".join(report.cases[0].protocol_failures)


def test_target_leaked_reported_time_is_excluded_from_primary_metrics(tmp_path: Path) -> None:
    artifact = _benchmark(tmp_path, decision=_bounded(_interval(8, 50, 20)))
    artifact.cases[0].independent_recall_attested = False

    report = evaluate_rectification_benchmark(artifact, tmp_path / "benchmark.json")

    assert report.primary_case_count == 0
    assert "no-record-access attestation" in " ".join(report.cases[0].protocol_failures)


def test_deterministic_mask_places_truth_at_reproducible_hidden_position(
    tmp_path: Path,
) -> None:
    truth = _interval(9, 0)
    artifact = _benchmark(
        tmp_path,
        decision=_bounded(_interval(8, 50, 20)),
        truth=truth,
        reported_window_origin="deterministic_truth_mask",
        event_evidence_origin="public_documentary_record",
    )

    report = evaluate_rectification_benchmark(artifact, tmp_path / "benchmark.json")

    case = artifact.cases[0]
    assert case.masking_seed is not None
    assert case.masking_window_minutes is not None
    expected = deterministic_masked_window(
        case.case_id,
        truth,
        case.masking_seed,
        case.masking_window_minutes,
    )
    assert expected.start < truth.start < expected.end
    assert truth.end < expected.end
    assert report.primary_case_count_by_window_origin == {"deterministic_truth_mask": 1}
    assert report.primary_case_count_by_event_origin == {"public_documentary_record": 1}
    assert report.cohort_metrics["window:deterministic_truth_mask"].full_coverage_rate == 1
    assert report.cohort_metrics["event:public_documentary_record"].hit_count == 1


def test_tampered_deterministic_mask_is_excluded_from_primary_metrics(tmp_path: Path) -> None:
    artifact = _benchmark(
        tmp_path,
        decision=_bounded(_interval(8, 50, 20)),
        reported_window_origin="deterministic_truth_mask",
    )
    retained = artifact.cases[0].chart_record
    chart_path = tmp_path / retained.path
    record = ChartRecord.model_validate_json(chart_path.read_text(encoding="utf-8"))
    assert record.rectification is not None
    record.rectification.reported_window = TimeRange(
        start=datetime(1990, 1, 1, 8, 0, tzinfo=UTC),
        end=datetime(1990, 1, 1, 10, 0, tzinfo=UTC),
    )
    chart_path.write_text(
        record.model_dump_json(by_alias=True, indent=2) + "\n",
        encoding="utf-8",
    )
    retained.sha256 = "sha256:" + hashlib.sha256(chart_path.read_bytes()).hexdigest()

    report = evaluate_rectification_benchmark(artifact, tmp_path / "benchmark.json")

    assert report.primary_case_count == 0
    assert "does not match the committed deterministic mask" in " ".join(
        report.cases[0].protocol_failures
    )


def test_missing_blind_holdout_is_excluded_from_primary_metrics(tmp_path: Path) -> None:
    artifact = _benchmark(tmp_path, decision=_bounded(_interval(8, 50, 20)))
    retained = artifact.cases[0].chart_record
    chart_path = tmp_path / retained.path
    record = ChartRecord.model_validate_json(chart_path.read_text(encoding="utf-8"))
    assert record.rectification is not None
    for event in record.rectification.life_events:
        event.role = "calibration"
    chart_path.write_text(
        record.model_dump_json(by_alias=True, indent=2) + "\n",
        encoding="utf-8",
    )
    retained.sha256 = "sha256:" + hashlib.sha256(chart_path.read_bytes()).hexdigest()

    report = evaluate_rectification_benchmark(artifact, tmp_path / "benchmark.json")

    assert report.primary_case_count == 0
    assert "three calibration episodes and one blind holdout" in " ".join(
        report.cases[0].protocol_failures
    )


def test_truth_commitment_rejects_post_run_target_changes(tmp_path: Path) -> None:
    artifact = _benchmark(tmp_path, decision=_bounded(_interval(8, 50, 20)))
    payload = artifact.model_dump(by_alias=True, mode="json")
    payload["cases"][0]["truthInterval"] = {
        "start": "1990-01-01T09:30:00Z",
        "end": "1990-01-01T09:31:00Z",
    }

    with pytest.raises(ValidationError, match="truth commitment does not match"):
        RectificationBenchmarkArtifact.model_validate(payload)


def test_truth_source_artifact_hash_is_mandatory_at_evaluation(tmp_path: Path) -> None:
    artifact = _benchmark(tmp_path, decision=_bounded(_interval(8, 50, 20)))
    artifact.cases[0].truth_source_artifact.sha256 = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="artifact hash mismatch"):
        evaluate_rectification_benchmark(artifact, tmp_path / "benchmark.json")


def test_blind_input_rejects_target_bearing_fields() -> None:
    with pytest.raises(ValidationError, match="target-bearing field"):
        RectificationBenchmarkBlindInput(
            caseId="blind-case-target-leak",
            birthInput={
                "birthDate": "1990-01-01",
                "birthTime": "09:00",
                "groundTruth": "09:17",
            },
            lifeEvents=[{"eventId": f"event-{index}"} for index in range(4)],
            reportedWindow=TimeRange(
                start=datetime(1990, 1, 1, 8, tzinfo=UTC),
                end=datetime(1990, 1, 1, 10, tzinfo=UTC),
            ),
            reportedWindowOrigin="independent_subject_recall",
            eventEvidenceOrigin="subject_interview",
        )


def test_dirty_or_unpinned_runtime_receipt_is_excluded_from_primary_metrics(
    tmp_path: Path,
) -> None:
    artifact = _benchmark(tmp_path, decision=_bounded(_interval(8, 50, 20)))
    retained = artifact.cases[0].run_receipt
    receipt_path = tmp_path / retained.path
    receipt = RectificationBenchmarkRunReceipt.model_validate_json(
        receipt_path.read_text(encoding="utf-8")
    )
    receipt.working_tree_clean = False
    receipt_path.write_text(
        receipt.model_dump_json(by_alias=True, indent=2) + "\n",
        encoding="utf-8",
    )
    retained.sha256 = "sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest()

    report = evaluate_rectification_benchmark(artifact, tmp_path / "benchmark.json")

    assert report.primary_case_count == 0
    assert "clean, revision-pinned" in " ".join(report.cases[0].protocol_failures)


def test_runtime_receipt_must_bind_exact_terminal_chart_record(tmp_path: Path) -> None:
    artifact = _benchmark(tmp_path, decision=_bounded(_interval(8, 50, 20)))
    retained = artifact.cases[0].chart_record
    chart_path = tmp_path / retained.path
    record = ChartRecord.model_validate_json(chart_path.read_text(encoding="utf-8"))
    record.revision += 1
    chart_path.write_text(
        record.model_dump_json(by_alias=True, indent=2) + "\n",
        encoding="utf-8",
    )
    retained.sha256 = "sha256:" + hashlib.sha256(chart_path.read_bytes()).hexdigest()

    report = evaluate_rectification_benchmark(artifact, tmp_path / "benchmark.json")

    assert report.primary_case_count == 0
    assert "not bound to the terminal Chart Record" in " ".join(report.cases[0].protocol_failures)


def test_blind_event_content_must_match_terminal_chart_record(tmp_path: Path) -> None:
    artifact = _benchmark(tmp_path, decision=_bounded(_interval(8, 50, 20)))
    case = artifact.cases[0]
    blind_path = tmp_path / case.blind_input.path
    blind = json.loads(blind_path.read_text(encoding="utf-8"))
    blind["lifeEvents"][0]["date"] = "2011"
    blind_path.write_text(json.dumps(blind, indent=2) + "\n", encoding="utf-8")
    case.blind_input.sha256 = "sha256:" + hashlib.sha256(blind_path.read_bytes()).hexdigest()

    receipt_path = tmp_path / case.run_receipt.path
    receipt = RectificationBenchmarkRunReceipt.model_validate_json(
        receipt_path.read_text(encoding="utf-8")
    )
    receipt.blind_input_sha256 = case.blind_input.sha256
    receipt_path.write_text(
        receipt.model_dump_json(by_alias=True, indent=2) + "\n",
        encoding="utf-8",
    )
    case.run_receipt.sha256 = "sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest()

    report = evaluate_rectification_benchmark(artifact, tmp_path / "benchmark.json")

    assert report.primary_case_count == 0
    assert "changed date for event event-0" in " ".join(report.cases[0].protocol_failures)


def test_capture_command_binds_blind_input_to_runtime_output(tmp_path: Path) -> None:
    artifact = _benchmark(tmp_path, decision=_bounded(_interval(8, 50, 20)))
    case = artifact.cases[0]
    output = tmp_path / "captured-receipt.json"

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "capture-rectification-benchmark-run.py"),
            "--case-id",
            case.case_id,
            "--blind-input",
            str(tmp_path / case.blind_input.path),
            "--chart-record",
            str(tmp_path / case.chart_record.path),
            "--run-operator-id",
            case.run_operator_id,
            "--run-started-at",
            "2026-08-02T00:00:00Z",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    receipt = RectificationBenchmarkRunReceipt.model_validate_json(
        output.read_text(encoding="utf-8")
    )
    assert receipt.case_id == case.case_id
    assert receipt.blind_input_sha256 == case.blind_input.sha256
    assert receipt.chart_record_sha256 == case.chart_record.sha256
    assert len(receipt.engine_revision) == 40


def test_fixture_validator_requires_release_gate_evidence(tmp_path: Path) -> None:
    artifact = _benchmark(tmp_path, decision=_bounded(_interval(8, 50, 20)))
    artifact_path = tmp_path / "benchmark.json"
    artifact_path.write_text(
        artifact.model_dump_json(by_alias=True, indent=2) + "\n",
        encoding="utf-8",
    )
    fixture = ValidationFixtureReference(
        fixtureId="rectification.blind-aa",
        fixtureKind="rectification_benchmark",
        testNodes=[
            "backend/tests/test_rectification_benchmark.py::"
            "test_fixture_validator_requires_release_gate_evidence"
        ],
        description="Retains source-blind known-time benchmark evidence.",
        evidenceArtifactPath=artifact_path.name,
        evidenceArtifactSha256=("sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()),
    )

    report = validate_rectification_benchmark_fixture(
        fixture,
        artifact_path,
        require_release_gate=False,
    )
    assert report.primary_case_count == 1
    with pytest.raises(ValueError, match="requires at least 30"):
        validate_rectification_benchmark_fixture(fixture, artifact_path)
