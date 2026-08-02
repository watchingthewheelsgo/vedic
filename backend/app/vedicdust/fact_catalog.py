from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping, TypeAlias


FactType: TypeAlias = Literal[
    "rashi.lagna.position",
    "rashi.graha.position",
    "rashi.house.lord",
    "rashi.house.occupant",
    "role.house_ownership",
    "relationship.same_sign",
    "relationship.parivartana",
    "yoga.raja.kendra_trikona",
    "yoga.gaja_kesari.structure",
    "relationship.dispositor_chain",
    "varga.lagna.position",
    "varga.graha.position",
    "varga.house.lord",
    "varga.vargottama",
    "strength.dignity",
    "strength.shadbala",
    "strength.combustion",
    "strength.digbala",
    "strength.bhava_bala",
    "strength.vargeeya_bala",
    "ashtakavarga.sav.house",
    "ashtakavarga.bav.graha",
    "karaka.chara",
    "point.arudha",
    "point.special_lagna",
    "state.moon_phase",
    "aspect.graha_drishti",
    "timing.transit.position",
    "timing.transit.house",
    "timing.transit.sade_sati",
    "timing.transit.double_transit",
]

FactValueKind: TypeAlias = Literal["object", "number"]


@dataclass(frozen=True)
class FactDefinition:
    fact_type: FactType
    subject_pattern: str
    value_kind: FactValueKind
    derivation_rule_id: str
    evidence_layer: Literal["natal_promise", "capacity", "varga_confirmation", "timing"]


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
    "rashi.house.occupant": FactDefinition(
        fact_type="rashi.house.occupant",
        subject_pattern=rf"D1\.{HOUSE_PATTERN}\.occupant\.{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.rashi.whole-sign-house",
        evidence_layer="natal_promise",
    ),
    "role.house_ownership": FactDefinition(
        fact_type="role.house_ownership",
        subject_pattern=rf"D1\.{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.role.house-ownership",
        evidence_layer="natal_promise",
    ),
    "relationship.same_sign": FactDefinition(
        fact_type="relationship.same_sign",
        subject_pattern=rf"D1\.{GRAHA_PATTERN}~{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.relationship.same-sign-conjunction",
        evidence_layer="natal_promise",
    ),
    "relationship.parivartana": FactDefinition(
        fact_type="relationship.parivartana",
        subject_pattern=rf"D1\.{GRAHA_PATTERN}~{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.relationship.parivartana",
        evidence_layer="natal_promise",
    ),
    "yoga.raja.kendra_trikona": FactDefinition(
        fact_type="yoga.raja.kendra_trikona",
        subject_pattern=rf"D1\.{GRAHA_PATTERN}~{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.yoga.kendra-trikona-association",
        evidence_layer="natal_promise",
    ),
    "yoga.gaja_kesari.structure": FactDefinition(
        fact_type="yoga.gaja_kesari.structure",
        subject_pattern=r"D1\.Moon~Jupiter",
        value_kind="object",
        derivation_rule_id="derive.yoga.gaja-kesari-structure",
        evidence_layer="natal_promise",
    ),
    "relationship.dispositor_chain": FactDefinition(
        fact_type="relationship.dispositor_chain",
        subject_pattern=rf"D1\.{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.relationship.dispositor-chain",
        evidence_layer="natal_promise",
    ),
    "varga.lagna.position": FactDefinition(
        fact_type="varga.lagna.position",
        subject_pattern=rf"{VARGA_PATTERN}\.Lagna",
        value_kind="object",
        derivation_rule_id="derive.varga.profile-pinned",
        evidence_layer="varga_confirmation",
    ),
    "varga.graha.position": FactDefinition(
        fact_type="varga.graha.position",
        subject_pattern=rf"{VARGA_PATTERN}\.{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.varga.profile-pinned",
        evidence_layer="varga_confirmation",
    ),
    "varga.house.lord": FactDefinition(
        fact_type="varga.house.lord",
        subject_pattern=rf"{VARGA_PATTERN}\.{HOUSE_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.varga.profile-pinned",
        evidence_layer="varga_confirmation",
    ),
    "varga.vargottama": FactDefinition(
        fact_type="varga.vargottama",
        subject_pattern=rf"D1\.(?:Lagna|{GRAHA_PATTERN})",
        value_kind="object",
        derivation_rule_id="derive.varga.d1-d9-vargottama",
        evidence_layer="capacity",
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
    "strength.combustion": FactDefinition(
        fact_type="strength.combustion",
        subject_pattern=rf"D1\.{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.capacity.combustion-threshold",
        evidence_layer="capacity",
    ),
    "strength.digbala": FactDefinition(
        fact_type="strength.digbala",
        subject_pattern=rf"D1\.{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.capacity.directional-strength-house",
        evidence_layer="capacity",
    ),
    "strength.bhava_bala": FactDefinition(
        fact_type="strength.bhava_bala",
        subject_pattern=rf"D1\.{HOUSE_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.strength.bhava-bala-pyjhora",
        evidence_layer="capacity",
    ),
    "strength.vargeeya_bala": FactDefinition(
        fact_type="strength.vargeeya_bala",
        subject_pattern=rf"D1\.{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.strength.vargeeya-bala-pyjhora",
        evidence_layer="capacity",
    ),
    "ashtakavarga.sav.house": FactDefinition(
        fact_type="ashtakavarga.sav.house",
        subject_pattern=rf"D1\.{HOUSE_PATTERN}",
        value_kind="number",
        derivation_rule_id="derive.ashtakavarga.pyjhora",
        evidence_layer="capacity",
    ),
    "ashtakavarga.bav.graha": FactDefinition(
        fact_type="ashtakavarga.bav.graha",
        subject_pattern=rf"D1\.{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.ashtakavarga.pyjhora",
        evidence_layer="capacity",
    ),
    "karaka.chara": FactDefinition(
        fact_type="karaka.chara",
        subject_pattern=rf"D1\.{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.role.chara-karaka-7k",
        evidence_layer="capacity",
    ),
    "point.arudha": FactDefinition(
        fact_type="point.arudha",
        subject_pattern=r"D1\.(?:AL|UL)",
        value_kind="object",
        derivation_rule_id="derive.point.arudha-al-ul",
        evidence_layer="capacity",
    ),
    "point.special_lagna": FactDefinition(
        fact_type="point.special_lagna",
        subject_pattern=r"D1\.special_lagna\.[a-z_]+",
        value_kind="object",
        derivation_rule_id="derive.point.special-lagna-pyjhora",
        evidence_layer="capacity",
    ),
    "state.moon_phase": FactDefinition(
        fact_type="state.moon_phase",
        subject_pattern=r"D1\.Moon",
        value_kind="object",
        derivation_rule_id="derive.state.lunar-phase-hemicycle",
        evidence_layer="capacity",
    ),
    "aspect.graha_drishti": FactDefinition(
        fact_type="aspect.graha_drishti",
        subject_pattern=rf"D1\.{GRAHA_PATTERN}->(?:{GRAHA_PATTERN}|{HOUSE_PATTERN})",
        value_kind="object",
        derivation_rule_id="derive.aspect.parashari-graha-drishti",
        evidence_layer="natal_promise",
    ),
    "timing.transit.position": FactDefinition(
        fact_type="timing.transit.position",
        subject_pattern=rf"Transit\.{GRAHA_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.timing.transit-position-swisseph",
        evidence_layer="timing",
    ),
    "timing.transit.house": FactDefinition(
        fact_type="timing.transit.house",
        subject_pattern=rf"Transit\.{GRAHA_PATTERN}->D1\.{HOUSE_PATTERN}",
        value_kind="object",
        derivation_rule_id="derive.timing.transit-whole-sign-house",
        evidence_layer="timing",
    ),
    "timing.transit.sade_sati": FactDefinition(
        fact_type="timing.transit.sade_sati",
        subject_pattern=r"Transit\.Saturn\.Moon",
        value_kind="object",
        derivation_rule_id="derive.timing.sade-sati-phase",
        evidence_layer="timing",
    ),
    "timing.transit.double_transit": FactDefinition(
        fact_type="timing.transit.double_transit",
        subject_pattern=r"Transit\.Saturn~Jupiter",
        value_kind="object",
        derivation_rule_id="derive.timing.saturn-jupiter-double-transit",
        evidence_layer="timing",
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
