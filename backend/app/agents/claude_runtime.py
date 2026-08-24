from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal, cast

import httpx

from app.settings import Settings


logger = logging.getLogger(__name__)
place_trace_logger = logging.getLogger("uvicorn.error")
performance_logger = logging.getLogger("uvicorn.error")

AgentEffort = Literal["low", "medium", "high", "xhigh", "max"]
AgentProvenance = Literal["tool_observation", "agent_grounded", "agent_final"]


@dataclass(frozen=True)
class AgentRunResult:
    mode: Literal["claude", "mock"]
    raw_text: str
    session_id: str | None = None
    duration_ms: int | None = None
    total_cost_usd: float | None = None
    stop_reason: str | None = None
    model: str | None = None
    # Place lookup is product-eligible only when the same Agent turn observed a
    # WebSearch/WebFetch result. The Agent remains responsible for interpreting
    # that evidence and returning the typed decision.
    provenance: AgentProvenance = "agent_final"
    tool_queries: tuple[str, ...] = ()


class ClaudeRuntime:
    """Thin adapter around Claude Agent SDK with DeepSeek-compatible env."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return self.settings.vedic_ai_mode != "mock" and bool(self.settings.get_agent_auth_token())

    def config_summary(self) -> dict[str, object]:
        return self.settings.agent_config_summary()

    async def run_skill_task(
        self,
        task_name: str,
        prompt: str,
        *,
        cwd: Path,
        skills: list[str],
        max_turns: int | None = None,
    ) -> AgentRunResult:
        if not self.is_configured():
            raise RuntimeError("Claude Agent SDK runtime is not configured")

        from claude_agent_sdk import ClaudeAgentOptions

        options = ClaudeAgentOptions(
            tools=["Read", "Write", "Edit", "Glob", "Grep"],
            allowed_tools=[
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep",
                *self._backend_tool_names(),
            ],
            disallowed_tools=["Bash", "WebFetch", "WebSearch"],
            permission_mode="dontAsk",
            setting_sources=["project"],
            cwd=cwd,
            add_dirs=[cwd],
            mcp_servers=self._backend_tool_server(),
            env=self._agent_env(),
            model=self.settings.anthropic_model,
            max_turns=max_turns or self.settings.agent_max_turns,
            effort=cast(AgentEffort, self._agent_effort()),
            skills=skills,
            system_prompt=(
                "You are running a repo-local astrology skill workflow inside a web "
                "session workspace. Treat the current working directory as the user's skill "
                "workspace. Follow the selected skill's file names, phase order, interaction "
                "rules, and exact artifact contract. Markdown workflows must write Markdown; "
                "VedicDust contract workflows must write only their requested typed JSON. "
                "Do not invent checkout flows, daily notes, or extra summaries. Use only files "
                "in this workspace and the selected skill instructions."
            ),
        )
        return await self._run_query(
            task_name,
            prompt,
            options,
            model_name=self.settings.anthropic_model,
        )

    async def run_skill_prompt_task(
        self,
        task_name: str,
        prompt: str,
        *,
        skills: list[str],
        max_turns: int | None = None,
        allow_file_tools: bool = True,
        effort: AgentEffort | None = None,
    ) -> AgentRunResult:
        if not self.is_configured():
            raise RuntimeError("Claude Agent SDK runtime is not configured")

        from claude_agent_sdk import ClaudeAgentOptions

        # File tools are optional because workflows handling blind validation
        # evidence receive a backend-sanitized prompt and must not inspect the
        # project or persisted session workspaces. Other skills may still read
        # their own resources/*.md framework files. Write/Edit remain disabled:
        # the backend persists artifacts from the JSON wrapper.
        file_tools = ["Read", "Glob", "Grep"] if allow_file_tools else []
        model_name = self._prompt_task_model(task_name)
        options = ClaudeAgentOptions(
            tools=file_tools,
            allowed_tools=[*file_tools, *self._backend_tool_names()],
            disallowed_tools=["Bash", "Write", "Edit", "WebFetch", "WebSearch"],
            permission_mode="dontAsk",
            setting_sources=["project"],
            cwd=Path.cwd(),
            add_dirs=[Path.cwd()],
            env=self._agent_env(),
            model=model_name,
            max_turns=max_turns or self.settings.agent_max_turns,
            effort=cast(AgentEffort, effort or self._agent_effort()),
            skills=skills,
            system_prompt=(
                "You are adapting a repo-local astrology skill workflow into file artifacts. "
                "You may use Read/Glob/Grep to open the selected skill's own resources/*.md files "
                "when its instructions reference them. After following the skill, return only the "
                "requested JSON wrapper. Artifact content must preserve the selected skill's markdown "
                "style, phase order, and interaction rules. Do not add app cards, daily notes, "
                "checkout flows, or extra summaries."
            ),
        )
        return await self._run_query(
            task_name,
            prompt,
            options,
            model_name=model_name,
        )

    async def run_direct_prompt_task(
        self,
        task_name: str,
        prompt: str,
        *,
        model_name: str | None = None,
        max_tokens: int = 1800,
    ) -> AgentRunResult:
        """Run a bounded no-tool prompt without starting an Agent SDK session."""

        if not self.is_configured():
            raise RuntimeError("Claude runtime is not configured")

        model = model_name or self.settings.anthropic_default_haiku_model
        model = model or self.settings.anthropic_model
        token = self.settings.get_agent_auth_token()
        started_perf = time.perf_counter()
        performance_logger.info(
            "agent_timing event=start task=%s transport=messages_api model=%s effort=none "
            "max_turns=1 prompt_chars=%s",
            task_name,
            model,
            len(prompt),
        )
        try:
            async with httpx.AsyncClient(timeout=self.settings.agent_timeout_ms / 1000) as client:
                response = await client.post(
                    self.settings.anthropic_base_url.rstrip("/") + "/v1/messages",
                    headers={
                        "x-api-key": token,
                        "authorization": f"Bearer {token}",
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": max_tokens,
                        "temperature": 0.2,
                        "thinking": {"type": "disabled"},
                        "system": (
                            "You are executing one bounded astrology evidence-writing task. "
                            "Use only the supplied evidence, obey its stability restrictions, "
                            "and return only the requested JSON contract. You have no tools and "
                            "must not request files or continue researching."
                        ),
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except BaseException as exc:
            performance_logger.warning(
                "agent_timing event=failed task=%s transport=messages_api model=%s "
                "prompt_chars=%s wall_ms=%s error_type=%s",
                task_name,
                model,
                len(prompt),
                round((time.perf_counter() - started_perf) * 1000),
                type(exc).__name__,
            )
            raise

        content = payload.get("content") if isinstance(payload, dict) else None
        text_parts = (
            [
                str(item.get("text"))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text")
            ]
            if isinstance(content, list)
            else []
        )
        raw_text = "\n".join(text_parts).strip()
        if not raw_text:
            block_types = (
                [
                    str(item.get("type"))
                    for item in content
                    if isinstance(item, dict) and item.get("type")
                ]
                if isinstance(content, list)
                else []
            )
            performance_logger.warning(
                "agent_timing event=empty task=%s transport=messages_api model=%s "
                "prompt_chars=%s wall_ms=%s stop_reason=%s block_types=%s",
                task_name,
                model,
                len(prompt),
                round((time.perf_counter() - started_perf) * 1000),
                payload.get("stop_reason") if isinstance(payload, dict) else None,
                ",".join(block_types),
            )
            raise RuntimeError(f"Messages API {task_name} returned no text")

        duration_ms = round((time.perf_counter() - started_perf) * 1000)
        performance_logger.info(
            "agent_timing event=finish task=%s transport=messages_api model=%s effort=none "
            "max_turns=1 prompt_chars=%s output_chars=%s wall_ms=%s sdk_ms=%s "
            "stop_reason=%s cost_usd=unknown",
            task_name,
            model,
            len(prompt),
            len(raw_text),
            duration_ms,
            duration_ms,
            payload.get("stop_reason") if isinstance(payload, dict) else None,
        )
        return AgentRunResult(
            mode="claude",
            raw_text=raw_text,
            session_id=(
                str(payload.get("id")) if isinstance(payload, dict) and payload.get("id") else None
            ),
            duration_ms=duration_ms,
            stop_reason=(
                str(payload.get("stop_reason"))
                if isinstance(payload, dict) and payload.get("stop_reason")
                else None
            ),
            model=(
                str(payload.get("model"))
                if isinstance(payload, dict) and payload.get("model")
                else model
            ),
        )

    def _prompt_task_model(self, task_name: str) -> str:
        if task_name == "vedic-reader":
            return self.settings.anthropic_default_haiku_model or self.settings.anthropic_model
        if "grounding-audit" not in task_name:
            return self.settings.anthropic_model
        for candidate in (
            self.settings.anthropic_default_haiku_model,
            self.settings.anthropic_default_opus_model,
        ):
            if candidate and candidate != self.settings.anthropic_model:
                return candidate
        return self.settings.anthropic_model

    async def run_structured_reasoning_task(
        self,
        task_name: str,
        prompt: str,
        *,
        schema: dict[str, Any],
        max_turns: int | None = None,
    ) -> AgentRunResult:
        """Run a bounded semantic decision without file, shell, or web access."""

        if not self.is_configured():
            raise RuntimeError("Claude Agent SDK runtime is not configured")

        from claude_agent_sdk import ClaudeAgentOptions

        model_name = self.settings.anthropic_default_haiku_model or self.settings.anthropic_model
        options = ClaudeAgentOptions(
            tools=[],
            allowed_tools=[],
            disallowed_tools=[
                "Bash",
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep",
                "WebFetch",
                "WebSearch",
            ],
            permission_mode="dontAsk",
            setting_sources=["project"],
            cwd=Path.cwd(),
            add_dirs=[Path.cwd()],
            env=self._agent_env(),
            model=model_name,
            max_turns=max_turns or min(3, self.settings.agent_max_turns),
            effort="low",
            output_format={"type": "json_schema", "schema": schema},
            system_prompt=(
                "You are a bounded semantic decision maker. Follow the supplied ontology and "
                "return only the requested structured decision. Do not invent identifiers or "
                "infer facts that are not present in the supplied text."
            ),
        )
        return await self._run_query(
            task_name,
            prompt,
            options,
            model_name=model_name,
        )

    async def run_place_lookup_task(
        self,
        *,
        query: str,
        city_label: str,
        selected_scope_label: str | None = None,
        locale: Literal["zh", "en", "ja"] = "en",
        max_results: int = 5,
        progress_callback: Callable[[str, dict[str, object]], Awaitable[None]] | None = None,
    ) -> AgentRunResult:
        if not self.is_configured():
            raise RuntimeError("Claude Agent SDK runtime is not configured")

        from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

        tool_observations: list[dict[str, Any]] = []

        async def trace_place_tool_use(
            hook_input: object, tool_use_id: str | None, context: object
        ) -> dict[str, object]:
            return await self._trace_place_tool_use(
                hook_input,
                tool_use_id,
                context,
                city_label=city_label,
                tool_observations=tool_observations,
                selected_scope_label=selected_scope_label or city_label,
                progress_callback=progress_callback,
            )

        model_name = self.settings.anthropic_default_haiku_model or self.settings.anthropic_model
        options = ClaudeAgentOptions(
            tools=["WebSearch", "WebFetch"],
            allowed_tools=["WebSearch", "WebFetch"],
            disallowed_tools=[
                "Bash",
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep",
            ],
            permission_mode="dontAsk",
            setting_sources=["project"],
            cwd=Path.cwd(),
            add_dirs=[Path.cwd()],
            env=self._agent_env(),
            model=model_name,
            max_turns=self.settings.place_lookup_agent_max_turns,
            effort="low",
            output_format={"type": "json_schema", "schema": self._place_lookup_schema()},
            hooks={
                "PreToolUse": [HookMatcher(matcher=None, hooks=[trace_place_tool_use])],
                "PostToolUse": [HookMatcher(matcher=None, hooks=[trace_place_tool_use])],
                "PostToolUseFailure": [HookMatcher(matcher=None, hooks=[trace_place_tool_use])],
            },
            include_hook_events=self.settings.place_lookup_trace_enabled,
            system_prompt=(
                "You are the geocoding decision maker. Use WebSearch and WebFetch as needed, "
                "reason over their returned evidence, decide whether each result is the requested "
                "place inside the selected administrative scope, and return the required JSON. "
                "The application will not reinterpret place names, addresses, aliases, or scope "
                "membership after your answer."
            ),
        )
        self._log_place_trace(
            "start",
            {
                "query": query,
                "city_label": city_label,
                "selected_scope_label": selected_scope_label,
                "max_results": max_results,
            },
        )
        prompt = f"""
