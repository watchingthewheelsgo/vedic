from __future__ import annotations

import json
import math
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timedelta
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
from app.services.place_service import PlaceService, ResolvedPlace
from app.settings import Settings
from app.utils.ids import make_id


PRECISION_STATUS: dict[str, str] = {
    "exact": "passed",
    "approximate": "degraded",
    "part_of_day": "degraded",
    "unknown": "limited",
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


class VedicCalculator:
    """Adapter over the backend-owned Vedic calculation engine."""

    def __init__(self, settings: Settings, place_service: PlaceService) -> None:
        self.settings = settings
        self.place_service = place_service

    def calculate(self, intake: BirthInput) -> CalculationSnapshot:
        birth_date = self._parse_birth_date(intake.birth_date)
        birth_time = self._parse_birth_time(intake.birth_time, intake.birth_time_precision)
        place = self.place_service.resolve(intake.birth_place)
        payload = self._calculator_payload(intake, birth_date, birth_time, place)
        (
            structured_data,
            structured_data_json,
            birth_input_context_json,
            sensitivity_scan_json,
            facts,
        ) = self._run_engine(payload, intake, place)

        return CalculationSnapshot(
            snapshot_id=make_id("calc"),
            engine="real_vedic",
            calculation_version="vedic-calculator-pyjhora-0.5",
            ayanamsa="True Chitrapaksha",
            house_system="whole-sign",
            ephemeris_version="Swiss Ephemeris via pysweph + PyJHora",
            timezone_source=place.timezone,
            geo_source=place.source,
            input_precision=intake.birth_time_precision,
            validation_status=PRECISION_STATUS[intake.birth_time_precision],
            structured_data=structured_data,
            structured_data_json=structured_data_json,
            birth_input_context_json=birth_input_context_json,
            sensitivity_scan_json=sensitivity_scan_json,
            facts=facts,
        )

    def _run_engine(
        self, payload: dict[str, Any], intake: BirthInput, place: ResolvedPlace
    ) -> tuple[str, str, str, str, ChartFacts]:
        with redirect_stdout(sys.stderr):
            from app.calculator.engine import SIGNS, calculate_full_chart
            from app.calculator.formatter import format_structured_data
            from app.calculator.structured_schema import build_structured_schema
            from app.calculator.transit import calc_transit

            chart = calculate_full_chart(
                year=int(payload["year"]),
                month=int(payload["month"]),
                day=int(payload["day"]),
                hour=int(payload["hour"]),
                minute=int(payload["minute"]),
                lat=float(payload["lat"]),
                lon=float(payload["lon"]),
                tz_str=str(payload["timezone"]),
            )
            input_context = self._birth_input_context(payload, intake, place)
            sensitivity_scan = self._sensitivity_scan(
                calculate_full_chart,
                chart,
                payload,
                intake,
                place,
            )
            transit = calc_transit(
                chart["lagna"]["sign_idx"],
                chart["planets"]["Moon"]["sign_idx"],
                str(payload["timezone"]),
            )
            meta = {
                "dob": payload["dob"],
                "time": payload["time"],
                "place": payload["place"],
                "lat": payload["lat"],
                "lon": payload["lon"],
                "timezone": payload["timezone"],
                "time_precision": payload["time_precision"],
                "time_source": payload.get("time_source", "user-input"),
                "effective_precision": payload.get("effective_precision", "birth-time-tiered"),
            }
            user_info = {
                "gender": payload.get("gender", "[not-collected]"),
                "relationship": payload.get("relationship", "[not-collected]"),
            }
            structured_data = format_structured_data(
                chart,
                transit,
                meta,
                user_info,
                input_context=input_context,
                sensitivity_scan=sensitivity_scan,
            )
            structured_payload = build_structured_schema(
                chart,
                transit,
                meta,
                user_info,
                input_context=input_context,
                sensitivity_scan=sensitivity_scan,
            )
            structured_data_json = (
                json.dumps(structured_payload, ensure_ascii=False, indent=2) + "\n"
            )
            birth_input_context_json = (
                json.dumps(input_context, ensure_ascii=False, indent=2) + "\n"
            )
            sensitivity_scan_json = (
                json.dumps(sensitivity_scan, ensure_ascii=False, indent=2) + "\n"
            )
            sav_total = sum(chart["sav"].get(sign, 0) for sign in SIGNS)
            if sav_total != 337:
                raise RuntimeError(f"SAV validation failed: {sav_total} != 337")
            facts = self._chart_facts(chart, sav_total)

        return (
            structured_data,
            structured_data_json,
            birth_input_context_json,
            sensitivity_scan_json,
            facts,
        )

    def _birth_input_context(
        self,
        payload: dict[str, Any],
        intake: BirthInput,
        place: ResolvedPlace,
    ) -> dict[str, Any]:
        time_window = self._time_window(payload, intake.birth_time_precision)
        place_radius = round(float(place.radius_km), 3)
        place_rectification_allowed = self._place_rectification_allowed(place)
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
    ) -> dict[str, Any]:
        base_signature = self._chart_signature(base_chart)
        time_variants = self._time_scan_variants(
            calculate_full_chart,
            base_chart,
            base_signature,
            payload,
            intake.birth_time_precision,
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
        grouped: dict[str, dict[str, Any]] = {}
        for axis, variants in [("time", time_variants), ("place", place_variants)]:
            for variant in variants:
                signature = variant.get("signature")
                if not isinstance(signature, dict):
                    continue
                fingerprint = self._signature_fingerprint(signature)
                item = grouped.setdefault(
                    fingerprint,
                    {
                        "candidateId": "",
                        "signature": signature,
                        "members": [],
                        "changedFromBase": self._signature_changes(base_signature, signature),
                        "isBase": fingerprint == self._signature_fingerprint(base_signature),
                    },
                )
                item["members"].append(
                    {
                        "axis": axis,
                        "label": variant.get("label"),
                        "datetime": variant.get("datetime"),
                        "coordinates": variant.get("coordinates"),
                        "radiusKm": variant.get("radiusKm"),
                    }
                )
        sorted_items = sorted(
            grouped.values(),
            key=lambda item: (
                0 if item.get("isBase") else 1,
                len(item.get("changedFromBase", [])),
                self._signature_fingerprint(item.get("signature", {})),
            ),
        )
        for index, item in enumerate(sorted_items):
            item["candidateId"] = chr(ord("A") + index)
        return sorted_items

    @staticmethod
    def _signature_fingerprint(signature: dict[str, Any]) -> str:
        stable_keys = [
            "lagnaSign",
            "moonSign",
            "moonNakshatra",
            "moonPada",
            "d9Lagna",
            "d10Lagna",
            "d4Lagna",
            "d5Lagna",
            "currentDasha",
        ]
        return "|".join(str(signature.get(key)) for key in stable_keys)

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
            "d9Lagna": {
                "domain": "D9 relationship, inner maturation, promise refinement",
                "severity": "high",
            },
            "d10Lagna": {
                "domain": "D10 career environment and public action",
                "severity": "high",
            },
            "d4Lagna": {
                "domain": "D4 property, home, comfort context",
                "severity": "medium",
            },
            "d5Lagna": {
                "domain": "D5 creativity, authority, recognition context",
                "severity": "medium",
            },
        }
        stable_fields = []
        unstable_fields = []
        for field, impact in field_impacts.items():
            item = {"field": field, **impact}
            if field in changed_fields:
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
            "llmRestrictedEvidence": [item["field"] for item in unstable_fields]
            + low_confidence_divisions,
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
                    "birth_input_context.json",
                    "sensitivity_scan.json",
                    "prevalidation_result.json",
                    "structured_data.md",
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

    def _time_window(self, payload: dict[str, Any], precision: str) -> dict[str, Any]:
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
                "radiusMinutes": 720,
                "scanMode": "full_day_samples",
            }
        radius = {"exact": 2, "approximate": 15, "part_of_day": 120}.get(precision, 15)
        return {
            "start": (base - timedelta(minutes=radius)).strftime("%Y-%m-%d %H:%M"),
            "end": (base + timedelta(minutes=radius)).strftime("%Y-%m-%d %H:%M"),
            "radiusMinutes": radius,
            "scanMode": "offset_samples",
        }

    def _time_scan_variants(
        self,
        calculate_full_chart: Any,
        base_chart: dict[str, Any],
        base_signature: dict[str, Any],
        payload: dict[str, Any],
        precision: str,
    ) -> list[dict[str, Any]]:
        base_dt = datetime(
            int(payload["year"]),
            int(payload["month"]),
            int(payload["day"]),
            int(payload["hour"]),
            int(payload["minute"]),
        )
        if precision == "unknown":
            samples = [
                ("00:00", base_dt.replace(hour=0, minute=0)),
                ("06:00", base_dt.replace(hour=6, minute=0)),
                ("12:00", base_dt.replace(hour=12, minute=0)),
                ("18:00", base_dt.replace(hour=18, minute=0)),
                ("23:59", base_dt.replace(hour=23, minute=59)),
            ]
        else:
            offsets = {
                "exact": [-2, 0, 2],
                "approximate": [-15, -5, 0, 5, 15],
                "part_of_day": [-120, -60, 0, 60, 120],
            }.get(precision, [-15, 0, 15])
            samples = [
                (f"{offset:+d}m" if offset else "base", base_dt + timedelta(minutes=offset))
                for offset in offsets
            ]
        variants = []
        for label, sample in samples:
            try:
                chart = (
                    base_chart
                    if sample == base_dt
                    else calculate_full_chart(
                        sample.year,
                        sample.month,
                        sample.day,
                        sample.hour,
                        sample.minute,
                        float(payload["lat"]),
                        float(payload["lon"]),
                        str(payload["timezone"]),
                    )
                )
                signature = self._chart_signature(chart)
                variants.append(
                    {
                        "label": label,
                        "datetime": sample.strftime("%Y-%m-%d %H:%M"),
                        "changed": self._signature_changes(base_signature, signature),
                        "signature": signature,
                    }
                )
            except Exception as exc:
                variants.append(
                    {
                        "label": label,
                        "datetime": sample.strftime("%Y-%m-%d %H:%M"),
                        "error": str(exc),
                    }
                )
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
        }
        for key in ["d9", "d10", "d4", "d5"]:
            lagna = chart.get(key, {}).get("Lagna")
            if isinstance(lagna, tuple):
                signature[f"{key}Lagna"] = lagna[0]
            elif isinstance(lagna, dict):
                signature[f"{key}Lagna"] = lagna.get("sign")
            else:
                signature[f"{key}Lagna"] = None
        return signature

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

        if (
            precision in {"part_of_day", "unknown"}
            or "lagnaSign" in changed
            or "d9Lagna" in changed
            or "d10Lagna" in changed
            or "currentDasha" in changed
        ):
            risk_level = "high"
        elif risk_factors:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "riskLevel": risk_level,
            "riskFactors": risk_factors,
            "changedFields": sorted(changed),
            "divisionalConfidence": self._divisional_confidence(precision, changed),
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
        def confidence_for(field: str, base: str) -> dict[str, Any]:
            confidence = base
            reasons = []
            if field in changed:
                confidence = "low"
                reasons.append(f"{field} changed in sensitivity scan")
            return {"confidence": confidence, "reasons": reasons}

        if precision == "unknown":
            base = {"D1": "low", "D9": "low", "D10": "low", "D4": "low", "D5": "low"}
        elif precision == "part_of_day":
            base = {"D1": "medium", "D9": "low", "D10": "low", "D4": "low", "D5": "low"}
        elif precision == "approximate":
            base = {"D1": "medium", "D9": "medium", "D10": "medium", "D4": "medium", "D5": "medium"}
        else:
            base = {"D1": "high", "D9": "high", "D10": "high", "D4": "high", "D5": "high"}
        return {
            "D1": confidence_for("lagnaSign", base["D1"]),
            "D9": confidence_for("d9Lagna", base["D9"]),
            "D10": confidence_for("d10Lagna", base["D10"]),
            "D4": confidence_for("d4Lagna", base["D4"]),
            "D5": confidence_for("d5Lagna", base["D5"]),
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
