from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.agents.claude_runtime import AgentRunResult, ClaudeRuntime


def _runtime() -> ClaudeRuntime:
    return ClaudeRuntime(
        SimpleNamespace(
            place_lookup_trace_enabled=False,
            place_lookup_trace_max_chars=4000,
            agent_timeout_ms=5_000,
        )
    )


def test_grounding_audit_prefers_a_distinct_configured_model() -> None:
    runtime = ClaudeRuntime(
        SimpleNamespace(
            anthropic_model="writer-model",
            anthropic_default_haiku_model="audit-model",
            anthropic_default_opus_model="",
        )
    )

    assert runtime._prompt_task_model("vedicdust-consultation") == "writer-model"
    assert runtime._prompt_task_model("vedicdust-consultation-grounding-audit") == "audit-model"


def test_place_lookup_tool_evidence_accepts_verified_poi_coordinates() -> None:
    raw_text = """
    根据搜索结果，淄博市市立医院（即临淄区人民医院）的地址为：
    山东省淄博市临淄区桓公路139号。

    以下是该地址的经纬度坐标：
    纬度（Latitude）：36.8249° N
    经度（Longitude）：118.3165° E
    """

    result = _runtime()._place_lookup_json_from_tool_observations(
        query="淄博市立医院",
        city_label="Zibo, Shandong, China",
        city_lat=36.79056,
        city_lon=118.06333,
        max_distance_km=150.0,
        max_results=5,
        observations=[
            {
                "tool_name": "WebSearch",
                "tool_input": {"query": "淄博市立医院 经纬度"},
                "tool_response": {"query": "淄博市立医院 经纬度", "summary": raw_text},
            }
        ],
    )

    assert result is not None
    payload = json.loads(result)
    assert payload["candidates"][0]["latitude"] == 36.8249
    assert payload["candidates"][0]["longitude"] == 118.3165
    assert payload["candidates"][0]["accuracy"] == "poi"
    assert "医院" in payload["candidates"][0]["label"]
    assert "临淄区人民医院" in payload["candidates"][0]["rawEvidence"]


def test_place_lookup_tool_evidence_accepts_pinyin_query_with_chinese_poi_evidence() -> None:
    raw_text = """
    淄博市市立医院又称淄博市临淄区人民医院，位于山东省淄博市临淄区桓公路139号。
    坐标：36.8249, 118.3165。
    """

    result = _runtime()._place_lookup_json_from_tool_observations(
        query="zi bo shi li yi yuan",
        city_label="Zibo, Shandong, China",
        city_lat=36.79056,
        city_lon=118.06333,
        max_distance_km=150.0,
        max_results=5,
        observations=[
            {
                "tool_name": "WebSearch",
                "tool_input": {"query": "zi bo shi li yi yuan Zibo Shandong China coordinates"},
                "tool_response": {"result": raw_text},
            }
        ],
    )

    assert result is not None
    payload = json.loads(result)
    assert payload["candidates"][0]["latitude"] == 36.8249
    assert payload["candidates"][0]["longitude"] == 118.3165


def test_place_lookup_tool_evidence_rejects_same_city_wrong_pinyin_entity() -> None:
    raw_text = """
    淄博市中心医院位于山东省淄博市张店区。坐标：36.79000, 118.07000。
    """

    result = _runtime()._place_lookup_json_from_tool_observations(
        query="zi bo shi li yi yuan",
        city_label="Zibo, Shandong, China",
        city_lat=36.79056,
        city_lon=118.06333,
        max_distance_km=150.0,
        max_results=5,
        observations=[
            {
                "tool_name": "WebSearch",
                "tool_response": {"result": raw_text},
            }
        ],
    )

    assert result is None


def test_place_lookup_tool_evidence_rejects_generic_entity_query() -> None:
    result = _runtime()._place_lookup_json_from_tool_observations(
        query="医院",
        city_label="Zibo, Shandong, China",
        city_lat=36.79056,
        city_lon=118.06333,
        max_distance_km=150.0,
        max_results=5,
        observations=[
            {
                "tool_name": "WebSearch",
                "tool_response": {
                    "result": "淄博市中心医院位于山东省淄博市张店区。坐标：36.79000, 118.07000。"
                },
            }
        ],
    )

    assert result is None


