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


def test_place_lookup_hook_records_tool_result_for_agent_grounding() -> None:
    runtime = _runtime()
    observations: list[dict[str, object]] = []

    decision = asyncio.run(
        runtime._trace_place_tool_use(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "WebSearch",
                "tool_input": {"query": "环球港 普陀 经纬度"},
                "tool_response": {
                    "summary": ("上海环球港位于上海市普陀区中山北路3300号。坐标由搜索结果提供。")
                },
            },
            "tool-1",
            object(),
            city_label="普陀区, 上海市, China",
            tool_observations=observations,
        )
    )

    assert decision == {"continue_": True, "suppressOutput": False}
    assert observations == [
        {
            "tool_name": "WebSearch",
            "tool_use_id": "tool-1",
            "tool_input": {"query": "环球港 普陀 经纬度"},
            "tool_response": {
                "summary": ("上海环球港位于上海市普陀区中山北路3300号。坐标由搜索结果提供。")
            },
        }
    ]


def test_place_lookup_hook_emits_real_tool_verification_progress() -> None:
    runtime = _runtime()
    progress: list[tuple[str, dict[str, object]]] = []

    async def capture(stage: str, payload: dict[str, object]) -> None:
        progress.append((stage, payload))

    asyncio.run(
        runtime._trace_place_tool_use(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "WebSearch",
                "tool_input": {"query": "泗县人民医院 经纬度"},
                "tool_response": {"summary": "未找到明确坐标。"},
            },
            "tool-progress",
            object(),
            tool_observations=[],
            selected_scope_label="泗县, 宿州市, 安徽省, China",
            progress_callback=capture,
        )
    )

    assert progress == [
        (
            "verifying",
            {
                "tool": "WebSearch",
                "query": "泗县人民医院 经纬度",
                "scope": "泗县, 宿州市, 安徽省, China",
            },
        )
    ]


def test_structured_output_is_not_counted_as_web_evidence_or_search_progress() -> None:
    runtime = _runtime()
    observations: list[dict[str, object]] = []
    progress: list[tuple[str, dict[str, object]]] = []

    async def capture(stage: str, payload: dict[str, object]) -> None:
        progress.append((stage, payload))

    asyncio.run(
        runtime._trace_place_tool_use(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "StructuredOutput",
                "tool_input": {"topicIds": []},
                "tool_response": {"ok": True},
            },
            "structured-output",
            object(),
            tool_observations=observations,
            progress_callback=capture,
        )
    )

    assert observations == []
    assert progress == []


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

    result = asyncio.run(
        runtime.run_place_lookup_task(
            query="泗县人民医院",
            city_label="Suzhou, Anhui, China",
        )
    )

    assert captured["max_turns"] == 3
    assert captured["output_format"] == {
        "type": "json_schema",
        "schema": runtime._place_lookup_schema(),
    }
    assert result.provenance == "agent_final"


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
