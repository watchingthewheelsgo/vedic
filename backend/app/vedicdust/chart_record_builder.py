from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Literal, Mapping

import pytz

from app.calculator.civil_time import resolve_civil_time
from app.calculator.constants import SIGNS, SIGN_LORDS
from app.vedicdust.event_time import EVENT_TIMEZONE_BASIS, event_utc_envelope

from .fact_catalog import FactType, fact_definition
from .confidence import minimum_confidence
from .models import (
    AstronomySnapshot,
    BirthAssertion,
    CanonicalBirthMoment,
    CandidateEvidenceScore,
    CandidateInterval,
    CandidatePlaceHypothesis,
    ChartPlacement,
    ConfidenceGrade,
    EvidenceClass,
    EvidenceItem,
    GrahaPosition,
    IndependentReferenceSnapshot,
    InputSensitivityAssessment,
    JyotishFact,
    LifeEvent,
    PlaceResolution,
    QualityCheck,
    RectificationDecision,
    RectificationEvidenceObservation,
    RectificationRecord,
    RuleProvenance,
    SubjectContext,
    SensitivityBoundary,
    TimeRange,
    TimingBoundaryEnvelope,
    TimingPeriod,
    VargaChart,
    VargaHouseLord,
    ChartRecord,
    ZodiacPosition,
)
from .profiles import parashari_lahiri_profile, varga_method_setting
from .rectification_policy import (
    RECTIFICATION_CONVERGENCE_COMPONENTS,
    RECTIFICATION_EVENT_MAPPING_ID,
    RECTIFICATION_HOLDOUT_POLICY_ID,
    RECTIFICATION_METHOD_MATURITY,
    RECTIFICATION_SCORING_POLICY_ID,
    RECTIFICATION_SOURCE_IDS,
    RECTIFICATION_VALIDATION_STATUS,
)
from .source_registry import load_rule_catalog
from .sensitivity import (
    TIMING_SENSITIVITY_DEPENDENCIES,
    build_input_sensitivity_assessment,
    expected_fact_input_stability,
    expected_timing_input_stability,
    fact_sensitivity_dependencies,
)
from .validation import validate_chart_record_provenance


GRAHAS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
DASHA_REFERENCE_TOLERANCE_SECONDS = 120.0
NAKSHATRAS = [
    "Ashwini",
    "Bharani",
    "Krittika",
    "Rohini",
    "Mrigashira",
    "Ardra",
    "Punarvasu",
    "Pushya",
    "Ashlesha",
    "Magha",
    "Purva Phalguni",
    "Uttara Phalguni",
    "Hasta",
    "Chitra",
    "Swati",
    "Vishakha",
    "Anuradha",
    "Jyeshtha",
    "Moola",
    "Purva Ashadha",
    "Uttara Ashadha",
    "Shravana",
    "Dhanishta",
    "Shatabhisha",
    "Purva Bhadrapada",
    "Uttara Bhadrapada",
    "Revati",
]


@dataclass(frozen=True)
class ChartRecordBuildInput:
    chart_record_id: str
    reading_session_id: str
    revision: int
    subject_id: str
    created_at: datetime
    locale: str
    birth_date: str
    birth_time: str
    birth_place: str
    birth_time_precision: str
    time_source: str
    gender_context: str
    relationship_status: str
    reader_relationship: Literal["self", "parent", "partner", "family", "professional"]
    consultation_topics: tuple[str, ...]
    place_label: str
    latitude: float
    longitude: float
    timezone_id: str
    place_source: str
    place_accuracy: str
    place_confidence: str
    place_matched: Mapping[str, str] | None
    calculation_version: str
    ephemeris_version: str
    provider_versions: Mapping[str, str]
    timezone_database_version: str
    ephemeris_data_fingerprint: str
    chart: Mapping[str, Any]
    input_context: Mapping[str, Any]
    sensitivity_scan: Mapping[str, Any]
    utc_offset_seconds: int | None = None
    independent_reference: IndependentReferenceSnapshot | Mapping[str, Any] | None = None


def build_chart_record(source: ChartRecordBuildInput) -> ChartRecord:
    profile = parashari_lahiri_profile()
    local_moment = _local_moment(
        source.birth_date,
        source.birth_time,
        source.timezone_id,
        utc_offset_seconds=source.utc_offset_seconds,
    )
    utc_moment = local_moment.astimezone(pytz.utc)
    place_confidence = _confidence(source.place_confidence)
    birth_confidence = _birth_confidence(source.birth_time_precision)

    place_evidence = EvidenceItem(
        evidence_id=f"{source.chart_record_id}.place-resolution",
        evidence_class=_place_evidence_class(source.place_source),
        source_label=source.place_source,
        observed_value=(
            f"{source.place_label} @ {source.latitude:.6f},{source.longitude:.6f} "
            f"({source.timezone_id})"
        ),
        confidence=place_confidence,
        notes=_matched_place_note(source.place_matched),
    )
    birth_evidence = EvidenceItem(
        evidence_id=f"{source.chart_record_id}.birth-assertion",
        evidence_class=EvidenceClass.USER_TESTIMONY,
        source_label=source.time_source or "user-input",
        observed_value=f"{source.birth_date} {source.birth_time} @ {source.birth_place}",
        confidence=birth_confidence,
    )

    canonical_moment = CanonicalBirthMoment(
        local_datetime=local_moment,
        utc_datetime=utc_moment,
        timezone_id=source.timezone_id,
        utc_offset_seconds=int(local_moment.utcoffset().total_seconds()),
        historical_offset_status="resolved",
        place=PlaceResolution(
            label=source.place_label,
            point={
                "latitudeDeg": source.latitude,
                "longitudeDeg": source.longitude,
                "datum": "WGS84",
            },
            precision=_place_precision(source.place_accuracy),
            timezone_id=source.timezone_id,
            evidence=[place_evidence],
        ),
        resolution_confidence=minimum_confidence(birth_confidence, place_confidence),
    )

    astronomy = _astronomy_snapshot(source)
    independent_reference_passed = (
        _independent_reference_check(source.chart, source.independent_reference).status == "passed"
    )
    charts = _varga_charts(
        source.chart,
        source.sensitivity_scan,
        independent_reference_passed=independent_reference_passed,
    )
    input_sensitivity = build_input_sensitivity_assessment(source.sensitivity_scan)
    facts = _facts(source.chart, charts, profile.profile_id, input_sensitivity)
    timing_periods = _timing_periods(
        source.chart,
        source.timezone_id,
        profile.profile_id,
        input_sensitivity,
        canonical_moment.resolution_confidence,
        source.sensitivity_scan,
    )
    quality_checks = _quality_checks(source.chart, charts, source.independent_reference)
    rectification = _rectification(source, birth_confidence)

    has_failed_check = any(check.status == "failed" for check in quality_checks)
    rectification_calculation_failed = (
        rectification is not None and rectification.decision.status == "calculation_failed"
    )
    requires_rectification = rectification is not None and rectification.decision.status not in {
        "not_required",
        "bounded_interval",
        "multiple_equivalent",
    }
    status = (
        "blocked"
        if has_failed_check or rectification_calculation_failed
        else "rectification_required"
        if requires_rectification
        else "ready_for_judgement"
    )

    result = ChartRecord(
        chart_record_id=source.chart_record_id,
        reading_session_id=source.reading_session_id,
        revision=source.revision,
        created_at=source.created_at,
        subject=SubjectContext(
            subject_id=source.subject_id,
            locale=source.locale if source.locale in {"zh", "en", "ja"} else "en",
            current_age=_age_on(date.fromisoformat(source.birth_date), source.created_at.date()),
            life_stage=_life_stage(
                _age_on(date.fromisoformat(source.birth_date), source.created_at.date())
            ),
            reader_relationship=source.reader_relationship,
            gender_context=source.gender_context,
            relationship_status=source.relationship_status,
            consultation_topics=list(source.consultation_topics),
        ),
        birth_assertion=BirthAssertion(
            local_date=source.birth_date,
            reported_local_time=source.birth_time,
            reported_place=source.birth_place,
            time_certainty=_time_certainty(source.birth_time_precision),
            reported_time_window=_reported_window(source.input_context, source.timezone_id),
            evidence=[birth_evidence],
        ),
        canonical_moment=canonical_moment,
        calculation_profile=profile,
        astronomy=astronomy,
        charts=charts,
        facts=facts,
        timing_periods=timing_periods,
        quality_checks=quality_checks,
        input_sensitivity=input_sensitivity,
        sensitivity_boundaries=_sensitivity_boundaries(source),
        rectification=rectification,
        status=status,
    )
    validate_chart_record_provenance(result, load_rule_catalog())
    return result


def _astronomy_snapshot(source: ChartRecordBuildInput) -> AstronomySnapshot:
    chart = source.chart
    planets = chart.get("planets") or {}
    return AstronomySnapshot(
        snapshot_id=f"{source.chart_record_id}.astronomy.r{source.revision}",
        calculated_at=source.created_at,
        julian_day_ut=float(chart["julian_day_ut"]),
        calculation_provider="Swiss Ephemeris + PyJHora",
        calculation_adapter_version=source.calculation_version,
        ephemeris_version=source.ephemeris_version,
        provider_versions=dict(source.provider_versions),
        timezone_database_version=source.timezone_database_version,
        ephemeris_data_fingerprint=source.ephemeris_data_fingerprint,
        ayanamsa_value_deg=float(chart["ayanamsa"]),
        ascendant=_zodiac_position(chart["lagna"]),
        grahas=[
            GrahaPosition(
                graha=name,
                position=_zodiac_position(planets[name]),
                speed_deg_per_day=_optional_float(planets[name].get("speed")),
                motion=("retrograde" if planets[name].get("retrograde") else "direct"),
            )
            for name in GRAHAS
        ],
        status="complete",
    )


def _varga_charts(
    chart: Mapping[str, Any],
    sensitivity_scan: Mapping[str, Any],
    *,
    independent_reference_passed: bool = False,
) -> list[VargaChart]:
    raw_charts = chart.get("divisional_charts") or {}
    confidence_map = (sensitivity_scan.get("summary") or {}).get("divisionalConfidence") or {}
    result: list[VargaChart] = []
    for factor in parashari_lahiri_profile().supported_vargas:
        key = f"D{factor}"
        raw = raw_charts.get(key)
        if not isinstance(raw, Mapping) or "error" in raw or "Lagna" not in raw:
            continue
        confidence_entry = confidence_map.get(key) or {}
        input_stability = _division_confidence(confidence_entry)
        if factor == 1:
            lagna = chart["lagna"]
            lagna_index = int(lagna["sign_idx"])
            placements = [
                ChartPlacement(
                    object_id=name,
                    position=_zodiac_position(chart["planets"][name]),
                    house=((int(chart["planets"][name]["sign_idx"]) - lagna_index) % 12) + 1,
                )
                for name in GRAHAS
            ]
            result.append(
                VargaChart(
                    varga_id=key,
                    factor=factor,
                    method="canonical-swiss-ephemeris",
                    lagna=ChartPlacement(
                        object_id="Lagna",
                        position=_zodiac_position(lagna),
                        house=1,
                    ),
                    placements=placements,
                    house_lords=_varga_house_lords(lagna_index, placements),
                    inputStability=input_stability,
                    calculationAssurance="astronomical_authority",
                    confidence=minimum_confidence(
                        input_stability,
                        ConfidenceGrade.VERIFIED,
                    ),
                    eligible_as_primary_evidence=True,
                )
            )
            continue
        lagna = raw["Lagna"]
        lagna_index = int(lagna["sign_idx"])
        placements = [
            ChartPlacement(
                object_id=name,
                position=_varga_position(raw[name]),
                house=((int(raw[name]["sign_idx"]) - lagna_index) % 12) + 1,
            )
            for name in GRAHAS
            if isinstance(raw.get(name), Mapping)
        ]
        result.append(
            VargaChart(
                varga_id=key,
                factor=factor,
                method=varga_method_setting(factor).algorithm_id,
                lagna=ChartPlacement(
                    object_id="Lagna",
                    position=_varga_position(lagna),
                    house=1,
                ),
                placements=placements,
                house_lords=_varga_house_lords(lagna_index, placements),
                inputStability=input_stability,
                calculationAssurance=(
                    "independent_external_match"
                    if independent_reference_passed
                    else "internal_provider_regression"
                ),
                confidence=minimum_confidence(
                    input_stability,
                    ConfidenceGrade.VERIFIED
                    if independent_reference_passed
                    else ConfidenceGrade.CORROBORATED,
                ),
                eligible_as_primary_evidence=(
                    True
                    if factor == 1
                    else bool(confidence_entry.get("useAsPrimaryEvidence", False))
                ),
            )
        )
    return result


