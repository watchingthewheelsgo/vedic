from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping


VARGA_DOMAIN_POLICY_ID = "vedicdust-varga-domain-policy/1.0.0"
VARGA_DOMAIN_SOURCE_IDS = ("lineage.pvr-integrated-approach-2000-2010",)

VargaUsageTier = Literal[
    "primary_foundation",
    "supporting_domain",
    "rectification_domain",
    "advanced_validation",
    "final_confirmation_only",
]


@dataclass(frozen=True)
class VargaDomainPolicy:
    factor: int
    name: str
    scope: str
    usage_tier: VargaUsageTier


# These scopes select the relevant chart for a topic. They do not assign a
# favorable or unfavorable outcome and do not replace D1 promise or timing.
VARGA_DOMAIN_POLICIES: Mapping[int, VargaDomainPolicy] = MappingProxyType(
    {
        1: VargaDomainPolicy(
            1, "Rashi", "physical existence and chart foundation", "primary_foundation"
        ),
        2: VargaDomainPolicy(2, "Hora", "wealth and money", "supporting_domain"),
        3: VargaDomainPolicy(3, "Drekkana", "siblings", "supporting_domain"),
        4: VargaDomainPolicy(
            4,
            "Chaturthamsha",
            "residence, houses, property, and fortune",
            "supporting_domain",
        ),
        5: VargaDomainPolicy(5, "Panchamsha", "fame, authority, and power", "supporting_domain"),
        7: VargaDomainPolicy(
            7,
            "Saptamsha",
            "children and grandchildren",
            "rectification_domain",
        ),
        9: VargaDomainPolicy(
            9,
            "Navamsha",
            "marriage, spouse, dharma, interaction, basic skills, and inner self",
            "rectification_domain",
        ),
        10: VargaDomainPolicy(
            10,
            "Dashamsha",
            "career, activities, and achievements in society",
            "rectification_domain",
        ),
        12: VargaDomainPolicy(
            12,
            "Dwadashamsha",
            "parents and parents' blood relatives",
            "rectification_domain",
        ),
        16: VargaDomainPolicy(
            16,
            "Shodashamsha",
            "vehicles, pleasures, comforts, and discomforts",
            "advanced_validation",
        ),
        20: VargaDomainPolicy(
            20,
            "Vimshamsha",
            "religious and spiritual matters",
            "advanced_validation",
        ),
        24: VargaDomainPolicy(
            24,
            "Chaturvimshamsha",
            "learning, knowledge, and education",
            "advanced_validation",
        ),
        27: VargaDomainPolicy(
            27,
            "Bhamsa",
            "strengths, weaknesses, and inherent nature",
            "advanced_validation",
        ),
        30: VargaDomainPolicy(
            30,
            "Trimshamsha",
            "adversity, punishment, subconscious patterns, and some health troubles",
            "advanced_validation",
        ),
        60: VargaDomainPolicy(
            60,
            "Shashtiamsha",
            "past-life karma and final confirmation across all matters",
            "final_confirmation_only",
        ),
    }
)

SUPPORTED_VARGA_FACTORS = tuple(VARGA_DOMAIN_POLICIES)
INDEPENDENT_REFERENCE_VARGA_IDS = tuple(
    f"D{factor}" for factor in SUPPORTED_VARGA_FACTORS if factor != 1
)


def varga_domain_policy(factor: int) -> VargaDomainPolicy:
    try:
        return VARGA_DOMAIN_POLICIES[factor]
    except KeyError as exc:
        raise ValueError(f"unsupported VedicDust varga domain factor: {factor}") from exc
