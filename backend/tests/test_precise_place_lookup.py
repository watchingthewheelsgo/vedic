from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.place_service import PlaceService
from app.services.precise_place_lookup import PrecisePlaceLookupService


class FakeAgentRuntime:
    def __init__(self, raw_text: str, configured: bool = True) -> None:
        self.raw_text = raw_text
        self.configured = configured
        self.calls: list[dict[str, object]] = []

    def is_configured(self) -> bool:
        return self.configured

    async def run_place_lookup_task(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(raw_text=self.raw_text)


def test_precise_lookup_uses_agent_when_city_verified_candidates_are_missing(tmp_path) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Shanghai,上海|Shanghai,Shanghai,China,31.22222,121.45806,8\n",
        encoding="utf-8",
    )
    place_service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
            web_place_search_enabled=False,
        )
    )
    agent = FakeAgentRuntime(
        """
        {
          "candidates": [
            {
              "label": "Shanghai First Maternity and Infant Health Hospital",
              "address": "Shanghai, China",
              "latitude": 31.2169,
              "longitude": 121.4541,
              "accuracy": "poi",
              "sourceUrl": "https://example.test/hospital",
              "rawEvidence": "Coordinates listed near Shanghai First Maternity hospital.",
              "confidence": "high"
            }
          ]
        }
        """
    )
    lookup = PrecisePlaceLookupService(place_service, agent)  # type: ignore[arg-type]

    response = asyncio.run(
        lookup.search_precise(
            query="上海第一妇婴保健院",
            city_context="Shanghai, Shanghai, China",
            limit=8,
        )
    )

    assert len(agent.calls) == 1
    assert response.agent_attempted is True
    assert response.fallback_source == "agent"
    assert response.attempted_sources == ["local", "agent"]
    assert response.rejected_count == 0
    assert response.options[0].source == "agent"
    assert response.options[0].verification_status == "verified"
    assert response.options[0].distance_from_city_km is not None
    assert response.options[0].distance_from_city_km < 2


def test_precise_lookup_reports_agent_error_and_falls_back_to_web_or_city(tmp_path) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Shanghai,上海|Shanghai,Shanghai,China,31.22222,121.45806,8\n",
        encoding="utf-8",
    )
    place_service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
            web_place_search_enabled=False,
        )
    )

    class FailingAgent(FakeAgentRuntime):
        async def run_place_lookup_task(self, **kwargs: object) -> SimpleNamespace:
            self.calls.append(kwargs)
            raise RuntimeError("agent unavailable")

    agent = FailingAgent("{}", configured=True)
    lookup = PrecisePlaceLookupService(place_service, agent)  # type: ignore[arg-type]

    response = asyncio.run(
        lookup.search_precise(
            query="上海第一妇婴保健院",
            city_context="Shanghai, Shanghai, China",
            limit=8,
        )
    )

    assert len(agent.calls) == 1
    assert response.agent_attempted is True
    assert response.agent_error == "agent unavailable"
    assert response.options[0].verification_status == "city-fallback"
