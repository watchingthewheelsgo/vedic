from __future__ import annotations

import json
import math
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.schemas import (
    BirthInput,
    CalculationSnapshot,
    ChartFacts,
    CurrentDasha,
    Karakas,
    LagnaFact,
    PlanetFact,
    StrengthFact,
)
from app.calculator.provenance import calculation_runtime_provenance
from app.services.life_event_rectification import (
    parse_life_event_ledger,
    score_candidate_events,
)
from app.services.place_service import PlaceService, ResolvedPlace
from app.settings import Settings
from app.utils.ids import make_id
from app.vedicdust.chart_record_builder import ChartRecordBuildInput, build_chart_record


PRECISION_STATUS: dict[str, str] = {
    "exact": "passed",
    "approximate": "degraded",
    "part_of_day": "degraded",
    "unknown": "limited",
}

DIVISIONAL_FACTORS = [1, 2, 3, 4, 5, 7, 9, 10, 12, 16, 20, 24, 27, 30, 60]

DIVISIONAL_POLICIES: dict[int, dict[str, str]] = {
    1: {
        "name": "Rashi",
        "role": "body, identity, house lords, and the foundation for all readings",
        "usageTier": "primary_foundation",
    },
    2: {
        "name": "Hora",
        "role": "wealth flow, liquidity, food, family resources",
        "usageTier": "supporting_domain",
    },
    3: {
        "name": "Drekkana",
        "role": "siblings, initiative, courage, effort pattern",
        "usageTier": "supporting_domain",
    },
    4: {
        "name": "Chaturthamsha",
        "role": "home, property, residence, vehicles, core comforts",
        "usageTier": "supporting_domain",
    },
    5: {
        "name": "Panchamsha",
        "role": "creative authority, counsel, recognition, purva punya",
        "usageTier": "supporting_domain",
    },
    7: {
        "name": "Saptamsha",
        "role": "children, fertility, lineage, family continuity",
        "usageTier": "rectification_domain",
    },
    9: {
        "name": "Navamsha",
        "role": "marriage, dharma, maturity, promise confirmation",
        "usageTier": "rectification_domain",
    },
    10: {
        "name": "Dashamsha",
        "role": "career, public role, work environment, authority",
        "usageTier": "rectification_domain",
    },
    12: {
        "name": "Dwadashamsha",
        "role": "parents, ancestry, inherited family patterns",
        "usageTier": "rectification_domain",
    },
    16: {
        "name": "Shodashamsha",
        "role": "vehicles, luxuries, comforts, lived ease",
        "usageTier": "advanced_validation",
    },
    20: {
        "name": "Vimshamsha",
        "role": "spiritual practice, devotion, initiation",
        "usageTier": "advanced_validation",
    },
    24: {
        "name": "Chaturvimshamsha",
        "role": "education, learning, formal knowledge",
        "usageTier": "advanced_validation",
    },
    27: {
        "name": "Bhamsa",
        "role": "strengths, vulnerabilities, resilience",
        "usageTier": "advanced_validation",
    },
    30: {
        "name": "Trimshamsha",
        "role": "adversity, misfortune, hidden stress, faults",
        "usageTier": "advanced_validation",
    },
    60: {
        "name": "Shashtiamsha",
        "role": "fine karmic residue and final birth-time confirmation",
        "usageTier": "final_confirmation_only",
    },
}

DIVISIONAL_FINGERPRINT_FACTORS = [2, 3, 4, 5, 7, 9, 10, 12]
CALCULATION_VERSION = "vedic-calculator-pyjhora-0.5"
HIGH_RISK_CHANGED_FIELDS = {
    "lagnaSign",
    "moonNakshatra",
    "currentDasha",
    "d7Lagna",
    "d9Lagna",
    "d10Lagna",
}
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
TIME_SOURCE_MIN_RADIUS_MINUTES = {
    "出生证/医院记录": 2,
    "birth certificate / hospital record": 2,
    "birth certificate": 2,
    "hospital record": 2,
    "家人明确记忆": 10,
    "clear family memory": 10,
    "家人大概回忆": 30,
    "approximate family memory": 30,
    "family memory": 30,
}


@dataclass(frozen=True)
class BirthDate:
    year: int
    month: int
    day: int


@dataclass(frozen=True)
class BirthTime:
    hour: int
    minute: int
    normalized: str


@dataclass(frozen=True)
class ChartRecordIdentity:
    reading_session_id: str
    chart_record_id: str
    subject_id: str
    revision: int = 1


