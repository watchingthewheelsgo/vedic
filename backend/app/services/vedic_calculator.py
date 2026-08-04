from __future__ import annotations

import json
import hashlib
import math
import sys
from copy import deepcopy
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytz

from app.calculator.civil_time import AmbiguousCivilTimeError, resolve_civil_time
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
    candidate_event_period_fingerprint,
    parse_life_event_ledger,
    score_candidate_events,
)
from app.services.place_service import PlaceService, ResolvedPlace
from app.settings import Settings
from app.utils.ids import make_id
from app.vedicdust.chart_record_builder import ChartRecordBuildInput, build_chart_record
from app.vedicdust.independent_reference import find_independent_reference
from app.vedicdust.models import TimeRange
from app.vedicdust.profiles import PARASHARI_LAHIRI_PROFILE_ID
from app.vedicdust.varga_policy import (
    SUPPORTED_VARGA_FACTORS,
    VARGA_DOMAIN_POLICY_ID,
    VARGA_DOMAIN_SOURCE_IDS,
    varga_domain_policy,
)


PRECISION_STATUS: dict[str, str] = {
    "exact": "passed",
    "approximate": "degraded",
    "part_of_day": "degraded",
    "unknown": "limited",
}

DIVISIONAL_FACTORS = list(SUPPORTED_VARGA_FACTORS)

