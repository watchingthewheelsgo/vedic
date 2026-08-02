"""Deterministic Parashari sign dignity and Panchadha Maitri derivation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .constants import SIGN_LORDS


CLASSICAL_GRAHAS = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")

EXALTATION_SIGNS = {
    "Sun": "Aries",
    "Moon": "Taurus",
    "Mars": "Capricorn",
    "Mercury": "Virgo",
    "Jupiter": "Cancer",
    "Venus": "Pisces",
    "Saturn": "Libra",
}

DEBILITATION_SIGNS = {
    "Sun": "Libra",
    "Moon": "Scorpio",
    "Mars": "Cancer",
    "Mercury": "Pisces",
    "Jupiter": "Capricorn",
    "Venus": "Virgo",
    "Saturn": "Aries",
}

OWN_SIGNS = {
    "Sun": frozenset({"Leo"}),
    "Moon": frozenset({"Cancer"}),
    "Mars": frozenset({"Aries", "Scorpio"}),
    "Mercury": frozenset({"Gemini", "Virgo"}),
    "Jupiter": frozenset({"Sagittarius", "Pisces"}),
    "Venus": frozenset({"Taurus", "Libra"}),
    "Saturn": frozenset({"Capricorn", "Aquarius"}),
}

NATURAL_RELATIONSHIPS = {
    "Sun": {
        "friend": frozenset({"Moon", "Mars", "Jupiter"}),
        "enemy": frozenset({"Venus", "Saturn"}),
    },
    "Moon": {
        "friend": frozenset({"Sun", "Mercury"}),
        "enemy": frozenset(),
    },
    "Mars": {
        "friend": frozenset({"Sun", "Moon", "Jupiter"}),
        "enemy": frozenset({"Mercury"}),
    },
    "Mercury": {
        "friend": frozenset({"Sun", "Venus"}),
        "enemy": frozenset({"Moon"}),
    },
    "Jupiter": {
        "friend": frozenset({"Sun", "Moon", "Mars"}),
        "enemy": frozenset({"Mercury", "Venus"}),
    },
    "Venus": {
        "friend": frozenset({"Mercury", "Saturn"}),
        "enemy": frozenset({"Sun", "Moon"}),
    },
    "Saturn": {
        "friend": frozenset({"Mercury", "Venus"}),
        "enemy": frozenset({"Sun", "Moon", "Mars"}),
    },
}

COMPOUND_RELATIONSHIPS = {
    ("friend", "temporary_friend"): "great_friend",
    ("friend", "temporary_enemy"): "neutral",
    ("enemy", "temporary_friend"): "neutral",
    ("enemy", "temporary_enemy"): "great_enemy",
    ("neutral", "temporary_friend"): "friend",
    ("neutral", "temporary_enemy"): "enemy",
}

_TEMPORARY_FRIEND_OFFSETS = frozenset({1, 2, 3, 9, 10, 11})


def natural_relationship(graha: str, other_graha: str) -> str:
    if graha not in CLASSICAL_GRAHAS or other_graha not in CLASSICAL_GRAHAS:
        raise ValueError("natural relationship requires two classical grahas")
    if graha == other_graha:
        return "own"
    relationship = NATURAL_RELATIONSHIPS[graha]
    if other_graha in relationship["friend"]:
        return "friend"
    if other_graha in relationship["enemy"]:
        return "enemy"
    return "neutral"


def temporary_relationship(graha_sign_index: int, other_sign_index: int) -> str:
    if not 0 <= graha_sign_index <= 11 or not 0 <= other_sign_index <= 11:
        raise ValueError("sign indices must be between 0 and 11")
    offset = (other_sign_index - graha_sign_index) % 12
    if offset in _TEMPORARY_FRIEND_OFFSETS:
        return "temporary_friend"
    return "temporary_enemy"


def derive_dignity(
    graha: str,
    placement: Mapping[str, Any],
    placements: Mapping[str, Mapping[str, Any]],
) -> dict[str, str | None]:
    """Return special sign status plus natural, temporary, and compound relations."""

    if graha not in CLASSICAL_GRAHAS:
        raise ValueError(f"unsupported dignity graha: {graha}")
    sign = str(placement["sign"])
    sign_index = int(placement["sign_idx"])
    sign_lord = SIGN_LORDS[sign_index]

    if EXALTATION_SIGNS[graha] == sign:
        special_status = "exalted"
    elif DEBILITATION_SIGNS[graha] == sign:
        special_status = "debilitated"
    elif sign in OWN_SIGNS[graha]:
        special_status = "own_sign"
    else:
        special_status = None

    natural = natural_relationship(graha, sign_lord)
    if natural == "own":
        temporary = None
        panchadha = "own_sign"
    else:
        lord_placement = placements.get(sign_lord)
        if lord_placement is None:
            raise ValueError(f"missing sign-lord placement for {sign_lord}")
        temporary = temporary_relationship(sign_index, int(lord_placement["sign_idx"]))
        panchadha = COMPOUND_RELATIONSHIPS[(natural, temporary)]

    effective = special_status or panchadha
    return {
        "basic": special_status or natural,
        "special": special_status,
        "signLord": sign_lord,
        "natural": natural,
        "temporary": temporary,
        "compound": panchadha,
        "panchadha": panchadha,
        "effective": effective,
    }


def derive_dignities(
    placements: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, str | None]]:
    missing = [graha for graha in CLASSICAL_GRAHAS if graha not in placements]
    if missing:
        raise ValueError(f"missing classical graha placements: {', '.join(missing)}")
    return {
        graha: derive_dignity(graha, placements[graha], placements) for graha in CLASSICAL_GRAHAS
    }