def test_place_lookup_tool_evidence_reads_sdk_content_blocks() -> None:
    result = _runtime()._place_lookup_json_from_tool_observations(
        query="泗县人民医院",
        city_label="Suzhou, Anhui, China",
        city_lat=33.63611,
        city_lon=116.97889,
        max_distance_km=150.0,
        max_results=5,
        observations=[
            {
                "tool_name": "WebSearch",
                "tool_response": {
                    "results": [
                        {
                            "title": "泗县人民医院",
                            "url": "https://example.test/hospital",
                        }
                    ],
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "泗县人民医院位于安徽省宿州市泗县花园路120号。"
                                "纬度：33.50117，经度：117.88762。"
                            ),
                        }
                    ],
                },
            }
        ],
    )

    assert result is not None
    payload = json.loads(result)
    assert payload["candidates"][0]["latitude"] == 33.50117
    assert payload["candidates"][0]["longitude"] == 117.88762
    assert payload["candidates"][0]["sourceUrl"] == "https://example.test/hospital"


def test_place_lookup_tool_evidence_reads_structured_coordinate_fields() -> None:
    result = _runtime()._place_lookup_json_from_tool_observations(
        query="泗县人民医院",
        city_label="Suzhou, Anhui, China",
        city_lat=33.63611,
        city_lon=116.97889,
        max_distance_km=150.0,
        max_results=5,
        observations=[
            {
                "tool_name": "WebFetch",
                "tool_response": {
                    "name": "泗县人民医院",
                    "url": "https://example.test/structured-hospital",
                    "latitude": 33.50117,
                    "longitude": 117.88762,
                    "address": "安徽省宿州市泗县花园路120号",
                },
            }
        ],
    )

    assert result is not None
    payload = json.loads(result)
    assert payload["candidates"][0]["latitude"] == 33.50117
    assert payload["candidates"][0]["longitude"] == 117.88762
    assert payload["candidates"][0]["sourceUrl"] == "https://example.test/structured-hospital"


def test_place_lookup_tool_evidence_reads_provider_specific_summary_fields() -> None:
    result = _runtime()._place_lookup_json_from_tool_observations(
        query="泗县人民医院",
        city_label="Suzhou, Anhui, China",
        city_lat=33.63611,
        city_lon=116.97889,
        max_distance_km=150.0,
        max_results=5,
        observations=[
            {
                "tool_name": "WebSearch",
                "tool_response": {
                    "query": "泗县人民医院 经纬度",
                    "results": [{"title": "泗县人民医院", "url": "https://example.test/hospital"}],
                    "providerSummary": (
                        "泗县人民医院位于安徽省宿州市泗县。纬度 33.50117，经度 117.88762。"
                    ),
                },
            }
        ],
    )

    assert result is not None
    payload = json.loads(result)
    assert payload["candidates"][0]["latitude"] == 33.50117
    assert payload["candidates"][0]["longitude"] == 117.88762


def test_place_lookup_tool_evidence_extracts_multi_campus_labelled_coordinates() -> None:
    raw_text = """
    ## 上海市第一妇婴保健院 经纬度

    ### 东院（浦东新区）
    - 地址：上海市浦东新区高科西路2699号
    - 纬度：31.19174° N（北纬31°11′30″）
    - 经度：121.54581° E（东经121°32′45″）

    ### 西院（静安区）
    - 地址：上海市静安区长乐路536号（近陕西南路）
    - 纬度：31.22217° N（北纬31°13′20″）
    - 经度：121.45168° E（东经121°27′6″）
    """

    result = _runtime()._place_lookup_json_from_tool_observations(
        query="第一妇婴保健院",
        city_label="Shanghai, Shanghai, China",
        city_lat=31.22222,
        city_lon=121.45806,
        max_distance_km=150.0,
        max_results=5,
        observations=[{"tool_response": {"summary": raw_text}}],
    )

    assert result is not None
    payload = json.loads(result)
    assert len(payload["candidates"]) == 2
    coordinates = {
        (candidate["latitude"], candidate["longitude"]) for candidate in payload["candidates"]
    }
    assert coordinates == {(31.19174, 121.54581), (31.22217, 121.45168)}
    assert any("东院" in candidate["label"] for candidate in payload["candidates"])
    assert any("西院" in candidate["label"] for candidate in payload["candidates"])


