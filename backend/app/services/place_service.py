from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.schemas import (
    PlaceOption,
    PlaceSearchResponse,
    PrecisePlaceOption,
    PrecisePlaceSearchResponse,
)
from app.settings import Settings


@dataclass(frozen=True)
class PlaceRecord:
    place_name: str
    alternate_names: str
    state: str
    country: str
    latitude: float
    longitude: float
    timezone_hours: str
    search_text: str


@dataclass(frozen=True)
class ChinaAdministrativeUnitRecord:
    id: str
    code: str
    region_id: str
    name: str
    full_name: str
    pinyin: str
    source_level: int
    unit_type: str
    latitude: float
    longitude: float
    search_text: str


@dataclass(frozen=True)
class ChinaRegionRecord:
    id: str
    code: str
    name: str
    full_name: str
    pinyin: str
    latitude: float
    longitude: float
    search_text: str
    children: tuple[ChinaAdministrativeUnitRecord, ...]


@dataclass(frozen=True)
class PlacePreference:
    query: str
    country: str | None = None
    state: str | None = None


@dataclass(frozen=True)
class ResolvedPlace:
    label: str
    lat: float
    lon: float
    timezone: str
    source: str
    matched: dict[str, str] | None = None
    accuracy: str = "city"
    coordinate_system: str = "WGS84"
    radius_km: float = 25.0
    confidence: str = "medium"
    raw_query: str | None = None


