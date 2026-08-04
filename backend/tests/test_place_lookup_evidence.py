from __future__ import annotations

import json
from types import SimpleNamespace

from app.agents.claude_runtime import AgentRunResult, ClaudeRuntime


def _runtime() -> ClaudeRuntime:
    return ClaudeRuntime(
        SimpleNamespace(
            place_lookup_trace_enabled=False,
            place_lookup_trace_max_chars=4000,
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


def test_place_lookup_recovers_candidate_json_from_sdk_error_boundary() -> None:
    runtime = _runtime()

    recovered = runtime._recover_place_lookup_result(
        "tool_use",
        '{"candidates":[{"label":"医院","latitude":31.1,"longitude":121.5}]}',
    )

    assert recovered is not None
    assert json.loads(recovered)["candidates"][0]["label"] == "医院"


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
