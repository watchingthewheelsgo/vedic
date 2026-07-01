from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from app.schemas import PlaceOption, PlaceSearchResponse
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

    def resolve(self, raw_query: str) -> ResolvedPlace:
        trimmed = raw_query.strip()
        inline = self._parse_inline_coordinates(trimmed)
        if inline:
            return inline

        preference = self._detect_preference(trimmed)
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

    def _search_regions(
        self, country: str | None, query: str, limit: int
    ) -> list[PlaceOption]:
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
        if not country:
            return []
        variants = self._query_variants("city", query)
        if not region and not variants:
            return []

        items = []
        for record in self.records:
            if record.country != country:
                continue
            if region and record.state != region:
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
            )
            for _, _, _, record in items[:limit]
        ]

    def _detect_preference(self, raw_query: str) -> PlacePreference:
        normalized = self.normalize(raw_query)
        if normalized in self.default_preferences:
            return self.default_preferences[normalized]

        for marker, preference in self.city_aliases.items():
            if marker in raw_query:
                return preference

        parts = [part.strip() for part in re.split(r"[,，]", raw_query) if part.strip()]
        if len(parts) >= 3:
            return PlacePreference(parts[0], country=parts[-1], state=parts[-2])
        if len(parts) == 2:
            return PlacePreference(parts[0], state=parts[1])

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
        if preference.country and self.normalize(record.country) == self.normalize(preference.country):
            score += 35
        if preference.state and self.normalize(record.state) == self.normalize(preference.state):
            score += 25
        if self.normalize(record.place_name) == query_norm:
            score += 8
        if record.state == record.place_name:
            score += 4
        return score

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

    def _parse_inline_coordinates(self, value: str) -> ResolvedPlace | None:
        match = re.search(
            r"lat\s*[:=]\s*(-?\d+(?:\.\d+)?)\s*,?\s*"
            r"lon\s*[:=]\s*(-?\d+(?:\.\d+)?)\s*,?\s*"
            r"tz\s*[:=]\s*([A-Za-z_/-]+)",
            value,
        )
        if not match:
            return None
        return ResolvedPlace(
            label=value,
            lat=float(match.group(1)),
            lon=float(match.group(2)),
            timezone=match.group(3),
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
