from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


RECTIFICATION_RULE_ID = "rectify.event-evidence-ranking"
RECTIFICATION_KP_RULE_ID = "rectify.kp-sub-lord-corroboration"
RECTIFICATION_SCORING_POLICY_ID = "vedicdust-rectification-event-ranking/1.25.0"
RECTIFICATION_EVENT_MAPPING_ID = "vedicdust-rectification-event-map/1.8.0"
RECTIFICATION_HOLDOUT_POLICY_ID = "vedicdust-rectification-holdout/1.5.0"
RECTIFICATION_METHOD_MATURITY = "product_hypothesis"
RECTIFICATION_VALIDATION_STATUS = "internal_regression_only"
MINIMUM_RECTIFICATION_EVENTS = 4
RECTIFICATION_SOURCE_IDS = (
    "lineage.pvr-integrated-approach-2000-2010",
    "product.vedicdust-consultation-standard-1",
)

# Only these analysis components may rank or eliminate a birth-time candidate.
# They are complementary Jyotish layers, not statistically independent votes.
# Bounded D1 capacity, double transit, node transits, Sade Sati, KP, and Chara
# Dasha remain visible as auxiliary cross-checks until source-blind and
# professional validation grants their concrete implementations candidate-
# selection authority. The pinned rectification workflow directly supports
# event-period Dasha read through the event-relevant divisional chart.
RECTIFICATION_SELECTION_COMPONENTS = frozenset({"dasha", "varga"})

# A release-grade event needs both timing and its chart-specific domain layer.
# These are complementary Jyotish layers, not statistically independent votes.
RECTIFICATION_CONVERGENCE_COMPONENTS = frozenset({"dasha", "varga"})


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


# Direction is attached only when the subtype itself states an unambiguous
# constructive or disruptive outcome. A marriage, pregnancy, move, purchase,
# examination, or settlement does not reveal its quality and therefore remains
# neutral. Direction controls only bounded D1 capacity corroboration; it never
# turns one dignity condition into a deterministic life prediction.
RECTIFICATION_EVENT_OUTCOME_POLARITY: Mapping[tuple[str, str], str] = MappingProxyType(
    {
        ("education", "admission"): "constructive",
        ("education", "graduation"): "constructive",
        ("education", "exam"): "neutral",
        ("education", "study_abroad"): "neutral",
        ("career", "first_job"): "constructive",
        ("career", "promotion"): "constructive",
        ("career", "job_change"): "neutral",
        ("career", "job_loss"): "disruptive",
        ("relationship", "started_relationship"): "neutral",
        ("relationship", "marriage"): "neutral",
        ("relationship", "separation"): "disruptive",
        ("relocation", "moved_city"): "neutral",
        ("relocation", "moved_country"): "neutral",
        ("relocation", "first_home"): "neutral",
        ("child", "pregnancy"): "neutral",
        ("child", "birth"): "neutral",
        ("child", "child_major"): "neutral",
        ("health", "surgery"): "disruptive",
        ("health", "diagnosis"): "disruptive",
        ("health", "accident"): "disruptive",
        ("family", "family_structure"): "neutral",
        ("family", "parent_change"): "neutral",
        ("family", "caregiving"): "neutral",
        ("finance", "major_gain"): "constructive",
        ("finance", "major_loss"): "disruptive",
        ("finance", "financial_independence"): "constructive",
        ("property", "purchase"): "neutral",
        ("property", "sale"): "neutral",
        ("property", "move_home"): "neutral",
        ("legal", "lawsuit"): "disruptive",
        ("legal", "settlement"): "neutral",
        ("legal", "documents"): "neutral",
        ("loss", "bereavement"): "disruptive",
        ("loss", "sudden_loss"): "disruptive",
        ("spiritual", "practice"): "neutral",
        ("spiritual", "belief_change"): "neutral",
        ("spiritual", "community"): "neutral",
    }
)


@dataclass(frozen=True)
class RectificationScoringPolicy:
    policy_id: str
    dasha_level_weights: Mapping[str, float]
    natal_promise_support_weight: float
    varga_lagna_lord_support_weight: float
    double_transit_support_weight: float
    node_transit_support_weight: float
    sade_sati_support_weight: float
    kp_sub_lord_support_weight: float
    chara_dasha_level_weights: Mapping[str, float]
    minimum_calibration_events: int
    minimum_calibration_categories: int
    minimum_evidence_layers_per_event: int
    minimum_convergent_calibration_events: int
    minimum_discriminating_convergent_events: int
    event_discrimination_min_margin: float
    candidate_selection_min_score: float
    candidate_selection_min_margin: float
    holdout_min_score: float
    holdout_pass_margin: float


