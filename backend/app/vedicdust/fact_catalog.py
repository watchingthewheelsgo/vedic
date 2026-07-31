from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping, TypeAlias


FactType: TypeAlias = Literal[
    "rashi.lagna.position",
    "rashi.graha.position",
    "rashi.house.lord",
    "varga.lagna.position",
    "varga.graha.position",
    "strength.dignity",
    "strength.shadbala",
    "ashtakavarga.sav.house",
    "aspect.graha_drishti",
]

FactValueKind: TypeAlias = Literal["object", "number"]


@dataclass(frozen=True)
class FactDefinition:
    fact_type: FactType
    subject_pattern: str
    value_kind: FactValueKind
    derivation_rule_id: str
    evidence_layer: Literal["natal_promise", "capacity", "varga_confirmation"]


GRAHA_PATTERN = r"(?:Sun|Moon|Mars|Mercury|Jupiter|Venus|Saturn|Rahu|Ketu)"
VARGA_PATTERN = r"D(?:2|3|4|5|7|9|10|12|16|20|24|27|30|60)"
HOUSE_PATTERN = r"H(?:[1-9]|1[0-2])"


FACT_CATALOG: dict[FactType, FactDefinition] = {
    "rashi.lagna.position": FactDefinition(
        fact_type="rashi.lagna.position",
        subject_pattern=r"D1\.Lagna",
        value_kind="object",
        derivation_rule_id="derive.astronomy.sidereal-position",
        evidence_layer="natal_promise",
    ),
    "rashi.graha.position": FactDefinition(
        fact_type="rashi.graha.position",
        subject_pattern=rf"D1\.{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.astronomy.sidereal-position",
        evidence_layer="natal_promise",
    ),
    "rashi.house.lord": FactDefinition(
        fact_type="rashi.house.lord",
        subject_pattern=rf"D1\.{HOUSE_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.rashi.whole-sign-house",
        evidence_layer="natal_promise",
    ),
    "varga.lagna.position": FactDefinition(
        fact_type="varga.lagna.position",
        subject_pattern=rf"{VARGA_PATTERN}\.Lagna",
        value_kind="object",
        derivation_rule_id="derive.varga.parashara-method-1",
        evidence_layer="varga_confirmation",
    ),
    "varga.graha.position": FactDefinition(
        fact_type="varga.graha.position",
        subject_pattern=rf"{VARGA_PATTERN}\.{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.varga.parashara-method-1",
        evidence_layer="varga_confirmation",
    ),
    "strength.dignity": FactDefinition(
        fact_type="strength.dignity",
        subject_pattern=rf"D1\.{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.strength.dignity",
        evidence_layer="capacity",
    ),
    "strength.shadbala": FactDefinition(
        fact_type="strength.shadbala",
        subject_pattern=rf"D1\.{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.strength.shadbala-pyjhora",
        evidence_layer="capacity",
    ),
    "ashtakavarga.sav.house": FactDefinition(
        fact_type="ashtakavarga.sav.house",
        subject_pattern=rf"D1\.{HOUSE_PATTERN}",
        value_kind="number",
        derivation_rule_id="derive.ashtakavarga.pyjhora",
        evidence_layer="capacity",
    ),
    "aspect.graha_drishti": FactDefinition(
        fact_type="aspect.graha_drishti",
        subject_pattern=rf"D1\.{GRAHA_PATTERN}->(?:{GRAHA_PATTERN}|{HOUSE_PATTERN})",
        value_kind="object",
        derivation_rule_id="derive.aspect.parashari-graha-drishti",
        evidence_layer="natal_promise",
    ),
}


def fact_definition(fact_type: FactType) -> FactDefinition:
    return FACT_CATALOG[fact_type]


def validate_fact_payload(fact_type: FactType, subject_ref: str, value: Any) -> None:
    definition = fact_definition(fact_type)
    if re.fullmatch(definition.subject_pattern, subject_ref) is None:
        raise ValueError(f"subject ref {subject_ref!r} is invalid for fact type {fact_type!r}")
    if definition.value_kind == "object" and not isinstance(value, Mapping):
        raise ValueError(f"fact type {fact_type!r} requires an object value")
    if definition.value_kind == "number" and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        raise ValueError(f"fact type {fact_type!r} requires a numeric value")
