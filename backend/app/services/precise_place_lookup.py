from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from app.agents.claude_runtime import ClaudeRuntime
from app.schemas import PrecisePlaceOption, PrecisePlaceSearchResponse
from app.services.place_lookup_budget import PlaceLookupBudget, PlaceLookupRateLimitError
from app.services.place_service import PlaceService, ResolvedPlace


logger = logging.getLogger(__name__)
place_trace_logger = logging.getLogger("uvicorn.error")


class PrecisePlaceLookupService:
    """Orchestrate precise place lookup without letting agent output bypass verification."""

    def __init__(self, place_service: PlaceService, agent_runtime: ClaudeRuntime) -> None:
        self.place_service = place_service
        self.agent_runtime = agent_runtime
        settings = getattr(agent_runtime, "settings", None)
        self._agent_budget = PlaceLookupBudget(
            limit=int(getattr(settings, "place_lookup_rate_limit", 30)),
            window_seconds=float(getattr(settings, "place_lookup_rate_window_seconds", 60.0)),
            max_concurrent=int(getattr(settings, "place_lookup_max_concurrent", 4)),
        )

    async def search_precise(
        self,
        *,
        query: str = "",
        city_context: str | None = None,
        locale: Literal["zh", "en", "ja"] = "en",
        limit: int = 8,
        client_key: str | None = None,
        progress_callback: Callable[[str, dict[str, object]], Awaitable[None]] | None = None,
    ) -> PrecisePlaceSearchResponse:
        await self._emit_progress(progress_callback, "resolving", {"query": query})
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
        agent_search_queries: list[str] = []
        self._log_place_trace(
            "agent_candidate_lookup",
            {
                "query": query,
                "city_context": city_context,
                "city_label": city_base.label,
                "city_lat": city_base.lat,
                "city_lon": city_base.lon,
                "agent_enabled": agent_enabled,
            },
        )
        agent_error: str | None = None
        agent_attempted = False
        budget_acquired = False
        if agent_enabled:
            agent_attempted = True
            try:
                await self._emit_progress(
                    progress_callback,
                    "searching",
                    {"query": query, "scope": city_base.label},
                )
                self._agent_budget.acquire(client_key or "internal")
                budget_acquired = True
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
                        selected_scope_label=city_base.label,
                        locale=locale,
                        max_results=min(limit, 5),
                        progress_callback=progress_callback,
                    )
                agent_search_queries = list(getattr(result, "tool_queries", ()) or ())
                await self._emit_progress(
                    progress_callback,
                    "matching",
                    {"query": query, "scope": city_base.label},
                )
                agent_options = self._agent_result_to_options(result, query, city_base)
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
            except PlaceLookupRateLimitError:
                raise
            except Exception as exc:
                internal_error = str(exc)
                agent_error = "agent place lookup failed"
                logger.warning("precise_place_agent_lookup_failed: %s", internal_error)
                self._log_place_trace(
                    "agent_error",
                    {
                        "query": query,
                        "city_context": city_context,
                        "city_label": city_base.label,
                        "agent_search_queries": agent_search_queries,
                        "error": internal_error,
                    },
                )
            finally:
                if budget_acquired:
                    self._agent_budget.release()

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
        await self._emit_progress(
            progress_callback,
            "complete",
            {"query": query, "optionCount": len(final.options)},
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
    async def _emit_progress(
        callback: Callable[[str, dict[str, object]], Awaitable[None]] | None,
        stage: str,
        payload: dict[str, object],
    ) -> None:
        if callback is not None:
            await callback(stage, payload)

    @staticmethod
    def _should_attempt_agent(response: PrecisePlaceSearchResponse) -> bool:
        if not response.verification_base:
            return False
        if not response.options:
            return True
        return all(option.verification_status == "city-fallback" for option in response.options)

    def _log_place_trace(self, event: str, payload: dict[str, object]) -> None:
        settings = getattr(self.agent_runtime, "settings", None)
        if settings is not None and not getattr(settings, "place_lookup_trace_enabled", False):
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
        self, result: object, query: str, city_base: ResolvedPlace
    ) -> list[PrecisePlaceOption]:
        provenance = getattr(result, "provenance", "agent_final")
        if provenance not in {"tool_observation", "agent_grounded"}:
            # A final answer is usable only when the runtime observed at least one
            # WebSearch/WebFetch result during the same Agent turn.
            self._log_place_trace(
                "agent_result_rejected",
                {"reason": "untrusted_agent_final_provenance", "provenance": provenance},
            )
            return []
        raw_text = getattr(result, "raw_text", "")
        if not isinstance(raw_text, str) or not raw_text.strip():
            return []
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

        source_label = (
            self._string_value(item.get("label"))
            or self._string_value(item.get("name"))
            or query.strip()
            or city_base.label
        )
        source_address = self._string_value(item.get("address")) or source_label
        label = self._string_value(item.get("displayLabel")) or source_label
        address = self._string_value(item.get("displayAddress")) or source_address
        location_type = self._string_value(item.get("locationType")).lower()
        accuracy_by_location_type: dict[str, Literal["poi", "address", "district"]] = {
            "poi": "poi",
            "landmark": "poi",
            "address": "address",
            "district": "district",
            "county": "district",
            "town": "district",
            "village": "district",
        }
        accuracy = accuracy_by_location_type.get(location_type)
        if accuracy is None:
            return None
        coordinate_system = self._string_value(
            item.get("coordinateSystem") or item.get("coordinate_system")
        ).upper()
        if coordinate_system not in {"WGS84", "EPSG:4326", "EPSG4326"}:
            # Geodetic datum is part of the calculator input, not cosmetic
            # metadata. Unknown/GCJ-02/BD-09 coordinates must not be used.
            return None
        source_url = self._string_value(item.get("sourceUrl")) or self._string_value(
            item.get("url")
        )
        raw_evidence = (
            self._string_value(item.get("rawEvidence"))
            or self._string_value(item.get("evidence"))
            or self._string_value(item.get("source"))
        )
        if not source_url and not raw_evidence:
            # Coordinates without provenance are indistinguishable from model guesses.
            # Tool adapters may omit a URL, but they must still provide an evidence summary.
            return None
        scope_assessment = item.get("scopeAssessment")
        scope_status = self._string_value(item.get("scopeMatchStatus"))
        scope_reason = self._string_value(item.get("scopeMatchReason"))
        if isinstance(scope_assessment, dict):
            scope_status = scope_status or self._string_value(scope_assessment.get("status"))
            scope_reason = scope_reason or self._string_value(scope_assessment.get("reason"))
        if scope_status != "match":
            return None
        readable = ", ".join(part for part in [source_label, city_base.label] if part)
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
            locationType=location_type,
            scopeMatchStatus="match",
            scopeMatchReason=scope_reason or "Agent matched the candidate to the selected scope.",
        )

    @staticmethod
    def _string_value(value: object) -> str:
        return value.strip() if isinstance(value, str) else ""
