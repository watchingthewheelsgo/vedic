from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from app.settings import Settings


logger = logging.getLogger(__name__)
place_trace_logger = logging.getLogger("uvicorn.error")

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
        search_queries: list[str] | None = None,
    ) -> AgentRunResult:
        if not self.is_configured():
            raise RuntimeError("Claude Agent SDK runtime is not configured")

        from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

        tool_observations: list[dict[str, Any]] = []
        tool_state: dict[str, Any] = {
            "tool_count": 0,
            "verified_json": None,
        }

        async def trace_place_tool_use(
            hook_input: object, tool_use_id: str | None, context: object
        ) -> dict[str, object]:
            return await self._trace_place_tool_use(
                hook_input,
                tool_use_id,
                context,
                query=query,
                city_label=city_label,
                city_lat=city_lat,
                city_lon=city_lon,
                max_distance_km=max_distance_km,
                max_results=max_results,
                tool_observations=tool_observations,
                tool_state=tool_state,
            )

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
            model=self.settings.anthropic_default_haiku_model or self.settings.anthropic_model,
            max_turns=8,
            effort="low",
            hooks={
                "PreToolUse": [HookMatcher(matcher=None, hooks=[trace_place_tool_use])],
                "PostToolUse": [HookMatcher(matcher=None, hooks=[trace_place_tool_use])],
                "PostToolUseFailure": [HookMatcher(matcher=None, hooks=[trace_place_tool_use])],
            },
            include_hook_events=self.settings.place_lookup_trace_enabled,
            system_prompt=(
                "You are a precise geocoding evidence collector. Use Claude Code SDK WebSearch "
                "and, only when necessary, WebFetch to find candidate WGS84 coordinates for a "
                "named hospital, district, landmark, or address. Do not decide final validity; "
                "the backend will verify distance against the selected city. Return JSON only."
            ),
        )
        controlled_queries = search_queries or [
            f"{query} {city_label} latitude longitude coordinates",
            f"{query} {city_label} 经纬度 坐标",
        ]
        controlled_query_block = "\n".join(
            f"{index}. {search_query}"
            for index, search_query in enumerate(controlled_queries, start=1)
        )
        self._log_place_trace(
            "start",
            {
                "query": query,
                "city_label": city_label,
                "city_lat": city_lat,
                "city_lon": city_lon,
                "max_distance_km": max_distance_km,
                "max_results": max_results,
                "controlled_queries": controlled_queries,
            },
        )
        prompt = f"""
Find candidate WGS84 coordinates for this place query.

Query: {query}
Selected city baseline: {city_label}
City/admin baseline center: lat={city_lat}, lon={city_lon}
Administrative verification distance: {max_distance_km} km
Max candidates: {max_results}

Controlled WebSearch queries, in priority order:
{controlled_query_block}

Rules:
- Start with one query copied verbatim from the controlled list above.
- If the result does not contain coordinates for the named place, you may use another controlled
  query or one WebFetch for a specific promising URL.
- Evidence is sufficient as soon as one result contains the target name or a clear alias, the
  selected city/administrative context, and a legal latitude/longitude pair.
- When evidence is sufficient, stop using tools immediately and return the JSON candidate.
- Do not keep searching merely to find a more authoritative source after sufficient evidence exists.
- If the available results name only the city/district but not the target place, do not return a
  POI candidate from those city coordinates.
- Prefer official or map/knowledge-panel evidence when available.
- Include candidates that plausibly refer to the query inside the selected city or its
  administrative counties/districts.
- Do not reject a credible POI merely because it is far from the city-center point; the
  backend will verify administrative scope and distance.
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
        try:
            result = await self._run_query(
                "precise-place-agent-lookup",
                prompt.strip(),
                options,
                trace_label="place_lookup",
            )
        except Exception:
            fallback_json = self._place_lookup_json_from_tool_observations(
                query=query,
                city_label=city_label,
                city_lat=city_lat,
                city_lon=city_lon,
                max_distance_km=max_distance_km,
                max_results=max_results,
                observations=tool_observations,
            )
            if not fallback_json:
                raise
            self._log_place_trace(
                "final_from_tool_evidence",
                {
                    "observation_count": len(tool_observations),
                    "raw_text": fallback_json,
                },
            )
            return AgentRunResult(mode="claude", raw_text=fallback_json)
        self._log_place_trace(
            "final",
            {
                "session_id": result.session_id,
                "duration_ms": result.duration_ms,
                "total_cost_usd": result.total_cost_usd,
                "raw_text": result.raw_text,
            },
        )
        verified_json = tool_state.get("verified_json")
        if isinstance(verified_json, str) and not self._place_lookup_result_has_candidates(
            result.raw_text
        ):
            self._log_place_trace(
                "final_from_tool_evidence",
                {
                    "reason": "agent_final_missing_verified_candidates",
                    "session_id": result.session_id,
                    "raw_text": verified_json,
                },
            )
            return AgentRunResult(
                mode=result.mode,
                raw_text=verified_json,
                session_id=result.session_id,
                duration_ms=result.duration_ms,
                total_cost_usd=result.total_cost_usd,
            )
        return result

    async def _trace_place_tool_use(
        self,
        hook_input: object,
        tool_use_id: str | None,
        _context: object,
        *,
        query: str | None = None,
        city_label: str | None = None,
        city_lat: float | None = None,
        city_lon: float | None = None,
        max_distance_km: float | None = None,
        max_results: int = 5,
        tool_observations: list[dict[str, Any]] | None = None,
        tool_state: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        payload = self._hook_input_payload(hook_input)
        event_name = payload.get("hook_event_name") or payload.get("hookEventName")
        tool_name = payload.get("tool_name") or payload.get("toolName")
        if event_name == "PreToolUse" and tool_state is not None:
            tool_state["tool_count"] = int(tool_state.get("tool_count") or 0) + 1
            deny_reason = ""
            if tool_state.get("verified_json"):
                deny_reason = (
                    "Sufficient place-coordinate evidence was already found. "
                    "Stop using tools and return the JSON candidate now."
                )
            elif int(tool_state["tool_count"]) > 6:
                deny_reason = (
                    "Place lookup tool budget reached. Return JSON using evidence already found, "
                    "or an empty candidates array if no place-coordinate evidence exists."
                )
            if deny_reason:
                self._log_place_trace(
                    "tool_denied",
                    {
                        "tool_name": tool_name,
                        "tool_use_id": tool_use_id or payload.get("tool_use_id"),
                        "reason": deny_reason,
                    },
                )
                return {
                    "continue_": True,
                    "suppressOutput": False,
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": deny_reason,
                    },
                }
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
        if event_name == "PostToolUse" and tool_observations is not None:
            tool_observations.append(
                {
                    "tool_name": tool_name,
                    "tool_use_id": tool_use_id or payload.get("tool_use_id"),
                    "tool_input": payload.get("tool_input"),
                    "tool_response": payload.get("tool_response"),
                }
            )
            if (
                query is not None
                and city_label is not None
                and city_lat is not None
                and city_lon is not None
                and max_distance_km is not None
                and tool_state is not None
            ):
                verified_json = self._place_lookup_json_from_tool_observations(
                    query=query,
                    city_label=city_label,
                    city_lat=city_lat,
                    city_lon=city_lon,
                    max_distance_km=max_distance_km,
                    max_results=max_results,
                    observations=tool_observations,
                )
                if verified_json and not tool_state.get("verified_json"):
                    tool_state["verified_json"] = verified_json
                    self._log_place_trace(
                        "evidence_gate_verified",
                        {
                            "tool_name": tool_name,
                            "tool_use_id": tool_use_id or payload.get("tool_use_id"),
                            "raw_text": verified_json,
                        },
                    )
        return {"continue_": True, "suppressOutput": False}

    def _place_lookup_json_from_tool_observations(
        self,
        *,
        query: str,
        city_label: str,
        city_lat: float,
        city_lon: float,
        max_distance_km: float,
        max_results: int,
        observations: list[dict[str, Any]],
    ) -> str | None:
        candidates: list[dict[str, object]] = []
        seen: set[tuple[float, float]] = set()
        for observation in observations:
            text = self._json_preview(observation)
            full_text = self._observation_text(observation)
            for lat, lon in self._extract_coordinate_pairs(full_text, city_lat, city_lon):
                key = (round(lat, 5), round(lon, 5))
                if key in seen:
                    continue
                gate = self._place_evidence_gate(
                    query=query,
                    city_label=city_label,
                    text=full_text,
                    lat=lat,
                    lon=lon,
                    city_lat=city_lat,
                    city_lon=city_lon,
                    max_distance_km=max_distance_km,
                )
                if not gate["accepted"]:
                    continue
                seen.add(key)
                coordinate_context = self._coordinate_context(full_text, lat, lon)
                label = self._label_from_place_evidence(query, coordinate_context)
                address = self._address_from_place_evidence(coordinate_context) or city_label
                candidates.append(
                    {
                        "label": label,
                        "address": address,
                        "latitude": lat,
                        "longitude": lon,
                        "accuracy": "poi",
                        "sourceUrl": self._first_url(full_text) or "",
                        "rawEvidence": self._evidence_snippet(full_text, lat, lon) or text,
                        "confidence": gate["confidence"],
                    }
                )
        if not candidates:
            return None
        payload = {
            "candidates": candidates[: max(1, max_results)],
            "notes": [
                "Structured from WebSearch/WebFetch evidence after place evidence gate passed."
            ],
        }
        return json.dumps(payload, ensure_ascii=False)

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

    def _place_evidence_gate(
        self,
        *,
        query: str,
        city_label: str,
        text: str,
        lat: float,
        lon: float,
        city_lat: float,
        city_lon: float,
        max_distance_km: float,
    ) -> dict[str, object]:
        if not self._valid_lat_lon(lat, lon):
            return {"accepted": False, "confidence": "low"}
        distance = self._distance_km(city_lat, city_lon, lat, lon)
        if distance > max(max_distance_km, 35.0):
            return {"accepted": False, "confidence": "low"}
        entity_match = self._place_evidence_mentions_entity(query, city_label, text)
        if not entity_match:
            return {"accepted": False, "confidence": "low"}
        if distance < 1.0 and self._looks_like_city_center_only(query, text):
            return {"accepted": False, "confidence": "low"}
        if distance > 35.0 and not self._place_evidence_has_admin_context(city_label, text):
            return {"accepted": False, "confidence": "low"}
        confidence = "high" if self._address_from_place_evidence(text) else "medium"
        return {"accepted": True, "confidence": confidence}

    def _place_evidence_mentions_entity(self, query: str, city_label: str, text: str) -> bool:
        normalized_query = self._compact_for_match(query)
        normalized_text = self._compact_for_match(text)
        if normalized_query and normalized_query in normalized_text:
            return True

        query_has_cjk = bool(re.search(r"[\u4e00-\u9fff]", query))
        category_in_query = self._place_category_in_text(query)
        category_in_text = self._place_category_in_text(text)
        if query_has_cjk:
            terms = self._cjk_entity_terms(query)
            has_specific_term = any(term in text for term in terms)
            if category_in_query:
                return has_specific_term and category_in_text
            return has_specific_term

        if self._looks_like_pinyin_hospital_query(query):
            return category_in_text and self._place_evidence_has_admin_context(city_label, text)

        query_tokens = [
            token
            for token in re.findall(r"[a-z0-9]+", query.lower())
            if len(token) >= 3
            and token
            not in {
                "china",
                "coordinates",
                "coordinate",
                "latitude",
                "longitude",
                "wgs84",
            }
        ]
        if category_in_query or "hospital" in query.lower():
            return category_in_text and any(token in text.lower() for token in query_tokens)
        return len(query_tokens) >= 2 and all(token in text.lower() for token in query_tokens[:2])

    def _place_evidence_has_admin_context(self, city_label: str, text: str) -> bool:
        lowered = text.lower()
        city_tokens = [
            token
            for token in re.findall(r"[a-z0-9]+", city_label.lower())
            if len(token) >= 3 and token not in {"china", "city"}
        ]
        if any(token in lowered for token in city_tokens):
            return True
        return bool(
            re.search(
                r"[\u4e00-\u9fff]{1,12}(?:省|市|区|县|镇|路|号)|"
                r"\b(?:province|prefecture|district|county|road|street)\b",
                text,
                re.I,
            )
        )

    @staticmethod
    def _looks_like_pinyin_hospital_query(query: str) -> bool:
        lowered = query.lower()
        return "yi yuan" in lowered or "yiyuan" in lowered or "hospital" in lowered

    @staticmethod
    def _place_category_in_text(text: str) -> bool:
        lowered = text.lower()
        return bool(
            re.search(
                r"医院|保健院|卫生院|妇幼|妇婴|医科|诊所|"
                r"\b(?:hospital|medical center|clinic|maternity)\b",
                lowered,
                re.I,
            )
        )

    def _looks_like_city_center_only(self, query: str, text: str) -> bool:
        if self._place_category_in_text(query) and self._place_category_in_text(text):
            return False
        lowered = text.lower()
        city_only_markers = ["city center", "general consensus coordinates", "municipal government"]
        return any(marker in lowered for marker in city_only_markers)

    @staticmethod
    def _cjk_entity_terms(query: str) -> list[str]:
        compact = "".join(re.findall(r"[\u4e00-\u9fff]+", query))
        compact = re.sub(
            r"(医院|保健院|卫生院|人民|市立|省立|县立|区立|"
            r"第一|第二|第三|第四|第五|第[一二三四五六七八九十]+)",
            "",
            compact,
        )
        terms: list[str] = []
        if len(compact) >= 2:
            terms.append(compact[:2])
            terms.append(compact[-2:])
        if len(compact) >= 4:
            terms.append(compact[:4])
        return [term for index, term in enumerate(terms) if term and term not in terms[:index]]

    @staticmethod
    def _compact_for_match(value: str) -> str:
        return re.sub(r"\s+", "", value).lower()

    def _extract_coordinate_pairs(
        self, text: str, city_lat: float, city_lon: float
    ) -> list[tuple[float, float]]:
        pairs: list[tuple[float, float]] = []
        decimal = r"([+-]?\d{1,3}\.\d{3,})"
        lat_label = r"(?:纬度|北纬|latitude|lat)"
        lon_label = r"(?:经度|东经|longitude|lng|lon)"
        lat_mentions = [
            (match.start(), float(match.group(1)))
            for match in re.finditer(rf"{lat_label}[^0-9+\-]{{0,80}}{decimal}", text, re.I)
        ]
        lon_mentions = [
            (match.start(), float(match.group(1)))
            for match in re.finditer(rf"{lon_label}[^0-9+\-]{{0,80}}{decimal}", text, re.I)
        ]
        used_lon_positions: set[int] = set()
        for lat_position, lat in lat_mentions:
            nearby_lons = [
                (lon_position, lon)
                for lon_position, lon in lon_mentions
                if lon_position not in used_lon_positions and 0 < lon_position - lat_position < 700
            ]
            if not nearby_lons:
                continue
            lon_position, lon = min(nearby_lons, key=lambda item: item[0] - lat_position)
            if self._valid_lat_lon(lat, lon):
                pairs.append((lat, lon))
                used_lon_positions.add(lon_position)

        for match in re.finditer(
            r"(?<!\d)([+-]?\d{1,3}\.\d{3,})\s*[,，]\s*([+-]?\d{1,3}\.\d{3,})(?!\d)",
            text,
        ):
            first = float(match.group(1))
            second = float(match.group(2))
            pair = self._normalize_coordinate_order(first, second, city_lat, city_lon)
            if pair:
                pairs.append(pair)

        deduped: list[tuple[float, float]] = []
        seen: set[tuple[float, float]] = set()
        for lat, lon in pairs:
            key = (round(lat, 6), round(lon, 6))
            if key not in seen:
                seen.add(key)
                deduped.append((lat, lon))
        return deduped

    @staticmethod
    def _coordinate_context(text: str, lat: float, lon: float) -> str:
        needles = [
            f"{lat:.6f}".rstrip("0").rstrip("."),
            f"{lon:.6f}".rstrip("0").rstrip("."),
            f"{lat:.5f}".rstrip("0").rstrip("."),
            f"{lon:.5f}".rstrip("0").rstrip("."),
        ]
        positions = [text.find(needle) for needle in needles if text.find(needle) >= 0]
        if not positions:
            return text[:1000]
        index = min(positions)
        start = max(0, index - 260)
        end = min(len(text), index + 420)
        campus_markers = list(
            re.finditer(
                r"(?:^|\n|\s)(?:#{1,4}\s*)?(东院|西院|南院|北院|[一二三四五六七八九十]院区)", text
            )
        )
        previous_markers = [marker for marker in campus_markers if marker.start() < index]
        next_markers = [marker for marker in campus_markers if marker.start() > index]
        if previous_markers:
            start = max(start, previous_markers[-1].start())
        if next_markers:
            end = min(end, next_markers[0].start())
        return re.sub(r"\s+", " ", text[start:end]).strip()

    def _normalize_coordinate_order(
        self, first: float, second: float, city_lat: float, city_lon: float
    ) -> tuple[float, float] | None:
        options = []
        if self._valid_lat_lon(first, second):
            options.append((first, second))
        if self._valid_lat_lon(second, first):
            options.append((second, first))
        if not options:
            return None
        return min(
            options, key=lambda pair: self._distance_km(city_lat, city_lon, pair[0], pair[1])
        )

    @staticmethod
    def _valid_lat_lon(lat: float, lon: float) -> bool:
        return -90 <= lat <= 90 and -180 <= lon <= 180

    @staticmethod
    def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6371.0088
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        value = (
            math.sin(delta_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        )
        return 2 * radius * math.atan2(math.sqrt(value), math.sqrt(1 - value))

    def _label_from_place_evidence(self, query: str, text: str) -> str:
        campus = re.search(r"(东院|西院|南院|北院|[一二三四五六七八九十]院区)", text)
        if campus and re.search(r"[\u4e00-\u9fff]", query) and campus.group(1) not in query:
            return f"{query.strip()}{campus.group(1)}"
        for pattern in [
            r"([\u4e00-\u9fff]{2,32}(?:东院|西院|南院|北院|院区))",
            r"([\u4e00-\u9fff]{2,24}(?:医院|保健院|卫生院|诊所))",
            r"([A-Z][A-Za-z\s.'-]{2,80}(?:Hospital|Medical Center|Clinic))",
        ]:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return query.strip()

    @staticmethod
    def _address_from_place_evidence(text: str) -> str | None:
        for pattern in [
            r"(?:地址|Address)[：:\s\"“”]*([^\n。；;|]{4,90})",
            r"([\u4e00-\u9fff]{2,12}省[\u4e00-\u9fff]{2,12}市[^\n。；;|]{2,90})",
        ]:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(1).strip(" 。；;，,>\"'")
        return None

    @staticmethod
    def _first_url(text: str) -> str | None:
        match = re.search(r"https?://[^\s\"'<>，。)）]+", text)
        return match.group(0) if match else None

    @staticmethod
    def _evidence_snippet(text: str, lat: float, lon: float) -> str | None:
        lat_text = f"{lat:.4f}".rstrip("0").rstrip(".")
        lon_text = f"{lon:.4f}".rstrip("0").rstrip(".")
        compacted = re.sub(r"\s+", " ", text)
        for needle in [lat_text, lon_text, "纬度", "Latitude", "coordinates", "坐标"]:
            index = compacted.find(needle)
            if index >= 0:
                start = max(0, index - 140)
                end = min(len(compacted), index + 260)
                return compacted[start:end].strip()
        return compacted[:360].strip() or None

    @staticmethod
    def _observation_text(observation: dict[str, Any]) -> str:
        value = observation.get("tool_response")
        if value is None:
            value = observation
        fragments = ClaudeRuntime._text_fragments(value)
        if fragments:
            return "\n".join(fragments)
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            return repr(value)

    @staticmethod
    def _text_fragments(value: object) -> list[str]:
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, dict):
            fragments: list[str] = []
            for item in value.values():
                fragments.extend(ClaudeRuntime._text_fragments(item))
            return fragments
        if isinstance(value, list):
            fragments = []
            for item in value:
                fragments.extend(ClaudeRuntime._text_fragments(item))
            return fragments
        return []

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
            "mcp__vedic_backend_tools__vedic_synastry_validate",
            "mcp__vedic_backend_tools__vedic_synastry_build",
            "mcp__vedic_backend_tools__vedic_rectifier_time_scan",
            "mcp__vedic_backend_tools__vedic_report_builder",
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
    ) -> AgentRunResult:
        from claude_agent_sdk import AssistantMessage, HookEventMessage, ResultMessage, query

        assistant_parts: list[str] = []
        result_text = ""
        session_id = None
        duration_ms = None
        total_cost_usd = None

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
