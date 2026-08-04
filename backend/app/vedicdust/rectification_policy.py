from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


RECTIFICATION_RULE_ID = "rectify.event-evidence-ranking"
RECTIFICATION_SCORING_POLICY_ID = "vedicdust-rectification-event-ranking/1.9.0"
RECTIFICATION_EVENT_MAPPING_ID = "vedicdust-rectification-event-map/1.2.0"
RECTIFICATION_HOLDOUT_POLICY_ID = "vedicdust-rectification-holdout/1.0.0"
RECTIFICATION_METHOD_MATURITY = "product_hypothesis"
RECTIFICATION_VALIDATION_STATUS = "internal_regression_only"
RECTIFICATION_SOURCE_IDS = (
    "lineage.pvr-integrated-approach-2000-2010",
    "product.vedicdust-consultation-standard-1",
)


@dataclass(frozen=True)
class RectificationScoringPolicy:
    policy_id: str
    dasha_level_weights: Mapping[str, float]
    varga_lagna_lord_support_weight: float
    double_transit_support_weight: float
    minimum_calibration_events: int
    minimum_calibration_categories: int
    event_discrimination_min_margin: float
    candidate_selection_min_score: float
    candidate_selection_min_margin: float
    holdout_min_score: float
    holdout_pass_margin: float


RECTIFICATION_SCORING_POLICY = RectificationScoringPolicy(
    policy_id=RECTIFICATION_SCORING_POLICY_ID,
    dasha_level_weights=MappingProxyType({"md": 0.12, "ad": 0.16, "pd": 0.10}),
    varga_lagna_lord_support_weight=0.08,
    double_transit_support_weight=0.22,
    minimum_calibration_events=2,
    minimum_calibration_categories=2,
    event_discrimination_min_margin=0.05,
    candidate_selection_min_score=0.15,
    candidate_selection_min_margin=0.10,
    holdout_min_score=0.10,
    holdout_pass_margin=0.05,
)


# This map is a versioned product hypothesis. It narrows candidate charts; it is
# not a claim that one event category has a single universally accepted formula.
RECTIFICATION_EVENT_RULES: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        "marriage": {
            "label": "marriage / committed relationship",
            "houses": [7, 2, 11],
            "vargas": ["D9"],
            "karakas": ["Venus", "Jupiter"],
            "fields": ["d9Lagna", "d9Structure", "currentDasha"],
        },
        "relationship": {
            "label": "relationship change",
            "houses": [5, 7, 12],
            "vargas": ["D9"],
            "karakas": ["Venus", "Mars"],
            "fields": ["d9Lagna", "d9Structure", "currentDasha"],
        },
        "career": {
            "label": "career change",
            "houses": [10, 6, 11],
            "vargas": ["D10"],
            "karakas": ["Sun", "Saturn", "Mercury"],
            "fields": ["d10Lagna", "d10Structure", "currentDasha"],
        },
        "education": {
            "label": "education / examination",
            "houses": [4, 5, 9],
            "vargas": ["D24"],
            "karakas": ["Mercury", "Jupiter"],
            "fields": [
                "d24Lagna",
                "d24Structure",
                "currentDasha",
            ],
        },
        "relocation": {
            "label": "relocation / migration",
            "houses": [4, 9, 12],
            "vargas": ["D4"],
            "karakas": ["Moon", "Rahu"],
            "fields": ["d4Lagna", "d4Structure", "currentDasha"],
        },
        "property": {
            "label": "home / property",
            "houses": [4, 11, 12],
            "vargas": ["D4"],
            "karakas": ["Mars", "Moon"],
            "fields": ["d4Lagna", "d4Structure", "currentDasha"],
        },
        "child": {
            "label": "childbirth / child event",
            "houses": [5, 2, 9],
            "vargas": ["D7"],
            "karakas": ["Jupiter"],
            "fields": [
                "d7Lagna",
                "d7Structure",
                "currentDasha",
            ],
        },
        "health": {
            "label": "health / surgery",
            "houses": [1, 6, 8, 12],
            "vargas": ["D30"],
            "karakas": ["Mars", "Saturn"],
            "fields": ["d30Lagna", "d30Structure", "lagnaSign", "currentDasha"],
        },
        "family": {
            "label": "family event",
            "houses": [2, 4, 8],
            "vargas": ["D12"],
            "karakas": ["Moon", "Sun"],
            "fields": ["d12Lagna", "d12Structure", "lagnaSign", "currentDasha"],
        },
        "finance": {
            "label": "finance / income shock",
            "houses": [2, 6, 8, 11],
            "vargas": ["D2"],
            "karakas": ["Jupiter", "Venus", "Saturn"],
            "fields": ["d2Lagna", "d2Structure", "currentDasha", "lagnaSign"],
        },
        "legal": {
            "label": "legal / dispute",
            "houses": [6, 8, 12],
            "vargas": ["D30"],
            "karakas": ["Mars", "Saturn", "Rahu"],
            "fields": ["d30Lagna", "d30Structure", "lagnaSign", "currentDasha"],
        },
        "loss": {
            "label": "bereavement / major loss",
            "houses": [8, 12, 4],
            "vargas": ["D12", "D30"],
            "karakas": ["Saturn", "Ketu"],
            "fields": [
                "d12Lagna",
                "d12Structure",
                "d30Lagna",
                "d30Structure",
                "lagnaSign",
                "currentDasha",
            ],
        },
        "spiritual": {
            "label": "spiritual turn",
            "houses": [5, 9, 12],
            "vargas": ["D9", "D20"],
            "karakas": ["Jupiter", "Ketu"],
            "fields": [
                "d20Lagna",
                "d20Structure",
                "d9Lagna",
                "d9Structure",
                "currentDasha",
            ],
        },
        "unknown": {
            "label": "dated life event",
            "houses": [],
            "vargas": [],
            "karakas": [],
            "fields": ["currentDasha"],
        },
    }
)