def test_place_lookup_tool_evidence_rejects_city_center_coordinates_for_poi() -> None:
    raw_text = """
    Here are the latitude and longitude coordinates for Zibo, Shandong, China.
    General consensus coordinates: 36.79056, 118.06333.
    These are the city center coordinates.
    """

    result = _runtime()._place_lookup_json_from_tool_observations(
        query="淄博市立医院",
        city_label="Zibo, Shandong, China",
        city_lat=36.79056,
        city_lon=118.06333,
        max_distance_km=150.0,
        max_results=5,
        observations=[
            {
                "tool_name": "WebSearch",
                "tool_input": {"query": "淄博市立医院 经纬度"},
                "tool_response": {"summary": raw_text},
            }
        ],
    )

    assert result is None


def test_place_lookup_final_candidate_detection() -> None:
    runtime = _runtime()

    assert runtime._place_lookup_result_has_candidates(
        '{"candidates":[{"label":"A","latitude":1,"longitude":2}]}'
    )
    assert runtime._place_lookup_result_has_candidates(
        '```json\n{"candidates":[{"label":"A","latitude":1,"longitude":2}]}\n```'
    )
    assert not runtime._place_lookup_result_has_candidates('{"candidates":[]}')
    assert not runtime._place_lookup_result_has_candidates("not json")

    assert runtime._place_lookup_result_has_wgs84_coordinates(
        '{"candidates":[{"latitude":31.1,"longitude":121.5,"coordinateSystem":"WGS84"}]}'
    )
    assert not runtime._place_lookup_result_has_wgs84_coordinates(
        '{"candidates":[{"latitude":31.1,"longitude":121.5,"coordinateSystem":"unknown"}]}'
    )


def test_place_lookup_hook_stops_after_valid_wgs84_tool_evidence() -> None:
    runtime = _runtime()
    tool_state: dict[str, object] = {"tool_count": 0, "verified_json": None}
    observations: list[dict[str, object]] = []

    decision = asyncio.run(
        runtime._trace_place_tool_use(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "WebSearch",
                "tool_response": {
                    "results": [
                        {
                            "title": "泗县人民医院",
                            "url": "https://mapcarta.com/W1006725799",
                        }
                    ],
                    "summary": (
                        "泗县人民医院位于安徽省宿州市泗县。WGS84 坐标：33.50117, 117.88762。"
                    ),
                },
            },
            "tool-1",
            object(),
            query="泗县人民医院",
            city_label="Suzhou, Anhui, China",
            city_lat=33.63611,
            city_lon=116.97889,
            max_distance_km=150.0,
            tool_observations=observations,
            tool_state=tool_state,
        )
    )

    assert decision["continue_"] is False
    assert isinstance(tool_state["verified_json"], str)
    assert observations


def test_place_lookup_hook_continues_when_coordinate_datum_is_unknown() -> None:
    runtime = _runtime()
    tool_state: dict[str, object] = {"tool_count": 0, "verified_json": None}
    observations: list[dict[str, object]] = []

    decision = asyncio.run(
        runtime._trace_place_tool_use(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "WebSearch",
                "tool_response": {
                    "results": [{"title": "泗县人民医院", "url": "https://example.test/hospital"}],
                    "summary": "泗县人民医院位于安徽省宿州市泗县。坐标：33.50117, 117.88762。",
                },
            },
            "tool-2",
            object(),
            query="泗县人民医院",
            city_label="Suzhou, Anhui, China",
            city_lat=33.63611,
            city_lon=116.97889,
            max_distance_km=150.0,
            tool_observations=observations,
            tool_state=tool_state,
        )
    )

    assert decision["continue_"] is True
    assert tool_state["verified_json"] is None


def test_place_lookup_recovers_candidate_json_from_sdk_error_boundary() -> None:
    runtime = _runtime()

    recovered = runtime._recover_place_lookup_result(
        "tool_use",
        '{"candidates":[{"label":"医院","latitude":31.1,"longitude":121.5}]}',
    )

    assert recovered is not None
    assert json.loads(recovered)["candidates"][0]["label"] == "医院"


