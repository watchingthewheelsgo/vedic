from __future__ import annotations

import json
from types import SimpleNamespace

from app.agents.claude_runtime import ClaudeRuntime


def _runtime() -> ClaudeRuntime:
    return ClaudeRuntime(
        SimpleNamespace(
            place_lookup_trace_enabled=False,
            place_lookup_trace_max_chars=4000,
        )
    )


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
