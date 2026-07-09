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
            use_web_fallback=False,
        )
        if not self._should_attempt_agent(baseline):
            return baseline

        city_base = self.place_service.resolve(city_context or "")
        agent_options: list[PrecisePlaceOption] = []
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
                    )
                agent_options = self._agent_result_to_options(result.raw_text, query, city_base)
            except TimeoutError:
                agent_error = "agent place lookup timed out"
            except Exception as exc:
                agent_error = str(exc)
                logger.warning("precise_place_agent_lookup_failed: %s", agent_error)

        final = self.place_service.search_precise(
            query=query,
            limit=limit,
            city_context=city_context,
            agent_options=agent_options,
            agent_enabled=agent_enabled,
            agent_attempted=agent_attempted,
            agent_error=agent_error,
            use_web_fallback=True,
        )
        logger.info(
            "precise_place_lookup query=%r city=%r sources=%s agent_enabled=%s "
            "agent_attempted=%s agent_candidates=%s rejected=%s",
            query,
            city_context,
            final.attempted_sources,
            agent_enabled,
            agent_attempted,
            len(agent_options),
            final.rejected_count,
        )
        return final

    @staticmethod
    def _should_attempt_agent(response: PrecisePlaceSearchResponse) -> bool:
        if not response.verification_base:
            return False
        if not response.options:
            return True
        return all(option.verification_status == "city-fallback" for option in response.options)

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

        label = self._string_value(item.get("label")) or query.strip() or city_base.label
        address = self._string_value(item.get("address")) or label
        accuracy_value = self._string_value(item.get("accuracy")) or "poi"
        accuracy: Literal["city", "poi", "address", "district", "coordinate"]
        if accuracy_value in {"city", "poi", "address", "district", "coordinate"}:
            accuracy = cast(
                Literal["city", "poi", "address", "district", "coordinate"], accuracy_value
            )
        else:
            accuracy = "poi"
        source_url = self._string_value(item.get("sourceUrl"))
        raw_evidence = self._string_value(item.get("rawEvidence"))
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
