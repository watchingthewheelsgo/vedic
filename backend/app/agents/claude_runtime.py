from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from app.settings import Settings


AgentEffort = Literal["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True)
class AgentRunResult:
    mode: Literal["claude", "mock"]
    raw_text: str
    session_id: str | None = None
    duration_ms: int | None = None
    total_cost_usd: float | None = None


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
                "rules, and markdown output format. Do not invent app-specific JSON, checkout flows, "
                "daily notes, or extra summaries. Use only files in this workspace "
                "and the selected skill instructions."
            ),
        )
        return await self._run_query(task_name, prompt, options)

    async def run_skill_prompt_task(
        self,
        task_name: str,
        prompt: str,
        *,
        skills: list[str],
        max_turns: int | None = None,
    ) -> AgentRunResult:
        if not self.is_configured():
            raise RuntimeError("Claude Agent SDK runtime is not configured")

        from claude_agent_sdk import ClaudeAgentOptions

        # Read/Glob/Grep stay enabled so the selected skill can load its own
        # resources/*.md framework files (e.g. the original SKILL.md instructs
        # "view_file resources/chart_reading_rules.md"). Write/Edit remain
        # disabled: the backend still persists artifacts from the JSON wrapper.
        options = ClaudeAgentOptions(
            tools=["Read", "Glob", "Grep"],
            allowed_tools=["Read", "Glob", "Grep", *self._backend_tool_names()],
            disallowed_tools=["Bash", "Write", "Edit", "WebFetch", "WebSearch"],
            permission_mode="dontAsk",
            setting_sources=["project"],
            cwd=Path.cwd(),
            add_dirs=[Path.cwd()],
            mcp_servers=self._backend_tool_server(),
            env=self._agent_env(),
            model=self.settings.anthropic_model,
            max_turns=max_turns or self.settings.agent_max_turns,
            effort=cast(AgentEffort, self._agent_effort()),
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
        return await self._run_query(task_name, prompt, options)

    async def run_place_lookup_task(
        self,
        *,
        query: str,
        city_label: str,
        city_lat: float,
        city_lon: float,
        max_distance_km: float,
        max_results: int = 5,
    ) -> AgentRunResult:
        if not self.is_configured():
            raise RuntimeError("Claude Agent SDK runtime is not configured")

        from claude_agent_sdk import ClaudeAgentOptions

        place_search_tool = "mcp__vedic_backend_tools__place_web_search"
        options = ClaudeAgentOptions(
            tools=[],
            allowed_tools=[place_search_tool],
            disallowed_tools=[
                "Bash",
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep",
                "WebSearch",
                "WebFetch",
            ],
            permission_mode="dontAsk",
            setting_sources=["project"],
            cwd=Path.cwd(),
            add_dirs=[Path.cwd()],
            mcp_servers=self._backend_tool_server(),
            env=self._agent_env(),
            model=self.settings.anthropic_default_haiku_model or self.settings.anthropic_model,
            max_turns=6,
            effort="low",
            system_prompt=(
                "You are a precise geocoding evidence collector. Use web search only to find "
                "candidate coordinates for a named hospital, district, landmark, or address. "
                "Do not decide final validity; the backend will verify distance against the city. "
                "Return JSON only."
            ),
        )
        prompt = f"""
Find candidate WGS84 coordinates for this place query.

Query: {query}
Selected city baseline: {city_label}
City center: lat={city_lat}, lon={city_lon}
Expected max distance from city center: {max_distance_km} km
Max candidates: {max_results}

Rules:
- Use the `{place_search_tool}` tool to search for coordinate evidence. Suggested searches:
  1. "{query} {city_label} latitude longitude coordinates"
  2. "{query} {city_label} 经纬度 坐标"
- Prefer official or map/knowledge-panel evidence when available.
- Include only candidates that plausibly refer to the query inside the selected city.
- If evidence lists longitude before latitude, normalize output to latitude then longitude.
- If you cannot find credible coordinates, return an empty candidates array.
- Return valid JSON only, no markdown fences.

Schema:
{{
  "candidates": [
    {{
      "label": "place name",
      "address": "short address or locality",
      "latitude": 31.0,
      "longitude": 121.0,
      "accuracy": "poi",
      "sourceUrl": "https://...",
      "rawEvidence": "short quote or summary of where the coordinates came from",
      "confidence": "high"
    }}
  ],
  "notes": ["optional short notes"]
}}
"""
        return await self._run_query("precise-place-agent-lookup", prompt.strip(), options)

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
            "mcp__vedic_backend_tools__vedic_synastry_validate",
            "mcp__vedic_backend_tools__vedic_synastry_build",
            "mcp__vedic_backend_tools__vedic_rectifier_time_scan",
            "mcp__vedic_backend_tools__vedic_report_builder",
            "mcp__vedic_backend_tools__bazi_calculate_chart",
            "mcp__vedic_backend_tools__place_web_search",
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
    ) -> AgentRunResult:
        from claude_agent_sdk import AssistantMessage, ResultMessage, query

        assistant_parts: list[str] = []
        result_text = ""
        session_id = None
        duration_ms = None
        total_cost_usd = None

        async with asyncio.timeout(self.settings.agent_timeout_ms / 1000):
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        text = getattr(block, "text", None)
                        if text:
                            assistant_parts.append(str(text))
                elif isinstance(message, ResultMessage):
                    session_id = getattr(message, "session_id", None)
                    duration_ms = getattr(message, "duration_ms", None)
                    total_cost_usd = getattr(message, "total_cost_usd", None)
                    if getattr(message, "is_error", False):
                        raise RuntimeError(
                            getattr(message, "result", None)
                            or getattr(message, "stop_reason", None)
                            or f"Claude Agent SDK {task_name} failed"
                        )
                    if getattr(message, "result", None):
                        result_text = str(message.result)

        raw_text = (result_text or "\n".join(assistant_parts)).strip()
        if not raw_text:
            raise RuntimeError(f"Claude Agent SDK {task_name} returned no text")

        return AgentRunResult(
            mode="claude",
            raw_text=raw_text,
            session_id=session_id,
            duration_ms=duration_ms,
            total_cost_usd=total_cost_usd,
        )