RECTIFICATION_SCORING_POLICY = RectificationScoringPolicy(
    policy_id=RECTIFICATION_SCORING_POLICY_ID,
    dasha_level_weights=MappingProxyType({"md": 0.12, "ad": 0.16, "pd": 0.10}),
    natal_promise_support_weight=0.10,
    varga_lagna_lord_support_weight=0.08,
    double_transit_support_weight=0.22,
    node_transit_support_weight=0.11,
    sade_sati_support_weight=0.09,
    kp_sub_lord_support_weight=0.10,
    chara_dasha_level_weights=MappingProxyType({"md": 0.08, "ad": 0.10, "pd": 0.06}),
    minimum_calibration_events=3,
    minimum_calibration_categories=2,
    minimum_evidence_layers_per_event=2,
    minimum_convergent_calibration_events=2,
    minimum_discriminating_convergent_events=2,
    event_discrimination_min_margin=0.05,
    candidate_selection_min_score=0.15,
    candidate_selection_min_margin=0.05,
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
            "fields": ["d9Lagna", "d9Structure"],
        },
        "relationship": {
            "label": "relationship change",
            "houses": [5, 7, 12],
            "vargas": ["D9"],
            "karakas": ["Venus", "Mars"],
            "fields": ["d9Lagna", "d9Structure"],
        },
        "career": {
            "label": "career change",
            "houses": [10, 6, 11],
            "vargas": ["D10"],
            "karakas": ["Sun", "Saturn", "Mercury"],
            "fields": ["d10Lagna", "d10Structure"],
            "sadeSatiRelevant": True,
        },
        "education": {
            "label": "education / examination",
            "houses": [4, 5, 9],
            "vargas": ["D24"],
            "karakas": ["Mercury", "Jupiter"],
            "fields": ["d24Lagna", "d24Structure"],
        },
        "relocation": {
            "label": "relocation / migration",
            "houses": [4, 9, 12],
            "vargas": ["D4"],
            "karakas": ["Moon", "Rahu"],
            "fields": ["d4Lagna", "d4Structure"],
        },
        "property": {
            "label": "home / property",
            "houses": [4, 11, 12],
            "vargas": ["D4"],
            "karakas": ["Mars", "Moon"],
            "fields": ["d4Lagna", "d4Structure"],
        },
        "child": {
            "label": "childbirth / child event",
            "houses": [5, 2, 9],
            "vargas": ["D7"],
            "karakas": ["Jupiter"],
            "fields": ["d7Lagna", "d7Structure"],
        },
        "health": {
            "label": "health / surgery",
            "houses": [1, 6, 8, 12],
            "vargas": ["D30"],
            "karakas": ["Mars", "Saturn"],
            "fields": ["d30Lagna", "d30Structure", "lagnaSign"],
            "sadeSatiRelevant": True,
        },
        "family": {
            "label": "family event",
            "houses": [2, 4, 8],
            "vargas": ["D12"],
            "karakas": ["Moon", "Sun"],
            "fields": ["d12Lagna", "d12Structure", "lagnaSign"],
            "sadeSatiRelevant": True,
        },
        "finance": {
            "label": "finance / income shock",
            "houses": [2, 6, 8, 11],
            "vargas": ["D2"],
            "karakas": ["Jupiter", "Venus", "Saturn"],
            "fields": ["d2Lagna", "d2Structure", "lagnaSign"],
            "sadeSatiRelevant": True,
        },
        "legal": {
            "label": "legal / dispute",
            "houses": [6, 8, 12],
            "vargas": ["D30"],
            "karakas": ["Mars", "Saturn", "Rahu"],
            "fields": ["d30Lagna", "d30Structure", "lagnaSign"],
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
            ],
        },
        "unknown": {
            "label": "dated life event",
            "houses": [],
            "vargas": [],
            "karakas": [],
            "fields": [],
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
                "fields": ["d9Lagna", "d9Structure"],
                "sadeSatiRelevant": True,
            }
        ),
        ("career", "promotion"): MappingProxyType(
            {
                "label": "promotion / authority increase",
                "houses": [2, 10, 11],
                "vargas": ["D10"],
                "karakas": ["Sun", "Jupiter", "Saturn"],
                "fields": ["d10Lagna", "d10Structure"],
            }
        ),
        ("career", "job_loss"): MappingProxyType(
            {
                "label": "job loss / work interruption",
                "houses": [6, 8, 10, 12],
                "vargas": ["D10"],
                "karakas": ["Saturn", "Mars", "Rahu"],
                "fields": ["d10Lagna", "d10Structure"],
                "sadeSatiRelevant": True,
            }
        ),
        ("finance", "major_gain"): MappingProxyType(
            {
                "label": "major financial gain",
                "houses": [2, 9, 11],
                "vargas": ["D2"],
                "karakas": ["Jupiter", "Venus"],
                "fields": ["d2Lagna", "d2Structure", "lagnaSign"],
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
                "fields": ["d4Lagna", "d4Structure"],
            }
        ),
        ("property", "sale"): MappingProxyType(
            {
                "label": "property sale",
                "houses": [4, 8, 12],
                "vargas": ["D4"],
                "karakas": ["Mars", "Saturn"],
                "fields": ["d4Lagna", "d4Structure"],
            }
        ),
        ("health", "surgery"): MappingProxyType(
            {
                "label": "surgery / hospitalization",
                "houses": [1, 6, 8, 12],
                "vargas": ["D30"],
                "karakas": ["Mars", "Saturn", "Ketu"],
                "fields": ["d30Lagna", "d30Structure", "lagnaSign"],
                "sadeSatiRelevant": True,
            }
        ),
    }
)


