from __future__ import annotations

import hashlib
import json
import calendar
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Mapping

import pytz

from app.calculator.constants import SIGNS, SIGN_LORDS

from .fact_catalog import FactType, fact_definition
from .models import (
    AstronomySnapshot,
    BirthAssertion,
    CanonicalBirthMoment,
    CandidateEvidenceScore,
    CandidateInterval,
    ChartPlacement,
    ConfidenceGrade,
    EvidenceClass,
    EvidenceItem,
    GrahaPosition,
    JyotishFact,
    LifeEvent,
    PlaceResolution,
    QualityCheck,
    RectificationDecision,
    RectificationRecord,
    RuleProvenance,
    SubjectContext,
    TimeRange,
    TimingPeriod,
    VargaChart,
    VargaHouseLord,
    ChartRecord,
    ZodiacPosition,
)
from .profiles import parashari_lahiri_profile
from .source_registry import load_rule_catalog
from .validation import validate_chart_record_provenance


GRAHAS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
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


def build_chart_record(source: ChartRecordBuildInput) -> ChartRecord:
    profile = parashari_lahiri_profile()
    local_moment = _local_moment(source.birth_date, source.birth_time, source.timezone_id)
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
        resolution_confidence=min(birth_confidence, place_confidence, key=_confidence_rank),
    )

    astronomy = _astronomy_snapshot(source)
    charts = _varga_charts(source.chart, source.sensitivity_scan)
    facts = _facts(source.chart, charts, profile.profile_id)
    timing_periods = _timing_periods(source.chart, source.timezone_id, profile.profile_id)
    quality_checks = _quality_checks(source.chart, charts)
    rectification = _rectification(source, birth_confidence)

    has_failed_check = any(check.status == "failed" for check in quality_checks)
    requires_rectification = rectification is not None and rectification.decision.status not in {
        "not_required",
        "bounded_interval",
    }
    status = (
        "blocked"
        if has_failed_check
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
            reader_relationship="self",
            gender_context=source.gender_context,
            relationship_status=source.relationship_status,
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
                motion=(
                    "not_applicable"
                    if name == "Ketu"
                    else "retrograde"
                    if planets[name].get("retrograde")
                    else "direct"
                ),
            )
            for name in GRAHAS
        ],
        status="complete",
    )


