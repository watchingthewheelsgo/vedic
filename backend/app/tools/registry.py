from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

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

        return [validate_synastry, build_synastry, time_scan, report_builder]

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


def _tool_text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}