def _varga_house_lords(
    lagna_sign_index: int, placements: list[ChartPlacement]
) -> list[VargaHouseLord]:
    placement_houses = {placement.object_id: placement.house for placement in placements}
    return [
        VargaHouseLord(
            house=house,
            sign=SIGNS[sign_index],
            sign_index=sign_index,
            lord=SIGN_LORDS[sign_index],
            lord_house=placement_houses.get(SIGN_LORDS[sign_index]),
        )
        for house in range(1, 13)
        for sign_index in [(lagna_sign_index + house - 1) % 12]
    ]


def _kendra_trikona_associations(
    house_lords: Mapping[Any, Any], source: str, target: str
) -> list[dict[str, Any]]:
    """Return only the declared same-sign kendra/trikona lord associations."""

    if source == target or source not in GRAHAS[:7] or target not in GRAHAS[:7]:
        return []
    owned: dict[str, set[int]] = {source: set(), target: set()}
    for raw_house, value in house_lords.items():
        if not isinstance(value, Mapping):
            continue
        try:
            house = int(raw_house)
        except (TypeError, ValueError):
            continue
        lord = str(value.get("lord") or "")
        if lord in owned:
            owned[lord].add(house)

    associations: list[dict[str, Any]] = []
    for kendra_lord, trikona_lord in ((source, target), (target, source)):
        kendra_houses = sorted(owned[kendra_lord] & {1, 4, 7, 10})
        trikona_houses = sorted(owned[trikona_lord] & {1, 5, 9})
        if kendra_houses and trikona_houses:
            associations.append(
                {
                    "kendraLord": kendra_lord,
                    "kendraHouses": kendra_houses,
                    "trikonaLord": trikona_lord,
                    "trikonaHouses": trikona_houses,
                }
            )
    return associations


def _parivartana_exchanges(house_lords: Mapping[Any, Any]) -> list[dict[str, Any]]:
    """Return exact D1 house-lord exchanges without assigning an outcome."""

    normalized: dict[int, tuple[str, int]] = {}
    for raw_house, value in house_lords.items():
        if not isinstance(value, Mapping):
            continue
        try:
            house = int(raw_house)
            lord_house = int(value["lord_house"])
        except (KeyError, TypeError, ValueError):
            continue
        lord = str(value.get("lord") or "")
        if house not in range(1, 13) or lord_house not in range(1, 13) or lord not in GRAHAS[:7]:
            continue
        normalized[house] = (lord, lord_house)

    exchanges: list[dict[str, Any]] = []
    for first_house in range(1, 13):
        first = normalized.get(first_house)
        if first is None:
            continue
        first_lord, first_lord_house = first
        second_house = first_lord_house
        if second_house <= first_house:
            continue
        second = normalized.get(second_house)
        if second is None:
            continue
        second_lord, second_lord_house = second
        if first_lord == second_lord or second_lord_house != first_house:
            continue
        exchanges.append(
            {
                "houses": [first_house, second_house],
                "lords": [first_lord, second_lord],
                "placements": {
                    first_lord: second_house,
                    second_lord: first_house,
                },
                "association": "parivartana",
            }
        )
    return exchanges