def _varga_charts(
    chart: Mapping[str, Any], sensitivity_scan: Mapping[str, Any]
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
                    confidence=ConfidenceGrade.VERIFIED,
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
                method="parashara-method-1",
                lagna=ChartPlacement(
                    object_id="Lagna",
                    position=_varga_position(lagna),
                    house=1,
                ),
                placements=placements,
                house_lords=_varga_house_lords(lagna_index, placements),
                confidence=_division_confidence(confidence_entry),
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


def _facts(
    chart: Mapping[str, Any], charts: list[VargaChart], method_profile_id: str
) -> list[JyotishFact]:
    facts: list[JyotishFact] = []
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
    for house, value in (chart.get("house_lords") or {}).items():
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
                confidence=varga.confidence,
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
                    confidence=varga.confidence,
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
                    confidence=varga.confidence,
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
                confidence=ConfidenceGrade.PROVISIONAL,
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
                confidence=ConfidenceGrade.CORROBORATED,
            )
        )
    combustion = chart.get("combustion") or {}
    sun_longitude = float(chart["planets"]["Sun"]["longitude"])
    for name in ["Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]:
        value = combustion.get(name) if isinstance(combustion, Mapping) else None
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
                    "isCombust": isinstance(value, Mapping),
                    "distanceDeg": round(float(value.get("distance", distance)), 4)
                    if isinstance(value, Mapping)
                    else round(distance, 4),
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
        if name not in GRAHAS:
            continue
        facts.append(
            _fact(
                fact_id=f"fact.D1.{name}.vargottama",
                fact_type="varga.vargottama",
                subject_ref=f"D1.{name}",
                value={"isVargottamaD1D9": bool(value)},
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.PROVISIONAL,
            )
        )
    for row in (chart.get("karakas") or {}).get("7k") or []:
        if not isinstance(row, (list, tuple)) or len(row) < 3 or str(row[1]) not in GRAHAS:
            continue
        role, name, degree = str(row[0]), str(row[1]), float(row[2])
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
                confidence=ConfidenceGrade.CORROBORATED,
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
                confidence=ConfidenceGrade.CORROBORATED,
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
        if not isinstance(value, Mapping):
            continue
        facts.append(
            _fact(
                fact_id=f"fact.D1.special_lagna.{name}",
                fact_type="point.special_lagna",
                subject_ref=f"D1.special_lagna.{name}",
                value=dict(value),
                method_profile_id=method_profile_id,
                confidence=ConfidenceGrade.CORROBORATED,
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
                    confidence=ConfidenceGrade.PROVISIONAL,
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
                confidence=ConfidenceGrade.PROVISIONAL,
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
                confidence=ConfidenceGrade.PROVISIONAL,
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
            facts.append(
                _fact(
                    fact_id=f"fact.Transit.{name}.position",
                    fact_type="timing.transit.position",
                    subject_ref=f"Transit.{name}",
                    value={**dict(value), "asOfUtc": as_of_utc},
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
    return facts


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


def _timing_periods(
    chart: Mapping[str, Any], timezone_id: str, method_profile_id: str
) -> list[TimingPeriod]:
    result: list[TimingPeriod] = []
    for md_index, dasha in enumerate(chart.get("dashas") or []):
        if not isinstance(dasha, Mapping):
            continue
        md_start = _period_moment(str(dasha["start"]), timezone_id)
        md_end = _period_moment(str(dasha["end"]), timezone_id)
        if md_end <= md_start:
            continue
        md_id = f"vimshottari.md.{md_index:02d}.{str(dasha['planet']).lower()}"
        result.append(
            TimingPeriod(
                period_id=md_id,
                system="Vimshottari",
                level="mahadasha",
                lords=[str(dasha["planet"])],
                interval=TimeRange(start=md_start, end=md_end),
                provenance=_timing_provenance(method_profile_id),
            )
        )
        for ad_index, antardasha in enumerate(dasha.get("antardashas") or []):
            if not isinstance(antardasha, Mapping):
                continue
            ad_start = _period_moment(str(antardasha["start"]), timezone_id)
            ad_end = _period_moment(str(antardasha["end"]), timezone_id)
            if ad_end <= ad_start:
                continue
            result.append(
                TimingPeriod(
                    period_id=f"{md_id}.ad.{ad_index:02d}.{str(antardasha['planet']).lower()}",
                    system="Vimshottari",
                    level="antardasha",
                    lords=[str(dasha["planet"]), str(antardasha["planet"])],
                    interval=TimeRange(start=ad_start, end=ad_end),
                    provenance=_timing_provenance(method_profile_id),
                )
            )
            for pd_index, pratyantardasha in enumerate(antardasha.get("pratyantardashas") or []):
                if not isinstance(pratyantardasha, Mapping):
                    continue
                pd_start = _period_moment(str(pratyantardasha["start"]), timezone_id)
                pd_end = _period_moment(str(pratyantardasha["end"]), timezone_id)
                if pd_end <= pd_start:
                    continue
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
                    )
                )
    return result


def _quality_checks(chart: Mapping[str, Any], charts: list[VargaChart]) -> list[QualityCheck]:
    planets = chart.get("planets") or {}
    sav_total = sum(int(value) for value in (chart.get("sav") or {}).values())
    rahu = float(planets["Rahu"]["longitude"])
    ketu = float(planets["Ketu"]["longitude"])
    node_gap = abs((rahu - ketu + 180.0) % 360.0 - 180.0)
    expected_vargas = set(parashari_lahiri_profile().supported_vargas)
    observed_vargas = {varga.factor for varga in charts}
    d1_mismatches = _d1_provider_sign_mismatches(chart)
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
            check_id="calculation.independent-golden-reference",
            status="warning",
            expected="Pinned outputs from an independent Jyotish desktop reference",
            observed="Swiss Ephemeris core checks plus direct PyJHora adapter checks",
            message=(
                "Provider compatibility is covered, but cross-software golden fixtures "
                "remain required before claiming independent desktop equivalence."
            ),
        ),
    ]


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


def _rectification(
    source: ChartRecordBuildInput, birth_confidence: ConfidenceGrade
) -> RectificationRecord | None:
    reported_window = _reported_window(source.input_context, source.timezone_id)
    readiness = source.sensitivity_scan.get("reportReadiness") or {}
    mode = str(readiness.get("mode") or "rectification_required")
    if reported_window is None:
        return None
    if mode == "rectification_required":
        decision = RectificationDecision(
            status="collecting_evidence",
            confidence=ConfidenceGrade.PROVISIONAL,
            reasons=[str(value) for value in readiness.get("blockingFactors") or []]
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
        reported_window=reported_window,
        life_events=_life_events(source),
        candidates=_candidate_intervals(source),
        decision=decision,
    )


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
        start = _localize_naive(
            datetime.strptime(str(interval.get("start")), "%Y-%m-%d %H:%M"),
            source.timezone_id,
        )
        end = _localize_naive(
            datetime.strptime(str(interval.get("end")), "%Y-%m-%d %H:%M"),
            source.timezone_id,
        )
        representative_moment = _localize_naive(
            datetime.strptime(str(representative), "%Y-%m-%d %H:%M"),
            source.timezone_id,
        )
        signature = raw.get("signature") if isinstance(raw.get("signature"), Mapping) else {}
        fingerprint = hashlib.sha256(
            json.dumps(signature, ensure_ascii=True, sort_keys=True).encode("utf-8")
        ).hexdigest()
        result.append(
            CandidateInterval(
                candidate_id=str(candidate_id),
                interval=TimeRange(start=start, end=end),
                representative_moment=representative_moment,
                fingerprint=fingerprint,
                evidence_scores=[
                    CandidateEvidenceScore(
                        event_id=str(score.get("eventId")),
                        score=float(score.get("score") or 0.0),
                        supporting_fact_ids=[
                            str(value) for value in score.get("supportingFactIds") or []
                        ],
                        contradicting_fact_ids=[
                            str(value) for value in score.get("contradictingFactIds") or []
                        ],
                        neutral_evidence_ids=[
                            str(value) for value in score.get("neutralEvidenceIds") or []
                        ],
                        rule_ids=[str(value) for value in score.get("ruleIds") or []],
                        explanation=str(score.get("explanation") or "No explanation supplied."),
                    )
                    for score in raw.get("evidenceScores") or []
                    if isinstance(score, Mapping) and score.get("eventId")
                ],
                aggregate_score=(
                    float(raw["aggregateScore"]) if raw.get("aggregateScore") is not None else None
                ),
            )
        )
    return result


def _life_events(source: ChartRecordBuildInput) -> list[LifeEvent]:
    ledger = source.input_context.get("lifeEvents") or {}
    raw_events = ledger.get("events") if isinstance(ledger, Mapping) else []
    result: list[LifeEvent] = []
    for raw in raw_events or []:
        if not isinstance(raw, Mapping) or not raw.get("eventId") or not raw.get("date"):
            continue
        date_value = str(raw["date"])
        precision = str(raw.get("datePrecision") or "year")
        if precision == "month":
            year, month = (int(value) for value in date_value.split("-"))
            start_naive = datetime(year, month, 1)
            end_naive = datetime(
                year,
                month,
                calendar.monthrange(year, month)[1],
                23,
                59,
                59,
            )
        else:
            year = int(date_value[:4])
            start_naive = datetime(year, 1, 1)
            end_naive = datetime(year, 12, 31, 23, 59, 59)
            precision = "year"
        confidence = (
            ConfidenceGrade.CORROBORATED
            if str(raw.get("confidence")) == "high"
            else ConfidenceGrade.PROVISIONAL
        )
        result.append(
            LifeEvent(
                event_id=str(raw["eventId"]),
                category=str(raw.get("category") or "unknown"),
                interval=TimeRange(
                    start=_localize_naive(start_naive, source.timezone_id),
                    end=_localize_naive(end_naive, source.timezone_id),
                ),
                date_precision=precision,
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
    return TimeRange(
        start=_localize_naive(datetime.strptime(str(start), "%Y-%m-%d %H:%M"), timezone_id),
        end=_localize_naive(datetime.strptime(str(end), "%Y-%m-%d %H:%M"), timezone_id),
    )


def _local_moment(birth_date: str, birth_time: str, timezone_id: str) -> datetime:
    return _localize_naive(
        datetime.fromisoformat(f"{birth_date}T{birth_time}"),
        timezone_id,
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
    pattern = "%Y-%m-%d" if len(value) == 10 else "%Y-%m"
    return _localize_naive(datetime.strptime(value, pattern), timezone_id)


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


def _confidence_rank(value: ConfidenceGrade) -> int:
    return {
        ConfidenceGrade.UNAVAILABLE: 0,
        ConfidenceGrade.DISPUTED: 1,
        ConfidenceGrade.PROVISIONAL: 2,
        ConfidenceGrade.CORROBORATED: 3,
        ConfidenceGrade.VERIFIED: 4,
    }[value]


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