# Refinements cover every concrete user-facing subtype that materially changes
# the Jyotish domain being tested. "other" intentionally retains the category
# rule because it carries no narrower deterministic meaning.
RECTIFICATION_EVENT_SUBTYPE_REFINEMENTS: Mapping[tuple[str, str], Mapping[str, Any]] = (
    MappingProxyType(
        {
            ("education", "admission"): MappingProxyType(
                {
                    "label": "education admission",
                    "houses": [4, 5, 9],
                    "karakas": ["Mercury", "Jupiter"],
                }
            ),
            ("education", "graduation"): MappingProxyType(
                {
                    "label": "graduation / completion of study",
                    "houses": [4, 5, 9, 10, 11],
                    "karakas": ["Mercury", "Jupiter", "Saturn"],
                }
            ),
            ("education", "exam"): MappingProxyType(
                {
                    "label": "major examination",
                    "houses": [4, 5, 6, 9],
                    "karakas": ["Mercury", "Jupiter"],
                }
            ),
            ("education", "study_abroad"): MappingProxyType(
                {
                    "label": "study abroad",
                    "houses": [4, 5, 9, 12],
                    "vargas": ["D24", "D4"],
                    "karakas": ["Mercury", "Jupiter", "Rahu"],
                    "fields": [
                        "d24Lagna",
                        "d24Structure",
                        "d4Lagna",
                        "d4Structure",
                    ],
                }
            ),
            ("career", "first_job"): MappingProxyType(
                {
                    "label": "first sustained employment",
                    "houses": [2, 6, 10, 11],
                    "karakas": ["Sun", "Saturn", "Mercury"],
                }
            ),
            ("career", "job_change"): MappingProxyType(
                {
                    "label": "job or career change",
                    "houses": [3, 6, 10, 11, 12],
                    "karakas": ["Saturn", "Mercury", "Rahu"],
                }
            ),
            ("relationship", "started_relationship"): MappingProxyType(
                {
                    "label": "start of committed relationship",
                    "houses": [5, 7, 11],
                    "karakas": ["Venus", "Jupiter"],
                }
            ),
            ("relocation", "moved_city"): MappingProxyType(
                {
                    "label": "move to another city",
                    "houses": [3, 4, 9, 12],
                    "karakas": ["Moon", "Rahu"],
                }
            ),
            ("relocation", "moved_country"): MappingProxyType(
                {
                    "label": "international relocation",
                    "houses": [4, 9, 12],
                    "karakas": ["Moon", "Jupiter", "Rahu"],
                }
            ),
            ("relocation", "first_home"): MappingProxyType(
                {
                    "label": "first independent home",
                    "houses": [2, 4, 11, 12],
                    "karakas": ["Moon", "Mars"],
                }
            ),
            ("child", "pregnancy"): MappingProxyType(
                {
                    "label": "pregnancy milestone",
                    "houses": [5, 8, 9],
                    "karakas": ["Jupiter", "Moon"],
                }
            ),
            ("child", "birth"): MappingProxyType(
                {
                    "label": "birth of a child",
                    "houses": [2, 5, 9, 11],
                    "karakas": ["Jupiter", "Moon"],
                }
            ),
            ("child", "child_major"): MappingProxyType(
                {
                    "label": "major child-related event",
                    "houses": [2, 5, 8, 9],
                    "karakas": ["Jupiter"],
                }
            ),
            ("health", "diagnosis"): MappingProxyType(
                {
                    "label": "major diagnosis",
                    "houses": [1, 6, 8],
                    "karakas": ["Saturn", "Mars"],
                    "sadeSatiRelevant": True,
                }
            ),
            ("health", "accident"): MappingProxyType(
                {
                    "label": "serious accident",
                    "houses": [1, 3, 6, 8, 12],
                    "karakas": ["Mars", "Saturn", "Rahu"],
                    "sadeSatiRelevant": True,
                }
            ),
            ("family", "family_structure"): MappingProxyType(
                {
                    "label": "family structure change",
                    "houses": [2, 4, 8],
                    "karakas": ["Moon", "Sun"],
                }
            ),
            ("family", "parent_change"): MappingProxyType(
                {
                    "label": "major parent-related change",
                    "houses": [4, 8, 9, 10],
                    "karakas": ["Moon", "Sun", "Saturn"],
                }
            ),
            ("family", "caregiving"): MappingProxyType(
                {
                    "label": "major caregiving period",
                    "houses": [4, 6, 8, 12],
                    "karakas": ["Moon", "Saturn"],
                }
            ),
            ("finance", "financial_independence"): MappingProxyType(
                {
                    "label": "financial independence",
                    "houses": [2, 6, 10, 11],
                    "vargas": ["D2", "D10"],
                    "karakas": ["Jupiter", "Saturn", "Mercury"],
                    "fields": [
                        "d2Lagna",
                        "d2Structure",
                        "d10Lagna",
                        "d10Structure",
                        "lagnaSign",
                    ],
                }
            ),
            ("property", "move_home"): MappingProxyType(
                {"label": "change of home", "houses": [4, 12], "karakas": ["Moon", "Mars"]}
            ),
            ("legal", "lawsuit"): MappingProxyType(
                {
                    "label": "lawsuit or formal dispute",
                    "houses": [6, 8, 12],
                    "karakas": ["Mars", "Saturn", "Rahu"],
                }
            ),
            ("legal", "settlement"): MappingProxyType(
                {
                    "label": "legal settlement",
                    "houses": [6, 7, 8, 11],
                    "karakas": ["Jupiter", "Saturn"],
                }
            ),
            ("legal", "documents"): MappingProxyType(
                {
                    "label": "major legal documentation",
                    "houses": [3, 6, 9],
                    "karakas": ["Mercury", "Jupiter"],
                }
            ),
            ("loss", "bereavement"): MappingProxyType(
                {
                    "label": "bereavement",
                    "houses": [4, 8, 12],
                    "karakas": ["Saturn", "Ketu", "Moon"],
                }
            ),
            ("loss", "sudden_loss"): MappingProxyType(
                {
                    "label": "sudden major loss",
                    "houses": [3, 8, 12],
                    "karakas": ["Mars", "Saturn", "Ketu"],
                    "sadeSatiRelevant": True,
                }
            ),
            ("spiritual", "practice"): MappingProxyType(
                {
                    "label": "sustained spiritual practice",
                    "houses": [5, 9, 12],
                    "karakas": ["Jupiter", "Ketu"],
                }
            ),
            ("spiritual", "belief_change"): MappingProxyType(
                {
                    "label": "lasting belief change",
                    "houses": [5, 8, 9, 12],
                    "karakas": ["Jupiter", "Ketu", "Rahu"],
                }
            ),
            ("spiritual", "community"): MappingProxyType(
                {
                    "label": "entry into spiritual community",
                    "houses": [5, 9, 11, 12],
                    "karakas": ["Jupiter", "Ketu"],
                }
            ),
        }
    )
)


def rectification_rules_for(category: str, event_subtype: str | None = None) -> Mapping[str, Any]:
    """Resolve a versioned event rule without letting Agent semantics invent one."""

    subtype = str(event_subtype or "").strip().casefold()
    exact = RECTIFICATION_EVENT_SUBTYPE_RULES.get((category, subtype))
    if exact is not None:
        return exact
    base = RECTIFICATION_EVENT_RULES.get(category, RECTIFICATION_EVENT_RULES["unknown"])
    refinement = RECTIFICATION_EVENT_SUBTYPE_REFINEMENTS.get((category, subtype))
    if refinement is None:
        return base
    return MappingProxyType({**dict(base), **dict(refinement)})


def rectification_outcome_polarity(category: str, event_subtype: str | None = None) -> str:
    """Return a bounded event direction for D1 promise corroboration."""

    subtype = str(event_subtype or "").strip().casefold()
    return RECTIFICATION_EVENT_OUTCOME_POLARITY.get((category, subtype), "neutral")
