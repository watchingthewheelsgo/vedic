from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.place_service import PlaceService
from app.services.precise_place_lookup import PrecisePlaceLookupService


class FakeAgentRuntime:
    def __init__(
        self,
        raw_text: str,
        configured: bool = True,
        provenance: str = "agent_grounded",
        tool_queries: tuple[str, ...] = (),
    ) -> None:
        self.raw_text = raw_text
        self.configured = configured
        self.provenance = provenance
        self.tool_queries = tool_queries
        self.calls: list[dict[str, object]] = []

    def is_configured(self) -> bool:
        return self.configured

    async def run_place_lookup_task(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            raw_text=self.raw_text,
            provenance=self.provenance,
            tool_queries=self.tool_queries,
        )


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
        )
    )
    agent = FakeAgentRuntime(
        """
        {
          "candidates": [
            {
              "name": "上海市第一妇婴保健院",
              "address": "上海市浦东新区高科西路2699号",
              "latitude": 31.2169,
              "longitude": 121.4541,
              "coordinateSystem": "WGS84",
              "accuracy": "poi",
              "locationType": "poi",
              "scopeMatchStatus": "match",
              "scopeMatchReason": "The address is inside Shanghai.",
              "source": "Search result coordinates",
              "evidence": "Coordinates listed near Shanghai First Maternity hospital.",
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
    assert response.attempted_sources == ["agent"]
    assert response.rejected_count == 0
    assert response.options[0].source == "agent"
    assert response.options[0].label == "上海市第一妇婴保健院"
    assert (
        response.options[0].raw_evidence
        == "Coordinates listed near Shanghai First Maternity hospital."
    )
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
    assert response.agent_error == "agent place lookup failed"
    assert response.options[0].verification_status == "city-fallback"


def test_precise_lookup_rejects_agent_coordinates_without_provenance(tmp_path) -> None:
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
        )
    )
    agent = FakeAgentRuntime(
        '{"candidates":[{"label":"医院","latitude":31.2169,"longitude":121.4541}]}',
        provenance="agent_final",
    )
    lookup = PrecisePlaceLookupService(place_service, agent)  # type: ignore[arg-type]

    response = asyncio.run(
        lookup.search_precise(
            query="上海第一妇婴保健院",
            city_context="Shanghai, Shanghai, China",
            limit=8,
        )
    )

    assert response.options[0].verification_status == "city-fallback"
    assert response.fallback_source is None


def test_precise_lookup_does_not_override_agent_entity_reasoning_with_text_matching(
    tmp_path,
) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Zibo,淄博|Zibo,Shandong,China,36.79056,118.06333,8\n",
        encoding="utf-8",
    )
    place_service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
        )
    )
    agent = FakeAgentRuntime(
        """
        {
          "candidates": [
            {
              "label": "淄博市中心医院",
              "address": "山东省淄博市张店区",
              "latitude": 36.79000,
              "longitude": 118.07000,
              "accuracy": "poi",
              "coordinateSystem": "WGS84",
              "locationType": "poi",
              "scopeMatchStatus": "match",
              "scopeMatchReason": "The address is inside Zibo.",
              "rawEvidence": "淄博市中心医院位于山东省淄博市张店区。"
            }
          ]
        }
        """
    )
    lookup = PrecisePlaceLookupService(place_service, agent)  # type: ignore[arg-type]

    response = asyncio.run(
        lookup.search_precise(
            query="zi bo shi li yi yuan",
            city_context="Zibo, Shandong, China",
            limit=8,
        )
    )

    assert response.options[0].verification_status == "verified"
    assert response.options[0].source == "agent"
    assert response.options[0].label == "淄博市中心医院"
    assert response.fallback_source == "agent"


def test_precise_lookup_falls_back_when_agent_candidate_conflicts_with_selected_district(
    monkeypatch, tmp_path
) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Shanghai,上海|Shanghai,Shanghai,China,31.22222,121.45806,8\n"
        "Pudong,浦东|Pudong,Shanghai,China,31.23995,121.50094,8\n",
        encoding="utf-8",
    )
    place_service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
        )
    )
    monkeypatch.setattr(place_service, "_timezone_for", lambda lat, lon, hours: "Asia/Shanghai")
    agent = FakeAgentRuntime(
        """
        {
          "candidates": [
            {
              "name": "上海市第一妇婴保健院西院",
              "address": "静安区长乐路536号, Shanghai, China",
                      "latitude": 31.22217,
                      "longitude": 121.45168,
                      "coordinateSystem": "WGS84",
                      "accuracy": "poi",
                      "locationType": "poi",
                      "scopeMatchStatus": "conflict",
                      "scopeMatchReason": "The west campus is in Jing'an, not Pudong.",
              "evidence": "Map evidence for the west campus."
            }
          ]
        }
        """
    )
    lookup = PrecisePlaceLookupService(place_service, agent)  # type: ignore[arg-type]

    response = asyncio.run(
        lookup.search_precise(
            query="上海市第一妇婴保健院",
            city_context="Pudong, Shanghai, China",
            limit=8,
        )
    )

    assert len(agent.calls) == 1
    assert agent.calls[0]["city_label"] == "Pudong, Shanghai, China"
    assert agent.calls[0]["selected_scope_label"] == "Pudong, Shanghai, China"
    assert response.verification_base == "Pudong, Shanghai, China"
    assert response.options[0].source == "geonames-local"
    assert response.options[0].verification_status == "city-fallback"
    assert response.options[0].city_label == "Pudong, Shanghai, China"


def test_precise_lookup_keeps_only_the_candidate_in_selected_district(tmp_path) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Shanghai,上海|Shanghai,Shanghai,China,31.22222,121.45806,8\n"
        "Pudong,浦东|Pudong,Shanghai,China,31.23995,121.50094,8\n",
        encoding="utf-8",
    )
    place_service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
        )
    )
    agent = FakeAgentRuntime(
        """
        {
          "candidates": [
            {
              "name": "上海市第一妇婴保健院西院",
                  "address": "上海市静安区长乐路536号",
                  "latitude": 31.22217,
                  "longitude": 121.45168,
                  "coordinateSystem": "WGS84",
                  "accuracy": "poi",
                  "locationType": "poi",
                  "scopeMatchStatus": "conflict",
                  "scopeMatchReason": "The west campus is in Jing'an, not Pudong.",
                  "evidence": "Search evidence for the west campus."
                },
                {
                  "name": "上海市第一妇婴保健院东院",
                  "address": "上海市浦东新区高科西路2699号",
                      "latitude": 31.19174,
                      "longitude": 121.54581,
                      "coordinateSystem": "WGS84",
                      "accuracy": "poi",
                      "locationType": "poi",
                      "scopeMatchStatus": "match",
                      "scopeMatchReason": "The east campus is in Pudong.",
                  "evidence": "Search evidence for the east campus."
                }
          ]
        }
        """
    )
    lookup = PrecisePlaceLookupService(place_service, agent)  # type: ignore[arg-type]

    response = asyncio.run(
        lookup.search_precise(
            query="第一妇婴保健院",
            city_context="Pudong, Shanghai, China",
            limit=8,
        )
    )

    assert [option.label for option in response.options] == ["上海市第一妇婴保健院东院"]
    assert response.options[0].verification_status == "verified"


def test_precise_lookup_uses_readable_scope_for_china_catalog_id() -> None:
    from app.settings import Settings

    place_service = PlaceService(Settings(_env_file=None))
    agent = FakeAgentRuntime(
        """
        {
          "candidates": [
            {
              "label": "上海市第一妇婴保健院西院",
              "address": "上海市静安区长乐路536号",
              "latitude": 31.22217,
              "longitude": 121.45168,
              "coordinateSystem": "WGS84",
              "accuracy": "poi",
              "locationType": "poi",
              "scopeMatchStatus": "conflict",
              "scopeMatchReason": "静安区不属于用户选择的浦东新区。",
              "rawEvidence": "西院位于静安区。"
            },
            {
              "label": "上海市第一妇婴保健院东院",
              "address": "上海市浦东新区高科西路2699号",
              "latitude": 31.19174,
              "longitude": 121.54581,
              "coordinateSystem": "WGS84",
              "accuracy": "poi",
              "locationType": "poi",
              "scopeMatchStatus": "match",
              "scopeMatchReason": "地址明确位于用户选择的浦东新区。",
              "rawEvidence": "东院位于浦东新区。"
            }
          ]
        }
        """
    )
    lookup = PrecisePlaceLookupService(place_service, agent)  # type: ignore[arg-type]

    response = asyncio.run(
        lookup.search_precise(
            query="第一妇婴保健院",
            city_context="CN-310115",
            limit=8,
        )
    )

    assert agent.calls[0]["city_label"] == "浦东新区, 上海市, China"
    assert agent.calls[0]["selected_scope_label"] == "浦东新区, 上海市, China"
    assert [option.label for option in response.options] == ["上海市第一妇婴保健院东院"]


def test_precise_lookup_leaves_search_planning_to_agent(tmp_path) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Suzhou,宿州|宿州市|Suzhou,Anhui,China,33.63611,116.97889,8\n",
        encoding="utf-8",
    )
    place_service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
        )
    )
    agent = FakeAgentRuntime(
        '{"candidates": []}',
        tool_queries=("泗县人民医院 安徽 宿州 经纬度", "泗县人民医院 坐标"),
    )
    lookup = PrecisePlaceLookupService(place_service, agent)  # type: ignore[arg-type]

    response = asyncio.run(
        lookup.search_precise(
            query="泗县人民医院",
            city_context="Suzhou, Anhui, China",
            limit=8,
        )
    )

    assert len(agent.calls) == 1
    assert "search_queries" not in agent.calls[0]
    assert "max_distance_km" not in agent.calls[0]
    assert response.agent_search_queries == [
        "泗县人民医院 安徽 宿州 经纬度",
        "泗县人民医院 坐标",
    ]


def test_precise_lookup_rejects_nearby_candidate_outside_selected_city(tmp_path) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Suzhou,宿州|宿州市|Suzhou,Anhui,China,33.63611,116.97889,8\n",
        encoding="utf-8",
    )
    place_service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
        )
    )
    agent = FakeAgentRuntime(
        """
        {
          "candidates": [
            {
              "label": "人民公园",
              "address": "安徽省淮北市相山区人民中路",
              "latitude": 33.72000,
              "longitude": 116.85000,
              "coordinateSystem": "WGS84",
              "accuracy": "poi",
              "locationType": "poi",
              "scopeMatchStatus": "conflict",
              "scopeMatchReason": "The address is in Huaibei, not the selected Suzhou city.",
              "rawEvidence": "搜索结果明确标注安徽省淮北市人民公园。"
            }
          ]
        }
        """
    )
    lookup = PrecisePlaceLookupService(place_service, agent)  # type: ignore[arg-type]

    response = asyncio.run(
        lookup.search_precise(
            query="人民公园",
            city_context="Suzhou, Anhui, China",
            limit=8,
        )
    )

    assert len(response.options) == 1
    assert response.options[0].label == "Suzhou, Anhui, China"
    assert response.options[0].verification_status == "city-fallback"


def test_precise_lookup_reports_backend_progress_stages(tmp_path) -> None:
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
        )
    )
    agent = FakeAgentRuntime(
        """
        {
          "candidates": [
            {
              "label": "上海市第一妇婴保健院东院",
              "address": "上海市浦东新区高科西路2699号",
              "latitude": 31.19174,
              "longitude": 121.54581,
              "coordinateSystem": "WGS84",
              "accuracy": "poi",
              "locationType": "poi",
              "scopeMatchStatus": "match",
              "scopeMatchReason": "The address is inside Shanghai.",
              "rawEvidence": "搜索结果给出院区坐标。"
            }
          ]
        }
        """
    )
    lookup = PrecisePlaceLookupService(place_service, agent)  # type: ignore[arg-type]
    progress: list[tuple[str, dict[str, object]]] = []

    async def capture(stage: str, payload: dict[str, object]) -> None:
        progress.append((stage, payload))

    asyncio.run(
        lookup.search_precise(
            query="第一妇婴保健院",
            city_context="Shanghai, Shanghai, China",
            limit=8,
            progress_callback=capture,
        )
    )

    assert [stage for stage, _payload in progress] == [
        "resolving",
        "searching",
        "matching",
        "complete",
    ]
    assert progress[-1][1]["optionCount"] == 1


def test_precise_lookup_classifies_county_center_as_district_accuracy(tmp_path) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Suzhou,宿州|宿州市|Suzhou,Anhui,China,33.63611,116.97889,8\n",
        encoding="utf-8",
    )
    place_service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
        )
    )
    agent = FakeAgentRuntime(
        """
        {
          "candidates": [
            {
              "label": "泗县",
              "address": "安徽省宿州市泗县",
              "latitude": 33.48530,
              "longitude": 117.90480,
              "coordinateSystem": "WGS84",
              "accuracy": "poi",
              "locationType": "county",
              "scopeMatchStatus": "match",
              "scopeMatchReason": "泗县属于宿州市。",
              "rawEvidence": "搜索结果给出泗县行政中心坐标。"
            }
          ]
        }
        """
    )
    lookup = PrecisePlaceLookupService(place_service, agent)  # type: ignore[arg-type]

    response = asyncio.run(
        lookup.search_precise(
            query="泗县",
            city_context="Suzhou, Anhui, China",
            limit=8,
        )
    )

    assert response.options[0].label == "泗县"
    assert response.options[0].location_type == "county"
    assert response.options[0].accuracy == "district"
