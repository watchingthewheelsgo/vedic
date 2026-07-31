from __future__ import annotations

from .models import ChartRecord, ClaimGraph, RuleCatalog


def validate_chart_record_provenance(record: ChartRecord, catalog: RuleCatalog) -> None:
    """Reject facts or timing periods whose declared provenance drifted from the catalog."""

    rules_by_id = {rule.rule_id: rule for rule in catalog.rules if rule.status != "retired"}
    errors: list[str] = []
    provenance_items = [
        *(fact.provenance for fact in record.facts),
        *(period.provenance for period in record.timing_periods),
    ]
    for provenance in provenance_items:
        rule = rules_by_id.get(provenance.rule_id)
        if rule is None:
            errors.append(f"unknown provenance rule {provenance.rule_id}")
            continue
        if provenance.rule_version != rule.rule_version:
            errors.append(f"provenance version drift for {provenance.rule_id}")
        if provenance.method_profile_id not in rule.method_profile_ids:
            errors.append(f"method profile mismatch for {provenance.rule_id}")
        if provenance.evidence_class != rule.evidence_class:
            errors.append(f"evidence class drift for {provenance.rule_id}")
        if provenance.source_ids != rule.source_ids:
            errors.append(f"source drift for {provenance.rule_id}")
    if errors:
        raise ValueError("; ".join(sorted(set(errors))))


def validate_claim_graph(
    record: ChartRecord,
    graph: ClaimGraph,
    catalog: RuleCatalog,
) -> None:
    """Validate cross-artifact references at the judgement seam."""

    errors: list[str] = []
    if graph.chart_record_id != record.chart_record_id:
        errors.append("claim graph chart record id does not match the active chart record")
    if graph.method_profile_id != record.calculation_profile.profile_id:
        errors.append("claim graph method profile does not match the active chart record")

    facts_by_id = {fact.fact_id: fact for fact in record.facts}
    rules_by_id = {rule.rule_id: rule for rule in catalog.rules if rule.status != "retired"}
    for claim in graph.claims:
        for fact_id in claim.supporting_fact_ids + claim.counter_fact_ids + claim.timing_fact_ids:
            if fact_id not in facts_by_id:
                errors.append(f"claim {claim.claim_id} references unknown fact {fact_id}")
        for rule_id in claim.rule_ids:
            rule = rules_by_id.get(rule_id)
            if rule is None:
                errors.append(f"claim {claim.claim_id} references unknown rule {rule_id}")
            elif record.calculation_profile.profile_id not in rule.method_profile_ids:
                errors.append(
                    f"claim {claim.claim_id} uses rule {rule_id} from another method profile"
                )
        if claim.scope == "timing" and not claim.timing_fact_ids:
            errors.append(f"timing claim {claim.claim_id} has no timing evidence")

    if errors:
        raise ValueError("; ".join(errors))
