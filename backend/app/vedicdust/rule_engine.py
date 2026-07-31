from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Any

from .models import ChartRecord, JyotishFact, MethodRule, RulePredicate


def evaluate_method_rule(rule: MethodRule, record: ChartRecord) -> dict[str, Any]:
    """Evaluate a catalog rule against deterministic ChartRecord facts."""

    matched_fact_ids: set[str] = set()
    failed: list[str] = []

    for predicate in rule.all_of:
        passed, matches = _evaluate_predicate(predicate, record.facts)
        matched_fact_ids.update(matches)
        if not passed:
            failed.append(f"allOf:{_predicate_label(predicate)}")

    if rule.any_of:
        any_results = [_evaluate_predicate(predicate, record.facts) for predicate in rule.any_of]
        for _, matches in any_results:
            matched_fact_ids.update(matches)
        if not any(passed for passed, _ in any_results):
            failed.append("anyOf:" + "|".join(_predicate_label(item) for item in rule.any_of))

    for predicate in rule.none_of:
        passed, matches = _evaluate_predicate(predicate, record.facts)
        if passed:
            matched_fact_ids.update(matches)
            failed.append(f"noneOf:{_predicate_label(predicate)}")

    if not rule.all_of and not rule.any_of and not rule.none_of:
        failed.append("rule_has_no_executable_predicates")

    if rule.rule_id == "sop.d60-eligibility-gate":
        d60 = next((chart for chart in record.charts if chart.varga_id == "D60"), None)
        if d60 is None or not d60.eligible_as_primary_evidence:
            failed.append("D60_is_not_eligible_as_primary_evidence")

    return {
        "evaluationStatus": "eligible" if not failed else "ineligible",
        "matchedFactIds": sorted(matched_fact_ids),
        "failedPredicates": failed,
    }


def _evaluate_predicate(
    predicate: RulePredicate,
    facts: list[JyotishFact],
) -> tuple[bool, list[str]]:
    matching = [
        fact
        for fact in facts
        if fnmatchcase(fact.fact_type, predicate.fact_type)
        and fnmatchcase(fact.subject_ref, predicate.subject_selector)
    ]
    if predicate.operator == "exists":
        return bool(matching), [fact.fact_id for fact in matching]
    if predicate.operator == "not_exists":
        return not matching, []
    accepted = [
        fact for fact in matching if _compare(fact.value, predicate.operator, predicate.expected)
    ]
    return bool(accepted), [fact.fact_id for fact in accepted]


def _compare(value: Any, operator: str, expected: Any) -> bool:
    if operator == "equals":
        return value == expected
    if operator == "not_equals":
        return value != expected
    if operator == "greater_than":
        return isinstance(value, (int, float)) and value > expected
    if operator == "less_than":
        return isinstance(value, (int, float)) and value < expected
    if operator == "contains":
        if isinstance(value, dict):
            return expected in value or expected in value.values()
        if isinstance(value, (list, tuple, set, str)):
            return expected in value
    return False


def _predicate_label(predicate: RulePredicate) -> str:
    return f"{predicate.fact_type}@{predicate.subject_selector}:{predicate.operator}"