def _gaja_kesari_structure(chart: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the source-pinned Gaja-Kesari structure without outcome claims."""

    planets = chart.get("planets")
    if not isinstance(planets, Mapping):
        return None
    moon = planets.get("Moon")
    jupiter = planets.get("Jupiter")
    if not isinstance(moon, Mapping) or not isinstance(jupiter, Mapping):
        return None
    moon_sign = int(moon.get("sign_idx", -1))
    jupiter_sign = int(jupiter.get("sign_idx", -1))
    relative_house = ((jupiter_sign - moon_sign) % 12) + 1
    if relative_house not in {1, 4, 7, 10}:
        return None

    waxing_moon = bool((chart.get("moon_phase") or {}).get("waxing"))
    natural_benefics = {"Jupiter", "Venus"}
    if waxing_moon:
        natural_benefics.add("Moon")

    mercury = planets.get("Mercury")
    mercury_basis: dict[str, Any] | None = None
    if isinstance(mercury, Mapping):
        mercury_sign = int(mercury.get("sign_idx", -1))
        companions = {
            name
            for name, placement in planets.items()
            if name != "Mercury"
            and isinstance(placement, Mapping)
            and int(placement.get("sign_idx", -2)) == mercury_sign
        }
        benefic_companions = sorted(companions & natural_benefics)
        malefic_companions = sorted(
            companions
            & ({"Sun", "Mars", "Rahu", "Ketu"} | ({"Moon"} if not waxing_moon else set()))
        )
        mercury_is_benefic = not companions or len(benefic_companions) > len(malefic_companions)
        mercury_basis = {
            "isNaturalBenefic": mercury_is_benefic,
            "companions": sorted(companions),
            "beneficCompanions": benefic_companions,
            "maleficCompanions": malefic_companions,
            "policy": "pvr-published-natural-benefic-count",
        }
        if mercury_is_benefic:
            natural_benefics.add("Mercury")

    supporters: list[dict[str, Any]] = []
    for contact in chart.get("aspects") or []:
        if not isinstance(contact, Mapping):
            continue
        source = str(contact.get("source") or "")
        target = str(contact.get("target") or "")
        kind = str(contact.get("kind") or "")
        if kind == "same_sign":
            pair = {source, target}
            supporter = next(
                (name for name in sorted(pair - {"Jupiter"}) if name in natural_benefics),
                None,
            )
            if "Jupiter" in pair and supporter:
                supporters.append(
                    {
                        "graha": supporter,
                        "contact": "conjunction",
                        "degreeGap": contact.get("degree_gap"),
                    }
                )
        elif kind == "graha_drishti" and target == "Jupiter" and source in natural_benefics:
            supporters.append(
                {
                    "graha": source,
                    "contact": "graha_drishti",
                    "aspectNumber": contact.get("aspect"),
                    "degreeGap": contact.get("degree_gap"),
                }
            )
    unique_supporters = {
        (str(item["graha"]), str(item["contact"]), item.get("aspectNumber")): item
        for item in supporters
    }
    if not unique_supporters:
        return None

    dignity = (chart.get("dignities") or {}).get("Jupiter")
    combustion = (chart.get("combustion_statuses") or {}).get("Jupiter")
    if not isinstance(dignity, Mapping) or not isinstance(combustion, Mapping):
        return None
    compound_relationship = dignity.get("compound")
    if compound_relationship is None:
        return None
    disqualifiers = {
        "debilitated": dignity.get("special") == "debilitated",
        "combust": bool(combustion.get("is_combust")),
        "enemyHouse": compound_relationship in {"enemy", "great_enemy"},
    }
    if any(disqualifiers.values()):
        return None

    return {
        "yoga": "Gaja-Kesari",
        "reference": "Moon",
        "jupiterRelativeHouse": relative_house,
        "supporters": list(unique_supporters.values()),
        "jupiterCondition": {
            "dignity": dict(dignity),
            "combustion": dict(combustion),
            "disqualifiers": disqualifiers,
        },
        "naturalBenefics": sorted(natural_benefics),
        "mercuryQualification": mercury_basis,
        "interpretationPermission": "structure_only",
    }


def _facts(
    chart: Mapping[str, Any],
    charts: list[VargaChart],
    method_profile_id: str,
    input_sensitivity: InputSensitivityAssessment,
) -> list[JyotishFact]:
    facts: list[JyotishFact] = []
    d9_chart = next((varga for varga in charts if varga.factor == 9), None)
    d9_calculation_confidence = (
        _varga_calculation_confidence(d9_chart)
        if d9_chart is not None
        else ConfidenceGrade.UNAVAILABLE
    )
    facts.append(
        _fact(
            fact_id="fact.D1.Lagna.position",
            fact_type="rashi.lagna.position",
            subject_ref="D1.Lagna",
            value=_zodiac_position(chart["lagna"]).model_dump(by_alias=True),
            method_profile_id=method_profile_id,
            confidence=ConfidenceGrade.VERIFIED,
        )
    )
    for name in GRAHAS:
        planet = chart["planets"][name]
        house = int(planet["house"])
        facts.append(
            _fact(
                fact_id=f"fact.D1.{name}.position",
                fact_type="rashi.graha.position",
                subject_ref=f"D1.{name}",
                value=_zodiac_position(planet).model_dump(by_alias=True),
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.VERIFIED,
            )
        )
        facts.append(
            _fact(
                fact_id=f"fact.D1.H{house}.occupant.{name}",
                fact_type="rashi.house.occupant",
                subject_ref=f"D1.H{house}.occupant.{name}",
                value={
                    "graha": name,
                    "house": house,
                    "sign": str(planet["sign"]),
                    "signIndex": int(planet["sign_idx"]),
                },
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.VERIFIED,
            )
        )
    house_lords = chart.get("house_lords") or {}
    for house, value in house_lords.items():
        facts.append(
            _fact(
                fact_id=f"fact.D1.H{house}.lord",
                fact_type="rashi.house.lord",
                subject_ref=f"D1.H{house}",
                value=dict(value),
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.CORROBORATED,
            )
        )
    for name in GRAHAS[:7]:
        owned_houses = sorted(
            int(house)
            for house, value in house_lords.items()
            if isinstance(value, Mapping) and value.get("lord") == name
        )
        facts.append(
            _fact(
                fact_id=f"fact.D1.{name}.house_ownership",
                fact_type="role.house_ownership",
                subject_ref=f"D1.{name}",
                value={
                    "houses": owned_houses,
                    "kendraHouses": [house for house in owned_houses if house in {1, 4, 7, 10}],
                    "trikonaHouses": [house for house in owned_houses if house in {1, 5, 9}],
                    "dusthanaHouses": [house for house in owned_houses if house in {6, 8, 12}],
                    "upachayaHouses": [house for house in owned_houses if house in {3, 6, 10, 11}],
                },
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.CORROBORATED,
            )
        )
    for exchange in _parivartana_exchanges(house_lords):
        first_house, second_house = exchange["houses"]
        first_lord, second_lord = exchange["lords"]
        facts.append(
            _fact(
                fact_id=(f"fact.D1.relationship.parivartana.H{first_house}.H{second_house}"),
                fact_type="relationship.parivartana",
                subject_ref=f"D1.{first_lord}~{second_lord}",
                value=exchange,
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.CORROBORATED,
            )
        )
    gaja_kesari = _gaja_kesari_structure(chart)
    if gaja_kesari is not None:
        facts.append(
            _fact(
                fact_id="fact.D1.yoga.gaja_kesari",
                fact_type="yoga.gaja_kesari.structure",
                subject_ref="D1.Moon~Jupiter",
                value=gaja_kesari,
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.CORROBORATED,
            )
        )
    for name in GRAHAS:
        facts.append(
            _fact(
                fact_id=f"fact.D1.{name}.dispositor_chain",
                fact_type="relationship.dispositor_chain",
                subject_ref=f"D1.{name}",
                value=_dispositor_chain(chart, name),
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.CORROBORATED,
            )
        )
    for varga in charts:
        if varga.factor == 1:
            continue
        facts.append(
            _fact(
                fact_id=f"fact.{varga.varga_id}.Lagna.position",
                fact_type="varga.lagna.position",
                subject_ref=f"{varga.varga_id}.Lagna",
                value=varga.lagna.position.model_dump(by_alias=True),
                method_profile_id=method_profile_id,
                confidence=_varga_calculation_confidence(varga),
            )
        )
        for placement in varga.placements:
            facts.append(
                _fact(
                    fact_id=f"fact.{varga.varga_id}.{placement.object_id}.position",
                    fact_type="varga.graha.position",
                    subject_ref=f"{varga.varga_id}.{placement.object_id}",
                    value=placement.position.model_dump(by_alias=True),
                    method_profile_id=method_profile_id,
                    confidence=_varga_calculation_confidence(varga),
                )
            )
        for house_lord in varga.house_lords:
            facts.append(
                _fact(
                    fact_id=f"fact.{varga.varga_id}.H{house_lord.house}.lord",
                    fact_type="varga.house.lord",
                    subject_ref=f"{varga.varga_id}.H{house_lord.house}",
                    value=house_lord.model_dump(by_alias=True),
                    method_profile_id=method_profile_id,
                    confidence=_varga_calculation_confidence(varga),
                )
            )
    for name, value in (chart.get("dignity") or {}).items():
        if name not in GRAHAS or not isinstance(value, Mapping):
            continue
        facts.append(
            _fact(
                fact_id=f"fact.D1.{name}.dignity",
                fact_type="strength.dignity",
                subject_ref=f"D1.{name}",
                value=dict(value),
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.CORROBORATED,
            )
        )
    for name, value in (chart.get("shadbala") or {}).items():
        if name not in GRAHAS or not isinstance(value, Mapping):
            continue
        facts.append(
            _fact(
                fact_id=f"fact.D1.{name}.shadbala",
                fact_type="strength.shadbala",
                subject_ref=f"D1.{name}",
                value=dict(value),
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.PROVISIONAL,
            )
        )
    combustion = chart.get("combustion") or {}
    combustion_statuses = chart.get("combustion_statuses") or {}
    sun_longitude = float(chart["planets"]["Sun"]["longitude"])
    for name in ["Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]:
        value = combustion_statuses.get(name) if isinstance(combustion_statuses, Mapping) else None
        if not isinstance(value, Mapping):
            legacy_value = combustion.get(name) if isinstance(combustion, Mapping) else None
            value = legacy_value if isinstance(legacy_value, Mapping) else None
        longitude = float(chart["planets"][name]["longitude"])
        distance = abs(longitude - sun_longitude)
        if distance > 180:
            distance = 360 - distance
        facts.append(
            _fact(
                fact_id=f"fact.D1.{name}.combustion",
                fact_type="strength.combustion",
                subject_ref=f"D1.{name}",
                value={
                    "isCombust": bool(value.get("is_combust", True))
                    if isinstance(value, Mapping)
                    else False,
                    "distanceDeg": round(float(value.get("distance", distance)), 4)
                    if isinstance(value, Mapping)
                    else round(distance, 4),
                    "thresholdDeg": value.get("threshold") if isinstance(value, Mapping) else None,
                    "retrogradeThresholdApplied": bool(value.get("retrogradeThresholdApplied"))
                    if isinstance(value, Mapping)
                    else False,
                },
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.PROVISIONAL,
            )
        )
    for name, value in (chart.get("digbala") or {}).items():
        if name not in GRAHAS:
            continue
        facts.append(
            _fact(
                fact_id=f"fact.D1.{name}.digbala",
                fact_type="strength.digbala",
                subject_ref=f"D1.{name}",
                value={"hasDirectionalStrength": bool(value)},
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.PROVISIONAL,
            )
        )
    for name, value in (chart.get("vargottama") or {}).items():
        if name != "Lagna" and name not in GRAHAS:
            continue
        facts.append(
            _fact(
                fact_id=f"fact.D1.{name}.vargottama",
                fact_type="varga.vargottama",
                subject_ref=f"D1.{name}",
                value={"isVargottamaD1D9": bool(value)},
                method_profile_id=method_profile_id,
                confidence=d9_calculation_confidence,
            )
        )
    karaka_data = chart.get("karakas") or {}
    ambiguous_chara_grahas = {
        str(graha)
        for ambiguity in karaka_data.get("7k_ambiguities") or []
        if isinstance(ambiguity, Mapping)
        for graha in ambiguity.get("grahas") or []
    }
    for row in karaka_data.get("7k") or []:
        if not isinstance(row, (list, tuple)) or len(row) < 3 or str(row[1]) not in GRAHAS:
            continue
        role, name, degree = str(row[0]), str(row[1]), float(row[2])
        if name in ambiguous_chara_grahas:
            continue
        facts.append(
            _fact(
                fact_id=f"fact.D1.{name}.chara_karaka",
                fact_type="karaka.chara",
                subject_ref=f"D1.{name}",
                value={"scheme": "7K", "role": role, "degreeInSign": round(degree, 6)},
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.PROVISIONAL,
            )
        )
    for point, value in (chart.get("special_points") or {}).items():
        if point not in {"AL", "UL"} or not isinstance(value, Mapping):
            continue
        facts.append(
            _fact(
                fact_id=f"fact.D1.{point}.position",
                fact_type="point.arudha",
                subject_ref=f"D1.{point}",
                value=dict(value),
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.PROVISIONAL,
            )
        )
    moon_phase = chart.get("moon_phase")
    if isinstance(moon_phase, Mapping):
        facts.append(
            _fact(
                fact_id="fact.D1.Moon.phase",
                fact_type="state.moon_phase",
                subject_ref="D1.Moon",
                value=dict(moon_phase),
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.VERIFIED,
            )
        )
    for house, value in (chart.get("bhava_bala") or {}).items():
        if not isinstance(value, Mapping):
            continue
        facts.append(
            _fact(
                fact_id=f"fact.D1.H{house}.bhava_bala",
                fact_type="strength.bhava_bala",
                subject_ref=f"D1.H{house}",
                value=dict(value),
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.PROVISIONAL,
            )
        )
    vargeeya_by_graha: dict[str, dict[str, float]] = {name: {} for name in GRAHAS}
    for scheme, values in (chart.get("vargeeya_bala") or {}).items():
        if not isinstance(values, Mapping):
            continue
        for name, value in values.items():
            if name in vargeeya_by_graha and isinstance(value, (int, float)):
                vargeeya_by_graha[name][str(scheme)] = float(value)
    for name, values in vargeeya_by_graha.items():
        if not values:
            continue
        facts.append(
            _fact(
                fact_id=f"fact.D1.{name}.vargeeya_bala",
                fact_type="strength.vargeeya_bala",
                subject_ref=f"D1.{name}",
                value=values,
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.PROVISIONAL,
            )
        )
    for name, values in (chart.get("bav") or {}).items():
        if name not in GRAHAS or not isinstance(values, Mapping):
            continue
        facts.append(
            _fact(
                fact_id=f"fact.D1.{name}.bav",
                fact_type="ashtakavarga.bav.graha",
                subject_ref=f"D1.{name}",
                value=dict(values),
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.CORROBORATED,
            )
        )
    for name, value in (chart.get("special_lagnas") or {}).items():
        if name.startswith("_") or not isinstance(value, Mapping) or "error" in value:
            continue
        facts.append(
            _fact(
                fact_id=f"fact.D1.special_lagna.{name}",
                fact_type="point.special_lagna",
                subject_ref=f"D1.special_lagna.{name}",
                value=dict(value),
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.PROVISIONAL,
            )
        )
    for house, value in (chart.get("sav_by_house") or {}).items():
        facts.append(
            _fact(
                fact_id=f"fact.D1.H{house}.sav",
                fact_type="ashtakavarga.sav.house",
                subject_ref=f"D1.H{house}",
                value=int(value["value"]),
                unit="bindu",
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.CORROBORATED,
            )
        )
    aspect_index = 0
    house_lords = chart.get("house_lords") or {}
    for aspect in chart.get("aspects") or []:
        if not isinstance(aspect, Mapping):
            continue
        source = str(aspect["source"])
        target = str(aspect["target"])
        if aspect.get("kind") == "same_sign":
            facts.append(
                _fact(
                    fact_id=f"fact.D1.same_sign.{source}.{target}",
                    fact_type="relationship.same_sign",
                    subject_ref=f"D1.{source}~{target}",
                    value=dict(aspect),
                    method_profile_id=method_profile_id,
                    confidence=ConfidenceGrade.VERIFIED,
                )
            )
            yoga_associations = _kendra_trikona_associations(house_lords, source, target)
            if yoga_associations:
                facts.append(
                    _fact(
                        fact_id=f"fact.D1.yoga.raja_kendra_trikona.{source}.{target}",
                        fact_type="yoga.raja.kendra_trikona",
                        subject_ref=f"D1.{source}~{target}",
                        value={
                            "grahas": [source, target],
                            "sign": aspect.get("target_sign"),
                            "association": "same_sign",
                            "lordshipLinks": yoga_associations,
                        },
                        method_profile_id=method_profile_id,
                        confidence=ConfidenceGrade.CORROBORATED,
                    )
                )
            continue
        if aspect.get("kind") != "graha_drishti":
            continue
        facts.append(
            _fact(
                fact_id=f"fact.D1.aspect.{aspect_index:03d}",
                fact_type="aspect.graha_drishti",
                subject_ref=f"D1.{source}->{target}",
                value=dict(aspect),
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.VERIFIED,
            )
        )
        aspect_index += 1
    for aspect in chart.get("house_aspects") or []:
        if not isinstance(aspect, Mapping):
            continue
        source = str(aspect["source"])
        target = f"H{int(aspect['target_house'])}"
        facts.append(
            _fact(
                fact_id=f"fact.D1.aspect.{aspect_index:03d}",
                fact_type="aspect.graha_drishti",
                subject_ref=f"D1.{source}->{target}",
                value={**dict(aspect), "kind": "graha_drishti", "target": target},
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.VERIFIED,
            )
        )
        aspect_index += 1
    transits = chart.get("transits")
    if isinstance(transits, Mapping):
        as_of_utc = transits.get("as_of_utc")
        for name in ["Saturn", "Jupiter", "Rahu", "Ketu"]:
            value = transits.get(name)
            if not isinstance(value, Mapping):
                continue
            position_value = {
                key: value[key]
                for key in (
                    "longitude",
                    "sign",
                    "sign_idx",
                    "degree",
                    "speed",
                    "retrograde",
                )
                if key in value
            }
            facts.append(
                _fact(
                    fact_id=f"fact.Transit.{name}.position",
                    fact_type="timing.transit.position",
                    subject_ref=f"Transit.{name}",
                    value={**position_value, "asOfUtc": as_of_utc},
                    method_profile_id=method_profile_id,
                    confidence=ConfidenceGrade.VERIFIED,
                )
            )
            house = int(value["house"])
            facts.append(
                _fact(
                    fact_id=f"fact.Transit.{name}.house",
                    fact_type="timing.transit.house",
                    subject_ref=f"Transit.{name}->D1.H{house}",
                    value={
                        "house": house,
                        "transitSign": value.get("sign"),
                        "transitSignIndex": value.get("sign_idx"),
                        "asOfUtc": as_of_utc,
                    },
                    method_profile_id=method_profile_id,
                    confidence=ConfidenceGrade.VERIFIED,
                )
            )
        facts.append(
            _fact(
                fact_id="fact.Transit.Saturn.Moon.sade_sati",
                fact_type="timing.transit.sade_sati",
                subject_ref="Transit.Saturn.Moon",
                value={"phase": transits.get("sade_sati"), "asOfUtc": as_of_utc},
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.PROVISIONAL,
            )
        )
        facts.append(
            _fact(
                fact_id="fact.Transit.Saturn.Jupiter.double_transit",
                fact_type="timing.transit.double_transit",
                subject_ref="Transit.Saturn~Jupiter",
                value={
                    "houses": list(transits.get("double_transit_houses") or []),
                    "asOfUtc": as_of_utc,
                },
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.PROVISIONAL,
            )
        )
    for fact in facts:
        fact.sensitivity_dependencies = fact_sensitivity_dependencies(
            fact.fact_type,
            fact.subject_ref,
        )
        fact.input_stability = expected_fact_input_stability(
            fact,
            charts,
            input_sensitivity,
        )
    return facts


def _dispositor_chain(chart: Mapping[str, Any], graha: str) -> dict[str, Any]:
    planets = chart.get("planets") or {}
    chain: list[str] = []
    first_seen: dict[str, int] = {}
    current = graha
    terminal: str | None = None
    loop: list[str] = []
    while current in planets and len(chain) <= len(GRAHAS):
        if current in first_seen:
            loop = chain[first_seen[current] :]
            break
        first_seen[current] = len(chain)
        chain.append(current)
        value = planets[current]
        if not isinstance(value, Mapping):
            break
        next_dispositor = SIGN_LORDS[int(value["sign_idx"])]
        if next_dispositor == current:
            terminal = current
            break
        current = next_dispositor
    return {
        "chain": chain,
        "terminal": terminal,
        "loop": loop,
        "resolved": terminal is not None or bool(loop),
    }


def _fact(
    *,
    fact_id: str,
    fact_type: FactType,
    subject_ref: str,
    value: Any,
    method_profile_id: str,
    confidence: ConfidenceGrade,
    unit: str | None = None,
) -> JyotishFact:
    definition = fact_definition(fact_type)
    provenance = _rule_provenance(
        definition.derivation_rule_id,
        method_profile_id,
        confidence,
    )
    return JyotishFact(
        fact_id=fact_id,
        fact_type=fact_type,
        subject_ref=subject_ref,
        value=value,
        unit=unit,
        provenance=provenance,
    )


def _varga_calculation_confidence(varga: VargaChart) -> ConfidenceGrade:
    return (
        ConfidenceGrade.CORROBORATED
        if varga.calculation_assurance == "internal_provider_regression"
        else ConfidenceGrade.VERIFIED
    )


def _timing_sample_intervals(
    sensitivity_scan: Mapping[str, Any],
    timezone_id: str,
) -> tuple[
    dict[tuple[str, ...], list[TimeRange]],
    Literal["reported_window_endpoints", "partial_window_sampling", "canonical_only"],
    int,
]:
    sampling = sensitivity_scan.get("timingBoundarySampling")
    if not isinstance(sampling, Mapping):
        return {}, "canonical_only", 0
    status = str(sampling.get("status") or "failed")
    coverage = "reported_window_endpoints" if status == "complete" else "partial_window_sampling"
    intervals: dict[tuple[str, ...], list[TimeRange]] = {}
    successful_samples = 0
    for sample in sampling.get("samples") or []:
        if not isinstance(sample, Mapping):
            continue
        successful_samples += 1
        for dasha in sample.get("dashas") or []:
            if not isinstance(dasha, Mapping):
                continue
            md_lord = str(dasha.get("planet") or "")
            _append_timing_sample(intervals, ("mahadasha", md_lord), dasha, timezone_id)
            for antardasha in dasha.get("antardashas") or []:
                if not isinstance(antardasha, Mapping):
                    continue
                ad_lord = str(antardasha.get("planet") or "")
                _append_timing_sample(
                    intervals,
                    ("antardasha", md_lord, ad_lord),
                    antardasha,
                    timezone_id,
                )
                for pratyantardasha in antardasha.get("pratyantardashas") or []:
                    if not isinstance(pratyantardasha, Mapping):
                        continue
                    pd_lord = str(pratyantardasha.get("planet") or "")
                    _append_timing_sample(
                        intervals,
                        ("pratyantardasha", md_lord, ad_lord, pd_lord),
                        pratyantardasha,
                        timezone_id,
                    )
    return intervals, coverage, successful_samples


def _append_timing_sample(
    intervals: dict[tuple[str, ...], list[TimeRange]],
    key: tuple[str, ...],
    period: Mapping[str, Any],
    timezone_id: str,
) -> None:
    start = _period_moment(str(period.get("start_exact") or period.get("start")), timezone_id)
    end = _period_moment(str(period.get("end_exact") or period.get("end")), timezone_id)
    if end > start:
        intervals.setdefault(key, []).append(TimeRange(start=start, end=end))


def _timing_boundary_envelope(
    canonical: datetime,
    observed: list[datetime],
    coverage: Literal[
        "reported_window_endpoints",
        "partial_window_sampling",
        "canonical_only",
    ],
    successful_samples: int,
) -> TimingBoundaryEnvelope:
    if not observed:
        return TimingBoundaryEnvelope(
            earliest=canonical,
            latest=canonical,
            sampledHypotheses=1,
            coverage="canonical_only",
        )
    values = [canonical, *observed]
    effective_coverage = (
        coverage
        if coverage == "reported_window_endpoints" and len(observed) == successful_samples
        else "partial_window_sampling"
    )
    return TimingBoundaryEnvelope(
        earliest=min(values),
        latest=max(values),
        sampledHypotheses=max(1, successful_samples),
        coverage=effective_coverage,
    )


def _timing_periods(
    chart: Mapping[str, Any],
    timezone_id: str,
    method_profile_id: str,
    input_sensitivity: InputSensitivityAssessment,
    canonical_input_confidence: ConfidenceGrade,
    sensitivity_scan: Mapping[str, Any],
) -> list[TimingPeriod]:
    result: list[TimingPeriod] = []
    sampled_intervals, sampling_coverage, successful_samples = _timing_sample_intervals(
        sensitivity_scan,
        timezone_id,
    )
    for md_index, dasha in enumerate(chart.get("dashas") or []):
        if not isinstance(dasha, Mapping):
            continue
        md_start = _period_moment(str(dasha.get("start_exact") or dasha["start"]), timezone_id)
        md_end = _period_moment(str(dasha.get("end_exact") or dasha["end"]), timezone_id)
        if md_end <= md_start:
            continue
        md_id = f"vimshottari.md.{md_index:02d}.{str(dasha['planet']).lower()}"
        md_key = ("mahadasha", str(dasha["planet"]))
        md_samples = sampled_intervals.get(md_key, [])
        result.append(
            TimingPeriod(
                period_id=md_id,
                system="Vimshottari",
                level="mahadasha",
                lords=[str(dasha["planet"])],
                interval=TimeRange(start=md_start, end=md_end),
                provenance=_timing_provenance(method_profile_id),
                inputStability=expected_timing_input_stability(
                    input_sensitivity,
                    canonical_input_confidence,
                ),
                sensitivityDependencies=TIMING_SENSITIVITY_DEPENDENCIES,
                startBoundary=_timing_boundary_envelope(
                    md_start,
                    [sample.start for sample in md_samples],
                    sampling_coverage,
                    successful_samples,
                ),
                endBoundary=_timing_boundary_envelope(
                    md_end,
                    [sample.end for sample in md_samples],
                    sampling_coverage,
                    successful_samples,
                ),
            )
        )
        for ad_index, antardasha in enumerate(dasha.get("antardashas") or []):
            if not isinstance(antardasha, Mapping):
                continue
            ad_start = _period_moment(
                str(antardasha.get("start_exact") or antardasha["start"]), timezone_id
            )
            ad_end = _period_moment(
                str(antardasha.get("end_exact") or antardasha["end"]), timezone_id
            )
            if ad_end <= ad_start:
                continue
            ad_key = (
                "antardasha",
                str(dasha["planet"]),
                str(antardasha["planet"]),
            )
            ad_samples = sampled_intervals.get(ad_key, [])
            result.append(
                TimingPeriod(
                    period_id=f"{md_id}.ad.{ad_index:02d}.{str(antardasha['planet']).lower()}",
                    system="Vimshottari",
                    level="antardasha",
                    lords=[str(dasha["planet"]), str(antardasha["planet"])],
                    interval=TimeRange(start=ad_start, end=ad_end),
                    provenance=_timing_provenance(method_profile_id),
                    inputStability=expected_timing_input_stability(
                        input_sensitivity,
                        canonical_input_confidence,
                    ),
                    sensitivityDependencies=TIMING_SENSITIVITY_DEPENDENCIES,
                    startBoundary=_timing_boundary_envelope(
                        ad_start,
                        [sample.start for sample in ad_samples],
                        sampling_coverage,
                        successful_samples,
                    ),
                    endBoundary=_timing_boundary_envelope(
                        ad_end,
                        [sample.end for sample in ad_samples],
                        sampling_coverage,
                        successful_samples,
                    ),
                )
            )
            for pd_index, pratyantardasha in enumerate(antardasha.get("pratyantardashas") or []):
                if not isinstance(pratyantardasha, Mapping):
                    continue
                pd_start = _period_moment(
                    str(pratyantardasha.get("start_exact") or pratyantardasha["start"]),
                    timezone_id,
                )
                pd_end = _period_moment(
                    str(pratyantardasha.get("end_exact") or pratyantardasha["end"]),
                    timezone_id,
                )
                if pd_end <= pd_start:
                    continue
                pd_key = (
                    "pratyantardasha",
                    str(dasha["planet"]),
                    str(antardasha["planet"]),
                    str(pratyantardasha["planet"]),
                )
                pd_samples = sampled_intervals.get(pd_key, [])
                result.append(
                    TimingPeriod(
                        period_id=(
                            f"{md_id}.ad.{ad_index:02d}.{str(antardasha['planet']).lower()}"
                            f".pd.{pd_index:02d}.{str(pratyantardasha['planet']).lower()}"
                        ),
                        system="Vimshottari",
                        level="pratyantardasha",
                        lords=[
                            str(dasha["planet"]),
                            str(antardasha["planet"]),
                            str(pratyantardasha["planet"]),
                        ],
                        interval=TimeRange(start=pd_start, end=pd_end),
                        provenance=_timing_provenance(method_profile_id),
                        inputStability=expected_timing_input_stability(
                            input_sensitivity,
                            canonical_input_confidence,
                        ),
                        sensitivityDependencies=TIMING_SENSITIVITY_DEPENDENCIES,
                        startBoundary=_timing_boundary_envelope(
                            pd_start,
                            [sample.start for sample in pd_samples],
                            sampling_coverage,
                            successful_samples,
                        ),
                        endBoundary=_timing_boundary_envelope(
                            pd_end,
                            [sample.end for sample in pd_samples],
                            sampling_coverage,
                            successful_samples,
                        ),
                    )
                )
    return result


def _quality_checks(
    chart: Mapping[str, Any],
    charts: list[VargaChart],
    independent_reference: IndependentReferenceSnapshot | Mapping[str, Any] | None = None,
) -> list[QualityCheck]:
    planets = chart.get("planets") or {}
    sav_total = sum(int(value) for value in (chart.get("sav") or {}).values())
    rahu = float(planets["Rahu"]["longitude"])
    ketu = float(planets["Ketu"]["longitude"])
    node_gap = abs((rahu - ketu + 180.0) % 360.0 - 180.0)
    expected_vargas = set(parashari_lahiri_profile().supported_vargas)
    observed_vargas = {varga.factor for varga in charts}
    d1_mismatches = _d1_provider_sign_mismatches(chart)
    d1_position_mismatches = _d1_provider_position_mismatches(chart)
    position_issues = _position_integrity_issues(chart, charts)
    varga_issues = _varga_integrity_issues(charts)
    dasha_issues = _dasha_integrity_issues(chart)
    interpretive_input_issues = _interpretive_input_issues(chart)
    supplemental_input_issues = _supplemental_input_issues(chart)
    chara_karaka_ambiguities = list((chart.get("karakas") or {}).get("7k_ambiguities") or [])
    independent_check = _independent_reference_check(chart, independent_reference)
    return [
        QualityCheck(
            check_id="astronomy.nine-grahas",
            status="passed" if set(planets) == set(GRAHAS) else "failed",
            expected=GRAHAS,
            observed=sorted(planets),
            message="All nine grahas are present."
            if set(planets) == set(GRAHAS)
            else "Grahas are missing.",
        ),
        QualityCheck(
            check_id="ashtakavarga.sav-total",
            status="passed" if sav_total == 337 else "failed",
            expected=337,
            observed=sav_total,
            message="Sarvashtakavarga total is valid."
            if sav_total == 337
            else "Sarvashtakavarga total is invalid.",
        ),
        QualityCheck(
            check_id="astronomy.node-opposition",
            status="passed" if abs(node_gap - 180.0) < 0.01 else "failed",
            expected=180.0,
            observed=round(node_gap, 6),
            message="Rahu and Ketu are opposite."
            if abs(node_gap - 180.0) < 0.01
            else "Node opposition failed.",
        ),
        QualityCheck(
            check_id="varga.profile-completeness",
            status="passed" if observed_vargas == expected_vargas else "failed",
            expected=sorted(expected_vargas),
            observed=sorted(observed_vargas),
            message=(
                "All profile vargas are present."
                if observed_vargas == expected_vargas
                else "One or more profile vargas are unavailable."
            ),
        ),
        QualityCheck(
            check_id="varga.d1-provider-sign-alignment",
            status="passed" if not d1_mismatches else "failed",
            expected="Swiss Ephemeris and PyJHora D1 agree on zodiac signs",
            observed=d1_mismatches,
            message=(
                "Swiss Ephemeris and PyJHora D1 signs agree; Swiss positions remain canonical."
                if not d1_mismatches
                else "Swiss Ephemeris and PyJHora D1 signs disagree."
            ),
        ),
        QualityCheck(
            check_id="varga.d1-provider-position-alignment",
            status="passed" if not d1_position_mismatches else "failed",
            expected="Swiss Ephemeris and PyJHora D1 agree within 0.5 arcseconds",
            observed=d1_position_mismatches,
            message=(
                "Swiss Ephemeris and PyJHora D1 positions share the declared apparent "
                "geocentric frame."
                if not d1_position_mismatches
                else "Swiss Ephemeris and PyJHora D1 positions use incompatible coordinates."
            ),
        ),
        QualityCheck(
            check_id="calculation.position-integrity",
            status="passed" if not position_issues else "failed",
            expected="longitude, sign, sign index, and degree agree for every position",
            observed=position_issues,
            message=(
                "All zodiac positions are internally coherent."
                if not position_issues
                else "One or more zodiac positions are internally inconsistent."
            ),
        ),
        QualityCheck(
            check_id="calculation.varga-integrity",
            status="passed" if not varga_issues else "failed",
            expected="Lagna, nine grahas, and twelve coherent house lords in every varga",
            observed=varga_issues,
            message=(
                "Every supported varga has a complete, coherent placement matrix."
                if not varga_issues
                else "One or more varga placement matrices are incomplete or inconsistent."
            ),
        ),
        QualityCheck(
            check_id="calculation.vimshottari-continuity",
            status="passed" if not dasha_issues else "failed",
            expected="nine contiguous periods at MD, AD, and PD levels",
            observed=dasha_issues,
            message=(
                "Vimshottari periods are complete and contiguous through Pratyantardasha."
                if not dasha_issues
                else "Vimshottari hierarchy has missing, invalid, or discontinuous periods."
            ),
        ),
        QualityCheck(
            check_id="calculation.interpretive-input-integrity",
            status="passed" if not interpretive_input_issues else "failed",
            expected=("12 house lords, 12 SAV houses, and valid dignity/Shadbala for seven grahas"),
            observed=interpretive_input_issues,
            message=(
                "Required deterministic inputs for domain judgement are complete."
                if not interpretive_input_issues
                else "Required deterministic inputs for domain judgement are incomplete."
            ),
        ),
        QualityCheck(
            check_id="calculation.supplemental-input-integrity",
            status="passed" if not supplemental_input_issues else "warning",
            expected=(
                "complete Bhava Bala, seven declared special Lagnas, and Pancha/Dwadasha "
                "Vargeeya Bala outputs"
            ),
            observed=supplemental_input_issues,
            message=(
                "Supplemental PyJHora capacity measures are complete."
                if not supplemental_input_issues
                else "One or more supplemental capacity measures are unavailable and were excluded."
            ),
        ),
        QualityCheck(
            check_id="calculation.chara-karaka-ranking",
            status="passed" if not chara_karaka_ambiguities else "warning",
            expected="unique 7K role ranking at six-decimal degree precision",
            observed=chara_karaka_ambiguities,
            message=(
                "The seven-graha Chara Karaka ranking is unique."
                if not chara_karaka_ambiguities
                else "Ambiguous Chara Karaka roles were excluded from judgement evidence."
            ),
        ),
        independent_check,
    ]


def _independent_reference_check(
    chart: Mapping[str, Any],
    raw_reference: IndependentReferenceSnapshot | Mapping[str, Any] | None,
) -> QualityCheck:
    expected = (
        "A pinned, profile-matched snapshot from software outside Swiss Ephemeris, "
        "PyJHora, and VedicDust"
    )
    if raw_reference is None:
        return QualityCheck(
            check_id="calculation.independent-golden-reference",
            status="warning",
            expected=expected,
            observed="No independent reference snapshot supplied",
            message=(
                "Provider compatibility is covered, but independent desktop equivalence "
                "has not been established for this chart."
            ),
        )
    raw_source = (
        raw_reference.source_system
        if isinstance(raw_reference, IndependentReferenceSnapshot)
        else str(raw_reference.get("sourceSystem") or raw_reference.get("source_system") or "")
    )
    active_provider_tokens = ("pyjhora", "swiss ephemeris", "swisseph", "vedicdust")
    if any(token in raw_source.casefold() for token in active_provider_tokens):
        return QualityCheck(
            check_id="calculation.independent-golden-reference",
            status="failed",
            expected=expected,
            observed={"reason": "non-independent-source", "source": raw_source},
            message="The reference uses the active calculation chain and is not independent.",
        )
    try:
        reference = (
            raw_reference
            if isinstance(raw_reference, IndependentReferenceSnapshot)
            else IndependentReferenceSnapshot.model_validate(raw_reference)
        )
    except ValueError as exc:
        return QualityCheck(
            check_id="calculation.independent-golden-reference",
            status="failed",
            expected=expected,
            observed={"reason": "invalid-reference-contract", "details": str(exc)},
            message="The supplied independent reference is incomplete or malformed.",
        )

    if reference.method_profile_id != parashari_lahiri_profile().profile_id:
        return QualityCheck(
            check_id="calculation.independent-golden-reference",
            status="failed",
            expected=parashari_lahiri_profile().profile_id,
            observed=reference.method_profile_id,
            message="The independent reference uses a different calculation profile.",
        )

    try:
        issues = _independent_reference_issues(chart, reference)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return QualityCheck(
            check_id="calculation.independent-golden-reference",
            status="failed",
            expected=expected,
            observed={
                "reason": "invalid-active-chart-output",
                "errorType": type(exc).__name__,
                "details": str(exc),
            },
            message="The active calculation output is incomplete or malformed for comparison.",
        )
    return QualityCheck(
        check_id="calculation.independent-golden-reference",
        status="passed" if not issues else "failed",
        expected={
            "source": reference.source_system,
            "version": reference.source_version,
            "artifact": reference.source_artifact_sha256,
            "profile": reference.method_profile_id,
        },
        observed=issues,
        message=(
            "The chart matches the pinned independent desktop snapshot."
            if not issues
            else "The chart differs from the pinned independent desktop snapshot."
        ),
    )


def independent_reference_quality_check(
    chart: Mapping[str, Any],
    reference: IndependentReferenceSnapshot | Mapping[str, Any] | None,
) -> QualityCheck:
    """Public comparator used by release certification and Chart Record qualification."""

    return _independent_reference_check(chart, reference)


def _independent_reference_issues(
    chart: Mapping[str, Any], reference: IndependentReferenceSnapshot
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    d1_actual = {"Lagna": chart["lagna"], **dict(chart.get("planets") or {})}
    for body, expected in reference.d1_positions.items():
        actual = d1_actual[body]
        if str(actual["sign"]) != expected.sign:
            issues.append(
                {"field": f"D1.{body}.sign", "expected": expected.sign, "actual": actual["sign"]}
            )
        if not math.isclose(float(actual["degree"]), expected.degree_in_sign, abs_tol=0.02):
            issues.append(
                {
                    "field": f"D1.{body}.degree",
                    "expected": expected.degree_in_sign,
                    "actual": float(actual["degree"]),
                    "toleranceDeg": 0.02,
                }
            )
    raw_vargas = chart.get("divisional_charts") or {}
    for varga_id, expected_positions in reference.varga_signs.items():
        actual_positions = raw_vargas[varga_id]
        for body, expected_sign in expected_positions.items():
            actual_sign = str(actual_positions[body]["sign"])
            if actual_sign != expected_sign:
                issues.append(
                    {
                        "field": f"{varga_id}.{body}.sign",
                        "expected": expected_sign,
                        "actual": actual_sign,
                    }
                )
    actual_sav = {str(sign): int(value) for sign, value in (chart.get("sav") or {}).items()}
    if actual_sav != reference.sav_by_sign:
        issues.append({"field": "SAV", "expected": reference.sav_by_sign, "actual": actual_sav})
    actual_shadbala = {
        body: round(float(values["total_rupas"]), 2)
        for body, values in (chart.get("shadbala") or {}).items()
        if body in reference.shadbala_rupas
    }
    expected_shadbala = {body: round(value, 2) for body, value in reference.shadbala_rupas.items()}
    if actual_shadbala != expected_shadbala:
        issues.append(
            {"field": "Shadbala.rupas", "expected": expected_shadbala, "actual": actual_shadbala}
        )
    actual_dashas = list(chart.get("dashas") or [])
    if len(actual_dashas) != 9:
        issues.append(
            {
                "field": "Vimshottari.mahadashas.count",
                "expected": 9,
                "actual": len(actual_dashas),
            }
        )
    else:
        for index, (actual, expected) in enumerate(
            zip(actual_dashas, reference.mahadashas, strict=True)
        ):
            actual_lord = str(actual["planet"])
            actual_start = datetime.fromisoformat(str(actual["start_exact"]))
            actual_end = datetime.fromisoformat(str(actual["end_exact"]))
            if actual_lord != expected.lord:
                issues.append(
                    {
                        "field": f"Vimshottari.mahadashas[{index}].lord",
                        "expected": expected.lord,
                        "actual": actual_lord,
                    }
                )
            for boundary, actual_moment, expected_moment in (
                ("start", actual_start, expected.start),
                ("end", actual_end, expected.end),
            ):
                difference = abs((actual_moment - expected_moment).total_seconds())
                if difference > DASHA_REFERENCE_TOLERANCE_SECONDS:
                    issues.append(
                        {
                            "field": f"Vimshottari.mahadashas[{index}].{boundary}",
                            "expected": expected_moment.isoformat(),
                            "actual": actual_moment.isoformat(),
                            "differenceSeconds": round(difference, 3),
                            "toleranceSeconds": DASHA_REFERENCE_TOLERANCE_SECONDS,
                        }
                    )
    return issues[:50]


def _position_integrity_issues(
    chart: Mapping[str, Any], charts: list[VargaChart]
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    raw_positions: list[tuple[str, Mapping[str, Any]]] = [("D1.Lagna", chart["lagna"])]
    raw_positions.extend(
        (f"D1.{name}", value)
        for name, value in (chart.get("planets") or {}).items()
        if isinstance(value, Mapping)
    )
    for label, value in raw_positions:
        longitude = float(value["longitude"]) % 360.0
        sign_index = int(value["sign_idx"])
        degree = float(value["degree"])
        if sign_index != int(longitude // 30):
            issues.append({"subject": label, "reason": "sign-index-longitude-mismatch"})
        if not math.isclose(degree, longitude % 30.0, abs_tol=1e-4):
            issues.append({"subject": label, "reason": "degree-longitude-mismatch"})
        if str(value["sign"]) != SIGNS[sign_index]:
            issues.append({"subject": label, "reason": "sign-name-index-mismatch"})

    for varga in charts:
        for placement in [varga.lagna, *varga.placements]:
            position = placement.position
            expected_longitude = position.sign_index * 30.0 + position.degree_in_sign
            if not math.isclose(position.longitude_deg, expected_longitude, abs_tol=1e-4):
                issues.append(
                    {
                        "subject": f"{varga.varga_id}.{placement.object_id}",
                        "reason": "varga-position-mismatch",
                    }
                )
            if position.sign != SIGNS[position.sign_index]:
                issues.append(
                    {
                        "subject": f"{varga.varga_id}.{placement.object_id}",
                        "reason": "varga-sign-name-index-mismatch",
                    }
                )
    return issues[:50]


def _varga_integrity_issues(charts: list[VargaChart]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    expected_objects = set(GRAHAS)
    for varga in charts:
        placements = {placement.object_id: placement for placement in varga.placements}
        if set(placements) != expected_objects:
            issues.append(
                {
                    "varga": varga.varga_id,
                    "reason": "placement-set-mismatch",
                    "missing": sorted(expected_objects - set(placements)),
                    "extra": sorted(set(placements) - expected_objects),
                }
            )
            continue
        lagna_index = varga.lagna.position.sign_index
        for object_id, placement in placements.items():
            expected_house = (placement.position.sign_index - lagna_index) % 12 + 1
            if placement.house != expected_house:
                issues.append(
                    {
                        "varga": varga.varga_id,
                        "subject": object_id,
                        "reason": "placement-house-mismatch",
                    }
                )
        for lord in varga.house_lords:
            expected_sign_index = (lagna_index + lord.house - 1) % 12
            expected_lord = SIGN_LORDS[expected_sign_index]
            expected_lord_placement = placements.get(expected_lord)
            expected_lord_house = (
                expected_lord_placement.house if expected_lord_placement is not None else None
            )
            if (
                lord.sign_index != expected_sign_index
                or lord.sign != SIGNS[expected_sign_index]
                or lord.lord != expected_lord
                or lord.lord_house != expected_lord_house
            ):
                issues.append(
                    {
                        "varga": varga.varga_id,
                        "subject": f"H{lord.house}",
                        "reason": "house-lord-mismatch",
                    }
                )
    return issues[:50]


def _dasha_integrity_issues(chart: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    dashas = [item for item in chart.get("dashas") or [] if isinstance(item, Mapping)]
    _check_period_sequence(dashas, "MD", issues)
    for md_index, dasha in enumerate(dashas):
        antardashas = [item for item in dasha.get("antardashas") or [] if isinstance(item, Mapping)]
        _check_period_sequence(antardashas, f"MD[{md_index}].AD", issues)
        for ad_index, antardasha in enumerate(antardashas):
            pratyantardashas = [
                item
                for item in antardasha.get("pratyantardashas") or []
                if isinstance(item, Mapping)
            ]
            _check_period_sequence(
                pratyantardashas,
                f"MD[{md_index}].AD[{ad_index}].PD",
                issues,
            )
    return issues[:50]


def _check_period_sequence(
    periods: list[Mapping[str, Any]], path: str, issues: list[dict[str, Any]]
) -> None:
    if len(periods) != 9:
        issues.append({"path": path, "reason": "period-count", "observed": len(periods)})
        return
    previous_end: str | None = None
    for index, period in enumerate(periods):
        start = str(period.get("start_exact") or period.get("start") or "")
        end = str(period.get("end_exact") or period.get("end") or "")
        if not start or not end or start >= end:
            issues.append({"path": f"{path}[{index}]", "reason": "invalid-interval"})
        if previous_end is not None and start != previous_end:
            issues.append({"path": f"{path}[{index}]", "reason": "non-contiguous"})
        previous_end = end


def _interpretive_input_issues(chart: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    classical_grahas = set(GRAHAS[:7])
    expected_signs = set(SIGNS)
    expected_houses = set(range(1, 13))
    house_lords = {int(house) for house in (chart.get("house_lords") or {}) if str(house).isdigit()}
    if house_lords != expected_houses:
        issues.append({"field": "house_lords", "observed": sorted(house_lords)})
    sav = chart.get("sav") or {}
    if set(sav) != expected_signs or any(
        not isinstance(value, int) or value < 0 for value in sav.values()
    ):
        issues.append({"field": "sav", "observed": sorted(sav)})
    dignity = chart.get("dignity") or {}
    if set(dignity) != classical_grahas:
        issues.append({"field": "dignity", "observed": sorted(dignity)})
    shadbala = chart.get("shadbala") or {}
    if set(shadbala) != classical_grahas:
        issues.append({"field": "shadbala", "observed": sorted(shadbala)})
    for graha in sorted(classical_grahas & set(shadbala)):
        value = shadbala[graha]
        if not isinstance(value, Mapping):
            issues.append({"field": f"shadbala.{graha}", "reason": "not-an-object"})
            continue
        total_60ths = value.get("total_60ths")
        total_rupas = value.get("total_rupas")
        strength_pct = value.get("strength_pct")
        numeric_values = (total_60ths, total_rupas, strength_pct)
        if not all(
            isinstance(item, (int, float)) and math.isfinite(float(item)) and float(item) >= 0
            for item in numeric_values
        ):
            issues.append({"field": f"shadbala.{graha}", "reason": "invalid-values"})
        elif not math.isclose(float(total_60ths) / 60.0, float(total_rupas), abs_tol=0.02):
            issues.append({"field": f"shadbala.{graha}", "reason": "rashi-rupa-mismatch"})
    return issues[:50]


def _supplemental_input_issues(chart: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expose optional provider gaps without blocking the canonical chart."""

    issues: list[dict[str, Any]] = []
    bhava_bala = chart.get("bhava_bala")
    expected_houses = {str(house) for house in range(1, 13)}
    if not isinstance(bhava_bala, Mapping):
        issues.append({"field": "bhava_bala", "reason": "unavailable"})
    else:
        observed_houses = {str(house) for house in bhava_bala if str(house).isdigit()}
        if observed_houses != expected_houses:
            issues.append(
                {
                    "field": "bhava_bala",
                    "reason": "house-set-mismatch",
                    "observed": sorted(observed_houses),
                }
            )

    expected_special_lagnas = {
        "hora_lagna",
        "ghati_lagna",
        "sree_lagna",
        "bhava_lagna",
        "pranapada_lagna",
        "indu_lagna",
        "vighati_lagna",
    }
    special_lagnas = chart.get("special_lagnas")
    if not isinstance(special_lagnas, Mapping):
        issues.append({"field": "special_lagnas", "reason": "unavailable"})
    else:
        observed = {
            str(name)
            for name, value in special_lagnas.items()
            if not str(name).startswith("_") and isinstance(value, Mapping) and "error" not in value
        }
        if observed != expected_special_lagnas:
            issues.append(
                {
                    "field": "special_lagnas",
                    "reason": "point-set-mismatch",
                    "observed": sorted(observed),
                    "providerErrors": dict(special_lagnas.get("_provider_errors") or {}),
                }
            )

    expected_grahas = set(GRAHAS[:7])
    vargeeya_bala = chart.get("vargeeya_bala")
    if not isinstance(vargeeya_bala, Mapping):
        issues.append({"field": "vargeeya_bala", "reason": "unavailable"})
    else:
        for scheme in ("pancha_vargeeya", "dwadhasa_vargeeya"):
            values = vargeeya_bala.get(scheme)
            observed = set(values) if isinstance(values, Mapping) else set()
            if (
                not isinstance(values, Mapping)
                or observed != expected_grahas
                or any(not isinstance(value, (int, float)) for value in values.values())
            ):
                issues.append(
                    {
                        "field": f"vargeeya_bala.{scheme}",
                        "reason": "graha-set-or-value-mismatch",
                        "observed": sorted(observed),
                    }
                )
    return issues[:20]


def _d1_provider_sign_mismatches(chart: Mapping[str, Any]) -> list[dict[str, Any]]:
    d1 = (chart.get("divisional_charts") or {}).get("D1")
    if not isinstance(d1, Mapping) or "error" in d1:
        return [{"objectId": "D1", "reason": "missing"}]
    expected: dict[str, Mapping[str, Any]] = {
        "Lagna": chart["lagna"],
        **{name: chart["planets"][name] for name in GRAHAS},
    }
    mismatches: list[dict[str, Any]] = []
    for object_id, expected_position in expected.items():
        observed_position = d1.get(object_id)
        if not isinstance(observed_position, Mapping):
            mismatches.append({"objectId": object_id, "reason": "missing"})
            continue
        if int(observed_position["sign_idx"]) != int(expected_position["sign_idx"]):
            mismatches.append(
                {
                    "objectId": object_id,
                    "expectedSign": str(expected_position["sign"]),
                    "observedSign": str(observed_position["sign"]),
                }
            )
    return mismatches


def _d1_provider_position_mismatches(
    chart: Mapping[str, Any], *, tolerance_arcseconds: float = 0.5
) -> list[dict[str, Any]]:
    d1 = (chart.get("divisional_charts") or {}).get("D1")
    if not isinstance(d1, Mapping) or "error" in d1:
        return [{"objectId": "D1", "reason": "missing"}]
    expected: dict[str, Mapping[str, Any]] = {
        "Lagna": chart["lagna"],
        **{name: chart["planets"][name] for name in GRAHAS},
    }
    mismatches: list[dict[str, Any]] = []
    for object_id, expected_position in expected.items():
        observed_position = d1.get(object_id)
        if not isinstance(observed_position, Mapping):
            mismatches.append({"objectId": object_id, "reason": "missing"})
            continue
        expected_longitude = float(expected_position["longitude"])
        observed_longitude = int(observed_position["sign_idx"]) * 30.0 + float(
            observed_position["degree"]
        )
        separation_arcseconds = (
            abs((expected_longitude - observed_longitude + 180.0) % 360.0 - 180.0) * 3600.0
        )
        if separation_arcseconds > tolerance_arcseconds:
            mismatches.append(
                {
                    "objectId": object_id,
                    "separationArcseconds": round(separation_arcseconds, 4),
                }
            )
    return mismatches


def _rectification(
    source: ChartRecordBuildInput, birth_confidence: ConfidenceGrade
) -> RectificationRecord | None:
    readiness = source.sensitivity_scan.get("reportReadiness") or {}
    mode = str(readiness.get("mode") or "rectification_required")
    blocking_factors = [str(value) for value in readiness.get("blockingFactors") or []]
    if any(value.startswith("candidate_scoring_incomplete:") for value in blocking_factors):
        return RectificationRecord(
            **_rectification_method_contract(),
            reported_window=_reported_window(source.input_context, source.timezone_id),
            life_events=_life_events(source),
            candidates=_candidate_intervals(source),
            decision=RectificationDecision(
                status="calculation_failed",
                confidence=ConfidenceGrade.UNAVAILABLE,
                reasons=blocking_factors,
                unresolved_questions=[
                    "Retry deterministic event scoring before comparing birth-time candidates."
                ],
            ),
        )
    if any(value.startswith("scan_incomplete:") for value in blocking_factors):
        return RectificationRecord(
            **_rectification_method_contract(),
            reported_window=None,
            life_events=_life_events(source),
            candidates=[],
            decision=RectificationDecision(
                status="input_resolution_required",
                confidence=ConfidenceGrade.UNAVAILABLE,
                reasons=blocking_factors,
                unresolved_questions=[
                    "Resolve the civil-time ambiguity or place input before rectification."
                ],
            ),
        )
    reported_window = _reported_window(source.input_context, source.timezone_id)
    if reported_window is None:
        return None
    if mode == "rectification_required":
        decision = RectificationDecision(
            status="collecting_evidence",
            confidence=ConfidenceGrade.PROVISIONAL,
            reasons=blocking_factors
            or ["Decision-relevant chart facts vary inside the reported input window."],
            unresolved_questions=[
                "Candidate intervals and discriminating life events are required."
            ],
        )
    else:
        decision = RectificationDecision(
            status="not_required",
            confidence=birth_confidence,
            reasons=[
                "No decision-relevant instability requires rectification for the current scope."
            ],
        )
    return RectificationRecord(
        **_rectification_method_contract(),
        reported_window=reported_window,
        life_events=_life_events(source),
        candidates=_candidate_intervals(source),
        decision=decision,
    )


def _rectification_method_contract() -> dict[str, Any]:
    return {
        "selection_policy_id": RECTIFICATION_SCORING_POLICY_ID,
        "event_mapping_id": RECTIFICATION_EVENT_MAPPING_ID,
        "holdout_policy_id": RECTIFICATION_HOLDOUT_POLICY_ID,
        "method_maturity": RECTIFICATION_METHOD_MATURITY,
        "validation_status": RECTIFICATION_VALIDATION_STATUS,
        "source_ids": list(RECTIFICATION_SOURCE_IDS),
    }


def _sensitivity_boundaries(source: ChartRecordBuildInput) -> list[SensitivityBoundary]:
    """Publish sampled transition bounds without claiming sub-minute precision."""

    variants = [
        item
        for item in source.sensitivity_scan.get("timeVariants") or []
        if isinstance(item, Mapping) and isinstance(item.get("signature"), Mapping)
    ]
    result: list[SensitivityBoundary] = []
    for index, (before, after) in enumerate(zip(variants, variants[1:], strict=False), start=1):
        uncertainty = after.get("leftBoundaryUncertainty")
        if not isinstance(uncertainty, Mapping):
            continue
        before_signature = dict(before["signature"])
        after_signature = dict(after["signature"])
        changed_fields = _changed_signature_fields(before_signature, after_signature)
        if not changed_fields:
            continue
        if uncertainty.get("startUtc") and uncertainty.get("endUtc"):
            start = datetime.fromisoformat(str(uncertainty["startUtc"]))
            end = datetime.fromisoformat(str(uncertainty["endUtc"]))
        else:
            start = _localize_naive(
                datetime.strptime(str(uncertainty["start"]), "%Y-%m-%d %H:%M"),
                source.timezone_id,
            )
            end = _localize_naive(
                datetime.strptime(str(uncertainty["end"]), "%Y-%m-%d %H:%M"),
                source.timezone_id,
            )
        result.append(
            SensitivityBoundary(
                boundary_id=f"boundary.time.{index:03d}",
                axis="time",
                at=end,
                uncertainty_interval=TimeRange(start=start, end=end),
                resolution_seconds=int(after.get("boundaryResolutionSeconds") or 60),
                changed_fields=changed_fields,
                before_fingerprint=hashlib.sha256(
                    json.dumps(before_signature, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                after_fingerprint=hashlib.sha256(
                    json.dumps(after_signature, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            )
        )
    return result


def _changed_signature_fields(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    changed = [
        key
        for key in sorted(set(before) | set(after))
        if key not in {"lagnaDegree", "vargaPlanetSignIndices"}
        and before.get(key) != after.get(key)
    ]
    before_structures = before.get("vargaPlanetSignIndices")
    after_structures = after.get("vargaPlanetSignIndices")
    before_structures = before_structures if isinstance(before_structures, Mapping) else {}
    after_structures = after_structures if isinstance(after_structures, Mapping) else {}
    for varga_id in sorted(set(before_structures) | set(after_structures)):
        if before_structures.get(varga_id) != after_structures.get(varga_id):
            changed.append(f"d{str(varga_id).removeprefix('D')}Structure")
    return sorted(set(changed))


def _candidate_evidence_score(score: Mapping[str, Any]) -> CandidateEvidenceScore:
    observations = [
        RectificationEvidenceObservation.model_validate(observation)
        for observation in score.get("observations") or []
        if isinstance(observation, Mapping)
    ]
    payload: dict[str, Any] = {
        "event_id": str(score.get("eventId")),
        "episode_id": str(score.get("episodeId") or score.get("eventId")),
        "event_subtype": str(score["eventSubtype"]) if score.get("eventSubtype") else None,
        "event_fingerprint": (
            str(score["eventFingerprint"]) if score.get("eventFingerprint") else None
        ),
        "semantic_facts": (
            score.get("semanticFacts") if isinstance(score.get("semanticFacts"), Mapping) else None
        ),
        "semantic_adjustment": (
            score.get("semanticAdjustment")
            if isinstance(score.get("semanticAdjustment"), Mapping)
            else None
        ),
        "role": str(score.get("role") or "calibration"),
        "score": float(score.get("score") or 0.0),
        "support_score": float(score.get("supportScore") or 0.0),
        "contradiction_score": float(score.get("contradictionScore") or 0.0),
        "observations": observations,
        "rule_ids": [str(value) for value in score.get("ruleIds") or []],
        "source_ids": [str(value) for value in score.get("sourceIds") or []],
        "scoring_policy_id": str(score.get("scoringPolicyId") or ""),
        "event_mapping_id": str(score.get("eventMappingId") or ""),
        "event_timezone_basis": EVENT_TIMEZONE_BASIS,
        "explanation": str(score.get("explanation") or "No explanation supplied."),
    }
    optional_fields = {
        "selectionScore": "selection_score",
        "selectionSupportScore": "selection_support_score",
        "selectionContradictionScore": "selection_contradiction_score",
    }
    for source_key, target_key in optional_fields.items():
        if score.get(source_key) is not None:
            payload[target_key] = score[source_key]
    if score.get("methodConvergenceComponents") is not None:
        payload["method_convergence_components"] = [
            str(value)
            for value in score.get("methodConvergenceComponents") or []
            if value in RECTIFICATION_CONVERGENCE_COMPONENTS
        ]
    if score.get("methodConvergenceLayers") is not None:
        payload["method_convergence_layers"] = [
            str(value)
            for value in score.get("methodConvergenceLayers") or []
            if value in {"d1_period_activation", "domain_varga_activation"}
        ]
        if score.get("methodConvergenceCount") is not None:
            payload["method_convergence_count"] = score["methodConvergenceCount"]
        if score.get("methodConvergenceMet") is not None:
            payload["method_convergence_met"] = score["methodConvergenceMet"]
    return CandidateEvidenceScore.model_validate(payload)


def _candidate_intervals(source: ChartRecordBuildInput) -> list[CandidateInterval]:
    raw_candidates = source.sensitivity_scan.get("candidateGroups") or []
    result: list[CandidateInterval] = []
    for raw in raw_candidates:
        if not isinstance(raw, Mapping):
            continue
        interval = raw.get("interval")
        representative = raw.get("representativeDatetime")
        candidate_id = raw.get("candidateId")
        if not isinstance(interval, Mapping) or not representative or not candidate_id:
            continue
        if interval.get("startUtc") and interval.get("endUtc"):
            start = datetime.fromisoformat(str(interval["startUtc"]))
            end = datetime.fromisoformat(str(interval["endUtc"]))
        else:
            start = _localize_naive(
                datetime.strptime(str(interval.get("start")), "%Y-%m-%d %H:%M"),
                source.timezone_id,
            )
            end = _localize_naive(
                datetime.strptime(str(interval.get("end")), "%Y-%m-%d %H:%M"),
                source.timezone_id,
            )
        representative_moment = (
            datetime.fromisoformat(str(raw["representativeUtc"]))
            if raw.get("representativeUtc")
            else _localize_naive(
                datetime.strptime(str(representative), "%Y-%m-%d %H:%M"),
                source.timezone_id,
            )
        )
        signature = raw.get("signature") if isinstance(raw.get("signature"), Mapping) else {}
        members = [member for member in raw.get("members") or [] if isinstance(member, Mapping)]
        axes = list(
            dict.fromkeys(
                str(member.get("axis"))
                for member in members
                if member.get("axis") in {"time", "place"}
            )
        )
        place_member = next(
            (
                member
                for member in members
                if member.get("axis") == "place" and isinstance(member.get("coordinates"), Mapping)
            ),
            None,
        )
        place_hypothesis = None
        if place_member is not None:
            coordinates = place_member["coordinates"]
            place_hypothesis = CandidatePlaceHypothesis(
                label=str(place_member.get("label")) if place_member.get("label") else None,
                latitude=float(coordinates["lat"]),
                longitude=float(coordinates["lon"]),
                timezone_id=str(place_member.get("timezone") or source.timezone_id),
            )
        fingerprint = hashlib.sha256(
            json.dumps(signature, ensure_ascii=True, sort_keys=True).encode("utf-8")
        ).hexdigest()
        result.append(
            CandidateInterval(
                candidate_id=str(candidate_id),
                interval=TimeRange(start=start, end=end),
                representative_moment=representative_moment,
                fingerprint=fingerprint,
                hypothesis_axes=axes or ["time"],
                place_hypothesis=place_hypothesis,
                evidence_scores=[
                    _candidate_evidence_score(score)
                    for score in raw.get("evidenceScores") or []
                    if isinstance(score, Mapping) and score.get("eventId")
                ],
                aggregate_score=(
                    float(raw["aggregateScore"]) if raw.get("aggregateScore") is not None else None
                ),
                convergent_calibration_event_count=int(
                    raw.get("convergentCalibrationEventCount") or 0
                ),
                boundary_resolution_seconds=int(raw.get("boundaryResolutionSeconds") or 60),
                left_boundary_uncertainty=_boundary_range(
                    raw.get("leftBoundaryUncertainty"), source.timezone_id
                ),
                ayanamsa_risk=(
                    str(raw["ayanamsaRisk"])
                    if raw.get("ayanamsaRisk") in {"none", "medium", "high"}
                    else "none"
                ),
                vimshottari_dasha_score=(
                    float(raw["vimshottariDashaScore"])
                    if raw.get("vimshottariDashaScore") is not None
                    else None
                ),
                chara_dasha_score=(
                    float(raw["charaDashaScore"])
                    if raw.get("charaDashaScore") is not None
                    else None
                ),
                dasha_system_agreement=(
                    str(raw["dashaSystemAgreement"])
                    if raw.get("dashaSystemAgreement") in {"agrees", "disagrees", "not_applicable"}
                    else "not_applicable"
                ),
                holdout_period_boundary_checked=bool(raw.get("holdoutPeriodBoundaryChecked")),
                holdout_period_stable_within_interval=(
                    bool(raw["holdoutPeriodStableWithinInterval"])
                    if raw.get("holdoutPeriodStableWithinInterval") is not None
                    else None
                ),
                holdout_period_audit_resolution_seconds=(
                    int(raw["holdoutPeriodAuditResolutionSeconds"])
                    if raw.get("holdoutPeriodAuditResolutionSeconds") is not None
                    else None
                ),
            )
        )
    return result


def _boundary_range(value: object, timezone_id: str) -> TimeRange | None:
    if not isinstance(value, Mapping):
        return None
    if value.get("startUtc") and value.get("endUtc"):
        return TimeRange(
            start=datetime.fromisoformat(str(value["startUtc"])),
            end=datetime.fromisoformat(str(value["endUtc"])),
        )
    return TimeRange(
        start=_localize_naive(
            datetime.strptime(str(value["start"]), "%Y-%m-%d %H:%M"), timezone_id
        ),
        end=_localize_naive(datetime.strptime(str(value["end"]), "%Y-%m-%d %H:%M"), timezone_id),
    )


def _life_events(source: ChartRecordBuildInput) -> list[LifeEvent]:
    ledger = source.input_context.get("lifeEvents") or {}
    raw_events = ledger.get("events") if isinstance(ledger, Mapping) else []
    result: list[LifeEvent] = []
    for raw in raw_events or []:
        if not isinstance(raw, Mapping) or not raw.get("eventId") or not raw.get("date"):
            continue
        if raw.get("role") not in {"calibration", "holdout"}:
            continue
        date_value = str(raw["date"])
        precision = str(raw.get("datePrecision") or "year")
        if precision == "day":
            start_naive = datetime.fromisoformat(date_value)
            end_naive = start_naive + timedelta(days=1) - timedelta(seconds=1)
        elif precision == "month":
            year, month = (int(value) for value in date_value.split("-"))
            start_naive = datetime(year, month, 1)
            next_month = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
            end_naive = next_month - timedelta(seconds=1)
        else:
            year = int(date_value[:4])
            start_naive = datetime(year, 1, 1)
            end_naive = datetime(year + 1, 1, 1) - timedelta(seconds=1)
            precision = "year"
        event_start, event_end = event_utc_envelope(start_naive, end_naive)
        confidence = (
            ConfidenceGrade.CORROBORATED
            if str(raw.get("confidence")) == "high"
            else ConfidenceGrade.PROVISIONAL
        )
        result.append(
            LifeEvent(
                event_id=str(raw["eventId"]),
                episode_id=str(raw.get("episodeId") or raw["eventId"]),
                category=str(raw.get("category") or "unknown"),
                event_subtype=(str(raw["eventSubtype"]) if raw.get("eventSubtype") else None),
                interval=TimeRange(
                    start=event_start,
                    end=event_end,
                ),
                date_precision=precision,
                event_timezone_basis=EVENT_TIMEZONE_BASIS,
                description=str(raw.get("description") or "Dated life event"),
                role=str(raw.get("role") or "calibration"),
                evidence=EvidenceItem(
                    evidence_id=f"evidence.{raw['eventId']}",
                    evidence_class=EvidenceClass.USER_TESTIMONY,
                    source_label="user life-event intake",
                    observed_value=str(raw.get("description") or date_value),
                    confidence=confidence,
                    notes="Used for rectification ranking only; not proof of causation.",
                ),
            )
        )
    return result


def _zodiac_position(value: Mapping[str, Any]) -> ZodiacPosition:
    longitude = float(value["longitude"])
    nakshatra = value.get("nakshatra") or {}
    nakshatra_name = nakshatra.get("name")
    return ZodiacPosition(
        longitude_deg=longitude,
        sign=str(value["sign"]),
        sign_index=int(value["sign_idx"]),
        degree_in_sign=float(value["degree"]),
        nakshatra=(
            {
                "name": nakshatra_name,
                "index": NAKSHATRAS.index(nakshatra_name),
                "pada": int(nakshatra["pada"]),
                "lord": str(nakshatra["lord"]),
            }
            if nakshatra_name in NAKSHATRAS
            else None
        ),
    )


def _varga_position(value: Mapping[str, Any]) -> ZodiacPosition:
    sign_index = int(value["sign_idx"])
    degree = float(value.get("degree") or 0.0)
    return ZodiacPosition(
        longitude_deg=(sign_index * 30.0 + degree) % 360.0,
        sign=str(value["sign"]),
        sign_index=sign_index,
        degree_in_sign=degree,
    )


def _reported_window(input_context: Mapping[str, Any], timezone_id: str) -> TimeRange | None:
    time_context = input_context.get("time") or {}
    window = time_context.get("window") or {}
    start = window.get("start")
    end = window.get("endExclusive") or window.get("end")
    if not start or not end:
        return None
    if window.get("startUtc") and window.get("endExclusiveUtc"):
        return TimeRange(
            start=datetime.fromisoformat(str(window["startUtc"])),
            end=datetime.fromisoformat(str(window["endExclusiveUtc"])),
        )
    return TimeRange(
        start=_localize_naive(datetime.strptime(str(start), "%Y-%m-%d %H:%M"), timezone_id),
        end=_localize_naive(datetime.strptime(str(end), "%Y-%m-%d %H:%M"), timezone_id),
    )


def _local_moment(
    birth_date: str,
    birth_time: str,
    timezone_id: str,
    *,
    utc_offset_seconds: int | None = None,
) -> datetime:
    return resolve_civil_time(
        datetime.fromisoformat(f"{birth_date}T{birth_time}"),
        timezone_id,
        utc_offset_seconds=utc_offset_seconds,
    )


def _localize_naive(value: datetime, timezone_id: str) -> datetime:
    timezone = pytz.timezone(timezone_id)
    try:
        return timezone.localize(value, is_dst=None)
    except pytz.AmbiguousTimeError as exc:
        raise ValueError(
            f"Birth time {value.isoformat()} is ambiguous in {timezone_id}; an explicit UTC offset is required."
        ) from exc
    except pytz.NonExistentTimeError as exc:
        raise ValueError(
            f"Birth time {value.isoformat()} does not exist in {timezone_id} because of a civil-time transition."
        ) from exc


def _period_moment(value: str, timezone_id: str) -> datetime:
    if "T" in value:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            return parsed
    else:
        pattern = "%Y-%m-%d" if len(value) == 10 else "%Y-%m"
        parsed = datetime.strptime(value, pattern)
    return _localize_naive(parsed, timezone_id)


def _timing_provenance(method_profile_id: str) -> RuleProvenance:
    return _rule_provenance(
        "derive.timing.vimshottari-pyjhora",
        method_profile_id,
        ConfidenceGrade.CORROBORATED,
    )


def _rule_provenance(
    rule_id: str,
    method_profile_id: str,
    confidence: ConfidenceGrade,
) -> RuleProvenance:
    rule = _rules_by_id().get(rule_id)
    if rule is None:
        raise ValueError(f"unknown derivation rule: {rule_id}")
    if method_profile_id not in rule.method_profile_ids:
        raise ValueError(f"rule {rule_id} does not support method profile {method_profile_id}")
    return RuleProvenance(
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        method_profile_id=method_profile_id,
        evidence_class=rule.evidence_class,
        source_ids=rule.source_ids,
        confidence=confidence,
    )


@lru_cache(maxsize=1)
def _rules_by_id() -> dict[str, Any]:
    return {rule.rule_id: rule for rule in load_rule_catalog().rules}


def _place_evidence_class(place_source: str) -> EvidenceClass:
    normalized = place_source.lower()
    if "manual" in normalized or "user" in normalized:
        return EvidenceClass.USER_TESTIMONY
    return EvidenceClass.SOFTWARE_REFERENCE


def _confidence(value: str) -> ConfidenceGrade:
    return {
        "high": ConfidenceGrade.VERIFIED,
        "medium": ConfidenceGrade.CORROBORATED,
        "low": ConfidenceGrade.PROVISIONAL,
    }.get(value.lower(), ConfidenceGrade.PROVISIONAL)


def _birth_confidence(precision: str) -> ConfidenceGrade:
    return {
        "exact": ConfidenceGrade.CORROBORATED,
        "approximate": ConfidenceGrade.PROVISIONAL,
        "part_of_day": ConfidenceGrade.PROVISIONAL,
        "unknown": ConfidenceGrade.UNAVAILABLE,
    }.get(precision, ConfidenceGrade.PROVISIONAL)


def _division_confidence(value: Mapping[str, Any]) -> ConfidenceGrade:
    return _confidence(str(value.get("confidence") or "low"))


def _time_certainty(precision: str) -> str:
    return {
        "exact": "reported_exact",
        "approximate": "approximate",
        "part_of_day": "broad_window",
        "unknown": "unknown",
    }.get(precision, "unknown")


def _place_precision(accuracy: str) -> str:
    return accuracy if accuracy in {"coordinate", "poi", "address", "district", "city"} else "city"


def _matched_place_note(matched: Mapping[str, str] | None) -> str | None:
    if not matched:
        return None
    return ", ".join(f"{key}={value}" for key, value in sorted(matched.items()))


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _age_on(birth_date: date, current_date: date) -> int:
    return (
        current_date.year
        - birth_date.year
        - ((current_date.month, current_date.day) < (birth_date.month, birth_date.day))
    )


def _life_stage(age: int) -> str:
    if age < 13:
        return "child"
    if age < 18:
        return "teen"
    if age < 25:
        return "young_adult"
    if age < 65:
        return "adult"
    return "elder"
