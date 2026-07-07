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
from urllib.request import urlopen

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


class PlaceService:
    country_aliases = {
        "中国": "China",
        "中國": "China",
        "美国": "United States",
        "美國": "United States",
        "英国": "United Kingdom",
        "英國": "United Kingdom",
        "日本": "Japan",
        "韩国": "South Korea",
        "韓國": "South Korea",
        "新加坡": "Singapore",
        "加拿大": "Canada",
        "澳大利亚": "Australia",
        "澳洲": "Australia",
        "印度": "India",
        "法国": "France",
        "法國": "France",
        "德国": "Germany",
        "德國": "Germany",
    }
    region_aliases = {
        "广东": "Guangdong",
        "广东省": "Guangdong",
        "浙江": "Zhejiang",
        "江苏": "Jiangsu",
        "四川": "Sichuan",
        "湖北": "Hubei",
        "陕西": "Shaanxi",
        "山东": "Shandong",
        "福建": "Fujian",
        "加州": "California",
        "纽约州": "New York",
        "乔治亚": "Georgia",
        "德州": "Texas",
        "华盛顿州": "Washington",
        "麻省": "Massachusetts",
    }
    city_aliases = {
        "北京": PlacePreference("Beijing", "China", "Beijing"),
        "北京市": PlacePreference("Beijing", "China", "Beijing"),
        "上海": PlacePreference("Shanghai", "China", "Shanghai"),
        "上海市": PlacePreference("Shanghai", "China", "Shanghai"),
        "广州": PlacePreference("Guangzhou", "China", "Guangdong"),
        "广州市": PlacePreference("Guangzhou", "China", "Guangdong"),
        "深圳": PlacePreference("Shenzhen", "China", "Guangdong"),
        "深圳市": PlacePreference("Shenzhen", "China", "Guangdong"),
        "杭州": PlacePreference("Hangzhou", "China", "Zhejiang"),
        "成都": PlacePreference("Chengdu", "China", "Sichuan"),
        "纽约": PlacePreference("New York City", "United States", "New York"),
        "洛杉矶": PlacePreference("Los Angeles", "United States", "California"),
        "旧金山": PlacePreference("San Francisco", "United States", "California"),
        "西雅图": PlacePreference("Seattle", "United States", "Washington"),
        "亚特兰大": PlacePreference("Atlanta", "United States", "Georgia"),
        "伦敦": PlacePreference("London", "United Kingdom", "England"),
        "巴黎": PlacePreference("Paris", "France", "Ile-de-France"),
        "东京": PlacePreference("Tokyo", "Japan", "Tokyo"),
        "首尔": PlacePreference("Seoul", "South Korea", "Seoul"),
    }
    default_preferences = {
        "la": PlacePreference("Los Angeles", "United States", "California"),
        "losangeles": PlacePreference("Los Angeles", "United States", "California"),
        "nyc": PlacePreference("New York City", "United States", "New York"),
        "newyork": PlacePreference("New York City", "United States", "New York"),
        "newyorkcity": PlacePreference("New York City", "United States", "New York"),
        "sf": PlacePreference("San Francisco", "United States", "California"),
        "sanfrancisco": PlacePreference("San Francisco", "United States", "California"),
        "atlanta": PlacePreference("Atlanta", "United States", "Georgia"),
        "shenzhen": PlacePreference("Shenzhen", "China", "Guangdong"),
    }
    preferred_countries = [
        "United States",
        "China",
        "India",
        "United Kingdom",
        "Canada",
        "Australia",
        "Singapore",
        "Japan",
        "South Korea",
        "Thailand",
        "Malaysia",
        "United Arab Emirates",
        "France",
        "Germany",
    ]
    preferred_regions = {
        "China": [
            "Beijing",
            "Shanghai",
            "Guangdong",
            "Zhejiang",
            "Jiangsu",
            "Sichuan",
            "Hubei",
            "Shaanxi",
            "Shandong",
            "Fujian",
        ],
        "United States": [
            "California",
            "New York",
            "Georgia",
            "Texas",
            "Washington",
            "Massachusetts",
            "Illinois",
            "Florida",
        ],
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

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
    def country_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.records:
            counts[record.country] = counts.get(record.country, 0) + 1
        return counts

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
        limit: int = 30,
    ) -> PlaceSearchResponse:
        limit = max(5, min(80, limit))
        if level == "country":
            return PlaceSearchResponse(options=self._search_countries(query, limit))
        if level == "region":
            return PlaceSearchResponse(options=self._search_regions(country, query, limit))
        if level == "city":
            return PlaceSearchResponse(options=self._search_cities(country, region, query, limit))
        return PlaceSearchResponse(options=[])

    def search_precise(self, query: str = "", limit: int = 8) -> PrecisePlaceSearchResponse:
        trimmed = query.strip()
        limit = max(1, min(20, limit))
        local_options = self._search_precise_local(trimmed, limit)
        if local_options:
            return PrecisePlaceSearchResponse(
                options=local_options,
                localCount=len(local_options),
                fallbackEnabled=self._amap_enabled(),
            )

        fallback_enabled = self._amap_enabled()
        fallback_options = self._search_precise_amap(trimmed, limit) if fallback_enabled else []
        return PrecisePlaceSearchResponse(
            options=fallback_options,
            localCount=0,
            fallbackSource="amap" if fallback_options else None,
            fallbackEnabled=fallback_enabled,
        )

    def resolve(self, raw_query: str) -> ResolvedPlace:
        trimmed = raw_query.strip()
        inline = self._parse_inline_coordinates(trimmed)
        if inline:
            return inline

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
                "state": best.state,
                "country": best.country,
            },
        )

    def _search_countries(self, query: str, limit: int) -> list[PlaceOption]:
        variants = self._query_variants("country", query)
        items = []
        for country, count in self.country_counts.items():
            score = self._label_score(country, self.normalize(country), variants)
            if not variants:
                score += self._priority(country, self.preferred_countries)
            if score <= 0:
                continue
            items.append((score, count, country))
        items.sort(key=lambda item: (-item[0], -item[1], item[2]))
        return [
            PlaceOption(
                id=f"country:{country}",
                label=country,
                value=country,
                meta=f"{count} cities",
            )
            for _, count, country in items[:limit]
        ]

    def _search_regions(self, country: str | None, query: str, limit: int) -> list[PlaceOption]:
        if not country:
            return []
        regions = self.region_counts.get(country, {})
        variants = self._query_variants("region", query)
        preferred = self.preferred_regions.get(country, [])
        items = []
        for region, count in regions.items():
            score = self._label_score(region, self.normalize(region), variants)
            if not variants:
                score += self._priority(region, preferred)
            if score <= 0:
                continue
            items.append((score, count, region))
        items.sort(key=lambda item: (-item[0], -item[1], item[2]))
        return [
            PlaceOption(
                id=f"region:{country}:{region}",
                label=region,
                value=region,
                meta=f"{count} cities",
                country=country,
                region=region,
            )
            for _, count, region in items[:limit]
        ]

    def _search_cities(
        self, country: str | None, region: str | None, query: str, limit: int
    ) -> list[PlaceOption]:
        variants = self._query_variants("city", query)
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
            if country and record.country != country:
                continue
            if region and record.state != region:
                continue
            score = self._label_score(record.place_name, record.search_text, variants)
            if score <= 0:
                continue
            if global_search:
                # Surface well-known countries first when names collide (e.g. Paris).
                score = score * 10 + self._priority(record.country, self.preferred_countries)
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
            )
            for _, _, _, record in items[:limit]
        ]

    def _search_precise_local(self, query: str, limit: int) -> list[PrecisePlaceOption]:
        if len(self.normalize(query)) < 2:
            return []
        variants = self._query_variants("city", query)
        items = []
        for record in self.records:
            score = self._label_score(record.place_name, record.search_text, variants)
            if score <= 0:
                continue
            score = score * 10 + self._priority(record.country, self.preferred_countries)
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
            birthPlace=self._birth_place_with_coordinates(label, record.latitude, record.longitude),
        )

    def _amap_enabled(self) -> bool:
        return bool(
            getattr(self.settings, "amap_place_fallback_enabled", False)
            and getattr(self.settings, "amap_web_service_key", "").strip()
        )

    def _search_precise_amap(self, query: str, limit: int) -> list[PrecisePlaceOption]:
        if not query:
            return []
        pois = self._amap_get(
            "https://restapi.amap.com/v3/place/text",
            {
                "keywords": query,
                "offset": str(limit),
                "page": "1",
                "extensions": "base",
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
            birthPlace=self._birth_place_with_coordinates(readable or name, lat, lon),
        )

    def _amap_accuracy(self, item: dict[str, object]) -> Literal["poi", "address", "district"]:
        typecode = self._string_or_empty(item.get("typecode"))
        if typecode.startswith("1901"):
            return "district"
        if self._string_or_empty(item.get("address")):
            return "address"
        return "poi"

    def _birth_place_with_coordinates(self, label: str, lat: float, lon: float) -> str:
        return f"{label} | lat={self._format_coordinate(lat)}, lon={self._format_coordinate(lon)}"

    @staticmethod
    def _string_or_empty(value: object) -> str:
        if isinstance(value, str):
            return value.strip()
        return ""

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
        normalized = self.normalize(raw_query)
        if normalized in self.default_preferences:
            return self.default_preferences[normalized]

        for marker, preference in self.city_aliases.items():
            if marker in raw_query:
                return preference

        parts = [part.strip() for part in re.split(r"[,，]", raw_query) if part.strip()]
        if len(parts) >= 3:
            return PlacePreference(
                parts[0],
                country=self._canonical_country(parts[-1]),
                state=self._canonical_region(parts[-2]),
            )
        if len(parts) == 2:
            tail_country = self._canonical_country(parts[1])
            if tail_country in self.country_counts:
                return PlacePreference(parts[0], country=tail_country)
            return PlacePreference(parts[0], state=self._canonical_region(parts[1]))

        country = None
        state = None
        if any(marker in raw_query for marker in ["中国", "China", "china"]):
            country = "China"
        elif any(marker in raw_query for marker in ["美国", "United States", "USA", "usa"]):
            country = "United States"
        if "CA" in raw_query or "California" in raw_query or "加州" in raw_query:
            state = "California"
        elif "NY" in raw_query or "New York" in raw_query or "纽约州" in raw_query:
            state = "New York"
        elif "GA" in raw_query or "Georgia" in raw_query or "乔治亚" in raw_query:
            state = "Georgia"
        return PlacePreference(raw_query, country=country, state=state)

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
                -self._priority(record.country, self.preferred_countries),
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
        return self.country_aliases.get(value, value)

    def _canonical_region(self, value: str | None) -> str | None:
        if not value:
            return value
        return self.region_aliases.get(value, value)

    def _timezone_for(self, lat: float, lon: float, timezone_hours: str) -> str:
        try:
            from timezonefinder import TimezoneFinder  # type: ignore

            timezone = TimezoneFinder().timezone_at(lat=lat, lng=lon)
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
            from timezonefinder import TimezoneFinder  # type: ignore

            timezone = TimezoneFinder().timezone_at(lat=lat, lng=lon)
            if timezone:
                return timezone
        except Exception as exc:
            raise RuntimeError("timezonefinder is required for direct coordinates") from exc
        raise ValueError("无法根据这个经纬度识别时区，请检查坐标是否位于有效陆地区域。")

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

        return ResolvedPlace(
            label=value,
            lat=lat,
            lon=lon,
            timezone=timezone,
            source="inline-coordinates",
            matched=None,
        )

    def _query_variants(self, level: str, query: str) -> list[str]:
        trimmed = query.strip()
        variants = {trimmed} if trimmed else set()
        maps: list[dict[str, str] | dict[str, PlacePreference]]
        if level == "country":
            maps = [self.country_aliases]
        elif level == "region":
            maps = [self.region_aliases]
        else:
            maps = [self.city_aliases, self.region_aliases, self.country_aliases]
        for aliases in maps:
            alias = aliases.get(trimmed)
            if isinstance(alias, PlacePreference):
                variants.add(alias.query)
            elif alias:
                variants.add(alias)
        return [self.normalize(variant) for variant in variants if self.normalize(variant)]

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

    def _priority(self, value: str, preferred: list[str]) -> int:
        return 0 if value not in preferred else 1000 - preferred.index(value)

    def _birth_place_value(self, record: PlaceRecord) -> str:
        return ", ".join(part for part in [record.place_name, record.state, record.country] if part)

    @staticmethod
    def normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value)
        asciiish = "".join(char for char in decomposed if not unicodedata.combining(char))
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", asciiish.casefold())
