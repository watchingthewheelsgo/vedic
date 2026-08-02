from __future__ import annotations

import pytest

from app.calculator.dignity import (
    COMPOUND_RELATIONSHIPS,
    derive_dignity,
    natural_relationship,
    temporary_relationship,
)
from app.calculator.constants import SIGNS


def _placements(**overrides: int) -> dict[str, dict[str, int | str]]:
    sign_indices = {
        "Sun": 4,
        "Moon": 3,
        "Mars": 0,
        "Mercury": 2,
        "Jupiter": 8,
        "Venus": 1,
        "Saturn": 10,
    }
    sign_indices.update(overrides)
    return {
        graha: {"sign_idx": sign_index, "sign": SIGNS[sign_index]}
        for graha, sign_index in sign_indices.items()
    }


@pytest.mark.parametrize(
    ("graha", "other", "expected"),
    [
        ("Sun", "Moon", "friend"),
        ("Sun", "Mercury", "neutral"),
        ("Sun", "Saturn", "enemy"),
        ("Moon", "Saturn", "neutral"),
        ("Mars", "Mercury", "enemy"),
        ("Mercury", "Venus", "friend"),
        ("Jupiter", "Venus", "enemy"),
        ("Venus", "Jupiter", "neutral"),
        ("Saturn", "Venus", "friend"),
    ],
)
def test_natural_relationship_table(graha: str, other: str, expected: str) -> None:
    assert natural_relationship(graha, other) == expected


def test_temporary_relationship_covers_all_twelve_relative_signs() -> None:
    observed = [temporary_relationship(0, other_sign) for other_sign in range(12)]
    assert observed == [
        "temporary_enemy",
        "temporary_friend",
        "temporary_friend",
        "temporary_friend",
        "temporary_enemy",
        "temporary_enemy",
        "temporary_enemy",
        "temporary_enemy",
        "temporary_enemy",
        "temporary_friend",
        "temporary_friend",
        "temporary_friend",
    ]


@pytest.mark.parametrize(
    ("natural", "temporary", "expected"),
    [
        ("friend", "temporary_friend", "great_friend"),
        ("friend", "temporary_enemy", "neutral"),
        ("neutral", "temporary_friend", "friend"),
        ("neutral", "temporary_enemy", "enemy"),
        ("enemy", "temporary_friend", "neutral"),
        ("enemy", "temporary_enemy", "great_enemy"),
    ],
)
def test_compound_relationship_matrix(natural: str, temporary: str, expected: str) -> None:
    assert COMPOUND_RELATIONSHIPS[(natural, temporary)] == expected


@pytest.mark.parametrize(
    ("graha", "sign_index", "expected"),
    [
        ("Sun", 0, "exalted"),
        ("Sun", 6, "debilitated"),
        ("Sun", 4, "own_sign"),
        ("Mars", 9, "exalted"),
        ("Mars", 3, "debilitated"),
        ("Mars", 7, "own_sign"),
        ("Mercury", 5, "exalted"),
        ("Venus", 11, "exalted"),
        ("Saturn", 0, "debilitated"),
    ],
)
def test_special_sign_status_sets_effective_status_without_erasing_panchadha(
    graha: str, sign_index: int, expected: str
) -> None:
    placements = _placements(**{graha: sign_index})
    result = derive_dignity(graha, placements[graha], placements)

    assert result["basic"] == expected
    assert result["special"] == expected
    assert result["effective"] == expected
    assert result["compound"] == result["panchadha"]
    assert result["panchadha"] in {
        "own_sign",
        "great_friend",
        "friend",
        "neutral",
        "enemy",
        "great_enemy",
    }


def test_regular_sign_keeps_natural_temporary_and_compound_evidence_separate() -> None:
    placements = _placements(Sun=2, Mercury=4)

    result = derive_dignity("Sun", placements["Sun"], placements)

    assert result == {
        "basic": "neutral",
        "special": None,
        "signLord": "Mercury",
        "natural": "neutral",
        "temporary": "temporary_friend",
        "compound": "friend",
        "panchadha": "friend",
        "effective": "friend",
    }
