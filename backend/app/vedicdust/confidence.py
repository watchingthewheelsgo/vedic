from __future__ import annotations

from .models import ConfidenceGrade, JyotishFact, TimingPeriod


def minimum_confidence(*values: ConfidenceGrade) -> ConfidenceGrade:
    if not values:
        return ConfidenceGrade.UNAVAILABLE
    return min(values, key=lambda value: value.rank)


def effective_fact_confidence(fact: JyotishFact) -> ConfidenceGrade:
    """Combine calculation assurance with birth-input stability without conflating them."""

    return minimum_confidence(fact.provenance.confidence, fact.input_stability)


def effective_timing_confidence(period: TimingPeriod) -> ConfidenceGrade:
    """Combine Dasha-provider assurance with stability under the reported birth window."""

    return minimum_confidence(period.provenance.confidence, period.input_stability)