Find candidate WGS84 coordinates for this place query.

Query: {query}
Selected city baseline: {city_label}
Selected place scope: {selected_scope_label or city_label}
Response locale: {locale}
Max candidates: {max_results}

Use the tools and choose the search queries yourself. Continue searching while the evidence is
insufficient; stop immediately when you can make the requested decision reliably. Optimize for
latency: do not fetch another page or seek a more authoritative source merely to repeat evidence
that already supports the structured decision. For every candidate, decide:
- whether it is the place the user meant, including aliases, translated names, branches, and typos;
- whether its address belongs to the selected administrative scope;
- whether the coordinates are WGS84/EPSG:4326 and represent the POI, address, or administrative area;
- whether multiple in-scope results genuinely require a user choice.

Return only in-scope candidates supported by web evidence. If evidence conflicts or remains
insufficient, return no candidate and explain why in `notes`. Preserve source names and addresses.
Do not substitute city-center coordinates for a requested POI. Keep `label` and `address` as the
source identifies them; provide `displayLabel` and `displayAddress` in the response locale when a
natural localized form is available.
"""
        result = await self._run_query(
            "precise-place-agent-lookup",
            prompt.strip(),
            options,
            trace_label="place_lookup",
            model_name=model_name,
        )
        self._log_place_trace(
            "final",
            {
                "session_id": result.session_id,
                "duration_ms": result.duration_ms,
                "total_cost_usd": result.total_cost_usd,
                "raw_text": result.raw_text,
            },
        )
        tool_queries = tuple(
            query_text
            for observation in tool_observations
            if (query_text := self._observation_query(observation))
        )
        if tool_observations:
            self._log_place_trace(
                "agent_final_grounded",
                {
                    "observation_count": len(tool_observations),
                    "session_id": result.session_id,
                },
            )
            return AgentRunResult(
                mode=result.mode,
                raw_text=result.raw_text,
                session_id=result.session_id,
                duration_ms=result.duration_ms,
                total_cost_usd=result.total_cost_usd,
                stop_reason=result.stop_reason,
                model=result.model,
                provenance="agent_grounded",
                tool_queries=tool_queries,
            )
        return result

    async def _trace_place_tool_use(
        self,
        hook_input: object,
        tool_use_id: str | None,
        _context: object,
        *,
        city_label: str | None = None,
        tool_observations: list[dict[str, Any]] | None = None,
        selected_scope_label: str | None = None,
        progress_callback: Callable[[str, dict[str, object]], Awaitable[None]] | None = None,
    ) -> dict[str, object]:
        payload = self._hook_input_payload(hook_input)
        event_name = payload.get("hook_event_name") or payload.get("hookEventName")
        tool_name = payload.get("tool_name") or payload.get("toolName")
        evidence_tool = tool_name in {"WebSearch", "WebFetch"}
        if event_name == "PreToolUse" and evidence_tool:
            await self._emit_place_progress(
                progress_callback,
                "searching",
                {
                    "tool": str(tool_name or ""),
                    "query": self._tool_query(payload),
                    "scope": selected_scope_label or city_label or "",
                },
            )
        self._log_place_trace(
            str(event_name or "tool"),
            {
                "tool_name": tool_name,
                "tool_use_id": tool_use_id or payload.get("tool_use_id"),
                "tool_input": payload.get("tool_input"),
                "tool_response": payload.get("tool_response"),
                "error": payload.get("error"),
            },
        )
        if event_name == "PostToolUse" and evidence_tool and tool_observations is not None:
            await self._emit_place_progress(
                progress_callback,
                "verifying",
                {
                    "tool": str(tool_name or ""),
                    "query": self._tool_query(payload),
                    "scope": selected_scope_label or city_label or "",
                },
            )
            tool_observations.append(
                {
                    "tool_name": tool_name,
                    "tool_use_id": tool_use_id or payload.get("tool_use_id"),
                    "tool_input": payload.get("tool_input"),
                    "tool_response": payload.get("tool_response"),
                }
            )
        return {"continue_": True, "suppressOutput": False}

    @staticmethod
    def _observation_query(observation: dict[str, Any]) -> str:
        tool_input = observation.get("tool_input")
        if not isinstance(tool_input, dict):
            return ""
        return str(tool_input.get("query") or tool_input.get("url") or "").strip()

    @staticmethod
    def _place_lookup_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "label": {"type": "string"},
                            "address": {"type": "string"},
                            "displayLabel": {"type": "string"},
                            "displayAddress": {"type": "string"},
                            "latitude": {"type": "number", "minimum": -90, "maximum": 90},
                            "longitude": {"type": "number", "minimum": -180, "maximum": 180},
                            "coordinateSystem": {
                                "type": "string",
                                "enum": ["WGS84", "EPSG:4326"],
                            },
                            "locationType": {
                                "type": "string",
                                "enum": [
                                    "poi",
                                    "address",
                                    "district",
                                    "county",
                                    "town",
                                    "village",
                                    "landmark",
                                ],
                            },
                            "sourceUrl": {"type": "string"},
                            "rawEvidence": {"type": "string"},
                            "confidence": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                            },
                            "scopeAssessment": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "status": {
                                        "type": "string",
                                        "enum": ["match", "conflict", "uncertain"],
                                    },
                                    "reason": {"type": "string"},
                                },
                                "required": ["status", "reason"],
                            },
                        },
                        "required": [
                            "label",
                            "address",
                            "displayLabel",
                            "displayAddress",
                            "latitude",
                            "longitude",
                            "coordinateSystem",
                            "locationType",
                            "sourceUrl",
                            "rawEvidence",
                            "confidence",
                            "scopeAssessment",
                        ],
                    },
                },
                "notes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["candidates", "notes"],
        }

    @staticmethod
    async def _emit_place_progress(
        callback: Callable[[str, dict[str, object]], Awaitable[None]] | None,
        stage: str,
        payload: dict[str, object],
    ) -> None:
        if callback is not None:
            await callback(stage, payload)

    @staticmethod
    def _tool_query(payload: dict[str, Any]) -> str:
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return ""
        return str(tool_input.get("query") or tool_input.get("url") or "").strip()

    @staticmethod
    def _place_lookup_result_has_candidates(raw_text: str) -> bool:
        stripped = raw_text.strip()
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.S)
        if fence:
            stripped = fence.group(1)
        if not stripped.startswith("{"):
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start >= 0 and end > start:
                stripped = stripped[start : end + 1]
        try:
            payload = json.loads(stripped)
        except Exception:
            return False
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        return isinstance(candidates, list) and len(candidates) > 0

    @classmethod
    def _recover_place_lookup_result(cls, *values: object) -> str | None:
        """Recover a complete candidate payload from an SDK result/error boundary."""

        for value in values:
            candidate = str(value or "").strip()
            if candidate and cls._place_lookup_result_has_candidates(candidate):
                return candidate
        return None

    def _hook_input_payload(self, hook_input: object) -> dict[str, Any]:
        if isinstance(hook_input, dict):
            return dict(hook_input)
        if hasattr(hook_input, "__dict__"):
            return {
                key: value for key, value in vars(hook_input).items() if not key.startswith("_")
            }
        return {"value": repr(hook_input)}

    def _log_place_trace(self, event: str, payload: dict[str, object]) -> None:
        if not self.settings.place_lookup_trace_enabled:
            return
        place_trace_logger.warning(
            "place_lookup_trace event=%s payload=%s",
            event,
            self._json_preview(payload),
        )

    def _json_preview(self, value: object) -> str:
        max_chars = max(500, int(self.settings.place_lookup_trace_max_chars))
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            text = repr(value)
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars]}...<truncated {len(text) - max_chars} chars>"

    def _agent_env(self) -> dict[str, str]:
        token = self.settings.get_agent_auth_token()
        haiku = self.settings.anthropic_default_haiku_model
        return {
            "ANTHROPIC_BASE_URL": self.settings.anthropic_base_url,
            "ANTHROPIC_AUTH_TOKEN": token,
            "ANTHROPIC_API_KEY": token,
            "ANTHROPIC_MODEL": self.settings.anthropic_model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": self.settings.anthropic_default_opus_model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": self.settings.anthropic_default_sonnet_model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": haiku,
            "CLAUDE_CODE_SUBAGENT_MODEL": haiku,
            "CLAUDE_CODE_EFFORT_LEVEL": self._agent_effort(),
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }

    def _backend_tool_server(self) -> dict[str, object]:
        from claude_agent_sdk import create_sdk_mcp_server

        from app.tools.registry import BackendToolRunner

        return {
            "vedic_backend_tools": create_sdk_mcp_server(
                name="vedic_backend_tools",
                version="0.1.0",
                tools=BackendToolRunner(self.settings).sdk_tools(),
            )
        }

    def _backend_tool_names(self) -> list[str]:
        return [
            "mcp__vedic_backend_tools__bazi_calculate_chart",
        ]

    def _agent_effort(self) -> AgentEffort:
        value = self.settings.agent_effort
        if value in ["low", "medium", "high", "xhigh", "max"]:
            return cast(AgentEffort, value)
        return "max"

    async def _run_query(
        self,
        task_name: str,
        prompt: str,
        options: object,
        trace_label: str | None = None,
        model_name: str | None = None,
    ) -> AgentRunResult:
        from claude_agent_sdk import AssistantMessage, HookEventMessage, ResultMessage, query

        assistant_parts: list[str] = []
        result_text = ""
        session_id = None
        duration_ms = None
        total_cost_usd = None
        stop_reason = None
        structured_output: object | None = None
        started_perf = time.perf_counter()
        prompt_chars = len(prompt)
        configured_effort = getattr(options, "effort", None)
        configured_turns = getattr(options, "max_turns", None)
        performance_logger.info(
            "agent_timing event=start task=%s model=%s effort=%s max_turns=%s prompt_chars=%s",
            task_name,
            model_name,
            configured_effort,
            configured_turns,
            prompt_chars,
        )

        try:
            async with asyncio.timeout(self.settings.agent_timeout_ms / 1000):
                async for message in query(prompt=prompt, options=options):
                    if isinstance(message, AssistantMessage):
                        if trace_label:
                            self._trace_message_blocks(trace_label, message)
                        for block in message.content:
                            text = getattr(block, "text", None)
                            if text:
                                assistant_parts.append(str(text))
                    elif isinstance(message, HookEventMessage):
                        if trace_label == "place_lookup":
                            self._log_place_trace(
                                "hook_event_message",
                                self._hook_input_payload(message),
                            )
                    elif isinstance(message, ResultMessage):
                        session_id = getattr(message, "session_id", None)
                        duration_ms = getattr(message, "duration_ms", None)
                        total_cost_usd = getattr(message, "total_cost_usd", None)
                        stop_reason = getattr(message, "stop_reason", None)
                        structured_output = getattr(message, "structured_output", None)
                        if getattr(message, "is_error", False):
                            # A tool-use stop can mark the SDK result as an error even after the
                            # model has emitted a complete place candidate. Preserve that bounded
                            # JSON so the deterministic place service can verify it instead of
                            # converting a usable answer into a generic agent_error.
                            if trace_label == "place_lookup":
                                recovered = self._recover_place_lookup_result(
                                    getattr(message, "result", ""),
                                    "\n".join(assistant_parts),
                                )
                                if recovered is not None:
                                    result_text = recovered
                                    continue
                            raise RuntimeError(
                                getattr(message, "result", None)
                                or getattr(message, "stop_reason", None)
                                or f"Claude Agent SDK {task_name} failed"
                            )
                        if getattr(message, "result", None):
                            result_text = str(message.result)
        except BaseException as exc:
            wall_duration_ms = round((time.perf_counter() - started_perf) * 1000)
            performance_logger.warning(
                "agent_timing event=failed task=%s model=%s effort=%s max_turns=%s "
                "prompt_chars=%s wall_ms=%s error_type=%s",
                task_name,
                model_name,
                configured_effort,
                configured_turns,
                prompt_chars,
                wall_duration_ms,
                type(exc).__name__,
            )
            raise

        if structured_output is not None:
            result_text = json.dumps(structured_output, ensure_ascii=False)
        raw_text = (result_text or "\n".join(assistant_parts)).strip()
        if not raw_text:
            raise RuntimeError(f"Claude Agent SDK {task_name} returned no text")

        wall_duration_ms = round((time.perf_counter() - started_perf) * 1000)
        performance_logger.info(
            "agent_timing event=finish task=%s model=%s effort=%s max_turns=%s "
            "prompt_chars=%s output_chars=%s wall_ms=%s sdk_ms=%s stop_reason=%s cost_usd=%s",
            task_name,
            model_name,
            configured_effort,
            configured_turns,
            prompt_chars,
            len(raw_text),
            wall_duration_ms,
            duration_ms,
            stop_reason,
            total_cost_usd,
        )

        return AgentRunResult(
            mode="claude",
            raw_text=raw_text,
            session_id=session_id,
            duration_ms=duration_ms,
            total_cost_usd=total_cost_usd,
            stop_reason=str(stop_reason) if stop_reason is not None else None,
            model=model_name,
        )

    def _trace_message_blocks(self, trace_label: str, message: object) -> None:
        if trace_label != "place_lookup" or not self.settings.place_lookup_trace_enabled:
            return
        blocks = []
        for block in getattr(message, "content", []):
            block_payload = self._hook_input_payload(block)
            block_payload["block_type"] = type(block).__name__
            blocks.append(block_payload)
        if blocks:
            self._log_place_trace("assistant_blocks", {"blocks": blocks})