def test_run_query_recovers_candidate_json_from_real_sdk_error_message(monkeypatch) -> None:
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

    runtime = _runtime()
    payload = '{"candidates":[{"label":"泗县人民医院","latitude":33.50117,"longitude":117.88762}]}'

    async def fake_query(*, prompt: str, options: object):
        del prompt, options
        yield AssistantMessage(
            content=[TextBlock(text=payload)],
            model="test-model",
            session_id="session-1",
        )
        yield ResultMessage(
            subtype="error_during_execution",
            duration_ms=123,
            duration_api_ms=100,
            is_error=True,
            num_turns=1,
            session_id="session-1",
            stop_reason="tool_use",
            result="tool_use",
        )

    monkeypatch.setattr("claude_agent_sdk.query", fake_query)

    result = asyncio.run(
        runtime._run_query(
            "precise-place-agent-lookup",
            "find place",
            object(),
            trace_label="place_lookup",
            model_name="test-model",
        )
    )

    assert json.loads(result.raw_text)["candidates"][0]["label"] == "泗县人民医院"
    assert result.session_id == "session-1"
    assert result.stop_reason == "tool_use"


def test_place_lookup_uses_configured_agent_turn_budget(monkeypatch) -> None:
    from app.settings import Settings

    monkeypatch.setenv("VEDIC_AI_MODE", "claude")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("PLACE_LOOKUP_AGENT_MAX_TURNS", "3")
    monkeypatch.setenv("PLACE_LOOKUP_TRACE_ENABLED", "false")
    settings = Settings(_env_file=None)
    runtime = ClaudeRuntime(settings)
    captured: dict[str, object] = {}

    class FakeOptions:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    async def fake_run_query(
        task_name: str, prompt: str, options: object, **kwargs: object
    ) -> AgentRunResult:
        del task_name, prompt, options, kwargs
        return AgentRunResult(mode="claude", raw_text='{"candidates":[]}')

    monkeypatch.setattr("claude_agent_sdk.ClaudeAgentOptions", FakeOptions)
    monkeypatch.setattr(runtime, "_run_query", fake_run_query)

    asyncio.run(
        runtime.run_place_lookup_task(
            query="泗县人民医院",
            city_label="Suzhou, Anhui, China",
            city_lat=33.63611,
            city_lon=116.97889,
            max_distance_km=150.0,
        )
    )

    assert captured["max_turns"] == 3


def test_run_query_does_not_swallow_sdk_error_without_candidate_json(monkeypatch) -> None:
    from claude_agent_sdk import ResultMessage

    runtime = _runtime()

    async def fake_query(*, prompt: str, options: object):
        del prompt, options
        yield ResultMessage(
            subtype="error_during_execution",
            duration_ms=123,
            duration_api_ms=100,
            is_error=True,
            num_turns=1,
            session_id="session-2",
            stop_reason="tool_use",
            result="tool_use",
        )

    monkeypatch.setattr("claude_agent_sdk.query", fake_query)

    with pytest.raises(RuntimeError, match="tool_use"):
        asyncio.run(
            runtime._run_query(
                "precise-place-agent-lookup",
                "find place",
                object(),
                trace_label="place_lookup",
                model_name="test-model",
            )
        )


def test_verified_tool_evidence_overrides_agent_candidate_json() -> None:
    runtime = _runtime()
    agent_result = AgentRunResult(
        mode="claude",
        raw_text='{"candidates":[{"label":"wrong","latitude":1,"longitude":2}]}',
        session_id="session-1",
        duration_ms=123,
        total_cost_usd=0.01,
        stop_reason="end_turn",
        model="test-model",
    )

    resolved = runtime._finalize_place_lookup_result(
        agent_result,
        '{"candidates":[{"label":"verified","latitude":31.1,"longitude":121.5}]}',
    )

    payload = json.loads(resolved.raw_text)
    assert payload["candidates"][0]["label"] == "verified"
    assert payload["candidates"][0]["latitude"] == 31.1
    assert resolved.session_id == "session-1"
    assert resolved.stop_reason == "end_turn"