# D2-D30 can distinguish rectification candidates. D60 is deliberately excluded:
# its minute-level volatility is evidence for uncertainty, not an initial split key.
DIVISIONAL_FINGERPRINT_FACTORS = [2, 3, 4, 5, 7, 9, 10, 12, 16, 20, 24, 27, 30]
CALCULATION_VERSION = f"vedicdust-{PARASHARI_LAHIRI_PROFILE_ID}"
SUB_MINUTE_BOUNDARY_TARGET_SECONDS = 5
HIGH_RISK_CHANGED_FIELDS = {
    "lagnaSign",
    "d1Structure",
    "moonNakshatra",
    "currentDasha",
    "d7Lagna",
    "d9Lagna",
    "d10Lagna",
}
CONTINUOUS_DEGREE_THRESHOLDS = {
    "lagnaDegree": 1.0,
    "planetLongitude": 0.25,
    "vargaLagnaDegree": 1.0,
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
    second: int
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
        timing_window_override: TimeRange | None = None,
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
        if timing_window_override is not None:
            payload["timing_window_override"] = timing_window_override.model_dump(
                mode="json",
            )
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
                second=int(payload.get("second") or 0),
                lat=float(payload["lat"]),
                lon=float(payload["lon"]),
                tz_str=str(payload["timezone"]),
                transit_as_of=calculated_at,
                utc_offset_seconds=payload.get("utc_offset_seconds"),
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
                reference_moment=calculated_at,
            )
            sensitivity_scan["timingBoundarySampling"] = self._timing_boundary_sampling(
                payload,
                intake.birth_time_precision,
                intake.time_source,
                chart,
                calculated_at,
            )
            timing_sampling = sensitivity_scan["timingBoundarySampling"]
            if timing_sampling["status"] != "complete":
                sensitivity_scan["summary"].setdefault("timingBoundaryErrors", []).extend(
                    timing_sampling.get("errors") or ["timing boundary sampling incomplete"]
                )
                readiness = sensitivity_scan["reportReadiness"]
                readiness.setdefault("blockingFactors", []).append(
                    "timing_boundary_sampling_incomplete"
                )
                readiness["timingEvidenceAllowed"] = False
                readiness["llmContract"].setdefault("mustNotUseAsPrimaryEvidence", []).append(
                    "Vimshottari boundary dates"
                )
            else:
                sensitivity_scan["reportReadiness"]["timingEvidenceAllowed"] = True
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
                    reader_relationship=intake.reader_relationship,
                    consultation_topics=(
                        (intake.reading_focus.strip(),) if intake.reading_focus.strip() else ()
                    ),
                    place_label=place.label,
                    latitude=float(place.lat),
                    longitude=float(place.lon),
                    timezone_id=place.timezone,
                    utc_offset_seconds=(
                        int(payload["utc_offset_seconds"])
                        if payload.get("utc_offset_seconds") is not None
                        else None
                    ),
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
                    independent_reference=find_independent_reference(
                        self._independent_reference_registry_path(),
                        local_date=str(payload["dob"]),
                        local_time=str(payload["time"]),
                        latitude=float(place.lat),
                        longitude=float(place.lon),
                        timezone_id=place.timezone,
                        utc_offset_seconds=(
                            int(payload["utc_offset_seconds"])
                            if payload.get("utc_offset_seconds") is not None
                            else None
                        ),
                    ),
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

    def _timing_boundary_sampling(
        self,
        payload: dict[str, Any],
        precision: str,
        time_source: str,
        base_chart: dict[str, Any],
        calculation_as_of: datetime,
    ) -> dict[str, Any]:
        """Recalculate Vimshottari at the declared birth-window endpoints.

        This is an uncertainty envelope, not a claim that endpoint sampling proves
        monotonicity between the samples. The coverage label is deliberately explicit.
        """

        from app.calculator.dasha_pyjhora import calculate_dasha_fixed

        window = self._time_window(payload, precision, time_source)
        base_moment = self._resolved_payload_moment(payload)
        candidates = [
            ("window-start", str(window["startUtc"])),
            ("reported", base_moment.astimezone(pytz.utc).isoformat()),
            ("window-end", str(window["endUtc"])),
        ]
        moments: dict[str, dict[str, Any]] = {}
        for role, raw_moment in candidates:
            instant = datetime.fromisoformat(raw_moment)
            if instant.tzinfo is None or instant.utcoffset() is None:
                raise ValueError("timing boundary sample moment must include a UTC offset")
            key = instant.astimezone(pytz.utc).isoformat()
            moments.setdefault(key, {"instant": instant, "roles": []})["roles"].append(role)

        timezone_id = str(payload["timezone"])
        timezone_value = pytz.timezone(timezone_id)
        base_utc = base_moment.astimezone(pytz.utc)
        samples: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for index, item in enumerate(moments.values()):
            instant = item["instant"].astimezone(pytz.utc)
            local_moment = instant.astimezone(timezone_value)
            try:
                if instant == base_utc:
                    dashas = base_chart.get("dashas") or []
                else:
                    dashas = calculate_dasha_fixed(
                        local_moment.year,
                        local_moment.month,
                        local_moment.day,
                        local_moment.hour,
                        local_moment.minute,
                        float(payload["lat"]),
                        float(payload["lon"]),
                        float(local_moment.utcoffset().total_seconds()) / 3600.0,
                        second=local_moment.second,
                        as_of=calculation_as_of,
                        timezone_id=timezone_id,
                    )
                samples.append(
                    {
                        "sampleId": f"timing-boundary-{index + 1}",
                        "roles": item["roles"],
                        "birthMomentUtc": instant.isoformat(),
                        "dashas": dashas,
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "birthMomentUtc": instant.isoformat(),
                        "error": str(exc),
                    }
                )

        status = (
            "complete"
            if not errors and len(samples) == len(moments)
            else ("partial" if samples else "failed")
        )
        return {
            "schemaVersion": "vedicdust-timing-boundary-sampling/1.0.0",
            "methodId": "vedicdust-vimshottari-boundary-envelope/1.0.0",
            "status": status,
            "coverage": "reported_window_endpoints",
            "successfulSampleCount": len(samples),
            "requestedSampleCount": len(moments),
            "samples": samples,
            "errors": errors,
            "limitation": (
                "The envelope covers the declared window endpoints and canonical input. "
                "It does not assert unobserved monotonic behavior between samples."
            ),
        }

    def _independent_reference_registry_path(self) -> Path | None:
        resolver = getattr(self.settings, "independent_reference_registry_path", None)
        if callable(resolver):
            resolved = resolver()
            return resolved if isinstance(resolved, Path) else None
        return None

    def _birth_input_context(
        self,
        payload: dict[str, Any],
        intake: BirthInput,
        place: ResolvedPlace,
    ) -> dict[str, Any]:
        time_window = self._time_window(payload, intake.birth_time_precision, intake.time_source)
        place_radius = round(float(place.radius_km), 3)
        place_rectification_allowed = self._place_rectification_allowed(place)
        raw_semantic_evidence = str(payload.get("life_event_facts") or "").strip()
        try:
            parsed_semantic_evidence = (
                json.loads(raw_semantic_evidence) if raw_semantic_evidence else []
            )
        except json.JSONDecodeError:
            parsed_semantic_evidence = []
        semantic_evidence = (
            [item for item in parsed_semantic_evidence if isinstance(item, dict)]
            if isinstance(parsed_semantic_evidence, list)
            else []
        )
        life_event_ledger = parse_life_event_ledger(
            str(payload.get("life_events") or ""),
            semantic_evidence=semantic_evidence,
        )
        return {
            "schemaVersion": "birth-input-context/v1",
            "time": {
                "reported": payload["time"],
                "date": payload["dob"],
                "precision": intake.birth_time_precision,
                "source": intake.time_source,
                "normalized": payload["time"],
                "timezone": place.timezone,
                "utcOffsetSeconds": payload.get("utc_offset_seconds"),
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
            "readingFocus": intake.reading_focus,
            "subject": {
                "readerRelationship": intake.reader_relationship,
                "consultationTopics": (
                    [intake.reading_focus.strip()] if intake.reading_focus.strip() else []
                ),
            },
            "lifeEvents": life_event_ledger,
            "lifeEventSemantics": semantic_evidence,
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
        reference_moment: datetime | None = None,
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
            life_event_ledger=life_event_ledger or {},
            reference_moment=reference_moment,
        )
        place_variants = self._place_scan_variants(
            calculate_full_chart,
            base_chart,
            base_signature,
            payload,
            place,
        )
        place_rectification_allowed = self._place_rectification_allowed(place)
        joint_variants = self._joint_time_place_variants(
            calculate_full_chart,
            calculate_signature,
            base_chart,
            base_signature,
            payload,
            intake.birth_time_precision,
            intake.time_source,
            place_variants if place_rectification_allowed else [],
            life_event_ledger=life_event_ledger or {},
            reference_moment=reference_moment,
        )
        boundary_flags = self._boundary_flags(base_chart)
        summary = self._scan_summary(
            intake.birth_time_precision,
            place,
            [*time_variants, *joint_variants],
            place_variants,
            boundary_flags,
        )
        candidate_groups = self._candidate_groups(
            base_signature,
            [*time_variants, *joint_variants],
            (place_variants if place_rectification_allowed and not joint_variants else []),
        )
        self._score_candidate_groups(
            candidate_groups,
            life_event_ledger or {},
            payload,
        )
        scoring_errors = [
            {
                "candidateId": str(candidate.get("candidateId") or ""),
                "error": str(candidate.get("scoringError")),
            }
            for candidate in candidate_groups
            if candidate.get("scoringError")
        ]
        if scoring_errors:
            summary["candidateScoringErrors"] = scoring_errors
            summary["riskLevel"] = "high"
            summary.setdefault("riskFactors", []).append(
                f"candidate_scoring_errors:{len(scoring_errors)}"
            )
        self._assign_equivalence_classes(candidate_groups)
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
            "jointTimePlaceVariants": joint_variants,
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
                    "representativeUtc": variant.get("representativeUtc"),
                    "utcOffsetSeconds": variant.get("utcOffsetSeconds"),
                    "civilTimeFold": bool(variant.get("civilTimeFold")),
                    "boundaryResolutionSeconds": int(
                        variant.get("boundaryResolutionSeconds") or 60
                    ),
                    "leftBoundaryUncertainty": variant.get("leftBoundaryUncertainty"),
                    "eventPeriodBoundaryChecked": bool(variant.get("eventPeriodBoundaryChecked")),
                    "eventPeriodStableWithinInterval": bool(
                        variant.get("eventPeriodStableWithinInterval")
                    ),
                    "members": [
                        {
                            "axis": "time",
                            "label": variant.get("label"),
                            "datetime": variant.get("representativeDatetime"),
                            "utcDatetime": variant.get("representativeUtc"),
                            "utcOffsetSeconds": variant.get("utcOffsetSeconds"),
                            "interval": interval,
                        },
                        *(
                            [variant["placeMember"]]
                            if isinstance(variant.get("placeMember"), dict)
                            else []
                        ),
                    ],
                    "changedFromBase": self._signature_changes(base_signature, signature),
                    "isBase": bool(variant.get("isBase"))
                    and not isinstance(variant.get("placeMember"), dict),
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
                    "timezone": variant.get("timezone"),
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
            int(payload.get("second") or 0),
        )
        for candidate in candidates:
            if isinstance(candidate.get("interval"), dict) and not candidate.get(
                "eventPeriodBoundaryChecked"
            ):
                candidate.update(
                    {
                        "evidenceScores": [],
                        "aggregateScore": None,
                        "holdoutScore": None,
                        "scoringError": (
                            "Dated-event period evidence was not checked across the full "
                            "candidate interval."
                        ),
                    }
                )
                continue
            raw_representative = candidate.get("representativeDatetime")
            raw_representative_utc = candidate.get("representativeUtc")
            try:
                representative = (
                    datetime.fromisoformat(str(raw_representative_utc)).astimezone(
                        pytz.timezone(str(payload["timezone"]))
                    )
                    if raw_representative_utc
                    else (
                        datetime.strptime(str(raw_representative), "%Y-%m-%d %H:%M")
                        if raw_representative
                        else base_moment
                    )
                )
                candidate_latitude = float(payload["lat"])
                candidate_longitude = float(payload["lon"])
                candidate_timezone = str(payload["timezone"])
                for member in candidate.get("members") or []:
                    if not isinstance(member, dict) or member.get("axis") != "place":
                        continue
                    coordinates = member.get("coordinates")
                    if isinstance(coordinates, dict):
                        candidate_latitude = float(coordinates.get("lat", candidate_latitude))
                        candidate_longitude = float(coordinates.get("lon", candidate_longitude))
                    if member.get("timezone"):
                        candidate_timezone = str(member["timezone"])
                    break
                candidate["scoringLocation"] = {
                    "latitude": candidate_latitude,
                    "longitude": candidate_longitude,
                    "timezoneId": candidate_timezone,
                }
                result = score_candidate_events(
                    candidate_id=str(candidate.get("candidateId") or "candidate"),
                    signature=(
                        candidate.get("signature")
                        if isinstance(candidate.get("signature"), dict)
                        else {}
                    ),
                    representative_moment=representative,
                    latitude=candidate_latitude,
                    longitude=candidate_longitude,
                    timezone_id=candidate_timezone,
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

    @classmethod
    def _assign_equivalence_classes(cls, candidates: list[dict[str, Any]]) -> None:
        """Group hypotheses that expose the same chart and event evidence.

        Candidate rows remain separate because they retain distinct time/place
        hypotheses. The class is used only to avoid redundant questions and to
        propagate feedback across astrologically equivalent rows.
        """

        classes: dict[str, list[str]] = {}
        for candidate in candidates:
            evidence = [
                {
                    "eventId": score.get("eventId"),
                    "role": score.get("role"),
                    "score": score.get("score"),
                    "supportScore": score.get("supportScore"),
                    "contradictionScore": score.get("contradictionScore"),
                    "observations": [
                        {
                            "component": observation.get("component"),
                            "outcome": observation.get("outcome"),
                            "weight": observation.get("weight"),
                            "details": observation.get("details"),
                        }
                        for observation in score.get("observations") or []
                        if isinstance(observation, dict)
                    ],
                }
                for score in candidate.get("evidenceScores") or []
                if isinstance(score, dict) and score.get("role") == "calibration"
            ]
            class_payload = {
                "chartFingerprint": cls._signature_fingerprint(
                    candidate.get("signature")
                    if isinstance(candidate.get("signature"), dict)
                    else {}
                ),
                "eventEvidence": evidence,
            }
            digest = hashlib.sha256(
                json.dumps(class_payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()[:16]
            class_id = f"equivalence.{digest}"
            candidate["equivalenceClassId"] = class_id
            classes.setdefault(class_id, []).append(str(candidate.get("candidateId") or ""))
        for candidate in candidates:
            candidate["equivalentCandidateIds"] = classes.get(
                str(candidate.get("equivalenceClassId") or ""),
                [],
            )

    @staticmethod
    def _signature_fingerprint(signature: dict[str, Any]) -> str:
        stable_keys = [
            "lagnaSign",
            "moonSign",
            "moonNakshatra",
            "moonPada",
            "currentDasha",
            "moonPhase",
        ]
        values = [str(signature.get(key)) for key in stable_keys]
        for key in (
            "charaKaraka7k",
            "combustionStatus",
            "shadbalaClassification",
            "digbalaStatus",
            "specialPointSigns",
            "specialLagnaSigns",
        ):
            values.append(
                json.dumps(
                    signature.get(key),
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        d1_structure = signature.get("planetSignIndices")
        values.append(json.dumps(d1_structure, sort_keys=True, separators=(",", ":")))
        varga_structures = signature.get("vargaPlanetSignIndices")
        for factor in DIVISIONAL_FINGERPRINT_FACTORS:
            values.append(str(signature.get(VedicCalculator._divisional_field(factor))))
            structure = (
                varga_structures.get(f"D{factor}") if isinstance(varga_structures, dict) else None
            )
            values.append(json.dumps(structure, sort_keys=True, separators=(",", ":")))
        return "|".join(values)

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
            "lagnaDegree": {
                "domain": "D1 Ascendant degree and degree-sensitive house interpretation",
                "severity": "blocking",
            },
            "d1Structure": {
                "domain": "D1 graha signs and every relationship derived from them",
                "severity": "blocking",
            },
            "moonSign": {
                "domain": "Moon-sign anchors, Sade Sati, and Moon-dependent D1 structure",
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
            "charaKaraka7k": {
                "domain": "7K Chara Karaka role assignments",
                "severity": "high",
            },
            "moonPhase": {
                "domain": "waxing or waning Moon phase",
                "severity": "medium",
            },
            "combustionStatus": {
                "domain": "graha combustion classifications",
                "severity": "high",
            },
            "shadbalaClassification": {
                "domain": "Shadbala interpretive strength bands",
                "severity": "high",
            },
            "digbalaStatus": {
                "domain": "directional-strength classifications",
                "severity": "high",
            },
            "specialPointSigns": {
                "domain": "Arudha and Upapada sign positions",
                "severity": "high",
            },
            "specialLagnaSigns": {
                "domain": "special Lagna sign positions",
                "severity": "high",
            },
        }
        for factor in DIVISIONAL_FACTORS:
            if factor == 1:
                continue
            policy = varga_domain_policy(factor)
            severity = "medium"
            if factor in {7, 9, 10}:
                severity = "high"
            elif factor in {27, 30, 60}:
                severity = "validation-only"
            field_impacts[self._divisional_field(factor)] = {
                "domain": f"{self._divisional_key(factor)} {policy.scope}",
                "severity": severity,
            }
            field_impacts[f"d{factor}Structure"] = {
                "domain": (
                    f"{self._divisional_key(factor)} graha signs and dependent house structure"
                ),
                "severity": severity,
            }
            field_impacts[f"d{factor}LagnaDegree"] = {
                "domain": f"{self._divisional_key(factor)} Ascendant degree sensitivity",
                "severity": severity,
            }

        for field in changed_fields:
            if field.startswith("planetLongitude:"):
                planet = field.split(":", 1)[1] or "planet"
                field_impacts[field] = {
                    "domain": f"{planet} continuous longitude and degree-sensitive aspects",
                    "severity": "high",
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
        stable_bounded_window = (
            candidate_count == 1
            and not summary.get("changedFields")
            and not summary.get("scanErrors")
            and not summary.get("candidateScoringErrors")
        )

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
        elif stable_bounded_window:
            mode = "guarded_after_strong_prevalidation"
            min_hit_rate = 0.9
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
        if summary.get("scanErrors"):
            blockers.append("scan_incomplete:resolve_civil_time_or_place_input")
        if summary.get("candidateScoringErrors"):
            blockers.append("candidate_scoring_incomplete:retry_deterministic_calculation")

        return {
            "mode": mode,
            "scope": scope,
            "prevalidationRequired": True,
            "minimumHitRateForCore": min_hit_rate,
            "coreAllowedWithoutRectification": core_allowed_without_rectification,
            "candidateCount": candidate_count,
            "stableBoundedWindow": stable_bounded_window,
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
        base = self._resolved_payload_moment(payload)
        override = payload.get("timing_window_override")
        if isinstance(override, dict):
            start = datetime.fromisoformat(str(override["start"]))
            end_exclusive = datetime.fromisoformat(str(override["end"]))
            if (
                start.tzinfo is None
                or end_exclusive.tzinfo is None
                or start.utcoffset() is None
                or end_exclusive.utcoffset() is None
            ):
                raise ValueError("rectified timing window override must include UTC offsets")
            if not start <= base < end_exclusive:
                raise ValueError("rectified canonical moment must be inside its selected interval")
            timezone_value = pytz.timezone(str(payload["timezone"]))
            local_start = start.astimezone(timezone_value)
            local_end_exclusive = end_exclusive.astimezone(timezone_value)
            local_end = local_end_exclusive - timedelta(seconds=1)
            return {
                "start": local_start.strftime("%Y-%m-%d %H:%M:%S"),
                "end": local_end.strftime("%Y-%m-%d %H:%M:%S"),
                "endExclusive": local_end_exclusive.strftime("%Y-%m-%d %H:%M:%S"),
                "startUtc": start.astimezone(pytz.utc).isoformat(),
                "endUtc": local_end.astimezone(pytz.utc).isoformat(),
                "endExclusiveUtc": end_exclusive.astimezone(pytz.utc).isoformat(),
                "reportedUtc": base.astimezone(pytz.utc).isoformat(),
                "selectedUtcOffsetSeconds": int(base.utcoffset().total_seconds()),
                "radiusMinutes": round(
                    (end_exclusive - start).total_seconds() / 120.0,
                    3,
                ),
                "scanMode": "selected_rectification_interval",
                "resolutionMinutes": 1,
                "sourcePolicy": {
                    **self._time_source_policy(time_source),
                    "windowOverride": "selected_rectification_candidate",
                },
            }
        if precision == "unknown":
            local_date = base.date()
            start = resolve_civil_time(
                datetime.combine(local_date, datetime.min.time()),
                str(payload["timezone"]),
            )
            next_midnight = resolve_civil_time(
                datetime.combine(local_date + timedelta(days=1), datetime.min.time()),
                str(payload["timezone"]),
            )
            end = self._shift_absolute(next_midnight, -1)
            end_exclusive = next_midnight
            return {
                "start": start.strftime("%Y-%m-%d %H:%M"),
                "end": end.strftime("%Y-%m-%d %H:%M"),
                "endExclusive": end_exclusive.strftime("%Y-%m-%d %H:%M"),
                "startUtc": start.astimezone(pytz.utc).isoformat(),
                "endUtc": end.astimezone(pytz.utc).isoformat(),
                "endExclusiveUtc": end_exclusive.astimezone(pytz.utc).isoformat(),
                "radiusMinutes": 720,
                "scanMode": "continuous_minute_grid",
                "resolutionMinutes": 1,
                "elapsedMinutes": int(
                    (
                        end_exclusive.astimezone(pytz.utc) - start.astimezone(pytz.utc)
                    ).total_seconds()
                    // 60
                ),
                "sourcePolicy": self._time_source_policy(time_source),
            }
        radius = self._time_radius_minutes(precision, time_source)
        start = self._shift_absolute(base, -radius)
        end = self._shift_absolute(base, radius)
        end_exclusive = self._shift_absolute(base, radius + 1)
        return {
            "start": start.strftime("%Y-%m-%d %H:%M"),
            "end": end.strftime("%Y-%m-%d %H:%M"),
            "endExclusive": end_exclusive.strftime("%Y-%m-%d %H:%M"),
            "startUtc": start.astimezone(pytz.utc).isoformat(),
            "endUtc": end.astimezone(pytz.utc).isoformat(),
            "endExclusiveUtc": end_exclusive.astimezone(pytz.utc).isoformat(),
            "reportedUtc": base.astimezone(pytz.utc).isoformat(),
            "selectedUtcOffsetSeconds": int(base.utcoffset().total_seconds()),
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
        life_event_ledger: dict[str, Any] | None = None,
        calculate_event_period_fingerprint: Any | None = candidate_event_period_fingerprint,
        reuse_base_signature_at_reported_time: bool = True,
        reference_moment: datetime | None = None,
    ) -> list[dict[str, Any]]:
        base_dt = self._resolved_payload_moment(payload)
        window = self._time_window(payload, precision, time_source)
        timezone_value = pytz.timezone(str(payload["timezone"]))
        start = datetime.fromisoformat(str(window["startUtc"])).astimezone(timezone_value)
        end = datetime.fromisoformat(str(window["endUtc"])).astimezone(timezone_value)

        points: list[dict[str, Any]] = []
        sample = start
        while sample <= end:
            try:
                if (
                    sample.astimezone(pytz.utc) == base_dt.astimezone(pytz.utc)
                    and reuse_base_signature_at_reported_time
                ):
                    signature = dict(base_signature)
                elif calculate_signature is not None:
                    offset_kwargs = self._ambiguous_offset_kwargs(sample, str(payload["timezone"]))
                    signature = calculate_signature(
                        sample.year,
                        sample.month,
                        sample.day,
                        sample.hour,
                        sample.minute,
                        float(payload["lat"]),
                        float(payload["lon"]),
                        str(payload["timezone"]),
                        second=sample.second,
                        **offset_kwargs,
                    )
                    signature["currentDasha"] = base_signature.get("currentDasha")
                else:
                    offset_kwargs = self._ambiguous_offset_kwargs(sample, str(payload["timezone"]))
                    chart = calculate_full_chart(
                        sample.year,
                        sample.month,
                        sample.day,
                        sample.hour,
                        sample.minute,
                        float(payload["lat"]),
                        float(payload["lon"]),
                        str(payload["timezone"]),
                        second=sample.second,
                        **offset_kwargs,
                    )
                    signature = self._chart_signature(chart)
                event_period_fingerprint = None
                if calculate_event_period_fingerprint is not None and (
                    (life_event_ledger or {}).get("events") or reference_moment is not None
                ):
                    event_period_fingerprint = calculate_event_period_fingerprint(
                        birth_moment=sample,
                        latitude=float(payload["lat"]),
                        longitude=float(payload["lon"]),
                        timezone_id=str(payload["timezone"]),
                        ledger=life_event_ledger or {},
                        reference_moment=reference_moment,
                    )
                    if isinstance(event_period_fingerprint, dict) and event_period_fingerprint.get(
                        "currentDasha"
                    ):
                        signature["currentDasha"] = event_period_fingerprint["currentDasha"]
                points.append(
                    {
                        "moment": sample,
                        "signature": signature,
                        "eventPeriodFingerprint": event_period_fingerprint,
                    }
                )
            except Exception as exc:
                points.append(
                    {
                        "moment": sample,
                        "error": str(exc),
                    }
                )
            sample = self._shift_absolute(sample, 1)
        return self._coalesce_time_points(points, base_dt, base_signature)

    def refine_selected_time_boundary(
        self,
        state: dict[str, Any],
        birth_input_context: dict[str, Any],
        *,
        calculate_signature: Any | None = None,
        target_resolution_seconds: int = SUB_MINUTE_BOUNDARY_TARGET_SECONDS,
    ) -> dict[str, Any]:
        """Refine every minute-grid transition touching the selected interval."""

        selected_id = str(state.get("selectedCandidateId") or "")
        working = self._refine_selected_left_time_boundary(
            state,
            birth_input_context,
            calculate_signature=calculate_signature,
            target_resolution_seconds=target_resolution_seconds,
        )
        results = [{"side": "left", **dict(working.get("boundaryRefinement") or {})}]
        candidates = [
            candidate
            for candidate in working.get("candidates") or []
            if isinstance(candidate, dict)
        ]
        selected = next(
            (
                candidate
                for candidate in candidates
                if str(candidate.get("candidateId") or "") == selected_id
            ),
            None,
        )
        place_context = birth_input_context.get("place")
        if not isinstance(place_context, dict):
            place_context = {}
        coordinates = place_context.get("coordinates")
        if not isinstance(coordinates, dict):
            coordinates = {}
        default_latitude = coordinates.get("lat")
        default_longitude = coordinates.get("lon")
        default_timezone = str(place_context.get("timezone") or "").strip()

        if (
            selected is not None
            and default_latitude is not None
            and default_longitude is not None
            and default_timezone
            and isinstance(selected.get("interval"), dict)
        ):
            selected_place_key = self._candidate_place_key(
                selected,
                default_latitude,
                default_longitude,
                default_timezone,
            )
            selected_end = self._interval_bound(selected["interval"], "end", selected_place_key[2])
            for candidate in candidates:
                uncertainty = candidate.get("leftBoundaryUncertainty")
                if candidate is selected or not isinstance(uncertainty, dict):
                    continue
                candidate_place_key = self._candidate_place_key(
                    candidate,
                    default_latitude,
                    default_longitude,
                    default_timezone,
                )
                if candidate_place_key != selected_place_key:
                    continue
                uncertainty_end = self._interval_bound(uncertainty, "end", candidate_place_key[2])
                if (
                    selected_end is None
                    or uncertainty_end is None
                    or selected_end.astimezone(pytz.utc) != uncertainty_end.astimezone(pytz.utc)
                ):
                    continue
                right_state = deepcopy(working)
                right_state["selectedCandidateId"] = candidate.get("candidateId")
                right_state = self._refine_selected_left_time_boundary(
                    right_state,
                    birth_input_context,
                    calculate_signature=calculate_signature,
                    target_resolution_seconds=target_resolution_seconds,
                )
                right_result = dict(right_state.get("boundaryRefinement") or {})
                results.append({"side": "right", **right_result})
                if right_result.get("status") in {"refined", "already_refined"}:
                    working = right_state
                break

        working["selectedCandidateId"] = selected_id or None
        statuses = {str(result.get("status") or "") for result in results}
        aggregate_status = (
            "refined"
            if "refined" in statuses
            else "already_refined"
            if "already_refined" in statuses
            else "not_applicable"
            if statuses <= {"not_applicable"}
            else "skipped"
        )
        aggregate = {
            "status": aggregate_status,
            "candidateId": selected_id or None,
            "targetResolutionSeconds": target_resolution_seconds,
            "d60Used": False,
            "boundaries": results,
        }
        working["boundaryRefinement"] = aggregate
        for candidate in working.get("candidates") or []:
            if (
                isinstance(candidate, dict)
                and str(candidate.get("candidateId") or "") == selected_id
            ):
                candidate["boundaryRefinement"] = aggregate
                break
        return working

    def _refine_selected_left_time_boundary(
        self,
        state: dict[str, Any],
        birth_input_context: dict[str, Any],
        *,
        calculate_signature: Any | None = None,
        target_resolution_seconds: int = SUB_MINUTE_BOUNDARY_TARGET_SECONDS,
    ) -> dict[str, Any]:
        """Narrow one selected chart-transition band without claiming an exact second.

        The minute scan remains the exhaustive search. This method runs only after
        evidence has selected a candidate and only inside its typed left-boundary
        uncertainty interval. D60 and Dasha-only changes are intentionally excluded.
        """

        next_state = deepcopy(state)
        selected_id = str(next_state.get("selectedCandidateId") or "")
        candidates = [
            candidate
            for candidate in next_state.get("candidates") or []
            if isinstance(candidate, dict)
        ]
        selected = next(
            (
                candidate
                for candidate in candidates
                if str(candidate.get("candidateId") or "") == selected_id
            ),
            None,
        )

        def finish(status: str, reason: str, **details: Any) -> dict[str, Any]:
            result = {
                "status": status,
                "candidateId": selected_id or None,
                "reason": reason,
                "targetResolutionSeconds": target_resolution_seconds,
                "d60Used": False,
                **details,
            }
            next_state["boundaryRefinement"] = result
            if selected is not None:
                selected["boundaryRefinement"] = result
            return next_state

        if selected is None:
            return finish("skipped", "No selected candidate is available for refinement.")
        uncertainty = selected.get("leftBoundaryUncertainty")
        if not isinstance(uncertainty, dict):
            return finish("not_applicable", "The selected interval has no left transition band.")
        current_resolution = int(selected.get("boundaryResolutionSeconds") or 60)
        if current_resolution <= target_resolution_seconds:
            return finish(
                "already_refined",
                "The selected transition band already meets the target resolution.",
                resolutionSeconds=current_resolution,
            )

        place_context = birth_input_context.get("place")
        if not isinstance(place_context, dict):
            place_context = {}
        coordinates = place_context.get("coordinates")
        if not isinstance(coordinates, dict):
            coordinates = {}
        latitude = coordinates.get("lat")
        longitude = coordinates.get("lon")
        timezone_id = str(place_context.get("timezone") or "").strip()
        for member in selected.get("members") or []:
            if not isinstance(member, dict) or member.get("axis") != "place":
                continue
            member_coordinates = member.get("coordinates")
            if isinstance(member_coordinates, dict):
                latitude = member_coordinates.get("lat", latitude)
                longitude = member_coordinates.get("lon", longitude)
            timezone_id = str(member.get("timezone") or timezone_id).strip()
            break
        if latitude is None or longitude is None or not timezone_id:
            return finish(
                "skipped",
                "Coordinates or timezone are unavailable for deterministic refinement.",
            )

        try:
            lower = self._interval_bound(uncertainty, "start", timezone_id)
            upper = self._interval_bound(uncertainty, "end", timezone_id)
        except (TypeError, ValueError, AmbiguousCivilTimeError) as exc:
            return finish("skipped", f"The transition band could not be resolved: {exc}")
        if lower is None or upper is None or lower >= upper:
            return finish("skipped", "The transition band is missing valid ordered bounds.")
        initial_span = int(
            round((upper.astimezone(pytz.utc) - lower.astimezone(pytz.utc)).total_seconds())
        )
        if initial_span > 60 or initial_span <= target_resolution_seconds:
            return finish(
                "skipped",
                "Only a single minute-grid transition band can be refined.",
                observedSpanSeconds=initial_span,
            )

        if calculate_signature is None:
            from app.calculator.engine import calculate_rectification_signature

            calculate_signature = calculate_rectification_signature

        factors = [1, *DIVISIONAL_FINGERPRINT_FACTORS]

        def signature_at(value: datetime) -> dict[str, Any]:
            local_value = value.astimezone(pytz.timezone(timezone_id))
            offset_kwargs = self._ambiguous_offset_kwargs(local_value, timezone_id)
            signature = calculate_signature(
                local_value.year,
                local_value.month,
                local_value.day,
                local_value.hour,
                local_value.minute,
                float(latitude),
                float(longitude),
                timezone_id,
                chart_factors=factors,
                second=local_value.second,
                **offset_kwargs,
            )
            signature["currentDasha"] = None
            return signature

        try:
            before_signature = signature_at(lower)
            after_signature = signature_at(upper)
            target_signature = dict(selected.get("signature") or {})
            target_signature["currentDasha"] = None
            before_fingerprint = self._signature_fingerprint(before_signature)
            after_fingerprint = self._signature_fingerprint(after_signature)
            target_fingerprint = self._signature_fingerprint(target_signature)
            if after_fingerprint != target_fingerprint:
                return finish(
                    "skipped",
                    "The selected candidate does not match the deterministic upper-bound chart.",
                )
            if before_fingerprint == after_fingerprint:
                return finish(
                    "not_applicable",
                    "The minute boundary is Dasha-only or otherwise absent from stable chart structure.",
                )

            while (
                upper.astimezone(pytz.utc) - lower.astimezone(pytz.utc)
            ).total_seconds() > target_resolution_seconds:
                span_seconds = int(
                    (upper.astimezone(pytz.utc) - lower.astimezone(pytz.utc)).total_seconds()
                )
                midpoint_utc = lower.astimezone(pytz.utc) + timedelta(
                    seconds=max(1, span_seconds // 2)
                )
                midpoint = midpoint_utc.astimezone(lower.tzinfo)
                midpoint_signature = signature_at(midpoint)
                midpoint_fingerprint = self._signature_fingerprint(midpoint_signature)
                if midpoint_fingerprint == before_fingerprint:
                    lower = midpoint
                elif midpoint_fingerprint == after_fingerprint:
                    upper = midpoint
                else:
                    return finish(
                        "skipped",
                        "A third chart fingerprint exists inside the minute; preserve the original band.",
                    )
        except Exception as exc:
            return finish("skipped", f"Deterministic boundary refinement failed: {exc}")

        refined_uncertainty = self._interval_payload(lower, upper)
        refined_resolution = max(
            1,
            int(
                math.ceil((upper.astimezone(pytz.utc) - lower.astimezone(pytz.utc)).total_seconds())
            ),
        )
        selected["leftBoundaryUncertainty"] = refined_uncertainty
        selected["boundaryResolutionSeconds"] = refined_resolution
        selected_interval = selected.get("interval")
        if isinstance(selected_interval, dict):
            selected_end = self._interval_bound(selected_interval, "end", timezone_id)
            if selected_end is not None:
                selected["interval"] = self._interval_payload(lower, selected_end)
        for member in selected.get("members") or []:
            if not isinstance(member, dict) or member.get("axis") != "time":
                continue
            member_interval = member.get("interval")
            if isinstance(member_interval, dict):
                member_end = self._interval_bound(member_interval, "end", timezone_id)
                if member_end is not None:
                    member["interval"] = self._interval_payload(lower, member_end)

        selected_place_key = self._candidate_place_key(selected, latitude, longitude, timezone_id)
        original_upper_utc = self._interval_bound(uncertainty, "end", timezone_id)
        for candidate in candidates:
            if candidate is selected or not isinstance(candidate.get("interval"), dict):
                continue
            if (
                self._candidate_place_key(candidate, latitude, longitude, timezone_id)
                != selected_place_key
            ):
                continue
            candidate_signature = dict(candidate.get("signature") or {})
            candidate_signature["currentDasha"] = None
            if self._signature_fingerprint(candidate_signature) != before_fingerprint:
                continue
            candidate_end = self._interval_bound(candidate["interval"], "end", timezone_id)
            if (
                candidate_end is None
                or original_upper_utc is None
                or candidate_end.astimezone(pytz.utc) != original_upper_utc.astimezone(pytz.utc)
            ):
                continue
            candidate_start = self._interval_bound(candidate["interval"], "start", timezone_id)
            if candidate_start is not None:
                candidate["interval"] = self._interval_payload(candidate_start, upper)

        return finish(
            "refined",
            "The selected chart-transition band was narrowed without choosing an exact second.",
            originalResolutionSeconds=current_resolution,
            resolutionSeconds=refined_resolution,
            uncertainty=refined_uncertainty,
            changedFields=self._signature_changes(before_signature, after_signature),
        )

    def _joint_time_place_variants(
        self,
        calculate_full_chart: Any,
        calculate_signature: Any | None,
        base_chart: dict[str, Any],
        base_signature: dict[str, Any],
        payload: dict[str, Any],
        precision: str,
        time_source: str,
        place_variants: list[dict[str, Any]],
        *,
        life_event_ledger: dict[str, Any] | None = None,
        reference_moment: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Scan the reported time window at every admissible place hypothesis.

        Independent time and place scans cannot reveal a boundary caused by both
        axes moving together. The production fast-signature provider makes this
        bounded Cartesian scan cheap enough for city/district uncertainty.
        """

        if calculate_signature is None:
            return []
        variants: list[dict[str, Any]] = []
        for place_variant in place_variants:
            coordinates = place_variant.get("coordinates")
            if not isinstance(coordinates, dict):
                continue
            latitude = coordinates.get("lat")
            longitude = coordinates.get("lon")
            if latitude is None or longitude is None:
                continue
            timezone_id = str(place_variant.get("timezone") or payload["timezone"])
            variant_payload = {
                **payload,
                "lat": float(latitude),
                "lon": float(longitude),
                "timezone": timezone_id,
                "utc_offset_seconds": (
                    payload.get("utc_offset_seconds")
                    if timezone_id == str(payload["timezone"])
                    else None
                ),
            }
            place_member = {
                "axis": "place",
                "label": place_variant.get("label"),
                "coordinates": {
                    "lat": float(latitude),
                    "lon": float(longitude),
                },
                "timezone": timezone_id,
                "radiusKm": place_variant.get("radiusKm"),
            }
            scanned = self._time_scan_variants(
                calculate_full_chart,
                base_chart,
                base_signature,
                variant_payload,
                precision,
                time_source,
                calculate_signature=calculate_signature,
                life_event_ledger=life_event_ledger or {},
                reuse_base_signature_at_reported_time=False,
                reference_moment=reference_moment,
            )
            for time_variant in scanned:
                time_variant["isBase"] = False
                time_variant["placeMember"] = place_member
                time_variant["label"] = (
                    f"{place_variant.get('label') or 'place'} · "
                    f"{time_variant.get('label') or 'time'}"
                )
                variants.append(time_variant)
        return variants

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

    @staticmethod
    def _resolved_payload_moment(payload: dict[str, Any]) -> datetime:
        return resolve_civil_time(
            datetime(
                int(payload["year"]),
                int(payload["month"]),
                int(payload["day"]),
                int(payload["hour"]),
                int(payload["minute"]),
                int(payload.get("second") or 0),
            ),
            str(payload["timezone"]),
            utc_offset_seconds=(
                int(payload["utc_offset_seconds"])
                if payload.get("utc_offset_seconds") is not None
                else None
            ),
        )

    @staticmethod
    def _shift_absolute(value: datetime, minutes: int) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value + timedelta(minutes=minutes)
        return (value.astimezone(pytz.utc) + timedelta(minutes=minutes)).astimezone(value.tzinfo)

    @staticmethod
    def _is_aware(value: datetime) -> bool:
        return value.tzinfo is not None and value.utcoffset() is not None

    @classmethod
    def _interval_payload(cls, start: datetime, end: datetime) -> dict[str, str]:
        include_seconds = any(value.second or value.microsecond for value in (start, end))
        local_format = "%Y-%m-%d %H:%M:%S" if include_seconds else "%Y-%m-%d %H:%M"
        payload = {
            "start": start.strftime(local_format),
            "end": end.strftime(local_format),
        }
        if cls._is_aware(start) and cls._is_aware(end):
            payload.update(
                {
                    "startUtc": start.astimezone(pytz.utc).isoformat(),
                    "endUtc": end.astimezone(pytz.utc).isoformat(),
                }
            )
        return payload

    @staticmethod
    def _interval_bound(interval: dict[str, Any], key: str, timezone_id: str) -> datetime | None:
        utc_value = interval.get(f"{key}Utc")
        if utc_value:
            parsed = datetime.fromisoformat(str(utc_value))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError(f"{key}Utc must include an offset")
            return parsed.astimezone(pytz.timezone(timezone_id))
        local_value = interval.get(key)
        if not local_value:
            return None
        parsed = datetime.fromisoformat(str(local_value).replace(" ", "T"))
        if parsed.tzinfo is not None and parsed.utcoffset() is not None:
            return parsed.astimezone(pytz.timezone(timezone_id))
        return resolve_civil_time(parsed, timezone_id)

    @staticmethod
    def _candidate_place_key(
        candidate: dict[str, Any],
        default_latitude: object,
        default_longitude: object,
        default_timezone: str,
    ) -> tuple[float, float, str]:
        latitude = float(default_latitude)
        longitude = float(default_longitude)
        timezone_id = default_timezone
        for member in candidate.get("members") or []:
            if not isinstance(member, dict) or member.get("axis") != "place":
                continue
            coordinates = member.get("coordinates")
            if isinstance(coordinates, dict):
                latitude = float(coordinates.get("lat", latitude))
                longitude = float(coordinates.get("lon", longitude))
            timezone_id = str(member.get("timezone") or timezone_id)
            break
        return (round(latitude, 6), round(longitude, 6), timezone_id)

    @classmethod
    def _representative_metadata(cls, value: datetime) -> dict[str, Any]:
        if not cls._is_aware(value):
            return {}
        timezone_id = getattr(value.tzinfo, "zone", None)
        civil_time_fold = False
        if timezone_id:
            try:
                resolve_civil_time(value.replace(tzinfo=None), str(timezone_id))
            except AmbiguousCivilTimeError:
                civil_time_fold = True
        return {
            "representativeUtc": value.astimezone(pytz.utc).isoformat(),
            "utcOffsetSeconds": int(value.utcoffset().total_seconds()),
            "civilTimeFold": civil_time_fold,
        }

    @staticmethod
    def _ambiguous_offset_kwargs(value: datetime, timezone_id: str) -> dict[str, int]:
        local_value = value.astimezone(pytz.timezone(timezone_id))
        naive_value = local_value.replace(tzinfo=None)
        try:
            resolve_civil_time(naive_value, timezone_id)
        except AmbiguousCivilTimeError:
            return {"utc_offset_seconds": int(local_value.utcoffset().total_seconds())}
        return {}

    def _coalesce_time_points(
        self,
        points: list[dict[str, Any]],
        base_dt: datetime,
        base_signature: dict[str, Any],
    ) -> list[dict[str, Any]]:
        variants: list[dict[str, Any]] = []
        run: list[dict[str, Any]] = []
        run_has_left_boundary = False

        def flush() -> None:
            if not run:
                return
            first = run[0]
            last = run[-1]
            signature = first.get("signature")
            sampled_start = first["moment"]
            start = (
                self._shift_absolute(sampled_start, -1) if run_has_left_boundary else sampled_start
            )
            sampled_end = self._shift_absolute(last["moment"], 1)
            end = sampled_end
            if self._is_aware(sampled_start) and self._is_aware(sampled_end):
                representative_utc = (
                    sampled_start.astimezone(pytz.utc)
                    + (sampled_end.astimezone(pytz.utc) - sampled_start.astimezone(pytz.utc)) / 2
                )
                representative = representative_utc.astimezone(sampled_start.tzinfo).replace(
                    second=0, microsecond=0
                )
            else:
                representative = (sampled_start + (sampled_end - sampled_start) / 2).replace(
                    second=0, microsecond=0
                )
            boundary_metadata = (
                {
                    "boundaryResolutionSeconds": 60,
                    "leftBoundaryUncertainty": self._interval_payload(start, sampled_start),
                }
                if run_has_left_boundary
                else {"boundaryResolutionSeconds": 60}
            )
            if not isinstance(signature, dict):
                variants.append(
                    {
                        "label": sampled_start.strftime("%H:%M"),
                        "interval": self._interval_payload(start, end),
                        "representativeDatetime": representative.strftime("%Y-%m-%d %H:%M"),
                        **self._representative_metadata(representative),
                        "error": str(first.get("error") or "signature calculation failed"),
                        **boundary_metadata,
                    }
                )
                return
            internal_changed_fields = sorted(
                {
                    change
                    for point in run[1:]
                    if isinstance(point.get("signature"), dict)
                    for change in self._signature_changes(signature, point["signature"])
                }
            )
            changed_fields = sorted(
                set(self._signature_changes(base_signature, signature))
                | set(internal_changed_fields)
            )
            variants.append(
                {
                    "label": (
                        f"{sampled_start.strftime('%H:%M')}-"
                        f"{self._shift_absolute(sampled_end, -1).strftime('%H:%M')}"
                    ),
                    "interval": self._interval_payload(start, end),
                    "representativeDatetime": representative.strftime("%Y-%m-%d %H:%M"),
                    **self._representative_metadata(representative),
                    "isBase": (
                        sampled_start.astimezone(pytz.utc)
                        <= base_dt.astimezone(pytz.utc)
                        < sampled_end.astimezone(pytz.utc)
                        if self._is_aware(sampled_start) and self._is_aware(base_dt)
                        else sampled_start <= base_dt < sampled_end
                    ),
                    "eventPeriodBoundaryChecked": first.get("eventPeriodFingerprint") is not None,
                    "eventPeriodStableWithinInterval": True,
                    "internalChangedFields": internal_changed_fields,
                    "changed": changed_fields,
                    "signature": signature,
                    **boundary_metadata,
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
                and previous.get("eventPeriodFingerprint") == point.get("eventPeriodFingerprint")
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
            run_has_left_boundary = True
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
        # radiusKm is the declared uncertainty envelope, not a display hint.
        # Clipping it would exclude valid coordinate hypotheses from rectification.
        scan_radius = radius_km
        lat = float(payload["lat"])
        lon = float(payload["lon"])
        samples = [
            (label, *self._destination_point(lat, lon, scan_radius, bearing))
            for label, bearing in (
                ("north", 0.0),
                ("north-east", 45.0),
                ("east", 90.0),
                ("south-east", 135.0),
                ("south", 180.0),
                ("south-west", 225.0),
                ("west", 270.0),
                ("north-west", 315.0),
            )
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
                sample_timezone = self._timezone_for_scan_point(
                    sample_lat,
                    sample_lon,
                    str(payload["timezone"]),
                )
                offset_kwargs = (
                    {"utc_offset_seconds": int(payload["utc_offset_seconds"])}
                    if sample_timezone == str(payload["timezone"])
                    and payload.get("utc_offset_seconds") is not None
                    else {}
                )
                chart = calculate_full_chart(
                    int(payload["year"]),
                    int(payload["month"]),
                    int(payload["day"]),
                    int(payload["hour"]),
                    int(payload["minute"]),
                    sample_lat,
                    sample_lon,
                    sample_timezone,
                    second=int(payload.get("second") or 0),
                    **offset_kwargs,
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
                        "timezone": sample_timezone,
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

    @staticmethod
    def _destination_point(
        latitude: float,
        longitude: float,
        distance_km: float,
        bearing_degrees: float,
    ) -> tuple[float, float]:
        """Return a spherical WGS84-envelope sample at distance and bearing."""

        angular_distance = distance_km / 6371.0088
        bearing = math.radians(bearing_degrees)
        latitude_radians = math.radians(latitude)
        longitude_radians = math.radians(longitude)
        target_latitude = math.asin(
            math.sin(latitude_radians) * math.cos(angular_distance)
            + math.cos(latitude_radians) * math.sin(angular_distance) * math.cos(bearing)
        )
        target_longitude = longitude_radians + math.atan2(
            math.sin(bearing) * math.sin(angular_distance) * math.cos(latitude_radians),
            math.cos(angular_distance) - math.sin(latitude_radians) * math.sin(target_latitude),
        )
        normalized_longitude = (math.degrees(target_longitude) + 540.0) % 360.0 - 180.0
        return round(math.degrees(target_latitude), 8), round(normalized_longitude, 8)

    @staticmethod
    def _timezone_for_scan_point(latitude: float, longitude: float, fallback: str) -> str:
        try:
            from timezonefinder import TimezoneFinder  # type: ignore

            timezone_id = TimezoneFinder().timezone_at(lat=latitude, lng=longitude)
        except Exception as exc:
            raise RuntimeError(
                f"timezone lookup failed for scan point {latitude:.6f},{longitude:.6f}"
            ) from exc
        if not timezone_id:
            raise RuntimeError(
                f"timezone lookup returned no zone for scan point "
                f"{latitude:.6f},{longitude:.6f}; refusing fallback {fallback}"
            )
        return timezone_id

    def _chart_signature(self, chart: dict[str, Any]) -> dict[str, Any]:
        moon = chart.get("planets", {}).get("Moon", {})
        moon_nakshatra = moon.get("nakshatra") or {}
        signature = {
            "lagnaSign": chart.get("lagna", {}).get("sign"),
            "lagnaDegree": self._finite_degree((chart.get("lagna") or {}).get("degree")),
            "moonSign": moon.get("sign"),
            "moonNakshatra": moon_nakshatra.get("name"),
            "moonPada": moon_nakshatra.get("pada"),
            "currentDasha": self._current_dasha_label(chart),
            "charaKaraka7k": {
                str(row[0]): str(row[1])
                for row in ((chart.get("karakas") or {}).get("7k") or [])
                if isinstance(row, (list, tuple)) and len(row) >= 2
            },
            "moonPhase": bool((chart.get("moon_phase") or {}).get("waxing")),
            "combustionStatus": {
                str(name): bool(value.get("is_combust"))
                for name, value in (chart.get("combustion_statuses") or {}).items()
                if isinstance(value, dict)
            },
            "shadbalaClassification": {
                str(name): str(value.get("classification"))
                for name, value in (chart.get("shadbala") or {}).items()
                if isinstance(value, dict) and value.get("classification")
            },
            "digbalaStatus": {
                str(name): bool(value) for name, value in (chart.get("digbala") or {}).items()
            },
            "specialPointSigns": {
                str(name): int(value["sign_idx"])
                for name, value in (chart.get("special_points") or {}).items()
                if isinstance(value, dict) and value.get("sign_idx") is not None
            },
            "specialLagnaSigns": {
                str(name): int(value["sign_idx"])
                for name, value in (chart.get("special_lagnas") or {}).items()
                if isinstance(value, dict) and value.get("sign_idx") is not None
            },
            "planetSignIndices": {
                name: int(position.get("sign_idx", 0))
                for name, position in (chart.get("planets") or {}).items()
                if isinstance(position, dict) and position.get("sign_idx") is not None
            },
            "planetLongitudes": {
                name: round(float(position["longitude"]), 6)
                for name, position in (chart.get("planets") or {}).items()
                if isinstance(position, dict)
                and position.get("longitude") is not None
                and math.isfinite(float(position["longitude"]))
            },
            "vargaPlanetSignIndices": {},
            "vargaLagnaDegrees": {},
        }
        for factor in DIVISIONAL_FACTORS:
            if factor == 1:
                continue
            signature[self._divisional_field(factor)] = self._divisional_lagna_sign(
                chart,
                factor,
            )
            divisional_degree = self._divisional_lagna_degree(chart, factor)
            if divisional_degree is not None:
                signature["vargaLagnaDegrees"][f"d{factor}LagnaDegree"] = round(
                    divisional_degree,
                    4,
                )
            raw_chart = (chart.get("divisional_charts") or {}).get(f"D{factor}")
            if isinstance(raw_chart, dict) and "error" not in raw_chart:
                signature["vargaPlanetSignIndices"][f"D{factor}"] = {
                    name: int(position["sign_idx"])
                    for name, position in raw_chart.items()
                    if name != "Lagna"
                    and isinstance(position, dict)
                    and position.get("sign_idx") is not None
                }
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
    def _divisional_lagna_degree(chart: dict[str, Any], factor: int) -> float | None:
        raw_chart = (chart.get("divisional_charts") or {}).get(f"D{factor}")
        if not isinstance(raw_chart, dict) or "error" in raw_chart:
            return None
        lagna = raw_chart.get("Lagna")
        value = lagna.get("degree") if isinstance(lagna, dict) else None
        try:
            degree = float(value)
        except (TypeError, ValueError):
            return None
        return degree if math.isfinite(degree) else None

    @staticmethod
    def _signature_changes(
        base_signature: dict[str, Any], variant_signature: dict[str, Any]
    ) -> list[str]:
        changes = []
        for key, base_value in base_signature.items():
            if key in {
                "lagnaDegree",
                "planetLongitudes",
                "planetSignIndices",
                "vargaLagnaDegrees",
                "vargaPlanetSignIndices",
            }:
                continue
            if variant_signature.get(key) != base_value:
                changes.append(key)
        if VedicCalculator._continuous_degree_changed(
            base_signature.get("lagnaDegree"),
            variant_signature.get("lagnaDegree"),
            CONTINUOUS_DEGREE_THRESHOLDS["lagnaDegree"],
        ):
            changes.append("lagnaDegree")
        base_longitudes = base_signature.get("planetLongitudes")
        variant_longitudes = variant_signature.get("planetLongitudes")
        if isinstance(base_longitudes, dict) or isinstance(variant_longitudes, dict):
            base_longitudes = base_longitudes if isinstance(base_longitudes, dict) else {}
            variant_longitudes = variant_longitudes if isinstance(variant_longitudes, dict) else {}
            for planet in sorted(set(base_longitudes) | set(variant_longitudes)):
                if VedicCalculator._continuous_degree_changed(
                    base_longitudes.get(planet),
                    variant_longitudes.get(planet),
                    CONTINUOUS_DEGREE_THRESHOLDS["planetLongitude"],
                ):
                    changes.append(f"planetLongitude:{planet}")
        if variant_signature.get("planetSignIndices") != base_signature.get("planetSignIndices"):
            changes.append("d1Structure")
        base_structures = base_signature.get("vargaPlanetSignIndices")
        variant_structures = variant_signature.get("vargaPlanetSignIndices")
        if isinstance(base_structures, dict) or isinstance(variant_structures, dict):
            base_structures = base_structures if isinstance(base_structures, dict) else {}
            variant_structures = variant_structures if isinstance(variant_structures, dict) else {}
            for varga_id in sorted(set(base_structures) | set(variant_structures)):
                if base_structures.get(varga_id) != variant_structures.get(varga_id):
                    factor = str(varga_id).removeprefix("D")
                    changes.append(f"d{factor}Structure")
        base_varga_degrees = base_signature.get("vargaLagnaDegrees")
        variant_varga_degrees = variant_signature.get("vargaLagnaDegrees")
        if isinstance(base_varga_degrees, dict) or isinstance(variant_varga_degrees, dict):
            base_varga_degrees = base_varga_degrees if isinstance(base_varga_degrees, dict) else {}
            variant_varga_degrees = (
                variant_varga_degrees if isinstance(variant_varga_degrees, dict) else {}
            )
            for field in sorted(set(base_varga_degrees) | set(variant_varga_degrees)):
                if VedicCalculator._continuous_degree_changed(
                    base_varga_degrees.get(field),
                    variant_varga_degrees.get(field),
                    CONTINUOUS_DEGREE_THRESHOLDS["vargaLagnaDegree"],
                ):
                    changes.append(field)
        return changes

    @staticmethod
    def _finite_degree(value: Any) -> float | None:
        try:
            degree = float(value)
        except (TypeError, ValueError):
            return None
        return round(degree, 4) if math.isfinite(degree) else None

    @staticmethod
    def _continuous_degree_changed(base: Any, variant: Any, threshold: float) -> bool:
        """Treat missing continuous data as a change, never as a stable value."""

        base_value = VedicCalculator._finite_degree(base)
        variant_value = VedicCalculator._finite_degree(variant)
        if base_value is None or variant_value is None:
            return base_value != variant_value
        return VedicCalculator._degree_delta(base_value, variant_value) >= threshold

    @staticmethod
    def _degree_delta(base: Any, variant: Any) -> float:
        try:
            base_value = float(base)
            variant_value = float(variant)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(base_value) or not math.isfinite(variant_value):
            return 0.0
        return abs((variant_value - base_value + 180.0) % 360.0 - 180.0)

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
        scan_errors = [
            {
                "label": variant.get("label"),
                "interval": variant.get("interval"),
                "error": str(variant.get("error")),
            }
            for variant in [*time_variants, *place_variants]
            if variant.get("error")
        ]
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
        if scan_errors:
            risk_factors.append(f"scan_errors:{len(scan_errors)}")

        # Planet longitudes move continuously even when no discrete chart boundary
        # changes. Surface those movements for sensitivity reporting, but do not
        # turn every ordinary minute-to-minute ephemeris delta into a rectification
        # blocker. Missing/invalid values are still represented as changes and are
        # rejected by the deterministic position-integrity checks.
        blocking_changed = sorted(changed & HIGH_RISK_CHANGED_FIELDS)
        unresolved_place = place.accuracy in {"city", "district"}
        if (
            precision in {"part_of_day", "unknown"}
            or blocking_changed
            or scan_errors
            or unresolved_place
        ):
            risk_level = "high"
        elif risk_factors:
            risk_level = "medium"
        else:
            risk_level = "low"

        divisional_confidence = self._divisional_confidence(precision, changed)
        return {
            "riskLevel": risk_level,
            "riskFactors": risk_factors,
            "scanErrors": scan_errors,
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
            policy = varga_domain_policy(factor)
            interval = round(120 / factor, 3)
            structure_field = f"d{factor}Structure"
            degree_field = "lagnaDegree" if factor == 1 else f"d{factor}LagnaDegree"
            division_changed = (
                field in changed or structure_field in changed or degree_field in changed
            )
            confidence = VedicCalculator._confidence_for_division(
                precision,
                radius_minutes,
                factor,
                division_changed,
            )
            reasons = [
                f"reported time window radius is +/-{radius_minutes}m",
                f"approx average {key} Lagna slice is {interval}m",
            ]
            if division_changed:
                changed_parts = [
                    item for item in (field, degree_field, structure_field) if item in changed
                ]
                reasons.insert(0, f"{', '.join(changed_parts)} changed in sensitivity scan")
            if policy.usage_tier == "final_confirmation_only":
                reasons.append(
                    "D60 is validation/final confirmation only until birth time is rectified"
                )
            elif policy.usage_tier == "advanced_validation":
                reasons.append(
                    "advanced varga should corroborate dated events, not drive first-pass claims"
                )

            recommended_use = VedicCalculator._recommended_divisional_use(
                confidence,
                policy.usage_tier,
            )
            result[key] = {
                "division": key,
                "factor": factor,
                "field": field,
                "name": policy.name,
                "role": policy.scope,
                "usageTier": policy.usage_tier,
                "policyId": VARGA_DOMAIN_POLICY_ID,
                "sourceIds": list(VARGA_DOMAIN_SOURCE_IDS),
                "confidence": confidence,
                "approxLagnaIntervalMinutes": interval,
                "timeWindowRadiusMinutes": radius_minutes,
                "timeSensitive": True,
                "locationSensitive": True,
                "changedInScan": division_changed,
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
                "policyId": item.get("policyId"),
                "sourceIds": item.get("sourceIds"),
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
            "policyId": VARGA_DOMAIN_POLICY_ID,
            "sourceIds": list(VARGA_DOMAIN_SOURCE_IDS),
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
                mahadasha_start=dasha.get("start_exact") or dasha.get("start"),
                mahadasha_end=dasha.get("end_exact") or dasha.get("end"),
                antardasha=current_ad.get("planet") if current_ad else None,
                antardasha_start=(current_ad.get("start_exact") or current_ad.get("start"))
                if current_ad
                else None,
                antardasha_end=(current_ad.get("end_exact") or current_ad.get("end"))
                if current_ad
                else None,
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
            "second": birth_time.second,
            "dob": intake.birth_date,
            "time": birth_time.normalized,
            "place": place.label,
            "lat": place.lat,
            "lon": place.lon,
            "timezone": place.timezone,
            "utc_offset_seconds": intake.utc_offset_seconds,
            "place_source": place.source,
            "place_accuracy": place.accuracy,
            "place_radius_km": place.radius_km,
            "place_confidence": place.confidence,
            "place_coordinate_system": place.coordinate_system,
            "time_precision": self._precision_label(intake.birth_time_precision),
            "time_source": intake.time_source,
            "reading_focus": intake.reading_focus,
            "life_events": intake.life_events,
            "life_event_facts": intake.life_event_facts,
            "effective_precision": (
                "±分钟级" if intake.birth_time_precision == "exact" else "按出生时间精度降级解释"
            ),
            "gender": intake.gender,
            "relationship": intake.relationship,
            "reader_relationship": intake.reader_relationship,
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
            return BirthTime(hour=12, minute=0, second=0, normalized="12:00")
        parts = value.split(":")
        if len(parts) not in {2, 3}:
            raise ValueError("Birth time must be HH:MM or HH:MM:SS")
        hour, minute = [int(part) for part in parts[:2]]
        second = int(parts[2]) if len(parts) == 3 else 0
        if hour < 0 or hour > 23 or minute < 0 or minute > 59 or second < 0 or second > 59:
            raise ValueError("Birth time must be a valid HH:MM or HH:MM:SS value")
        return BirthTime(
            hour=hour,
            minute=minute,
            second=second,
            normalized=(
                f"{hour:02d}:{minute:02d}:{second:02d}"
                if len(parts) == 3
                else f"{hour:02d}:{minute:02d}"
            ),
        )

    def _precision_label(self, precision: str) -> str:
        if precision == "exact":
            return "精确到分钟"
        if precision == "approximate":
            return "约略时间"
        if precision == "part_of_day":
            return "仅知道时段"
        return "未知出生时间"
