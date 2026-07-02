from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import Any

from app.schemas import BirthInput, CalculationSnapshot, ChartFacts, CurrentDasha, Karakas, LagnaFact, PlanetFact, StrengthFact
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
        structured_data, structured_data_json, facts = self._run_engine(payload)

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
            facts=facts,
        )

    def _run_engine(self, payload: dict[str, Any]) -> tuple[str, str, ChartFacts]:
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
            structured_data = format_structured_data(chart, transit, meta, user_info)
            structured_payload = build_structured_schema(chart, transit, meta, user_info)
            structured_data_json = json.dumps(structured_payload, ensure_ascii=False, indent=2) + "\n"
            sav_total = sum(chart["sav"].get(sign, 0) for sign in SIGNS)
            if sav_total != 337:
                raise RuntimeError(f"SAV validation failed: {sav_total} != 337")
            facts = self._chart_facts(chart, sav_total)

        return structured_data, structured_data_json, facts

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
            "time_precision": self._precision_label(intake.birth_time_precision),
            "time_source": intake.time_source,
            "effective_precision": (
                "±分钟级"
                if intake.birth_time_precision == "exact"
                else "按出生时间精度降级解释"
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