class PlaceService:
    china_country = "China"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @cached_property
    def country_names(self) -> dict[str, dict[str, object]]:
        catalog_path = Path(__file__).resolve().parents[1] / "data" / "country_names.json"
        with catalog_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return {
            str(item["sourceName"]): item
            for item in payload.get("countries", [])
            if isinstance(item, dict) and item.get("sourceName")
        }

    @cached_property
    def geonames_path(self) -> Path:
        return self.settings.geonames_path()

    @cached_property
    def records(self) -> list[PlaceRecord]:
        records: list[PlaceRecord] = []
        with self.geonames_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                place_name = (row.get("place_name") or "").strip()
                country = (row.get("country") or "").strip()
                latitude = row.get("latitude")
                longitude = row.get("longitude")
                if not place_name or not country or not latitude or not longitude:
                    continue
                state = (row.get("state") or country).strip()
                alternate_names = row.get("alternate_names") or ""
                records.append(
                    PlaceRecord(
                        place_name=place_name,
                        alternate_names=alternate_names,
                        state=state,
                        country=country,
                        latitude=float(latitude),
                        longitude=float(longitude),
                        timezone_hours=row.get("timezone_hours") or "0",
                        search_text=self.normalize(
                            "|".join([place_name, alternate_names, state, country])
                        ),
                    )
                )
        return records

    @cached_property
    def china_regions(self) -> tuple[ChinaRegionRecord, ...]:
        catalog_path = Path(__file__).resolve().parents[1] / "data" / "china_location_catalog.json"
        if not catalog_path.exists():
            return ()

        with catalog_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        regions: list[ChinaRegionRecord] = []
        for raw_region in payload.get("regions", []):
            if not isinstance(raw_region, dict):
                continue
            center = raw_region.get("center") or {}
            try:
                latitude = float(center["latitude"])
                longitude = float(center["longitude"])
            except (KeyError, TypeError, ValueError):
                continue

            region_id = str(raw_region.get("id") or "").strip()
            code = str(raw_region.get("code") or "").strip()
            name = str(raw_region.get("name") or "").strip()
            if not region_id or not code or not name:
                continue
            full_name = str(raw_region.get("fullName") or name).strip()
            pinyin = str(raw_region.get("pinyin") or "").strip()
            search_names = raw_region.get("searchNames") or [name, full_name, pinyin]
            children: list[ChinaAdministrativeUnitRecord] = []
            raw_children = raw_region.get("children", raw_region.get("cities", []))
            for raw_child in raw_children:
                if not isinstance(raw_child, dict):
                    continue
                child_center = raw_child.get("center") or {}
                try:
                    child_latitude = float(child_center["latitude"])
                    child_longitude = float(child_center["longitude"])
                except (KeyError, TypeError, ValueError):
                    continue
                child_id = str(raw_child.get("id") or "").strip()
                child_code = str(raw_child.get("code") or "").strip()
                child_name = str(raw_child.get("name") or "").strip()
                if not child_id or not child_code or not child_name:
                    continue
                child_full_name = str(raw_child.get("fullName") or child_name).strip()
                child_pinyin = str(raw_child.get("pinyin") or "").strip()
                child_search_names = raw_child.get("searchNames") or [
                    child_name,
                    child_full_name,
                    child_pinyin,
                ]
                try:
                    source_level = int(raw_child.get("sourceLevel") or 2)
                except (TypeError, ValueError):
                    source_level = 2
                children.append(
                    ChinaAdministrativeUnitRecord(
                        id=child_id,
                        code=child_code,
                        region_id=region_id,
                        name=child_name,
                        full_name=child_full_name,
                        pinyin=child_pinyin,
                        source_level=source_level,
                        unit_type=str(raw_child.get("unitType") or "administrative-unit"),
                        latitude=child_latitude,
                        longitude=child_longitude,
                        search_text=self.normalize("|".join(map(str, child_search_names))),
                    )
                )
            children.sort(key=lambda child: (child.name, child.code))
            regions.append(
                ChinaRegionRecord(
                    id=region_id,
                    code=code,
                    name=name,
                    full_name=full_name,
                    pinyin=pinyin,
                    latitude=latitude,
                    longitude=longitude,
                    search_text=self.normalize("|".join(map(str, search_names))),
                    children=tuple(children),
                )
            )
        regions.sort(key=lambda region: (region.name, region.code))
        return tuple(regions)

    @cached_property
    def china_region_index(self) -> dict[str, ChinaRegionRecord]:
        return {region.id: region for region in self.china_regions}

    @cached_property
    def china_unit_index(self) -> dict[str, ChinaAdministrativeUnitRecord]:
        return {child.id: child for region in self.china_regions for child in region.children}

    @cached_property
    def country_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.records:
            counts[record.country] = counts.get(record.country, 0) + 1
        return counts

    @cached_property
    def timezone_finder(self):
        from timezonefinder import TimezoneFinder  # type: ignore

        return TimezoneFinder()

    @cached_property
    def region_counts(self) -> dict[str, dict[str, int]]:
        counts: dict[str, dict[str, int]] = {}
        for record in self.records:
            regions = counts.setdefault(record.country, {})
            regions[record.state] = regions.get(record.state, 0) + 1
        return counts

    def search(
        self,
        level: str,
        query: str = "",
        country: str | None = None,
        region: str | None = None,
        locale: Literal["zh", "en", "ja"] = "zh",
        limit: int = 30,
    ) -> PlaceSearchResponse:
        limit = max(5, min(500, limit))
        if level == "country":
            return PlaceSearchResponse(options=self._search_countries(query, limit, locale))
        if level == "region":
            return PlaceSearchResponse(options=self._search_regions(country, query, limit, locale))
        if level == "city":
            return PlaceSearchResponse(
                options=self._search_cities(country, region, query, limit, locale)
            )
        return PlaceSearchResponse(options=[])

    def search_precise(
        self,
        query: str = "",
        limit: int = 8,
        city_context: str | None = None,
        agent_options: list[PrecisePlaceOption] | None = None,
        agent_enabled: bool = False,
        agent_attempted: bool = False,
        agent_error: str | None = None,
        agent_search_queries: list[str] | None = None,
    ) -> PrecisePlaceSearchResponse:
        trimmed = query.strip()
        limit = max(1, min(20, limit))
        city_base = self._resolve_city_context(city_context)
        # When the Agent is available it owns all natural-language POI discovery
        # and scope reasoning. The local administrative catalog remains the
        # deterministic city-center fallback, not a competing semantic matcher.
        local_options = [] if agent_enabled else self._search_precise_local(trimmed, limit)
        fallback_enabled = self._amap_enabled() and not agent_enabled
        fallback_sources: list[str] = []
        attempted_sources = [] if agent_enabled else ["local"]
        if agent_attempted:
            attempted_sources.append("agent")
        options = list(local_options)

        if not local_options and fallback_enabled:
            attempted_sources.append("amap")
            amap_options = self._search_precise_amap(
                trimmed,
                limit,
                city_base,
            )
            if amap_options:
                options.extend(amap_options)
                fallback_sources.append("amap")

        if not local_options and len(options) < limit and agent_options:
            options.extend(agent_options[: limit - len(options)])
            fallback_sources.append("agent")

        options = self._dedupe_precise_options(options)
        rejected_count = 0
        if city_base:
            options, rejected_count = self._verify_precise_options(options, city_base)
            if not options and trimmed:
                reason = (
                    "No precise candidate stayed within the selected city scope; "
                    "using the city center until the user provides a better point."
                )
                options = [
                    self._city_fallback_option(
                        city_base,
                        reason=reason,
                    )
                ]

        return PrecisePlaceSearchResponse(
            options=options[:limit],
            localCount=len(local_options),
            fallbackSource="+".join(fallback_sources) if fallback_sources else None,
            fallbackEnabled=fallback_enabled,
            agentFallbackEnabled=agent_enabled,
            agentAttempted=agent_attempted,
            agentError=agent_error,
            agentSearchQueries=agent_search_queries or [],
            verificationBase=city_base.label if city_base else None,
            rejectedCount=rejected_count,
            attemptedSources=attempted_sources,
        )

    def resolve(self, raw_query: str) -> ResolvedPlace:
        trimmed = raw_query.strip()
        inline = self._parse_inline_coordinates(trimmed)
        if inline:
            return inline

        china_place = self._resolve_china_admin(trimmed)
        if china_place:
            return china_place

        preference = self._detect_preference(trimmed)
        ambiguous = self._ambiguous_exact_matches(preference)
        if ambiguous:
            examples = " / ".join(self._birth_place_value(record) for record in ambiguous[:5])
            raise LookupError(
                "出生城市存在多个同名地点，请从国家/省州/城市选择器中点选，"
                f"或输入完整地点。候选示例：{examples}"
            )

        best_score = 0
        best: PlaceRecord | None = None
        for record in self.records:
            score = self._score_record(record, preference)
            if score > best_score:
                best_score = score
                best = record

        if best is None:
            raise LookupError(
                "暂时没有识别这个出生城市。请换成“城市, 国家/省州”的格式；"
                "例如 Shenzhen, China / Atlanta, GA / New York City, United States；"
                "或输入坐标格式：lat=34.0522, lon=-118.2437, tz=America/Los_Angeles"
            )

        timezone = self._timezone_for(best.latitude, best.longitude, best.timezone_hours)
        label = self._birth_place_value(best)
        return ResolvedPlace(
            label=label,
            lat=best.latitude,
            lon=best.longitude,
            timezone=timezone,
            source="geonames-local",
            matched={
                "placeName": best.place_name,
                "alternateNames": best.alternate_names,
                "state": best.state,
                "country": best.country,
            },
            accuracy="city",
            coordinate_system="WGS84",
            radius_km=self._radius_for_accuracy("city"),
            confidence=self._confidence_for_accuracy("city"),
            raw_query=trimmed,
        )

    def _search_countries(
        self, query: str, limit: int, locale: Literal["zh", "en", "ja"]
    ) -> list[PlaceOption]:
        variants = self._query_variants(query)
        items = []
        for country, count in self.country_counts.items():
            label = self._country_display_name(country, locale)
            country_record = self.country_names.get(country, {})
            search_names = country_record.get("searchNames", [country, label])
            search_text = self.normalize("|".join(map(str, search_names)))
            score = self._label_score(label, search_text, variants)
            if score <= 0:
                continue
            items.append((score, count, country, label, search_text))
        items.sort(key=lambda item: (-item[0], -item[1], item[2]))
        return [
            PlaceOption(
                id=f"country:{country}",
                label=label,
                value=country,
                meta=self._place_count_label(count, locale),
                searchText=search_text,
            )
            for _, count, country, label, search_text in items[:limit]
        ]

    def _search_regions(
        self,
        country: str | None,
        query: str,
        limit: int,
        locale: Literal["zh", "en", "ja"],
    ) -> list[PlaceOption]:
        if not country:
            return []
        if self._is_china_country(country):
            return self._search_china_regions(query, limit, locale)
        regions = self.region_counts.get(country, {})
        variants = self._query_variants(query)
        items = []
        for region, count in regions.items():
            score = self._label_score(region, self.normalize(region), variants)
            if score <= 0:
                continue
            items.append((score, count, region))
        items.sort(key=lambda item: (-item[0], -item[1], item[2]))
        return [
            PlaceOption(
                id=f"region:{country}:{region}",
                label=region,
                value=region,
                meta=self._place_count_label(count, locale),
                country=country,
                region=region,
                searchText=self.normalize(region),
            )
            for _, count, region in items[:limit]
        ]

    def _search_cities(
        self,
        country: str | None,
        region: str | None,
        query: str,
        limit: int,
        locale: Literal["zh", "en", "ja"],
    ) -> list[PlaceOption]:
        if self._is_china_country(country):
            return self._search_china_cities(region, query, limit, locale)

        variants = self._query_variants(query)
        preference = self._detect_preference(query)
        # Global single-box typeahead: no country context, search the whole world
        # by name/alias. Require >= 2 chars so a single letter doesn't scan all.
        global_search = not country
        if global_search:
            if not variants or max((len(v) for v in variants), default=0) < 2:
                return []
        elif not region and not variants:
            return []

        items = []
        for record in self.records:
            effective_country = country or preference.country
            effective_region = region or preference.state
            if effective_country and record.country != effective_country:
                continue
            if effective_region and record.state != effective_region:
                continue
            score = self._label_score(record.place_name, record.search_text, variants)
            if score <= 0:
                continue
            items.append((score, record.place_name, record.state, record))
        items.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [
            PlaceOption(
                id=(
                    f"city:{record.country}:{record.state}:{record.place_name}:"
                    f"{record.latitude}:{record.longitude}"
                ),
                label=record.place_name,
                value=self._birth_place_value(record),
                meta=f"{record.state}, {record.country}",
                country=record.country,
                region=record.state,
                birth_place=self._birth_place_value(record),
                latitude=record.latitude,
                longitude=record.longitude,
                timezone=self._timezone_for(
                    record.latitude, record.longitude, record.timezone_hours
                ),
                searchText=record.search_text,
            )
            for _, _, _, record in items[:limit]
        ]

    def _search_china_regions(
        self, query: str, limit: int, locale: Literal["zh", "en", "ja"]
    ) -> list[PlaceOption]:
        variants = self._query_variants(query)
        items = []
        for region in self.china_regions:
            score = self._label_score(region.name, region.search_text, variants)
            if score <= 0:
                continue
            items.append((score, len(region.children), region.name, region))
        items.sort(key=lambda item: (-item[0], -item[1], item[2], item[3].code))
        return [
            PlaceOption(
                id=f"region:{region.id}",
                label=self._china_name(region.pinyin, region.full_name, locale),
                value=region.id,
                meta=None,
                country=self.china_country,
                region=region.id,
                birth_place=region.id,
                latitude=region.latitude,
                longitude=region.longitude,
                timezone=self._timezone_for_china_region(region.code),
                searchText=region.search_text,
            )
            for _, _, _, region in items[:limit]
        ]

    def _search_china_cities(
        self,
        region_id: str | None,
        query: str,
        limit: int,
        locale: Literal["zh", "en", "ja"],
    ) -> list[PlaceOption]:
        if not region_id:
            return []
        region = self.china_region_index.get(region_id)
        if not region:
            return []

        variants = self._query_variants(query)
        items = []
        for child in region.children:
            score = self._label_score(child.name, child.search_text, variants)
            if score <= 0:
                continue
            items.append((score, child.name, child.code, child))
        items.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [
            PlaceOption(
                id=f"administrative-unit:{child.id}",
                label=self._china_name(child.pinyin, child.full_name, locale),
                value=child.id,
                meta=self._china_name(region.pinyin, region.full_name, locale),
                country=self.china_country,
                region=region.id,
                birth_place=child.id,
                latitude=child.latitude,
                longitude=child.longitude,
                timezone=self._timezone_for_china_region(region.code),
                searchText=child.search_text,
            )
            for _, _, _, child in items[:limit]
        ]

    @staticmethod
    def _china_name(pinyin: str, full_name: str, locale: Literal["zh", "en", "ja"]) -> str:
        if locale != "en" or not pinyin:
            return full_name
        return f"{pinyin.title()} ({full_name})"

    def _country_display_name(self, country: str, locale: Literal["zh", "en", "ja"]) -> str:
        record = self.country_names.get(country)
        names = record.get("names") if record else None
        if isinstance(names, dict):
            label = names.get(locale)
            if isinstance(label, str) and label.strip():
                return label
        return country

    @staticmethod
    def _place_count_label(count: int, locale: Literal["zh", "en", "ja"]) -> str:
        if locale == "zh":
            return f"{count} 个地点"
        if locale == "ja":
            return f"{count} 件の地点"
        return f"{count} places"

    def _resolve_china_admin(self, value: str) -> ResolvedPlace | None:
        region = self.china_region_index.get(value)
        child = self.china_unit_index.get(value)
        if not region and not child:
            return None
        if region:
            label_parts = [region.full_name, self.china_country]
            latitude = region.latitude
            longitude = region.longitude
            administrative_level = 1
            unit_type = "province"
            place_name = region.full_name
            alternate_names = "|".join(
                item for item in [region.name, region.full_name, region.pinyin] if item
            )
            region_code = region.code
            region_name = region.full_name
            accuracy = "district"
        else:
            assert child is not None
            region = self.china_region_index.get(child.region_id)
            if not region:
                return None
            label_parts = [child.full_name, region.full_name, self.china_country]
            latitude = child.latitude
            longitude = child.longitude
            administrative_level = child.source_level
            unit_type = child.unit_type
            place_name = child.full_name
            alternate_names = "|".join(
                item for item in [child.name, child.full_name, child.pinyin] if item
            )
            region_code = region.code
            region_name = region.full_name
            accuracy = "city" if child.source_level == 2 else "district"
        return ResolvedPlace(
            label=", ".join(label_parts),
            lat=latitude,
            lon=longitude,
            timezone=self._timezone_for_coordinates(latitude, longitude),
            source="china-administrative-catalog",
            matched={
                "placeName": place_name,
                "alternateNames": alternate_names,
                "state": region_name,
                "country": self.china_country,
                "administrativeCode": region.code if child is None else child.code,
                "regionCode": region_code,
                "administrativeLevel": str(administrative_level),
                "administrativeType": unit_type,
            },
            accuracy=accuracy,
            coordinate_system="WGS84",
            radius_km=self._radius_for_accuracy(accuracy),
            confidence=self._confidence_for_accuracy(accuracy),
            raw_query=value,
        )

    def _search_precise_local(self, query: str, limit: int) -> list[PrecisePlaceOption]:
        if len(self.normalize(query)) < 2:
            return []
        variants = self._query_variants(query)
        items = []
        for record in self.records:
            score = self._label_score(record.place_name, record.search_text, variants)
            if score <= 0:
                continue
            items.append((score, record.place_name, record.state, record))
        items.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [self._precise_option_from_record(record) for _, _, _, record in items[:limit]]

    def _precise_option_from_record(self, record: PlaceRecord) -> PrecisePlaceOption:
        label = self._birth_place_value(record)
        return PrecisePlaceOption(
            id=(
                f"geonames:{record.country}:{record.state}:{record.place_name}:"
                f"{record.latitude}:{record.longitude}"
            ),
            label=record.place_name,
            address=label,
            meta=f"{record.state}, {record.country}",
            source="geonames-local",
            accuracy="city",
            coordinateSystem="WGS84",
            latitude=record.latitude,
            longitude=record.longitude,
            birthPlace=self._birth_place_with_coordinates(
                label,
                record.latitude,
                record.longitude,
                source="geonames-local",
                accuracy="city",
            ),
        )

    def _resolve_city_context(self, raw_city: str | None) -> ResolvedPlace | None:
        if not raw_city or not raw_city.strip():
            return None
        try:
            return self.resolve_city_scope(raw_city)
        except Exception:
            return None

    def resolve_city_scope(self, raw_query: str) -> ResolvedPlace:
        """Resolve the exact administrative scope selected by the user.

        Candidate discovery may search broadly, but validation must retain the
        selected province/city/district. The Agent compares candidate addresses
        with this readable scope; center distance is informational only.
        """

        return self.resolve(raw_query)

    def _verify_precise_options(
        self, options: list[PrecisePlaceOption], city_base: ResolvedPlace
    ) -> tuple[list[PrecisePlaceOption], int]:
        verified: list[PrecisePlaceOption] = []
        rejected_count = 0
        max_distance = self._max_city_distance_km(city_base)
        for option in options:
            distance = self._distance_km(
                city_base.lat,
                city_base.lon,
                option.latitude,
                option.longitude,
            )
            if option.source == "agent":
                if option.scope_match_status != "match":
                    rejected_count += 1
                    continue
                verified.append(
                    option.model_copy(
                        update={
                            "verification_status": "verified",
                            "verification_reason": option.scope_match_reason
                            or f"Agent matched the candidate address to {city_base.label}.",
                            "distance_from_city_km": round(distance, 3),
                            "city_label": city_base.label,
                        }
                    )
                )
                continue
            if distance > max_distance:
                rejected_count += 1
                continue
            reason = (
                f"Verified against {city_base.label}; "
                f"{self._format_distance(distance)} km from the selected city center."
            )
            verified.append(
                option.model_copy(
                    update={
                        "verification_status": "verified",
                        "verification_reason": reason,
                        "distance_from_city_km": round(distance, 3),
                        "city_label": city_base.label,
                    }
                )
            )
        verified.sort(
            key=lambda option: (
                option.distance_from_city_km if option.distance_from_city_km is not None else 9999,
                self._source_rank(option.source),
                self._accuracy_rank(option.accuracy),
                option.label,
            )
        )
        return verified, rejected_count

    def _city_fallback_option(self, city_base: ResolvedPlace, *, reason: str) -> PrecisePlaceOption:
        return PrecisePlaceOption(
            id=f"city-fallback:{city_base.label}:{city_base.lat}:{city_base.lon}",
            label=city_base.label,
            address=city_base.label,
            meta=reason,
            source="geonames-local",
            accuracy="city",
            coordinateSystem="WGS84",
            latitude=city_base.lat,
            longitude=city_base.lon,
            birthPlace=self._birth_place_with_coordinates(
                city_base.label,
                city_base.lat,
                city_base.lon,
                source="geonames-local",
                accuracy="city",
            ),
            verificationStatus="city-fallback",
            verificationReason=reason,
            distanceFromCityKm=0.0,
            cityLabel=city_base.label,
        )

    def _dedupe_precise_options(
        self, options: list[PrecisePlaceOption]
    ) -> list[PrecisePlaceOption]:
        deduped: list[PrecisePlaceOption] = []
        seen: set[tuple[str, float, float]] = set()
        for option in options:
            key = (
                self.normalize(option.label),
                round(option.latitude, 5),
                round(option.longitude, 5),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(option)
        return deduped

    def _amap_enabled(self) -> bool:
        return bool(
            getattr(self.settings, "amap_place_fallback_enabled", False)
            and getattr(self.settings, "amap_web_service_key", "").strip()
        )

    def _search_precise_amap(
        self, query: str, limit: int, city_context: ResolvedPlace | None = None
    ) -> list[PrecisePlaceOption]:
        if not query:
            return []
        city_name = (city_context.matched or {}).get("placeName", "") if city_context else ""
        city_params = {"city": city_name} if city_name else {}
        pois = self._amap_get(
            "https://restapi.amap.com/v3/place/text",
            {
                "keywords": query,
                "offset": str(limit),
                "page": "1",
                "extensions": "base",
                **city_params,
            },
        ).get("pois", [])
        options = self._amap_pois_to_options(pois, limit)
        if options:
            return options

        tips = self._amap_get(
            "https://restapi.amap.com/v3/assistant/inputtips",
            {
                "keywords": query,
                "datatype": "all",
                **city_params,
            },
        ).get("tips", [])
        return self._amap_tips_to_options(tips, limit)

    def _amap_get(self, url: str, params: dict[str, str]) -> dict[str, object]:
        key = getattr(self.settings, "amap_web_service_key", "").strip()
        timeout = float(getattr(self.settings, "amap_request_timeout_seconds", 2.5))
        query = urlencode({**params, "key": key})
        with urlopen(f"{url}?{query}", timeout=timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        if str(payload.get("status")) != "1":
            info = payload.get("info") or payload.get("infocode") or "AMap request failed"
            raise RuntimeError(str(info))
        return payload

    def _amap_pois_to_options(self, pois: object, limit: int) -> list[PrecisePlaceOption]:
        if not isinstance(pois, list):
            return []
        options: list[PrecisePlaceOption] = []
        for item in pois:
            if not isinstance(item, dict):
                continue
            option = self._amap_item_to_option(item)
            if option:
                options.append(option)
            if len(options) >= limit:
                break
        return options

    def _amap_tips_to_options(self, tips: object, limit: int) -> list[PrecisePlaceOption]:
        if not isinstance(tips, list):
            return []
        options: list[PrecisePlaceOption] = []
        for item in tips:
            if not isinstance(item, dict):
                continue
            option = self._amap_item_to_option(item)
            if option:
                options.append(option)
            if len(options) >= limit:
                break
        return options

    def _amap_item_to_option(self, item: dict[str, object]) -> PrecisePlaceOption | None:
        location = item.get("location")
        if not isinstance(location, str) or "," not in location:
            return None
        try:
            gcj_lon, gcj_lat = [float(part) for part in location.split(",", 1)]
        except ValueError:
            return None
        lat, lon = self._gcj02_to_wgs84(gcj_lat, gcj_lon)
        name = self._string_or_empty(item.get("name")) or "AMap result"
        district = self._string_or_empty(item.get("adname")) or self._string_or_empty(
            item.get("district")
        )
        city = self._string_or_empty(item.get("cityname"))
        province = self._string_or_empty(item.get("pname"))
        address = self._string_or_empty(item.get("address"))
        if address and district and address == district:
            address = ""
        meta = ", ".join(part for part in [district, city, province] if part)
        readable = ", ".join(part for part in [name, district, city, province] if part)
        accuracy = self._amap_accuracy(item)
        return PrecisePlaceOption(
            id=f"amap:{self._string_or_empty(item.get('id')) or location}:{name}",
            label=name,
            address=address or readable,
            meta=meta or address or "AMap",
            source="amap",
            accuracy=accuracy,
            coordinateSystem="WGS84",
            latitude=lat,
            longitude=lon,
            birthPlace=self._birth_place_with_coordinates(
                readable or name,
                lat,
                lon,
                source="amap",
                accuracy=accuracy,
            ),
        )

    def _amap_accuracy(self, item: dict[str, object]) -> Literal["poi", "address", "district"]:
        typecode = self._string_or_empty(item.get("typecode"))
        if typecode.startswith("1901"):
            return "district"
        if self._string_or_empty(item.get("address")):
            return "address"
        return "poi"

    def _birth_place_with_coordinates(
        self,
        label: str,
        lat: float,
        lon: float,
        *,
        source: str | None = None,
        accuracy: str | None = None,
    ) -> str:
        parts = [
            f"lat={self._format_coordinate(lat)}",
            f"lon={self._format_coordinate(lon)}",
        ]
        if source:
            parts.append(f"source={source}")
        if accuracy:
            parts.append(f"accuracy={accuracy}")
        return f"{label} | {', '.join(parts)}"

    def birth_place_with_coordinates(
        self,
        label: str,
        lat: float,
        lon: float,
        *,
        source: str | None = None,
        accuracy: str | None = None,
    ) -> str:
        return self._birth_place_with_coordinates(
            label,
            lat,
            lon,
            source=source,
            accuracy=accuracy,
        )

    @staticmethod
    def _string_or_empty(value: object) -> str:
        if isinstance(value, str):
            return value.strip()
        return ""

    @staticmethod
    def _source_rank(source: str) -> int:
        return {
            "geonames-local": 0,
            "amap": 1,
            "agent": 2,
            "manual": 3,
        }.get(source, 9)

    @staticmethod
    def _accuracy_rank(accuracy: str) -> int:
        return {
            "coordinate": 0,
            "poi": 1,
            "address": 2,
            "district": 3,
            "city": 4,
        }.get(accuracy, 9)

    @staticmethod
    def _max_city_distance_km(city_base: ResolvedPlace) -> float:
        return max(city_base.radius_km + 10.0, 35.0)

    def max_city_distance_km(self, city_base: ResolvedPlace) -> float:
        return self._max_city_distance_km(city_base)

    @staticmethod
    def _format_distance(distance: float) -> str:
        rounded = round(distance, 1)
        return str(int(rounded)) if rounded.is_integer() else f"{rounded:.1f}"

    @staticmethod
    def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius_km = 6371.0088
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        haversine = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        )
        return radius_km * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))

    @staticmethod
    def _format_coordinate(value: float) -> str:
        rounded = round(value, 6)
        return (
            str(int(rounded)) if rounded.is_integer() else f"{rounded:.6f}".rstrip("0").rstrip(".")
        )

    def _gcj02_to_wgs84(self, lat: float, lon: float) -> tuple[float, float]:
        if self._outside_china(lat, lon):
            return lat, lon
        dlat = self._transform_lat(lon - 105.0, lat - 35.0)
        dlon = self._transform_lon(lon - 105.0, lat - 35.0)
        radlat = lat / 180.0 * math.pi
        magic = math.sin(radlat)
        magic = 1 - 0.00669342162296594323 * magic * magic
        sqrt_magic = math.sqrt(magic)
        dlat = (dlat * 180.0) / ((6335552.717000426 / (magic * sqrt_magic)) * math.pi)
        dlon = (dlon * 180.0) / ((6378245.0 / sqrt_magic) * math.cos(radlat) * math.pi)
        gcj_lat = lat + dlat
        gcj_lon = lon + dlon
        return lat * 2 - gcj_lat, lon * 2 - gcj_lon

    @staticmethod
    def _outside_china(lat: float, lon: float) -> bool:
        return lon < 72.004 or lon > 137.8347 or lat < 0.8293 or lat > 55.8271

    @staticmethod
    def _transform_lat(x: float, y: float) -> float:
        ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y
        ret += 0.2 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (
            (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
        )
        return ret

    @staticmethod
    def _transform_lon(x: float, y: float) -> float:
        ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y
        ret += 0.1 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (
            (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi))
            * 2.0
            / 3.0
        )
        return ret

    def _detect_preference(self, raw_query: str) -> PlacePreference:
        parts = [part.strip() for part in re.split(r"[,，]", raw_query) if part.strip()]
        if len(parts) >= 3:
            country = self._canonical_country(parts[-1])
            return PlacePreference(
                parts[0],
                country=country,
                state=self._canonical_region(parts[-2], country=country),
            )
        if len(parts) == 2:
            tail_country = self._canonical_country(parts[1])
            if tail_country in self.country_counts:
                return PlacePreference(parts[0], country=tail_country)
            return PlacePreference(parts[0], state=self._canonical_region(parts[1]))
        return PlacePreference(raw_query)

    def _ambiguous_exact_matches(self, preference: PlacePreference) -> list[PlaceRecord]:
        if preference.country or preference.state:
            return []
        query_norm = self.normalize(preference.query)
        if not query_norm:
            return []
        place_name_matches = [
            record for record in self.records if self.normalize(record.place_name) == query_norm
        ]
        matches = place_name_matches or [
            record
            for record in self.records
            if query_norm
            in [self.normalize(item) for item in record.alternate_names.split("|") if item]
        ]
        unique_locations = {
            (
                self.normalize(record.place_name),
                self.normalize(record.state),
                self.normalize(record.country),
            )
            for record in matches
        }
        if len(unique_locations) <= 1:
            return []
        matches.sort(
            key=lambda record: (
                record.country,
                record.state,
                record.place_name,
            )
        )
        return matches

    def _score_record(self, record: PlaceRecord, preference: PlacePreference) -> int:
        query_norm = self.normalize(preference.query)
        if not query_norm:
            return 0
        candidates = [
            self.normalize(record.place_name),
            *[self.normalize(item) for item in record.alternate_names.split("|") if item],
        ]
        if query_norm in candidates:
            score = 100
        elif any(candidate.startswith(query_norm) for candidate in candidates):
            score = 78
        elif len(query_norm) >= 4 and any(query_norm in candidate for candidate in candidates):
            score = 64
        else:
            return 0
        if preference.country and self.normalize(record.country) == self.normalize(
            preference.country
        ):
            score += 35
        if preference.state and self.normalize(record.state) == self.normalize(preference.state):
            score += 25
        if self.normalize(record.place_name) == query_norm:
            score += 8
        if record.state == record.place_name:
            score += 4
        return score

    def _canonical_country(self, value: str | None) -> str | None:
        if not value:
            return value
        normalized = self.normalize(value)
        return next(
            (country for country in self.country_counts if self.normalize(country) == normalized),
            value,
        )

    def _is_china_country(self, country: str | None) -> bool:
        return bool(country and self.normalize(country) == self.normalize(self.china_country))

    def _canonical_region(self, value: str | None, *, country: str | None = None) -> str | None:
        if not value:
            return value
        normalized = self.normalize(value)
        regions = self.region_counts.get(country, {}) if country else {}
        if not regions:
            regions = {record.state: 1 for record in self.records if record.state}
        return next(
            (region for region in regions if self.normalize(region) == normalized),
            value,
        )

    def _timezone_for(self, lat: float, lon: float, timezone_hours: str) -> str:
        try:
            timezone = self.timezone_finder.timezone_at(lat=lat, lng=lon)
            if timezone:
                return timezone
        except Exception:
            pass
        offset = float(timezone_hours)
        if offset.is_integer():
            return f"Etc/GMT{int(-offset):+d}"
        raise RuntimeError("timezonefinder failed and GeoNames offset is not a whole hour")

    def _timezone_for_coordinates(self, lat: float, lon: float) -> str:
        try:
            timezone = self.timezone_finder.timezone_at(lat=lat, lng=lon)
            if timezone:
                return timezone
        except Exception as exc:
            raise RuntimeError("timezonefinder is required for direct coordinates") from exc
        raise ValueError("无法根据这个经纬度识别时区，请检查坐标是否位于有效陆地区域。")

    @staticmethod
    def _timezone_for_china_region(region_code: str) -> str:
        return {
            "710000": "Asia/Taipei",
            "810000": "Asia/Hong_Kong",
            "820000": "Asia/Macau",
        }.get(region_code, "Asia/Shanghai")

    def _parse_inline_coordinates(self, value: str) -> ResolvedPlace | None:
        number_pattern = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))"
        lat_match = re.search(rf"(?:lat|latitude|纬度|緯度)\s*[:=]\s*{number_pattern}", value, re.I)
        lon_match = re.search(
            rf"(?:lon|lng|longitude|经度|經度|経度)\s*[:=]\s*{number_pattern}",
            value,
            re.I,
        )
        if not lat_match and not lon_match:
            return None
        if not lat_match or not lon_match:
            raise ValueError("经纬度格式不完整，请同时填写纬度和经度。")

        lat = float(lat_match.group(1))
        lon = float(lon_match.group(1))
        if not -90 <= lat <= 90:
            raise ValueError("纬度必须在 -90 到 90 之间。")
        if not -180 <= lon <= 180:
            raise ValueError("经度必须在 -180 到 180 之间。")

        timezone_match = re.search(r"\btz\s*[:=]\s*([A-Za-z_/-]+)", value)
        timezone = (
            timezone_match.group(1) if timezone_match else self._timezone_for_coordinates(lat, lon)
        )
        source = self._parse_inline_token(value, ["source", "src"]) or "inline-coordinates"
        accuracy = self._parse_inline_token(value, ["accuracy", "acc"]) or "coordinate"
        if accuracy not in {"city", "poi", "address", "district", "coordinate"}:
            accuracy = "coordinate"
        coordinate_system = (
            self._parse_inline_token(value, ["coordinateSystem", "coord", "cs"]) or "WGS84"
        )

        label = value.split("|", 1)[0].strip() or value
        return ResolvedPlace(
            label=label,
            lat=lat,
            lon=lon,
            timezone=timezone,
            source=source,
            matched=None,
            accuracy=accuracy,
            coordinate_system=coordinate_system,
            radius_km=self._radius_for_accuracy(accuracy),
            confidence=self._confidence_for_accuracy(accuracy),
            raw_query=value,
        )

    @staticmethod
    def _parse_inline_token(value: str, keys: list[str]) -> str | None:
        key_pattern = "|".join(re.escape(key) for key in keys)
        match = re.search(rf"(?:{key_pattern})\s*[:=]\s*([A-Za-z0-9_.-]+)", value, re.I)
        return match.group(1) if match else None

    @staticmethod
    def _radius_for_accuracy(accuracy: str) -> float:
        return {
            "coordinate": 0.25,
            "poi": 0.3,
            "address": 0.8,
            "district": 8.0,
            "city": 25.0,
        }.get(accuracy, 25.0)

    @staticmethod
    def _confidence_for_accuracy(accuracy: str) -> str:
        return {
            "coordinate": "high",
            "poi": "high",
            "address": "high",
            "district": "medium",
            "city": "medium",
        }.get(accuracy, "low")

    def _query_variants(self, query: str) -> list[str]:
        trimmed = query.strip()
        normalized = self.normalize(trimmed)
        return [normalized] if normalized else []

    def _label_score(self, label: str, search_text: str, variants: list[str]) -> int:
        if not variants:
            return 1
        normalized_label = self.normalize(label)
        best = 0
        for variant in variants:
            if normalized_label == variant:
                best = max(best, 110)
            elif normalized_label.startswith(variant):
                best = max(best, 90)
            elif variant in search_text:
                best = max(best, 55)
        return best

    def _birth_place_value(self, record: PlaceRecord) -> str:
        return ", ".join(part for part in [record.place_name, record.state, record.country] if part)

    @staticmethod
    def normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value)
        asciiish = "".join(char for char in decomposed if not unicodedata.combining(char))
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", asciiish.casefold())
