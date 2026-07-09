from __future__ import annotations

from html import unescape
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from claude_agent_sdk import SdkMcpTool

    from app.settings import Settings


@dataclass(frozen=True)
class ToolRunResult:
    name: str
    output: str


class BackendToolRunner:
    """Small interface for backend-owned tools that support skill workflows."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def validate_synastry_data(self, a_path: Path, b_path: Path) -> ToolRunResult:
        return self._run_python_script(
            "vedic_synastry_validate",
            self._tool_path("synastry", "validate_synastry_data.py"),
            [str(a_path), str(b_path)],
        )

    def build_synastry_data(
        self,
        a_path: Path,
        b_path: Path,
        out_dir: Path,
        *,
        a_label: str = "A",
        b_label: str = "B",
    ) -> ToolRunResult:
        return self._run_python_script(
            "vedic_synastry_build",
            self._tool_path("synastry", "build_synastry_data.py"),
            [str(a_path), str(b_path), str(out_dir), "--a", a_label, "--b", b_label],
        )

    def scan_rectification_time(
        self,
        *,
        date: str,
        time_utc: str,
        lat: float,
        lon: float,
        range_minutes: int,
        save_path: Path | None = None,
    ) -> ToolRunResult:
        args = [
            "--date",
            date,
            "--time",
            time_utc,
            "--lat",
            str(lat),
            "--lon",
            str(lon),
            "--range",
            str(range_minutes),
        ]
        if save_path is not None:
            args.extend(["--save", str(save_path)])
        return self._run_python_script(
            "vedic_rectifier_time_scan",
            self._tool_path("rectifier", "time_scan.py"),
            args,
        )

    def build_legacy_report(
        self,
        folder: Path,
        *,
        name: str | None = None,
        lagna: str | None = None,
        lang: str = "cn",
        include: str | None = None,
    ) -> ToolRunResult:
        args = [str(folder), "--lang", lang]
        if name:
            args.extend(["--name", name])
        if lagna:
            args.extend(["--lagna", lagna])
        if include:
            args.extend(["--include", include])
        return self._run_python_script(
            "vedic_report_builder",
            self._tool_path("reporting", "legacy_report_builder.py"),
            args,
        )

    def calculate_bazi_chart(
        self,
        *,
        birth_date: str,
        birth_time: str = "",
        birth_place: str = "[not provided]",
        gender: str = "未提供",
        current_date: str = "",
        out_dir: Path | None = None,
        calendar_type: str = "solar",
        time_precision: str = "exact",
        timezone: str = "Asia/Shanghai",
        latitude: float | None = None,
        longitude: float | None = None,
        audience: str = "self",
        relationship: str = "[not provided]",
        topic: str = "[not provided]",
        day_boundary_sect: int = 2,
        luck_sect: int = 2,
        solar_time_policy: str = "civil",
        emit_artifact_content: bool = False,
    ) -> ToolRunResult:
        args = [
            "--birth-date",
            birth_date,
            "--birth-time",
            birth_time,
            "--birth-place",
            birth_place,
            "--gender",
            gender,
            "--calendar-type",
            calendar_type,
            "--time-precision",
            time_precision,
            "--timezone",
            timezone,
            "--current-date",
            current_date or date.today().isoformat(),
            "--audience",
            audience,
            "--relationship",
            relationship,
            "--topic",
            topic,
            "--day-boundary-sect",
            str(day_boundary_sect),
            "--luck-sect",
            str(luck_sect),
            "--solar-time-policy",
            solar_time_policy,
        ]
        if latitude is not None:
            args.extend(["--latitude", str(latitude)])
        if longitude is not None:
            args.extend(["--longitude", str(longitude)])
        if out_dir is not None:
            args.extend(["--out-dir", str(out_dir)])
        if emit_artifact_content:
            args.append("--emit-artifact-content")
        return self._run_python_script(
            "bazi_calculate_chart",
            self._tool_path("bazi", "calculate_chart.py"),
            args,
        )

    def place_web_search(self, query: str, *, max_chars: int = 6000) -> dict[str, str]:
        base_url = (
            getattr(self.settings, "web_place_search_url", "") or "https://duckduckgo.com/html/"
        ).strip()
        timeout = float(getattr(self.settings, "web_place_search_timeout_seconds", 3.0))
        user_agent = (
            getattr(self.settings, "web_place_search_user_agent", "")
            or "Mozilla/5.0 (compatible; VedicPlaceVerifier/1.0)"
        )
        separator = "&" if "?" in base_url else "?"
        url = f"{base_url}{separator}{urlencode({'q': query})}"
        request = Request(url, headers={"User-Agent": user_agent})
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw_html = response.read().decode("utf-8", errors="replace")
        text = self._html_to_text(raw_html)
        return {
            "query": query,
            "sourceUrl": url,
            "text": text[: max(1000, min(max_chars, 12000))],
        }

    def sdk_tools(self) -> list[SdkMcpTool[Any]]:
        """Return in-process SDK tools for agent workflows that explicitly need them."""

        from claude_agent_sdk import tool

        @tool(
            "vedic_synastry_validate",
            "Validate two structured_data.md files before generating synastry_data.md.",
            {"a_path": str, "b_path": str},
        )
        async def validate_synastry(args: dict[str, Any]) -> dict[str, Any]:
            result = self.validate_synastry_data(Path(args["a_path"]), Path(args["b_path"]))
            return _tool_text(result.output)

        @tool(
            "vedic_synastry_build",
            "Generate synastry_data.md from two structured_data.md files.",
            {"a_path": str, "b_path": str, "out_dir": str, "a_label": str, "b_label": str},
        )
        async def build_synastry(args: dict[str, Any]) -> dict[str, Any]:
            result = self.build_synastry_data(
                Path(args["a_path"]),
                Path(args["b_path"]),
                Path(args["out_dir"]),
                a_label=args.get("a_label") or "A",
                b_label=args.get("b_label") or "B",
            )
            return _tool_text(result.output)

        @tool(
            "vedic_rectifier_time_scan",
            "Scan Lagna/D9/D10 changes across a UTC birth-time range.",
            {
                "date": str,
                "time_utc": str,
                "lat": float,
                "lon": float,
                "range_minutes": int,
                "save_path": str,
            },
        )
        async def time_scan(args: dict[str, Any]) -> dict[str, Any]:
            save_value = args.get("save_path")
            result = self.scan_rectification_time(
                date=args["date"],
                time_utc=args["time_utc"],
                lat=float(args["lat"]),
                lon=float(args["lon"]),
                range_minutes=int(args.get("range_minutes") or 30),
                save_path=Path(save_value) if save_value else None,
            )
            return _tool_text(result.output)

        @tool(
            "vedic_report_builder",
            "Build a legacy Vedic HTML report from markdown artifacts.",
            {
                "folder": str,
                "name": str,
                "lagna": str,
                "lang": str,
                "include": str,
            },
        )
        async def report_builder(args: dict[str, Any]) -> dict[str, Any]:
            result = self.build_legacy_report(
                Path(args["folder"]),
                name=args.get("name") or None,
                lagna=args.get("lagna") or None,
                lang=args.get("lang") or "cn",
                include=args.get("include") or None,
            )
            return _tool_text(result.output)

        @tool(
            "bazi_calculate_chart",
            "Calculate BaZi four pillars, ten gods, relations, major luck, and optional report artifacts.",
            {
                "birth_date": str,
                "birth_time": str,
                "birth_place": str,
                "gender": str,
                "current_date": str,
                "out_dir": str,
                "calendar_type": str,
                "time_precision": str,
                "timezone": str,
                "latitude": float,
                "longitude": float,
                "audience": str,
                "relationship": str,
                "topic": str,
                "day_boundary_sect": int,
                "luck_sect": int,
                "solar_time_policy": str,
                "emit_artifact_content": bool,
            },
        )
        async def bazi_calculate_chart(args: dict[str, Any]) -> dict[str, Any]:
            out_dir = args.get("out_dir")
            result = self.calculate_bazi_chart(
                birth_date=args["birth_date"],
                birth_time=args.get("birth_time") or "",
                birth_place=args.get("birth_place") or "[not provided]",
                gender=args.get("gender") or "未提供",
                current_date=args.get("current_date") or "",
                out_dir=Path(out_dir) if out_dir else None,
                calendar_type=args.get("calendar_type") or "solar",
                time_precision=args.get("time_precision") or "exact",
                timezone=args.get("timezone") or "Asia/Shanghai",
                latitude=_optional_float(args.get("latitude")),
                longitude=_optional_float(args.get("longitude")),
                audience=args.get("audience") or "self",
                relationship=args.get("relationship") or "[not provided]",
                topic=args.get("topic") or "[not provided]",
                day_boundary_sect=int(args.get("day_boundary_sect") or 2),
                luck_sect=int(args.get("luck_sect") or 2),
                solar_time_policy=args.get("solar_time_policy") or "civil",
                emit_artifact_content=bool(args.get("emit_artifact_content")),
            )
            return _tool_text(result.output)

        @tool(
            "place_web_search",
            "Search the web for place coordinate evidence and return result-page text.",
            {"query": str, "max_chars": int},
        )
        async def place_web_search(args: dict[str, Any]) -> dict[str, Any]:
            result = self.place_web_search(
                str(args["query"]),
                max_chars=int(args.get("max_chars") or 6000),
            )
            return _tool_text(json.dumps(result, ensure_ascii=False))

        return [
            validate_synastry,
            build_synastry,
            time_scan,
            report_builder,
            bazi_calculate_chart,
            place_web_search,
        ]

    def _tool_path(self, group: str, filename: str) -> Path:
        return self.settings.project_root / "backend" / "app" / "tools" / group / filename

    def _run_python_script(self, name: str, script: Path, args: list[str]) -> ToolRunResult:
        if not script.exists():
            raise RuntimeError(f"Backend tool script not found: {script}")
        result = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=self.settings.project_root,
            check=False,
            text=True,
            capture_output=True,
        )
        output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
        if result.returncode != 0:
            raise RuntimeError(output or f"{name} failed")
        return ToolRunResult(name=name, output=output)

    @staticmethod
    def _html_to_text(raw_html: str) -> str:
        without_scripts = re.sub(
            r"<(script|style)\b[^>]*>.*?</\1>", " ", raw_html, flags=re.I | re.S
        )
        without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
        return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def _tool_text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
