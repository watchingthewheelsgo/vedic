from __future__ import annotations

import re
from collections.abc import Mapping

from .fact_catalog import FactType
from .models import (
    ConfidenceGrade,
    InputSensitivityAssessment,
    JyotishFact,
    VargaChart,
)


FACT_SENSITIVITY_POLICY_ID = "vedicdust-fact-sensitivity/1.0.0"
VARGA_FACTORS = (2, 3, 4, 5, 7, 9, 10, 12, 16, 20, 24, 27, 30, 60)
TIMING_SENSITIVITY_DEPENDENCIES = ["currentDasha", "moonNakshatra", "moonPada"]


def build_input_sensitivity_assessment(
    sensitivity_scan: Mapping[str, object],
) -> InputSensitivityAssessment:
    summary = sensitivity_scan.get("summary")
    if not isinstance(summary, Mapping):
        return InputSensitivityAssessment(
            scanStatus="failed",
            changedFields=[],
            scanErrorCount=1,
        )

    changed = summary.get("changedFields")
    changed_fields = sorted(
        {str(value) for value in changed if value} if isinstance(changed, list) else set()
    )
    scan_errors = summary.get("scanErrors")
    scoring_errors = summary.get("candidateScoringErrors")
    error_count = (
        len(scan_errors) if isinstance(scan_errors, list) else int(bool(scan_errors))
    ) + (len(scoring_errors) if isinstance(scoring_errors, list) else int(bool(scoring_errors)))
    timing_sampling = sensitivity_scan.get("timingBoundarySampling")
    timing_status = "not_run"
    timing_sample_count = 0
    if isinstance(timing_sampling, Mapping):
        raw_status = str(timing_sampling.get("status") or "failed")
        timing_status = raw_status if raw_status in {"complete", "partial", "failed"} else "failed"
        raw_count = timing_sampling.get("successfulSampleCount")
        timing_sample_count = int(raw_count) if isinstance(raw_count, (int, float)) else 0
        if timing_status == "failed":
            timing_sample_count = 0
    return InputSensitivityAssessment(
        scanStatus="partial" if error_count else "complete",
        changedFields=changed_fields,
        scanErrorCount=error_count,
        timingBoundaryScanStatus=timing_status,
        timingBoundarySampleCount=timing_sample_count,
    )