class VedicCalculator:
    """Adapter over the backend-owned Vedic calculation engine."""

    def __init__(self, settings: Settings, place_service: PlaceService) -> None:
        self.settings = settings
        self.place_service = place_service

    def calculate(
        self,
        intake: BirthInput,
        *,
        identity: ChartRecordIdentity | None = None,
    ) -> CalculationSnapshot:
        identity = identity or ChartRecordIdentity(
            reading_session_id=make_id("reading"),
            chart_record_id=make_id("chart"),
            subject_id=make_id("subject"),
        )
        birth_date = self._parse_birth_date(intake.birth_date)
        birth_time = self._parse_birth_time(intake.birth_time, intake.birth_time_precision)
        place = self.place_service.resolve(intake.birth_place)
        payload = self._calculator_payload(intake, birth_date, birth_time, place)
        runtime_provenance = calculation_runtime_provenance()
        (
            birth_input_context_json,
            sensitivity_scan_json,
            chart_record_json,
            facts,
        ) = self._run_engine(payload, intake, place, identity)

        return CalculationSnapshot(
            snapshot_id=make_id("calc"),
            engine="real_vedic",
            calculation_version=CALCULATION_VERSION,
            ayanamsa="Lahiri",
            house_system="whole-sign",
            ephemeris_version=runtime_provenance.summary,
            provider_versions=runtime_provenance.provider_versions,
            timezone_database_version=runtime_provenance.timezone_database_version,
            ephemeris_data_fingerprint=runtime_provenance.ephemeris_data_fingerprint,
            timezone_source=place.timezone,
            geo_source=place.source,
            input_precision=intake.birth_time_precision,
            validation_status=PRECISION_STATUS[intake.birth_time_precision],
            birth_input_context_json=birth_input_context_json,
            sensitivity_scan_json=sensitivity_scan_json,
            chart_record_json=chart_record_json,
            facts=facts,
        )

    def _run_engine(
        self,
        payload: dict[str, Any],
        intake: BirthInput,
        place: ResolvedPlace,
        identity: ChartRecordIdentity,
    ) -> tuple[str, str, str, ChartFacts]:
        with redirect_stdout(sys.stderr):
            from app.calculator.engine import (
                SIGNS,
                calculate_full_chart,
                calculate_rectification_signature,
            )

            calculated_at = datetime.now(timezone.utc)
            runtime_provenance = calculation_runtime_provenance()
            chart = calculate_full_chart(
                year=int(payload["year"]),
                month=int(payload["month"]),
                day=int(payload["day"]),
                hour=int(payload["hour"]),
                minute=int(payload["minute"]),
                lat=float(payload["lat"]),
                lon=float(payload["lon"]),
                tz_str=str(payload["timezone"]),
                transit_as_of=calculated_at,
            )
            input_context = self._birth_input_context(payload, intake, place)
            sensitivity_scan = self._sensitivity_scan(
                calculate_full_chart,
                chart,
                payload,
                intake,
                place,
                calculate_signature=calculate_rectification_signature,
                life_event_ledger=input_context["lifeEvents"],
            )
            birth_input_context_json = (
                json.dumps(input_context, ensure_ascii=False, indent=2) + "\n"
            )
            sensitivity_scan_json = (
                json.dumps(sensitivity_scan, ensure_ascii=False, indent=2) + "\n"
            )
            chart_record = build_chart_record(
                ChartRecordBuildInput(
                    chart_record_id=identity.chart_record_id,
                    reading_session_id=identity.reading_session_id,
                    revision=identity.revision,
                    subject_id=identity.subject_id,
                    created_at=calculated_at,
                    locale=intake.locale,
                    birth_date=str(payload["dob"]),
                    birth_time=str(payload["time"]),
                    birth_place=intake.birth_place,
                    birth_time_precision=intake.birth_time_precision,
                    time_source=intake.time_source,
                    gender_context=intake.gender,
                    relationship_status=intake.relationship,
                    place_label=place.label,
                    latitude=float(place.lat),
                    longitude=float(place.lon),
                    timezone_id=place.timezone,
                    place_source=place.source,
                    place_accuracy=place.accuracy,
                    place_confidence=place.confidence,
                    place_matched=place.matched,
                    calculation_version=CALCULATION_VERSION,
                    ephemeris_version=runtime_provenance.summary,
                    provider_versions=runtime_provenance.provider_versions,
                    timezone_database_version=runtime_provenance.timezone_database_version,
                    ephemeris_data_fingerprint=runtime_provenance.ephemeris_data_fingerprint,
                    chart=chart,
                    input_context=input_context,
                    sensitivity_scan=sensitivity_scan,
                )
            )
            chart_record_json = chart_record.model_dump_json(by_alias=True, indent=2) + "\n"
            sav_total = sum(chart["sav"].get(sign, 0) for sign in SIGNS)
            if sav_total != 337:
                raise RuntimeError(f"SAV validation failed: {sav_total} != 337")
            facts = self._chart_facts(chart, sav_total)

        return (
            birth_input_context_json,
            sensitivity_scan_json,
            chart_record_json,
            facts,
        )

    def _birth_input_context(
        self,
        payload: dict[str, Any],
        intake: BirthInput,
        place: ResolvedPlace,
    ) -> dict[str, Any]:
        time_window = self._time_window(payload, intake.birth_time_precision, intake.time_source)
        place_radius = round(float(place.radius_km), 3)
        place_rectification_allowed = self._place_rectification_allowed(place)
        life_event_ledger = parse_life_event_ledger(str(payload.get("life_events") or ""))
        return {
            "schemaVersion": "birth-input-context/v1",
            "time": {
                "reported": payload["time"],
                "date": payload["dob"],
                "precision": intake.birth_time_precision,
                "source": intake.time_source,
                "normalized": payload["time"],
                "timezone": place.timezone,
                "window": time_window,
            },
            "place": {
                "reported": intake.birth_place,
                "resolvedLabel": place.label,
                "coordinates": {
                    "lat": round(float(place.lat), 6),
                    "lon": round(float(place.lon), 6),
                },
                "timezone": place.timezone,
                "source": place.source,
                "accuracy": place.accuracy,
                "coordinateSystem": place.coordinate_system,
                "radiusKm": place_radius,
                "confidence": place.confidence,
                "matched": place.matched,
                "rectificationAllowed": place_rectification_allowed,
                "rectificationPolicy": self._place_rectification_policy(place),
            },
            "lifeEvents": life_event_ledger,
            "constraints": {
                "timeSearchMustStayWithinReportedWindow": True,
                "placeSearchMustStayWithinRadiusKm": place_radius,
                "placeRectificationAllowed": place_rectification_allowed,
                "rectificationAxes": self._rectification_axes(place),
                "rejectRectificationOutsideUserFacts": True,
            },
        }

    def _sensitivity_scan(
        self,
        calculate_full_chart: Any,
        base_chart: dict[str, Any],
        payload: dict[str, Any],
        intake: BirthInput,
        place: ResolvedPlace,
        *,
        calculate_signature: Any | None = None,
        life_event_ledger: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base_signature = self._chart_signature(base_chart)
        time_variants = self._time_scan_variants(
            calculate_full_chart,
            base_chart,
            base_signature,
            payload,
            intake.birth_time_precision,
            intake.time_source,
            calculate_signature=calculate_signature,
        )
        place_variants = self._place_scan_variants(
            calculate_full_chart,
            base_chart,
            base_signature,
            payload,
            place,
        )
        place_rectification_allowed = self._place_rectification_allowed(place)
        boundary_flags = self._boundary_flags(base_chart)
        summary = self._scan_summary(
            intake.birth_time_precision,
            place,
            time_variants,
            place_variants,
            boundary_flags,
        )
        candidate_groups = self._candidate_groups(
            base_signature,
            time_variants,
            place_variants if place_rectification_allowed else [],
        )
        self._score_candidate_groups(
            candidate_groups,
            life_event_ledger or {},
            payload,
        )
        stability = self._stability_map(
            set(summary["changedFields"]),
            summary["divisionalConfidence"],
        )
        report_readiness = self._report_readiness(
            summary,
            stability,
            candidate_groups,
            intake.birth_time_precision,
            place,
        )
        return {
            "schemaVersion": "vedic-sensitivity-scan/v1",
            "base": base_signature,
            "summary": summary,
            "stability": stability,
            "candidateGroups": candidate_groups,
            "reportReadiness": report_readiness,
            "timeVariants": time_variants,
            "placeVariants": place_variants,
            "boundaryFlags": boundary_flags,
            "rectificationGuardrails": self._rectification_guardrails(place),
        }

    def _candidate_groups(
        self,
        base_signature: dict[str, Any],
        time_variants: list[dict[str, Any]],
        place_variants: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if time_variants and any(
            not isinstance(variant.get("interval"), dict) for variant in time_variants
        ):
            legacy_points: list[dict[str, Any]] = []
            base_dt: datetime | None = None
            for variant in time_variants:
                raw_moment = variant.get("datetime")
                if not raw_moment:
                    continue
                try:
                    moment = datetime.strptime(str(raw_moment), "%Y-%m-%d %H:%M")
                except ValueError:
                    continue
                point: dict[str, Any] = {"moment": moment}
                if isinstance(variant.get("signature"), dict):
                    point["signature"] = variant["signature"]
                    if self._signature_fingerprint(
                        variant["signature"]
                    ) == self._signature_fingerprint(base_signature) and (
                        variant.get("label") == "base" or base_dt is None
                    ):
                        base_dt = moment
                elif variant.get("error"):
                    point["error"] = variant["error"]
                legacy_points.append(point)
            if legacy_points:
                time_variants = self._coalesce_time_points(
                    legacy_points,
                    base_dt or legacy_points[0]["moment"],
                    base_signature,
                )
        grouped: list[dict[str, Any]] = []
        for variant in time_variants:
            signature = variant.get("signature")
            interval = variant.get("interval")
            if not isinstance(signature, dict) or not isinstance(interval, dict):
                continue
            grouped.append(
                {
                    "candidateId": "",
                    "signature": signature,
                    "interval": interval,
                    "representativeDatetime": variant.get("representativeDatetime"),
                    "members": [
                        {
                            "axis": "time",
                            "label": variant.get("label"),
                            "datetime": variant.get("representativeDatetime"),
                            "interval": interval,
                        }
                    ],
                    "changedFromBase": self._signature_changes(base_signature, signature),
                    "isBase": bool(variant.get("isBase")),
                }
            )

        for variant in place_variants:
            signature = variant.get("signature")
            if not isinstance(signature, dict):
                continue
            fingerprint = self._signature_fingerprint(signature)
            target = next(
                (
                    item
                    for item in grouped
                    if item.get("isBase")
                    and self._signature_fingerprint(item.get("signature", {})) == fingerprint
                ),
                None,
            )
            if target is None:
                target = {
                    "candidateId": "",
                    "signature": signature,
                    "members": [],
                    "changedFromBase": self._signature_changes(base_signature, signature),
                    "isBase": fingerprint == self._signature_fingerprint(base_signature),
                }
                grouped.append(target)
            target["members"].append(
                {
                    "axis": "place",
                    "label": variant.get("label"),
                    "coordinates": variant.get("coordinates"),
                    "radiusKm": variant.get("radiusKm"),
                }
            )
        sorted_items = sorted(
            grouped,
            key=lambda item: (
                0 if item.get("isBase") else 1,
                len(item.get("changedFromBase", [])),
                self._signature_fingerprint(item.get("signature", {})),
            ),
        )
        for index, item in enumerate(sorted_items):
            item["candidateId"] = self._candidate_label(index)
        return sorted_items

    @staticmethod
    def _score_candidate_groups(
        candidates: list[dict[str, Any]],
        life_event_ledger: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        if not life_event_ledger.get("events"):
            return
        base_moment = datetime(
            int(payload["year"]),
            int(payload["month"]),
            int(payload["day"]),
            int(payload["hour"]),
            int(payload["minute"]),
        )
        for candidate in candidates:
            raw_representative = candidate.get("representativeDatetime")
            try:
                representative = (
                    datetime.strptime(str(raw_representative), "%Y-%m-%d %H:%M")
                    if raw_representative
                    else base_moment
                )
                result = score_candidate_events(
                    candidate_id=str(candidate.get("candidateId") or "candidate"),
                    signature=(
                        candidate.get("signature")
                        if isinstance(candidate.get("signature"), dict)
                        else {}
                    ),
                    representative_moment=representative,
                    latitude=float(payload["lat"]),
                    longitude=float(payload["lon"]),
                    timezone_id=str(payload["timezone"]),
                    ledger=life_event_ledger,
                )
                candidate.update(result)
            except Exception as exc:
                candidate.update(
                    {
                        "evidenceScores": [],
                        "aggregateScore": None,
                        "holdoutScore": None,
                        "scoringError": str(exc),
                    }
                )

    @staticmethod
    def _candidate_label(index: int) -> str:
        label = ""
        value = index + 1
        while value:
            value, remainder = divmod(value - 1, 26)
            label = chr(ord("A") + remainder) + label
        return label

    @staticmethod
    def _signature_fingerprint(signature: dict[str, Any]) -> str:
        stable_keys = [
            "lagnaSign",
            "moonSign",
            "moonNakshatra",
            "moonPada",
            "currentDasha",
        ]
        stable_keys.extend(
            VedicCalculator._divisional_field(factor) for factor in DIVISIONAL_FINGERPRINT_FACTORS
        )
        return "|".join(str(signature.get(key)) for key in stable_keys)

    @staticmethod
    def _divisional_key(factor: int) -> str:
        return f"D{factor}"

    @staticmethod
    def _divisional_field(factor: int) -> str:
        return "lagnaSign" if factor == 1 else f"d{factor}Lagna"

    def _stability_map(
        self,
        changed_fields: set[str],
        divisional_confidence: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        field_impacts = {
            "lagnaSign": {
                "domain": "D1 identity, house lords, all house mapping",
                "severity": "blocking",
            },
            "moonNakshatra": {
                "domain": "Nakshatra, Dasha balance, psychological anchors",
                "severity": "blocking",
            },
            "moonPada": {
                "domain": "Nakshatra pada nuance",
                "severity": "medium",
            },
            "currentDasha": {
                "domain": "current timing and validation windows",
                "severity": "blocking",
            },
        }
        for factor in DIVISIONAL_FACTORS:
            if factor == 1:
                continue
            policy = DIVISIONAL_POLICIES[factor]
            severity = "medium"
            if factor in {7, 9, 10}:
                severity = "high"
            elif factor in {27, 30, 60}:
                severity = "validation-only"
            field_impacts[self._divisional_field(factor)] = {
                "domain": f"{self._divisional_key(factor)} {policy['role']}",
                "severity": severity,
            }

        confidence_by_field = {
            str(value.get("field")): value
            for value in divisional_confidence.values()
            if isinstance(value, dict) and value.get("field")
        }
        stable_fields = []
        unstable_fields = []
        for field, impact in field_impacts.items():
            confidence = confidence_by_field.get(field)
            item = {
                "field": field,
                **impact,
            }
            if confidence:
                item["division"] = confidence.get("division")
                item["confidence"] = confidence.get("confidence")
                item["recommendedUse"] = confidence.get("recommendedUse")
            restricted_by_policy = bool(confidence and not confidence.get("useAsPrimaryEvidence"))
            if field in changed_fields or restricted_by_policy:
                unstable_fields.append(item)
            else:
                stable_fields.append(item)
        low_confidence_divisions = [
            name
            for name, value in divisional_confidence.items()
            if value.get("confidence") == "low"
        ]
        return {
            "stableFields": stable_fields,
            "unstableFields": unstable_fields,
            "lowConfidenceDivisions": low_confidence_divisions,
            "llmStableEvidence": [item["field"] for item in stable_fields],
            "llmRestrictedEvidence": sorted(
                set([item["field"] for item in unstable_fields] + low_confidence_divisions)
            ),
        }

    def _report_readiness(
        self,
        summary: dict[str, Any],
        stability: dict[str, Any],
        candidate_groups: list[dict[str, Any]],
        precision: str,
        place: ResolvedPlace,
    ) -> dict[str, Any]:
        risk_level = str(summary.get("riskLevel") or "unknown")
        unstable_fields = [
            str(item.get("field"))
            for item in stability.get("unstableFields", [])
            if isinstance(item, dict)
        ]
        low_confidence_divisions = [
            str(item) for item in stability.get("lowConfidenceDivisions", [])
        ]
        candidate_count = len(candidate_groups)

        if risk_level == "low":
            mode = "standard_after_prevalidation"
            min_hit_rate = 0.6
            core_allowed_without_rectification = True
            scope = "full_report"
        elif risk_level == "medium":
            mode = "guarded_after_strong_prevalidation"
            min_hit_rate = 0.8
            core_allowed_without_rectification = True
            scope = "guarded_full_report"
        else:
            mode = "rectification_required"
            min_hit_rate = 0.9
            core_allowed_without_rectification = False
            scope = "prevalidation_or_d1_only"

        blockers = []
        if unstable_fields:
            blockers.append("unstable_fields:" + ",".join(unstable_fields))
        if low_confidence_divisions:
            blockers.append("low_confidence_divisions:" + ",".join(low_confidence_divisions))
        if precision in {"part_of_day", "unknown"}:
            blockers.append(f"time_precision:{precision}")
        if place.accuracy in {"city", "district"} and risk_level != "low":
            blockers.append(f"place_accuracy:{place.accuracy}")

        return {
            "mode": mode,
            "scope": scope,
            "prevalidationRequired": True,
            "minimumHitRateForCore": min_hit_rate,
            "coreAllowedWithoutRectification": core_allowed_without_rectification,
            "candidateCount": candidate_count,
            "rectificationAxes": summary.get("rectificationAxes", ["time"]),
            "placeRectificationAllowed": summary.get("placeRectificationAllowed", False),
            "placeRectificationPolicy": summary.get(
                "placeRectificationPolicy",
                "locked_precise_coordinates",
            ),
            "blockingFactors": blockers,
            "llmContract": {
                "mustRead": [
                    "chart_record.json",
                    "birth_input_context.json",
                    "sensitivity_scan.json",
                    "prevalidation_result.json",
                ],
                "mustNotUseAsPrimaryEvidence": stability.get("llmRestrictedEvidence", []),
                "mayUseAsPrimaryEvidence": stability.get("llmStableEvidence", []),
                "rectificationAxes": summary.get("rectificationAxes", ["time"]),
                "placeRectificationAllowed": summary.get("placeRectificationAllowed", False),
                "ifBlocked": (
                    "Do not write a full deterministic report. Ask for rectification "
                    "or write only a clearly labeled low-confidence/D1-only note."
                ),
                "claimStyle": (
                    "State confidence, cite stable evidence, and downgrade or omit "
                    "unstable divisional/timing claims."
                ),
            },
        }

    def _time_window(
        self, payload: dict[str, Any], precision: str, time_source: str
    ) -> dict[str, Any]:
        base = datetime(
            int(payload["year"]),
            int(payload["month"]),
            int(payload["day"]),
            int(payload["hour"]),
            int(payload["minute"]),
        )
        if precision == "unknown":
            start = base.replace(hour=0, minute=0)
            end = base.replace(hour=23, minute=59)
            return {
                "start": start.strftime("%Y-%m-%d %H:%M"),
                "end": end.strftime("%Y-%m-%d %H:%M"),
                "endExclusive": (end + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"),
                "radiusMinutes": 720,
                "scanMode": "continuous_minute_grid",
                "resolutionMinutes": 1,
                "sourcePolicy": self._time_source_policy(time_source),
            }
        radius = self._time_radius_minutes(precision, time_source)
        return {
            "start": (base - timedelta(minutes=radius)).strftime("%Y-%m-%d %H:%M"),
            "end": (base + timedelta(minutes=radius)).strftime("%Y-%m-%d %H:%M"),
            "endExclusive": (base + timedelta(minutes=radius + 1)).strftime("%Y-%m-%d %H:%M"),
            "radiusMinutes": radius,
            "scanMode": "continuous_minute_grid",
            "resolutionMinutes": 1,
            "sourcePolicy": self._time_source_policy(time_source),
        }

    def _time_scan_variants(
        self,
        calculate_full_chart: Any,
        base_chart: dict[str, Any],
        base_signature: dict[str, Any],
        payload: dict[str, Any],
        precision: str,
        time_source: str,
        *,
        calculate_signature: Any | None = None,
    ) -> list[dict[str, Any]]:
        base_dt = datetime(
            int(payload["year"]),
            int(payload["month"]),
            int(payload["day"]),
            int(payload["hour"]),
            int(payload["minute"]),
        )
        if precision == "unknown":
            start = base_dt.replace(hour=0, minute=0)
            end = base_dt.replace(hour=23, minute=59)
        else:
            radius = self._time_radius_minutes(precision, time_source)
            start = base_dt - timedelta(minutes=radius)
            end = base_dt + timedelta(minutes=radius)

        points: list[dict[str, Any]] = []
        sample = start
        while sample <= end:
            try:
                if sample == base_dt:
                    signature = base_signature
                elif calculate_signature is not None:
                    signature = calculate_signature(
                        sample.year,
                        sample.month,
                        sample.day,
                        sample.hour,
                        sample.minute,
                        float(payload["lat"]),
                        float(payload["lon"]),
                        str(payload["timezone"]),
                    )
                    signature["currentDasha"] = base_signature.get("currentDasha")
                else:
                    chart = calculate_full_chart(
                        sample.year,
                        sample.month,
                        sample.day,
                        sample.hour,
                        sample.minute,
                        float(payload["lat"]),
                        float(payload["lon"]),
                        str(payload["timezone"]),
                    )
                    signature = self._chart_signature(chart)
                points.append(
                    {
                        "moment": sample,
                        "signature": signature,
                    }
                )
            except Exception as exc:
                points.append(
                    {
                        "moment": sample,
                        "error": str(exc),
                    }
                )
            sample += timedelta(minutes=1)
        return self._coalesce_time_points(points, base_dt, base_signature)

    @staticmethod
    def _time_radius_minutes(precision: str, time_source: str) -> int:
        if precision == "unknown":
            return 720
        precision_radius = {"exact": 2, "approximate": 15, "part_of_day": 120}.get(precision, 15)
        source_radius = TIME_SOURCE_MIN_RADIUS_MINUTES.get(time_source.strip().lower(), 0)
        return max(precision_radius, source_radius)

    @staticmethod
    def _time_source_policy(time_source: str) -> dict[str, Any]:
        source_radius = TIME_SOURCE_MIN_RADIUS_MINUTES.get(time_source.strip().lower())
        return {
            "source": time_source,
            "minimumRadiusMinutes": source_radius,
            "directionalBiasApplied": False,
            "status": "recognized_product_prior" if source_radius is not None else "unclassified",
            "limitation": (
                "The source adjusts only the minimum uncertainty radius; it never shifts the "
                "reported time earlier or later without user evidence."
            ),
        }

    def _coalesce_time_points(
        self,
        points: list[dict[str, Any]],
        base_dt: datetime,
        base_signature: dict[str, Any],
    ) -> list[dict[str, Any]]:
        variants: list[dict[str, Any]] = []
        run: list[dict[str, Any]] = []

        def flush() -> None:
            if not run:
                return
            first = run[0]
            last = run[-1]
            signature = first.get("signature")
            start = first["moment"]
            end = last["moment"] + timedelta(minutes=1)
            representative = start + (end - start) / 2
            representative = representative.replace(second=0, microsecond=0)
            if not isinstance(signature, dict):
                variants.append(
                    {
                        "label": start.strftime("%H:%M"),
                        "interval": {
                            "start": start.strftime("%Y-%m-%d %H:%M"),
                            "end": end.strftime("%Y-%m-%d %H:%M"),
                        },
                        "representativeDatetime": representative.strftime("%Y-%m-%d %H:%M"),
                        "error": str(first.get("error") or "signature calculation failed"),
                    }
                )
                return
            variants.append(
                {
                    "label": (
                        f"{start.strftime('%H:%M')}-{(end - timedelta(minutes=1)).strftime('%H:%M')}"
                    ),
                    "interval": {
                        "start": start.strftime("%Y-%m-%d %H:%M"),
                        "end": end.strftime("%Y-%m-%d %H:%M"),
                    },
                    "representativeDatetime": representative.strftime("%Y-%m-%d %H:%M"),
                    "isBase": start <= base_dt < end,
                    "changed": self._signature_changes(base_signature, signature),
                    "signature": signature,
                }
            )

        for point in points:
            if not run:
                run.append(point)
                continue
            previous = run[-1]
            previous_signature = previous.get("signature")
            current_signature = point.get("signature")
            same = (
                isinstance(previous_signature, dict)
                and isinstance(current_signature, dict)
                and self._signature_fingerprint(previous_signature)
                == self._signature_fingerprint(current_signature)
            ) or (
                not isinstance(previous_signature, dict)
                and not isinstance(current_signature, dict)
                and previous.get("error") == point.get("error")
            )
            if same:
                run.append(point)
                continue
            flush()
            run = [point]
        flush()
        return variants

    def _place_scan_variants(
        self,
        calculate_full_chart: Any,
        base_chart: dict[str, Any],
        base_signature: dict[str, Any],
        payload: dict[str, Any],
        place: ResolvedPlace,
    ) -> list[dict[str, Any]]:
        radius_km = float(place.radius_km)
        if not self._place_rectification_allowed(place) or radius_km < 1.0:
            return [
                {
                    "label": "base",
                    "radiusKm": round(radius_km, 3),
                    "rectificationAllowed": self._place_rectification_allowed(place),
                    "rectificationPolicy": self._place_rectification_policy(place),
                    "changed": [],
                    "signature": base_signature,
                }
            ]
        scan_radius = min(radius_km, 30.0)
        lat = float(payload["lat"])
        lon = float(payload["lon"])
        delta_lat = scan_radius / 111.0
        cos_lat = max(abs(math.cos(math.radians(lat))), 0.2)
        delta_lon = scan_radius / (111.0 * cos_lat)
        samples = [
            ("north", lat + delta_lat, lon),
            ("south", lat - delta_lat, lon),
            ("east", lat, lon + delta_lon),
            ("west", lat, lon - delta_lon),
        ]
        variants = [
            {
                "label": "base",
                "radiusKm": round(radius_km, 3),
                "changed": [],
                "signature": base_signature,
            }
        ]
        for label, sample_lat, sample_lon in samples:
            try:
                chart = calculate_full_chart(
                    int(payload["year"]),
                    int(payload["month"]),
                    int(payload["day"]),
                    int(payload["hour"]),
                    int(payload["minute"]),
                    sample_lat,
                    sample_lon,
                    str(payload["timezone"]),
                )
                signature = self._chart_signature(chart)
                variants.append(
                    {
                        "label": label,
                        "radiusKm": round(scan_radius, 3),
                        "coordinates": {
                            "lat": round(sample_lat, 6),
                            "lon": round(sample_lon, 6),
                        },
                        "changed": self._signature_changes(base_signature, signature),
                        "signature": signature,
                    }
                )
            except Exception as exc:
                variants.append(
                    {
                        "label": label,
                        "radiusKm": round(scan_radius, 3),
                        "error": str(exc),
                    }
                )
        return variants

    def _chart_signature(self, chart: dict[str, Any]) -> dict[str, Any]:
        moon = chart.get("planets", {}).get("Moon", {})
        moon_nakshatra = moon.get("nakshatra") or {}
        signature = {
            "lagnaSign": chart.get("lagna", {}).get("sign"),
            "lagnaDegree": round(float(chart.get("lagna", {}).get("degree", 0)), 4),
            "moonSign": moon.get("sign"),
            "moonNakshatra": moon_nakshatra.get("name"),
            "moonPada": moon_nakshatra.get("pada"),
            "currentDasha": self._current_dasha_label(chart),
            "planetSignIndices": {
                name: int(position.get("sign_idx", 0))
                for name, position in (chart.get("planets") or {}).items()
                if isinstance(position, dict) and position.get("sign_idx") is not None
            },
        }
        for factor in DIVISIONAL_FACTORS:
            if factor == 1:
                continue
            signature[self._divisional_field(factor)] = self._divisional_lagna_sign(
                chart,
                factor,
            )
        return signature

    @staticmethod
    def _divisional_lagna_sign(chart: dict[str, Any], factor: int) -> str | None:
        chart_key = f"D{factor}"
        raw_chart = (chart.get("divisional_charts") or {}).get(chart_key)
        if isinstance(raw_chart, dict) and "error" not in raw_chart:
            lagna = raw_chart.get("Lagna")
            if isinstance(lagna, dict):
                sign = lagna.get("sign")
                return str(sign) if sign else None
            if isinstance(lagna, tuple) and lagna:
                return str(lagna[0]) if lagna[0] else None
        return None

    @staticmethod
    def _signature_changes(
        base_signature: dict[str, Any], variant_signature: dict[str, Any]
    ) -> list[str]:
        changes = []
        for key, base_value in base_signature.items():
            if key == "lagnaDegree":
                continue
            if variant_signature.get(key) != base_value:
                changes.append(key)
        return changes

    @staticmethod
    def _current_dasha_label(chart: dict[str, Any]) -> str | None:
        for dasha in chart.get("dashas", []):
            if not dasha.get("is_current"):
                continue
            for antardasha in dasha.get("antardashas", []):
                if antardasha.get("is_current"):
                    return f"{dasha.get('planet')}-{antardasha.get('planet')}"
            return str(dasha.get("planet"))
        return None

    def _boundary_flags(self, chart: dict[str, Any]) -> list[dict[str, Any]]:
        flags: list[dict[str, Any]] = []
        lagna_degree = float(chart.get("lagna", {}).get("degree", 0))
        lagna_distance = min(lagna_degree, 30 - lagna_degree)
        if lagna_distance <= 1.0:
            flags.append(
                {
                    "factor": "lagnaSign",
                    "distanceDegrees": round(lagna_distance, 4),
                    "risk": "high" if lagna_distance <= 0.25 else "medium",
                }
            )
        moon = chart.get("planets", {}).get("Moon", {})
        moon_longitude = float(moon.get("longitude", 0))
        nak_unit = 360 / 27
        nak_remainder = moon_longitude % nak_unit
        nak_distance = min(nak_remainder, nak_unit - nak_remainder)
        if nak_distance <= 0.25:
            flags.append(
                {
                    "factor": "moonNakshatra",
                    "distanceDegrees": round(nak_distance, 4),
                    "risk": "medium",
                }
            )
        ayanamsa_check = chart.get("ayanamsa_cross_check") or {}
        if ayanamsa_check and not ayanamsa_check.get("lagnaSignAgrees", True):
            flags.append(
                {
                    "factor": "ayanamsaLagnaSign",
                    "distanceDegrees": round(
                        abs(float(ayanamsa_check.get("diffArcminutes", 0))) / 60, 4
                    ),
                    "risk": "high",
                }
            )
        return flags

    def _scan_summary(
        self,
        precision: str,
        place: ResolvedPlace,
        time_variants: list[dict[str, Any]],
        place_variants: list[dict[str, Any]],
        boundary_flags: list[dict[str, Any]],
    ) -> dict[str, Any]:
        changed = {
            change
            for variant in [*time_variants, *place_variants]
            for change in variant.get("changed", [])
        }
        risk_factors = []
        if precision in {"part_of_day", "unknown"}:
            risk_factors.append(f"time_precision:{precision}")
        elif precision == "approximate":
            risk_factors.append("time_precision:approximate")
        if place.accuracy in {"city", "district"}:
            risk_factors.append(f"place_accuracy:{place.accuracy}")
        if changed:
            risk_factors.append("variant_changes:" + ",".join(sorted(changed)))
        if boundary_flags:
            risk_factors.append(
                "boundary_flags:" + ",".join(str(item["factor"]) for item in boundary_flags)
            )

        blocking_changed = sorted(changed & HIGH_RISK_CHANGED_FIELDS)
        if precision in {"part_of_day", "unknown"} or bool(blocking_changed):
            risk_level = "high"
        elif risk_factors:
            risk_level = "medium"
        else:
            risk_level = "low"

        divisional_confidence = self._divisional_confidence(precision, changed)
        return {
            "riskLevel": risk_level,
            "riskFactors": risk_factors,
            "blockingChangedFields": blocking_changed,
            "changedFields": sorted(changed),
            "divisionalConfidence": divisional_confidence,
            "divisionalSensitivity": self._divisional_sensitivity(divisional_confidence),
            "advancedVargaPolicy": self._advanced_varga_policy(divisional_confidence),
            "recommendedAction": self._recommended_action(
                risk_level,
                place_rectification_allowed=self._place_rectification_allowed(place),
            ),
            "rectificationAxes": self._rectification_axes(place),
            "placeRectificationAllowed": self._place_rectification_allowed(place),
            "placeRectificationPolicy": self._place_rectification_policy(place),
        }

    @staticmethod
    def _divisional_confidence(precision: str, changed: set[str]) -> dict[str, dict[str, Any]]:
        radius_minutes = VedicCalculator._precision_radius_minutes(precision)
        result: dict[str, dict[str, Any]] = {}
        for factor in DIVISIONAL_FACTORS:
            key = VedicCalculator._divisional_key(factor)
            field = VedicCalculator._divisional_field(factor)
            policy = DIVISIONAL_POLICIES[factor]
            interval = round(120 / factor, 3)
            confidence = VedicCalculator._confidence_for_division(
                precision,
                radius_minutes,
                factor,
                field in changed,
            )
            reasons = [
                f"reported time window radius is +/-{radius_minutes}m",
                f"approx average {key} Lagna slice is {interval}m",
            ]
            if field in changed:
                reasons.insert(0, f"{field} changed in sensitivity scan")
            if policy["usageTier"] == "final_confirmation_only":
                reasons.append(
                    "D60 is validation/final confirmation only until birth time is rectified"
                )
            elif policy["usageTier"] == "advanced_validation":
                reasons.append(
                    "advanced varga should corroborate dated events, not drive first-pass claims"
                )

            recommended_use = VedicCalculator._recommended_divisional_use(
                confidence,
                policy["usageTier"],
            )
            result[key] = {
                "division": key,
                "factor": factor,
                "field": field,
                "name": policy["name"],
                "role": policy["role"],
                "usageTier": policy["usageTier"],
                "confidence": confidence,
                "approxLagnaIntervalMinutes": interval,
                "timeWindowRadiusMinutes": radius_minutes,
                "timeSensitive": True,
                "locationSensitive": True,
                "changedInScan": field in changed,
                "recommendedUse": recommended_use,
                "useAsPrimaryEvidence": recommended_use == "primary_or_strong_support",
                "reasons": reasons,
            }
        return result

    @staticmethod
    def _precision_radius_minutes(precision: str) -> int:
        return {"exact": 2, "approximate": 15, "part_of_day": 120, "unknown": 720}.get(
            precision,
            15,
        )

    @staticmethod
    def _confidence_for_division(
        precision: str,
        radius_minutes: int,
        factor: int,
        changed: bool,
    ) -> str:
        if changed or precision == "unknown":
            return "low"
        if factor == 1:
            if precision == "exact":
                return "high"
            if precision in {"approximate", "part_of_day"}:
                return "medium"
            return "low"

        interval = 120 / factor
        ratio = radius_minutes / interval if interval else 999
        if ratio <= 0.25:
            confidence = "high"
        elif ratio <= 1.0:
            confidence = "medium"
        else:
            confidence = "low"

        if precision == "approximate":
            confidence = VedicCalculator._cap_confidence(confidence, "medium")
        elif precision == "part_of_day":
            confidence = VedicCalculator._cap_confidence(confidence, "low")
        return confidence

    @staticmethod
    def _cap_confidence(confidence: str, cap: str) -> str:
        if CONFIDENCE_RANK[confidence] <= CONFIDENCE_RANK[cap]:
            return confidence
        return cap

    @staticmethod
    def _recommended_divisional_use(confidence: str, usage_tier: str) -> str:
        if confidence == "low":
            return "rectification_only_or_omit"
        if usage_tier == "final_confirmation_only":
            return "final_confirmation_only"
        if usage_tier == "advanced_validation":
            return "corroboration_only"
        if confidence == "medium":
            return "supporting_only_with_cross_check"
        return "primary_or_strong_support"

    @staticmethod
    def _divisional_sensitivity(
        divisional_confidence: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "division": item.get("division"),
                "field": item.get("field"),
                "factor": item.get("factor"),
                "name": item.get("name"),
                "role": item.get("role"),
                "usageTier": item.get("usageTier"),
                "confidence": item.get("confidence"),
                "approxLagnaIntervalMinutes": item.get("approxLagnaIntervalMinutes"),
                "changedInScan": item.get("changedInScan"),
                "recommendedUse": item.get("recommendedUse"),
                "useAsPrimaryEvidence": item.get("useAsPrimaryEvidence"),
            }
            for item in divisional_confidence.values()
            if isinstance(item, dict)
        ]

    @staticmethod
    def _advanced_varga_policy(divisional_confidence: dict[str, dict[str, Any]]) -> dict[str, Any]:
        restricted = [
            key
            for key, item in divisional_confidence.items()
            if isinstance(item, dict) and not item.get("useAsPrimaryEvidence")
        ]
        final_only = [
            key
            for key, item in divisional_confidence.items()
            if isinstance(item, dict) and item.get("recommendedUse") == "final_confirmation_only"
        ]
        return {
            "principle": (
                "Use higher vargas after the birth-time window is narrowed. "
                "Do not let advanced vargas override D1/Dasha/event evidence."
            ),
            "restrictedDivisions": restricted,
            "finalConfirmationOnly": final_only,
            "ifRestricted": (
                "Use only for candidate discrimination or corroboration, and label the "
                "claim as provisional."
            ),
        }

    @staticmethod
    def _recommended_action(risk_level: str, *, place_rectification_allowed: bool) -> str:
        if risk_level == "high":
            if not place_rectification_allowed:
                return "Run prevalidation as time rectification: shrink time candidates before core synthesis; keep detailed place coordinates locked."
            return "Run prevalidation as rectification: shrink time/place candidates before core synthesis."
        if risk_level == "medium":
            if not place_rectification_allowed:
                return "Run targeted prevalidation and avoid deterministic claims from changed or boundary-sensitive factors; do not move the locked place."
            return "Run targeted prevalidation and avoid deterministic claims from changed or boundary-sensitive factors."
        return (
            "Proceed with standard prevalidation; still record user feedback before full synthesis."
        )

    @staticmethod
    def _place_rectification_allowed(place: ResolvedPlace) -> bool:
        return place.accuracy in {"city", "district"}

    def _rectification_axes(self, place: ResolvedPlace) -> list[str]:
        return ["time", "place"] if self._place_rectification_allowed(place) else ["time"]

    def _place_rectification_policy(self, place: ResolvedPlace) -> str:
        if self._place_rectification_allowed(place):
            return "scan_within_reported_radius"
        return "locked_precise_coordinates"

    def _rectification_guardrails(self, place: ResolvedPlace) -> dict[str, str]:
        if self._place_rectification_allowed(place):
            place_rule = (
                "City/district coordinates are approximate; place candidates may vary "
                "only inside the reported radius and must stay consistent with the "
                "user-selected city or district."
            )
            feedback_rule = (
                "If prevalidation misses, shrink time/place candidates before writing "
                "a deterministic report."
            )
        else:
            place_rule = (
                "Detailed place coordinates are locked; do not create place-axis "
                "rectification candidates unless the user corrects the place."
            )
            feedback_rule = (
                "If prevalidation misses, shrink time candidates first. Ask the user "
                "to correct the place only when they explicitly reject the selected POI/address."
            )
        return {
            "time": "Only search inside the reported time window.",
            "place": place_rule,
            "feedback": feedback_rule,
        }

    def _chart_facts(self, chart: dict[str, Any], sav_total: int) -> ChartFacts:
        shadbala_items: list[StrengthFact] = []
        for name, value in chart.get("shadbala", {}).items():
            if isinstance(value, dict) and "total_rupas" in value:
                shadbala_items.append(
                    StrengthFact(
                        planet=name,
                        rupas=round(float(value.get("total_rupas", 0)), 2),
                        strength_pct=round(float(value.get("strength_pct", 0)), 2),
                    )
                )
        shadbala_items.sort(key=lambda item: item.rupas, reverse=True)

        planets: dict[str, PlanetFact] = {}
        for name, value in chart.get("planets", {}).items():
            nakshatra = value.get("nakshatra") or {}
            planets[name] = PlanetFact(
                sign=value.get("sign"),
                house=value.get("house"),
                degree=round(float(value.get("degree", 0)), 2),
                nakshatra=nakshatra.get("name"),
                nakshatra_lord=nakshatra.get("lord"),
                retrograde=bool(value.get("retrograde")),
            )

        lagna = chart.get("lagna") or {}
        lagna_nakshatra = lagna.get("nakshatra") or {}
        return ChartFacts(
            lagna=LagnaFact(
                sign=lagna.get("sign"),
                degree=round(float(lagna.get("degree", 0)), 2),
                nakshatra=lagna_nakshatra.get("name"),
                nakshatra_lord=lagna_nakshatra.get("lord"),
            ),
            moon=planets.get("Moon", PlanetFact()),
            sun=planets.get("Sun", PlanetFact()),
            current_dasha=self._current_dasha(chart),
            sav_total=sav_total,
            strongest_planet=shadbala_items[0] if shadbala_items else None,
            weakest_planet=shadbala_items[-1] if shadbala_items else None,
            karakas=self._karakas(chart),
            planets=planets,
        )

    def _current_dasha(self, chart: dict[str, Any]) -> CurrentDasha:
        for dasha in chart.get("dashas", []):
            if not dasha.get("is_current"):
                continue
            current_ad = None
            for antardasha in dasha.get("antardashas", []):
                if antardasha.get("is_current"):
                    current_ad = antardasha
                    break
            return CurrentDasha(
                mahadasha=dasha.get("planet"),
                mahadasha_start=dasha.get("start"),
                mahadasha_end=dasha.get("end"),
                antardasha=current_ad.get("planet") if current_ad else None,
                antardasha_start=current_ad.get("start") if current_ad else None,
                antardasha_end=current_ad.get("end") if current_ad else None,
            )
        return CurrentDasha()

    def _karakas(self, chart: dict[str, Any]) -> Karakas:
        karakas = chart.get("karakas", {})
        by_role: dict[str, str] = {}
        for item in karakas.get("7k", []):
            if len(item) >= 2:
                by_role[str(item[0])] = str(item[1])
        return Karakas(
            ak=by_role.get("AK"),
            amk=by_role.get("AmK"),
            dk_7k=karakas.get("dk_7k") or by_role.get("DK"),
            dk_8k=karakas.get("dk_8k"),
        )

    def _calculator_payload(
        self,
        intake: BirthInput,
        birth_date: BirthDate,
        birth_time: BirthTime,
        place: ResolvedPlace,
    ) -> dict[str, Any]:
        return {
            "year": birth_date.year,
            "month": birth_date.month,
            "day": birth_date.day,
            "hour": birth_time.hour,
            "minute": birth_time.minute,
            "dob": intake.birth_date,
            "time": birth_time.normalized,
            "place": place.label,
            "lat": place.lat,
            "lon": place.lon,
            "timezone": place.timezone,
            "place_source": place.source,
            "place_accuracy": place.accuracy,
            "place_radius_km": place.radius_km,
            "place_confidence": place.confidence,
            "place_coordinate_system": place.coordinate_system,
            "time_precision": self._precision_label(intake.birth_time_precision),
            "time_source": intake.time_source,
            "life_events": intake.life_events,
            "effective_precision": (
                "±分钟级" if intake.birth_time_precision == "exact" else "按出生时间精度降级解释"
            ),
            "gender": intake.gender,
            "relationship": intake.relationship,
        }

    def _parse_birth_date(self, value: str) -> BirthDate:
        parts = value.split("-")
        if len(parts) != 3:
            raise ValueError("Birth date must be YYYY-MM-DD")
        year, month, day = [int(part) for part in parts]
        if year <= 0 or month < 1 or month > 12 or day < 1 or day > 31:
            raise ValueError("Birth date must be a valid YYYY-MM-DD date")
        return BirthDate(year=year, month=month, day=day)

    def _parse_birth_time(self, value: str, precision: str) -> BirthTime:
        if precision == "unknown" or not value:
            return BirthTime(hour=12, minute=0, normalized="12:00")
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("Birth time must be HH:MM")
        hour, minute = [int(part) for part in parts]
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("Birth time must be a valid HH:MM value")
        return BirthTime(
            hour=hour,
            minute=minute,
            normalized=f"{hour:02d}:{minute:02d}",
        )

    def _precision_label(self, precision: str) -> str:
        if precision == "exact":
            return "精确到分钟"
        if precision == "approximate":
            return "约略时间"
        if precision == "part_of_day":
            return "仅知道时段"
        return "未知出生时间"
