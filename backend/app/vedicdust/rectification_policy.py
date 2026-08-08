from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


RECTIFICATION_RULE_ID = "rectify.event-evidence-ranking"
RECTIFICATION_KP_RULE_ID = "rectify.kp-sub-lord-corroboration"
RECTIFICATION_SCORING_POLICY_ID = "vedicdust-rectification-event-ranking/1.13.0"
RECTIFICATION_EVENT_MAPPING_ID = "vedicdust-rectification-event-map/1.5.0"
RECTIFICATION_HOLDOUT_POLICY_ID = "vedicdust-rectification-holdout/1.1.0"
RECTIFICATION_METHOD_MATURITY = "product_hypothesis"
RECTIFICATION_VALIDATION_STATUS = "internal_regression_only"
RECTIFICATION_SOURCE_IDS = (
    "lineage.pvr-integrated-approach-2000-2010",
    "product.vedicdust-consultation-standard-1",
)


# Event subtypes are user-selected backend facts. They are versioned beside the
# scoring map so a free-form description or Agent response cannot silently
# switch the deterministic rule applied to an event.
RECTIFICATION_EVENT_SUBTYPES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "education": ("admission", "graduation", "exam", "study_abroad", "other"),
        "career": ("first_job", "promotion", "job_change", "job_loss", "other"),
        "relationship": ("started_relationship", "marriage", "separation", "other"),
        "relocation": ("moved_city", "moved_country", "first_home", "other"),
        "child": ("pregnancy", "birth", "child_major", "other"),
        "health": ("surgery", "diagnosis", "accident", "other"),
        "family": ("family_structure", "parent_change", "caregiving", "other"),
        "finance": ("major_gain", "major_loss", "financial_independence", "other"),
        "property": ("purchase", "sale", "move_home", "other"),
        "legal": ("lawsuit", "settlement", "documents", "other"),
        "loss": ("bereavement", "sudden_loss", "other"),
        "spiritual": ("practice", "belief_change", "community", "other"),
    }
)


@dataclass(frozen=True)
class RectificationScoringPolicy:
    policy_id: str
    dasha_level_weights: Mapping[str, float]
    varga_lagna_lord_support_weight: float
    double_transit_support_weight: float
    node_transit_support_weight: float
    sade_sati_support_weight: float
    kp_sub_lord_support_weight: float
    chara_dasha_level_weights: Mapping[str, float]
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
    node_transit_support_weight=0.11,
    sade_sati_support_weight=0.09,
    kp_sub_lord_support_weight=0.10,
    chara_dasha_level_weights=MappingProxyType({"md": 0.08, "ad": 0.10, "pd": 0.06}),
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
            "sadeSatiRelevant": True,
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
            "sadeSatiRelevant": True,
        },
        "family": {
            "label": "family event",
            "houses": [2, 4, 8],
            "vargas": ["D12"],
            "karakas": ["Moon", "Sun"],
            "fields": ["d12Lagna", "d12Structure", "lagnaSign", "currentDasha"],
            "sadeSatiRelevant": True,
        },
        "finance": {
            "label": "finance / income shock",
            "houses": [2, 6, 8, 11],
            "vargas": ["D2"],
            "karakas": ["Jupiter", "Venus", "Saturn"],
            "fields": ["d2Lagna", "d2Structure", "currentDasha", "lagnaSign"],
            "sadeSatiRelevant": True,
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
            "sadeSatiRelevant": True,
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


RECTIFICATION_EVENT_SUBTYPE_RULES: Mapping[tuple[str, str], Mapping[str, Any]] = MappingProxyType(
    {
        ("relationship", "marriage"): RECTIFICATION_EVENT_RULES["marriage"],
        ("relationship", "separation"): MappingProxyType(
            {
                "label": "separation / divorce",
                "houses": [7, 8, 12],
                "vargas": ["D9"],
                "karakas": ["Venus", "Mars", "Saturn"],
                "fields": ["d9Lagna", "d9Structure", "currentDasha"],
                "sadeSatiRelevant": True,
            }
        ),
        ("career", "promotion"): MappingProxyType(
            {
                "label": "promotion / authority increase",
                "houses": [2, 10, 11],
                "vargas": ["D10"],
                "karakas": ["Sun", "Jupiter", "Saturn"],
                "fields": ["d10Lagna", "d10Structure", "currentDasha"],
            }
        ),
        ("career", "job_loss"): MappingProxyType(
            {
                "label": "job loss / work interruption",
                "houses": [6, 8, 10, 12],
                "vargas": ["D10"],
                "karakas": ["Saturn", "Mars", "Rahu"],
                "fields": ["d10Lagna", "d10Structure", "currentDasha"],
                "sadeSatiRelevant": True,
            }
        ),
        ("finance", "major_gain"): MappingProxyType(
            {
                "label": "major financial gain",
                "houses": [2, 9, 11],
                "vargas": ["D2"],
                "karakas": ["Jupiter", "Venus"],
                "fields": ["d2Lagna", "d2Structure", "currentDasha", "lagnaSign"],
            }
        ),
        ("finance", "major_loss"): MappingProxyType(
            {
                "label": "major financial loss",
                "houses": [2, 8, 12],
                "vargas": ["D2", "D30"],
                "karakas": ["Saturn", "Mars", "Rahu"],
                "fields": [
                    "d2Lagna",
                    "d2Structure",
                    "d30Lagna",
                    "d30Structure",
                    "currentDasha",
                    "lagnaSign",
                ],
                "sadeSatiRelevant": True,
            }
        ),
        ("property", "purchase"): MappingProxyType(
            {
                "label": "property purchase",
                "houses": [2, 4, 11],
                "vargas": ["D4"],
                "karakas": ["Mars", "Moon", "Jupiter"],
                "fields": ["d4Lagna", "d4Structure", "currentDasha"],
            }
        ),
        ("property", "sale"): MappingProxyType(
            {
                "label": "property sale",
                "houses": [4, 8, 12],
                "vargas": ["D4"],
                "karakas": ["Mars", "Saturn"],
                "fields": ["d4Lagna", "d4Structure", "currentDasha"],
            }
        ),
        ("health", "surgery"): MappingProxyType(
            {
                "label": "surgery / hospitalization",
                "houses": [1, 6, 8, 12],
                "vargas": ["D30"],
                "karakas": ["Mars", "Saturn", "Ketu"],
                "fields": ["d30Lagna", "d30Structure", "lagnaSign", "currentDasha"],
                "sadeSatiRelevant": True,
            }
        ),
    }
)


def rectification_rules_for(category: str, event_subtype: str | None = None) -> Mapping[str, Any]:
    """Resolve a versioned event rule without letting Agent semantics invent one."""

    subtype = str(event_subtype or "").strip().casefold()
    return RECTIFICATION_EVENT_SUBTYPE_RULES.get(
        (category, subtype),
        RECTIFICATION_EVENT_RULES.get(category, RECTIFICATION_EVENT_RULES["unknown"]),
    )
