from __future__ import annotations

from datetime import datetime, timezone

from .models import AuditFinding, ChartAudit, ChartRecord


def audit_chart_record(record: ChartRecord) -> ChartAudit:
    """Apply deterministic workflow gates before any model-led interpretation."""

    findings: list[AuditFinding] = []
    for check in record.quality_checks:
        if check.status not in {"failed", "warning"}:
            continue
        findings.append(
            AuditFinding(
                finding_id=f"quality.{check.check_id}",
                severity="blocking" if check.status == "failed" else "warning",
                category="calculation",
                field_refs=[f"qualityChecks.{check.check_id}"],
                message=check.message,
                required_action=(
                    "Repair the deterministic calculation before continuing."
                    if check.status == "failed"
                    else None
                ),
            )
        )

    if record.canonical_moment is None:
        findings.append(
            AuditFinding(
                finding_id="birth.canonical-moment-missing",
                severity="blocking",
                category="civil_time",
                field_refs=["canonicalMoment"],
                message="The birth moment has not been resolved to UTC.",
                required_action="Resolve the civil time and IANA time zone.",
            )
        )
    else:
        place = record.canonical_moment.place
        if place.precision in {"city", "district"}:
            findings.append(
                AuditFinding(
                    finding_id="place.coarse-resolution",
                    severity="warning",
                    category="place",
                    field_refs=["canonicalMoment.place.precision"],
                    message=(
                        "The chart uses a broad place reference. Place sensitivity remains "
                        "part of rectification."
                    ),
                    required_action="Confirm a POI/address or retain place uncertainty.",
                )
            )

    rectification_status = (
        record.rectification.decision.status if record.rectification else "not_required"
    )
    if rectification_status in {
        "collecting_evidence",
        "comparing_candidates",
        "underdetermined",
    }:
        findings.append(
            AuditFinding(
                finding_id="rectification.unresolved",
                severity="warning",
                category="rectification",
                field_refs=["rectification.decision"],
                message="Decision-relevant chart facts still vary inside the reported window.",
                required_action="Continue rectification or retain a bounded uncertainty disclosure.",
            )
        )

    has_blocker = any(finding.severity == "blocking" for finding in findings)
    if has_blocker:
        status = "blocked"
        next_steps = ["collect_input"]
    elif rectification_status in {
        "collecting_evidence",
        "comparing_candidates",
        "underdetermined",
    }:
        status = "passed_with_limits"
        next_steps = ["rectify"]
    else:
        status = "passed_with_limits" if findings else "passed"
        next_steps = ["judge"]

    return ChartAudit(
        chart_record_id=record.chart_record_id,
        audited_at=datetime.now(timezone.utc),
        status=status,
        findings=findings,
        permitted_next_steps=next_steps,
    )