def fact_sensitivity_dependencies(fact_type: FactType, subject_ref: str) -> list[str]:
    varga_match = re.match(r"^D(\d+)\.", subject_ref)
    factor = int(varga_match.group(1)) if varga_match else None
    if factor is not None and factor != 1:
        lagna_field = f"d{factor}Lagna"
        structure_field = f"d{factor}Structure"
        if fact_type == "varga.lagna.position":
            return [lagna_field]
        if fact_type == "varga.graha.position":
            return [structure_field]
        if fact_type == "varga.house.lord":
            return [lagna_field, structure_field]

    dependencies: set[str] = set()
    if fact_type == "rashi.lagna.position":
        dependencies.add("lagnaSign")
    elif fact_type == "rashi.graha.position":
        dependencies.add("d1Structure")
    elif fact_type in {"rashi.house.lord", "rashi.house.occupant"}:
        dependencies.update({"lagnaSign", "d1Structure"})
    elif fact_type == "role.house_ownership":
        dependencies.add("lagnaSign")
    elif fact_type in {
        "relationship.same_sign",
        "relationship.dispositor_chain",
        "strength.dignity",
        "ashtakavarga.bav.graha",
    }:
        dependencies.add("d1Structure")
    elif fact_type in {"relationship.parivartana", "yoga.raja.kendra_trikona"}:
        dependencies.update({"lagnaSign", "d1Structure"})
    elif fact_type == "yoga.gaja_kesari.structure":
        dependencies.update(
            {
                "d1Structure",
                "moonSign",
                "moonPhase",
                "combustionStatus",
            }
        )
    elif fact_type == "strength.shadbala":
        dependencies.update({"lagnaSign", "d1Structure", "shadbalaClassification"})
    elif fact_type == "strength.combustion":
        dependencies.update({"d1Structure", "combustionStatus"})
    elif fact_type == "strength.digbala":
        dependencies.update({"lagnaSign", "d1Structure", "digbalaStatus"})
    elif fact_type == "varga.vargottama":
        dependencies.update({"d1Structure", "d9Structure"})
        if subject_ref == "D1.Lagna":
            dependencies.update({"lagnaSign", "d9Lagna"})
    elif fact_type == "karaka.chara":
        dependencies.add("charaKaraka7k")
    elif fact_type == "point.arudha":
        dependencies.update({"lagnaSign", "d1Structure", "specialPointSigns"})
    elif fact_type == "state.moon_phase":
        dependencies.add("moonPhase")
    elif fact_type == "strength.bhava_bala":
        dependencies.update({"lagnaSign", "d1Structure"})
    elif fact_type == "strength.vargeeya_bala":
        dependencies.add("d1Structure")
        dependencies.update(f"d{factor}Structure" for factor in VARGA_FACTORS)
    elif fact_type == "point.special_lagna":
        dependencies.add("specialLagnaSigns")
    elif fact_type == "ashtakavarga.sav.house":
        dependencies.update({"lagnaSign", "d1Structure"})
    elif fact_type == "aspect.graha_drishti":
        dependencies.add("d1Structure")
        if re.search(r"->H(?:[1-9]|1[0-2])$", subject_ref):
            dependencies.add("lagnaSign")
    elif fact_type == "timing.transit.house":
        dependencies.add("lagnaSign")
    elif fact_type == "timing.transit.sade_sati":
        dependencies.add("moonSign")
    elif fact_type == "timing.transit.double_transit":
        dependencies.add("lagnaSign")

    if "Moon" in subject_ref:
        if fact_type == "rashi.graha.position":
            dependencies.update({"moonSign", "moonNakshatra", "moonPada"})
        elif fact_type in {
            "relationship.same_sign",
            "relationship.parivartana",
            "relationship.dispositor_chain",
            "aspect.graha_drishti",
            "strength.dignity",
            "yoga.raja.kendra_trikona",
        }:
            dependencies.add("moonSign")

    return sorted(dependencies)


def expected_fact_input_stability(
    fact: JyotishFact,
    charts: list[VargaChart],
    assessment: InputSensitivityAssessment,
) -> ConfidenceGrade:
    dependencies = fact_sensitivity_dependencies(fact.fact_type, fact.subject_ref)
    if assessment.scan_status == "failed":
        return ConfidenceGrade.UNAVAILABLE
    if assessment.scan_status == "partial":
        return ConfidenceGrade.PROVISIONAL
    if set(dependencies) & set(assessment.changed_fields):
        return ConfidenceGrade.PROVISIONAL

    stability_by_varga = {chart.varga_id: chart.input_stability for chart in charts}
    subject_varga = fact.subject_ref.split(".", maxsplit=1)[0]
    chart_stability = stability_by_varga.get(subject_varga, ConfidenceGrade.VERIFIED)
    if fact.fact_type == "varga.vargottama":
        chart_stability = min(
            stability_by_varga.get("D1", ConfidenceGrade.UNAVAILABLE),
            stability_by_varga.get("D9", ConfidenceGrade.UNAVAILABLE),
            key=lambda value: value.rank,
        )

    # D1 chart confidence drops when either Lagna or graha structure changes.
    # Preserve only D1 facts proven invariant across the declared input window.
    if subject_varga == "D1" and dependencies and chart_stability.rank < 3:
        return ConfidenceGrade.CORROBORATED
    return chart_stability


def expected_timing_input_stability(
    assessment: InputSensitivityAssessment,
    canonical_input_confidence: ConfidenceGrade,
) -> ConfidenceGrade:
    if assessment.scan_status == "failed":
        return ConfidenceGrade.UNAVAILABLE
    if assessment.timing_boundary_scan_status == "failed":
        return ConfidenceGrade.UNAVAILABLE
    if assessment.scan_status == "partial":
        return ConfidenceGrade.PROVISIONAL
    if assessment.timing_boundary_scan_status in {"partial", "not_run"}:
        return ConfidenceGrade.PROVISIONAL
    if set(TIMING_SENSITIVITY_DEPENDENCIES) & set(assessment.changed_fields):
        return ConfidenceGrade.PROVISIONAL
    return canonical_input_confidence
