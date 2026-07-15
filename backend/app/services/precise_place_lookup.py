from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Literal, cast

from app.agents.claude_runtime import ClaudeRuntime
from app.schemas import PrecisePlaceOption, PrecisePlaceSearchResponse
from app.services.place_service import PlaceService, ResolvedPlace


logger = logging.getLogger(__name__)
place_trace_logger = logging.getLogger("uvicorn.error")


class PrecisePlaceLookupService:
    """Orchestrate precise place lookup without letting agent output bypass verification."""

    def __init__(self, place_service: PlaceService, agent_runtime: ClaudeRuntime) -> None:
        self.place_service = place_service
        self.agent_runtime = agent_runtime

    async def search_precise(
        self, *, query: str = "", city_context: str | None = None, limit: int = 8
    ) -> PrecisePlaceSearchResponse:
        agent_enabled = self.agent_runtime.is_configured()
        baseline = self.place_service.search_precise(
            query=query,
            limit=limit,
            city_context=city_context,
            agent_enabled=agent_enabled,
        )
        if not self._should_attempt_agent(baseline):
            return baseline

        city_base = self.place_service.resolve_city_scope(city_context or "")
        agent_options: list[PrecisePlaceOption] = []
        agent_search_queries = self._build_agent_search_queries(
            query=query,
            city_context=city_context,
            city_base=city_base,
        )
        self._log_place_trace(
            "agent_candidate_lookup",
            {
                "query": query,
                "city_context": city_context,
                "city_label": city_base.label,
                "city_lat": city_base.lat,
                "city_lon": city_base.lon,
                "agent_enabled": agent_enabled,
                "agent_search_queries": agent_search_queries,
            },
        )
        agent_error: str | None = None
        agent_attempted = False
        if agent_enabled:
            agent_attempted = True
            try:
                agent_settings = getattr(self.agent_runtime, "settings", None)
                async with asyncio.timeout(
                    float(
                        getattr(
                            agent_settings,
                            "place_lookup_agent_timeout_seconds",
                            45.0,
                        )
                    )
                ):
                    result = await self.agent_runtime.run_place_lookup_task(
                        query=query,
                        city_label=city_base.label,
                        city_lat=city_base.lat,
                        city_lon=city_base.lon,
                        max_distance_km=self.place_service.max_city_distance_km(city_base),
                        max_results=min(limit, 5),
                        search_queries=agent_search_queries,
                    )
                agent_options = self._agent_result_to_options(result.raw_text, query, city_base)
            except TimeoutError:
                agent_error = "agent place lookup timed out"
                self._log_place_trace(
                    "agent_timeout",
                    {
                        "query": query,
                        "city_context": city_context,
                        "city_label": city_base.label,
                        "agent_search_queries": agent_search_queries,
                        "timeout_seconds": float(
                            getattr(
                                getattr(self.agent_runtime, "settings", None),
                                "place_lookup_agent_timeout_seconds",
                                45.0,
                            )
                        ),
                    },
                )
            except Exception as exc:
                agent_error = str(exc)
                logger.warning("precise_place_agent_lookup_failed: %s", agent_error)
                self._log_place_trace(
                    "agent_error",
                    {
                        "query": query,
                        "city_context": city_context,
                        "city_label": city_base.label,
                        "agent_search_queries": agent_search_queries,
                        "error": agent_error,
                    },
                )

        final = self.place_service.search_precise(
            query=query,
            limit=limit,
            city_context=city_context,
            agent_options=agent_options,
            agent_enabled=agent_enabled,
            agent_attempted=agent_attempted,
            agent_error=agent_error,
            agent_search_queries=agent_search_queries,
        )
        logger.info(
            "precise_place_lookup query=%r city=%r agent_queries=%s sources=%s "
            "agent_enabled=%s agent_attempted=%s agent_candidates=%s rejected=%s",
            query,
            city_context,
            agent_search_queries,
            final.attempted_sources,
            agent_enabled,
            agent_attempted,
            len(agent_options),
            final.rejected_count,
        )
        self._log_place_trace(
            "lookup_final",
            {
                "query": query,
                "city_context": city_context,
                "agent_attempted": final.agent_attempted,
                "agent_error": final.agent_error,
                "fallback_source": final.fallback_source,
                "rejected_count": final.rejected_count,
                "option_count": len(final.options),
                "options": [
                    {
                        "label": option.label,
                        "source": option.source,
                        "verification_status": option.verification_status,
                        "latitude": option.latitude,
                        "longitude": option.longitude,
                        "distance_from_city_km": option.distance_from_city_km,
                    }
                    for option in final.options[:3]
                ],
            },
        )
        return final

    @staticmethod
    def _should_attempt_agent(response: PrecisePlaceSearchResponse) -> bool:
        if not response.verification_base:
            return False
        if not response.options:
            return True
        return all(option.verification_status == "city-fallback" for option in response.options)

    def _build_agent_search_queries(
        self,
        *,
        query: str,
        city_context: str | None,
        city_base: ResolvedPlace,
        max_queries: int = 6,
    ) -> list[str]:
        trimmed_query = self._compact_text(query)
        if not trimmed_query:
            return []

        contexts = self._agent_search_contexts(city_context, city_base)
        queries: list[str] = []

        def add(value: str) -> None:
            compacted = self._compact_text(value)
            if compacted and compacted not in queries:
                queries.append(compacted)

        if self._has_cjk(trimmed_query):
            for context in contexts:
                if self._has_cjk(context):
                    base = self._join_query_context(trimmed_query, context)
                    add(f"{base} 经纬度")
                    add(f"{base} 坐标")
            add(f"{trimmed_query} 经纬度")
            add(f"{trimmed_query} 地址 经纬度")

        english_contexts = [
            context for context in contexts if not self._has_cjk(context)
        ] or contexts
        for context in english_contexts:
            base = self._join_query_context(trimmed_query, context)
            add(f"{base} latitude longitude coordinates")
            add(f"{base} WGS84 coordinates")

        return queries[:max_queries]

    def _agent_search_contexts(
        self, city_context: str | None, city_base: ResolvedPlace
    ) -> list[str]:
        contexts: list[str] = []

        def add(value: str | None) -> None:
            compacted = self._compact_text(value or "")
            if compacted and compacted not in contexts:
                contexts.append(compacted)

        add(self._localized_china_context(city_base))
        if city_context and self._has_cjk(city_context):
            add(city_context)
        if city_base.raw_query and self._has_cjk(city_base.raw_query):
            add(city_base.raw_query)
        add(city_base.label.replace(",", " "))
        return contexts

    def _localized_china_context(self, city_base: ResolvedPlace) -> str | None:
        matched = city_base.matched or {}
        if matched.get("country") != "China":
            return None

        state = matched.get("state", "")
        place_name = matched.get("placeName", "")
        region_alias = self._first_cjk_region_alias(state)
        city_alias = self._first_cjk_city_alias(place_name, state)
        if not city_alias:
            city_alias = self._first_cjk_token(matched.get("alternateNames", ""))

        parts: list[str] = []
        if region_alias:
            parts.append(region_alias)
        if city_alias and self.place_service.normalize(city_alias) not in {
            self.place_service.normalize(part) for part in parts
        }:
            parts.append(city_alias)
        return " ".join(parts) or None

    def _first_cjk_city_alias(self, place_name: str, state: str) -> str | None:
        for alias, preference in self.place_service.city_aliases.items():
            if (
                self._has_cjk(alias)
                and preference.country == "China"
                and preference.state == state
                and self.place_service.normalize(preference.query)
                == self.place_service.normalize(place_name)
            ):
                return alias
        return None

    def _first_cjk_region_alias(self, state: str) -> str | None:
        for alias, canonical in self.place_service.region_aliases.items():
            if self._has_cjk(alias) and canonical == state:
                return alias
        return None

    def _first_cjk_token(self, value: str) -> str | None:
        for token in re.split(r"[|,，/;；\s]+", value):
            compacted = self._compact_text(token)
            if compacted and self._has_cjk(compacted):
                return compacted
        return None

    def _join_query_context(self, query: str, context: str) -> str:
        normalized_query = self.place_service.normalize(query)
        normalized_context = self.place_service.normalize(context)
        if normalized_context and normalized_context in normalized_query:
            return query
        return f"{query} {context}"

    @staticmethod
    def _compact_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _has_cjk(value: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", value))

    def _log_place_trace(self, event: str, payload: dict[str, object]) -> None:
        settings = getattr(self.agent_runtime, "settings", None)
        if settings is not None and not getattr(settings, "place_lookup_trace_enabled", True):
            return
        max_chars = max(
            500,
            int(getattr(settings, "place_lookup_trace_max_chars", 4000)),
        )
        try:
            text = json.dumps(payload, ensure_ascii=False, default=str)
        except TypeError:
            text = repr(payload)
        if len(text) > max_chars:
            text = f"{text[:max_chars]}...<truncated {len(text) - max_chars} chars>"
        place_trace_logger.warning("place_lookup_trace event=%s payload=%s", event, text)

    def _agent_result_to_options(
        self, raw_text: str, query: str, city_base: ResolvedPlace
    ) -> list[PrecisePlaceOption]:
        payload = self._parse_json_payload(raw_text)
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        if not isinstance(candidates, list):
            return []

        options: list[PrecisePlaceOption] = []
        for index, item in enumerate(candidates):
            if not isinstance(item, dict):
                continue
            option = self._agent_candidate_to_option(item, index, query, city_base)
            if option:
                options.append(option)
        return options

    @staticmethod
    def _parse_json_payload(raw_text: str) -> dict[str, Any]:
        stripped = raw_text.strip()
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.S)
        if fence:
            stripped = fence.group(1)
        if not stripped.startswith("{"):
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start >= 0 and end > start:
                stripped = stripped[start : end + 1]
        payload = json.loads(stripped)
        return payload if isinstance(payload, dict) else {}

    def _agent_candidate_to_option(
        self,
        item: dict[str, Any],
        index: int,
        query: str,
        city_base: ResolvedPlace,
    ) -> PrecisePlaceOption | None:
        try:
            lat = float(item["latitude"])
            lon = float(item["longitude"])
        except (KeyError, TypeError, ValueError):
            return None
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            return None

        label = (
            self._string_value(item.get("label"))
            or self._string_value(item.get("name"))
            or query.strip()
            or city_base.label
        )
        address = self._string_value(item.get("address")) or label
        accuracy_value = self._string_value(item.get("accuracy")) or "poi"
        accuracy: Literal["city", "poi", "address", "district", "coordinate"]
        if accuracy_value in {"city", "poi", "address", "district", "coordinate"}:
            accuracy = cast(
                Literal["city", "poi", "address", "district", "coordinate"], accuracy_value
            )
        else:
            accuracy = "poi"
        source_url = self._string_value(item.get("sourceUrl")) or self._string_value(
            item.get("url")
        )
        raw_evidence = (
            self._string_value(item.get("rawEvidence"))
            or self._string_value(item.get("evidence"))
            or self._string_value(item.get("source"))
        )
        readable = ", ".join(part for part in [label, city_base.label] if part)
        return PrecisePlaceOption(
            id=f"agent:{self.place_service.normalize(label)[:48]}:{lat:.6f}:{lon:.6f}:{index}",
            label=label,
            address=address,
            meta="Agent web evidence",
            source="agent",
            accuracy=accuracy,
            coordinateSystem="WGS84",
            latitude=lat,
            longitude=lon,
            birthPlace=self.place_service.birth_place_with_coordinates(
                readable,
                lat,
                lon,
                source="agent",
                accuracy=accuracy,
            ),
            sourceUrl=source_url or None,
            rawEvidence=raw_evidence or None,
        )

    @staticmethod
    def _string_value(value: object) -> str:
        return value.strip() if isinstance(value, str) else ""
