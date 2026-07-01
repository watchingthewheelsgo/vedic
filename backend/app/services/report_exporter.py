from __future__ import annotations

import asyncio
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from app.schemas import SkillArtifact
from app.services.skill_workspace import SkillWorkspace


ReportFormat = Literal["html", "pdf"]


PUBLIC_REPORT_ORDER = [
    "p1_overview.md",
    "p2a_planets.md",
    "p2b_planets.md",
    "p2c_planets.md",
    "p2d_planets.md",
    "p3a_d9.md",
    "p3b_divisional.md",
    "p4a_houses.md",
    "p4b_houses.md",
    "p5a_life.md",
    "p5b_life.md",
    "appendix.md",
]


@dataclass(frozen=True)
class ReportSection:
    path: str
    title: str
    html: str
    accent: str


@dataclass(frozen=True)
class ThemeConfig:
    name: str
    title: str
    subtitle: str
    accent_palette: tuple[str, ...]

    @staticmethod
    def private_advisor() -> "ThemeConfig":
        return ThemeConfig(
            name="private-advisor",
            title="Vedic Report",
            subtitle="Private advisor edition",
            accent_palette=(
                "#1f5f5b",
                "#8a5a22",
                "#334b7d",
                "#7f3d55",
                "#4f6f38",
                "#6d4c8d",
            ),
        )


@dataclass(frozen=True)
class ReportExportResult:
    session_id: str
    html_path: Path
    pdf_path: Path | None
    section_count: int


class ReportExporter:
    """Export session markdown artifacts into themed HTML and optional PDF."""

    def __init__(self, workspace: SkillWorkspace) -> None:
        self.workspace = workspace

    def export_session(
        self,
        session_id: str,
        *,
        output_dir: Path | None = None,
        theme: ThemeConfig | None = None,
        formats: tuple[ReportFormat, ...] = ("html",),
    ) -> ReportExportResult:
        artifacts = self.workspace.read_artifacts(session_id)
        report_theme = theme or ThemeConfig.private_advisor()
        sections = self._collect_sections(artifacts, report_theme)
        if not sections:
            raise ValueError("No public report artifacts found for export")

        metrics = self._load_metrics(artifacts)
        target_dir = output_dir or (
            self.workspace.settings.project_root / "backend" / "data" / "exports" / session_id
        )
        target_dir.mkdir(parents=True, exist_ok=True)

        html_path = target_dir / "report.html"
        html_path.write_text(
            self._render_html(
                session_id=session_id,
                sections=sections,
                metrics=metrics,
                theme=report_theme,
            ),
            encoding="utf-8",
        )

        pdf_path: Path | None = None
        if "pdf" in formats:
            pdf_path = target_dir / "report.pdf"
            self.export_pdf(html_path=html_path, pdf_path=pdf_path)

        return ReportExportResult(
            session_id=session_id,
            html_path=html_path,
            pdf_path=pdf_path,
            section_count=len(sections),
        )

    def export_pdf(self, *, html_path: Path, pdf_path: Path) -> None:
        asyncio.run(self._export_pdf_async(html_path=html_path, pdf_path=pdf_path))

    async def _export_pdf_async(self, *, html_path: Path, pdf_path: Path) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "PDF export requires Python Playwright. Install it with "
                "`uv add --project backend playwright`, then run "
                "`uv run --project backend python -m playwright install chromium`."
            ) from exc

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page(viewport={"width": 1280, "height": 1800})
            await page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            await page.emulate_media(media="print")
            await page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                margin={
                    "top": "16mm",
                    "right": "14mm",
                    "bottom": "18mm",
                    "left": "14mm",
                },
            )
            await browser.close()

    def _collect_sections(
        self, artifacts: list[SkillArtifact], theme: ThemeConfig
    ) -> list[ReportSection]:
        by_path = {artifact.path: artifact for artifact in artifacts}
        sections: list[ReportSection] = []
        for index, path in enumerate(PUBLIC_REPORT_ORDER):
            artifact = by_path.get(path)
            if artifact is None or not artifact.content.strip():
                continue
            sections.append(
                ReportSection(
                    path=path,
                    title=self._section_title(path),
                    html=self._markdown_to_html(artifact.content),
                    accent=theme.accent_palette[index % len(theme.accent_palette)],
                )
            )
        return sections

    def _load_metrics(self, artifacts: list[SkillArtifact]) -> dict[str, object] | None:
        metrics = next((artifact for artifact in artifacts if artifact.path == "run_metrics.json"), None)
        if metrics is None:
            return None
        try:
            payload = json.loads(metrics.content)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _render_html(
        self,
        *,
        session_id: str,
        sections: list[ReportSection],
        metrics: dict[str, object] | None,
        theme: ThemeConfig,
    ) -> str:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        section_nav = "\n".join(
            f'<a href="#section-{index + 1}"><span>{index + 1:02d}</span>{html.escape(section.title)}</a>'
            for index, section in enumerate(sections)
        )
        body = "\n".join(
            f"""
            <section class="report-section" id="section-{index + 1}" style="--accent: {section.accent}">
              <header class="section-header">
                <span>{index + 1:02d}</span>
                <div>
                  <p>{html.escape(section.path)}</p>
                  <h2>{html.escape(section.title)}</h2>
                </div>
              </header>
              <div class="markdown-body">{section.html}</div>
            </section>
            """
            for index, section in enumerate(sections)
        )
        metrics_html = self._metrics_html(metrics)
        return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%231f5f5b'/%3E%3Cpath d='M32 10 37.4 26.6H55L40.8 36.9 46.2 53.5 32 43.2 17.8 53.5 23.2 36.9 9 26.6h17.6L32 10Z' fill='%23f8fafc'/%3E%3C/svg%3E" />
    <title>{html.escape(theme.title)} - {html.escape(session_id)}</title>
    <style>{self._css()}</style>
  </head>
  <body>
    <main class="report-shell">
      <section class="cover">
        <p class="eyebrow">{html.escape(theme.subtitle)}</p>
        <h1>{html.escape(theme.title)}</h1>
        <div class="cover-meta">
          <span>Session</span>
          <strong>{html.escape(session_id)}</strong>
          <span>Generated</span>
          <strong>{html.escape(generated_at)}</strong>
        </div>
      </section>
      {metrics_html}
      <nav class="toc">
        <h2>Contents</h2>
        <div>{section_nav}</div>
      </nav>
      {body}
    </main>
  </body>
</html>
"""

    def _metrics_html(self, metrics: dict[str, object] | None) -> str:
        if not metrics:
            return ""
        waves = metrics.get("waves")
        wave_items = ""
        if isinstance(waves, list):
            wave_items = "\n".join(
                self._wave_item(wave)
                for wave in waves
                if isinstance(wave, dict)
            )
        calculator = metrics.get("calculator")
        calculator_seconds = (
            calculator.get("durationSeconds")
            if isinstance(calculator, dict)
            else None
        )
        return f"""
        <section class="metrics">
          <div>
            <span>Calculator</span>
            <strong>{self._duration(calculator_seconds)}</strong>
          </div>
          <div>
            <span>Core report</span>
            <strong>{self._duration(metrics.get("durationSeconds"))}</strong>
          </div>
          <div>
            <span>Status</span>
            <strong>{html.escape(str(metrics.get("status") or "recorded"))}</strong>
          </div>
          <div class="wave-row">{wave_items}</div>
        </section>
        """

    def _wave_item(self, wave: dict[str, object]) -> str:
        return (
            "<span>"
            f"Wave {html.escape(str(wave.get('wave')))} "
            f"<b>{self._duration(wave.get('durationSeconds'))}</b>"
            "</span>"
        )

    def _markdown_to_html(self, markdown: str) -> str:
        blocks: list[str] = []
        lines = markdown.splitlines()
        index = 0
        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            if not stripped:
                index += 1
                continue
            if stripped.startswith("```"):
                code_lines: list[str] = []
                index += 1
                while index < len(lines) and not lines[index].strip().startswith("```"):
                    code_lines.append(lines[index])
                    index += 1
                blocks.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                index += 1
                continue
            if self._is_table_start(lines, index):
                table_lines: list[str] = []
                while index < len(lines) and lines[index].strip().startswith("|"):
                    table_lines.append(lines[index])
                    index += 1
                blocks.append(self._table_to_html(table_lines))
                continue
            heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
            if heading:
                level = len(heading.group(1)) + 1
                blocks.append(f"<h{level}>{self._inline(heading.group(2))}</h{level}>")
                index += 1
                continue
            if stripped.startswith(">"):
                quote_lines: list[str] = []
                while index < len(lines) and lines[index].strip().startswith(">"):
                    quote_lines.append(lines[index].strip().lstrip(">").strip())
                    index += 1
                blocks.append(f"<blockquote>{self._inline(' '.join(quote_lines))}</blockquote>")
                continue
            if re.match(r"^[-*]\s+", stripped):
                items: list[str] = []
                while index < len(lines) and re.match(r"^[-*]\s+", lines[index].strip()):
                    items.append(re.sub(r"^[-*]\s+", "", lines[index].strip()))
                    index += 1
                blocks.append("<ul>" + "".join(f"<li>{self._inline(item)}</li>" for item in items) + "</ul>")
                continue
            paragraph: list[str] = [stripped]
            index += 1
            while index < len(lines) and lines[index].strip() and not self._starts_block(lines, index):
                paragraph.append(lines[index].strip())
                index += 1
            blocks.append(f"<p>{self._inline(' '.join(paragraph))}</p>")
        return "\n".join(blocks)

    def _is_table_start(self, lines: list[str], index: int) -> bool:
        return (
            index + 1 < len(lines)
            and lines[index].strip().startswith("|")
            and re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$", lines[index + 1].strip())
            is not None
        )

    def _table_to_html(self, lines: list[str]) -> str:
        rows = [
            [cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in lines
        ]
        if len(rows) < 2:
            return ""
        head = rows[0]
        body = rows[2:]
        thead = "<thead><tr>" + "".join(f"<th>{self._inline(cell)}</th>" for cell in head) + "</tr></thead>"
        tbody = "<tbody>" + "".join(
            "<tr>" + "".join(f"<td>{self._inline(cell)}</td>" for cell in row) + "</tr>"
            for row in body
        ) + "</tbody>"
        return f"<table>{thead}{tbody}</table>"

    def _starts_block(self, lines: list[str], index: int) -> bool:
        stripped = lines[index].strip()
        return (
            stripped.startswith("#")
            or stripped.startswith("```")
            or stripped.startswith(">")
            or stripped.startswith("|")
            or re.match(r"^[-*]\s+", stripped) is not None
        )

    def _inline(self, text: str) -> str:
        escaped = html.escape(text)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
        return escaped

    def _section_title(self, path: str) -> str:
        return {
            "p1_overview.md": "Identity Overview",
            "p2a_planets.md": "Planet Audit A",
            "p2b_planets.md": "Planet Audit B",
            "p2c_planets.md": "Planet Audit C",
            "p2d_planets.md": "Planet Audit D",
            "p3a_d9.md": "D9 Settlement",
            "p3b_divisional.md": "Divisional Charts",
            "p4a_houses.md": "House Diagnostics A",
            "p4b_houses.md": "House Diagnostics B",
            "p5a_life.md": "Life Synthesis A",
            "p5b_life.md": "Life Synthesis B",
            "appendix.md": "Technical Appendix",
        }.get(path, path)

    def _duration(self, value: object) -> str:
        if not isinstance(value, int | float):
            return "n/a"
        seconds = float(value)
        if seconds < 60:
            return f"{seconds:.1f}s" if seconds < 10 else f"{seconds:.0f}s"
        minutes = int(seconds // 60)
        remaining = int(round(seconds % 60))
        if minutes < 60:
            return f"{minutes}m {remaining}s"
        return f"{minutes // 60}h {minutes % 60}m"

    def _css(self) -> str:
        return """
:root {
  color: #18232f;
  background: #f1f3f0;
  font-family: ui-serif, Georgia, "Times New Roman", "Noto Serif SC", serif;
  line-height: 1.62;
}
* { box-sizing: border-box; }
body { margin: 0; }
.report-shell { max-width: 1040px; margin: 0 auto; padding: 36px; }
.cover {
  min-height: 520px;
  display: grid;
  align-content: end;
  gap: 26px;
  color: #f8fafc;
  background:
    linear-gradient(135deg, rgb(10 31 34 / 92%), rgb(56 42 74 / 88%)),
    radial-gradient(circle at 20% 20%, #b58a45, transparent 34%);
  border-radius: 14px;
  padding: 54px;
  page-break-after: always;
}
.eyebrow { margin: 0; color: #e0c58a; font-size: 13px; letter-spacing: .14em; text-transform: uppercase; }
.cover h1 { margin: 0; max-width: 760px; font-size: 64px; line-height: 1.02; letter-spacing: 0; }
.cover-meta { display: grid; grid-template-columns: 110px 1fr; gap: 8px 18px; max-width: 640px; }
.cover-meta span { color: #aec2bf; font-size: 12px; text-transform: uppercase; }
.cover-meta strong { color: #fff; font-size: 14px; overflow-wrap: anywhere; }
.metrics, .toc, .report-section {
  margin-top: 22px;
  background: #fff;
  border: 1px solid #d8ded9;
  border-radius: 12px;
  box-shadow: 0 12px 34px rgb(24 35 47 / 8%);
}
.metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; overflow: hidden; }
.metrics > div { padding: 18px; background: #fbfcfb; }
.metrics span { display: block; color: #62736f; font-size: 12px; font-weight: 700; }
.metrics strong { display: block; margin-top: 5px; color: #123f3d; font-size: 22px; }
.metrics .wave-row { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 8px; background: #fff; }
.wave-row span { padding: 7px 10px; color: #273943; background: #eef5f2; border-radius: 999px; }
.wave-row b { margin-left: 6px; color: #1f5f5b; }
.toc { padding: 24px; }
.toc h2 { margin: 0 0 14px; font-size: 24px; }
.toc div { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.toc a { color: #21323d; text-decoration: none; padding: 10px 12px; border: 1px solid #e2e8e2; border-radius: 8px; }
.toc a span { color: #8a5a22; font-weight: 800; margin-right: 9px; }
.report-section { padding: 30px; page-break-before: always; }
.section-header { display: flex; align-items: center; gap: 16px; padding-bottom: 18px; border-bottom: 2px solid var(--accent); }
.section-header > span { display: grid; place-items: center; width: 48px; height: 48px; color: #fff; background: var(--accent); border-radius: 10px; font-weight: 800; }
.section-header p { margin: 0; color: #65746f; font-size: 12px; font-weight: 700; }
.section-header h2 { margin: 2px 0 0; font-size: 28px; line-height: 1.2; }
.markdown-body { margin-top: 24px; }
.markdown-body h2, .markdown-body h3, .markdown-body h4, .markdown-body h5 { color: #172832; line-height: 1.25; }
.markdown-body h2 { margin-top: 34px; font-size: 26px; }
.markdown-body h3 { margin-top: 28px; font-size: 21px; }
.markdown-body h4, .markdown-body h5 { margin-top: 22px; font-size: 17px; }
.markdown-body p { margin: 12px 0; }
blockquote { margin: 16px 0; padding: 12px 16px; color: #334b45; background: #eef5f2; border-left: 4px solid var(--accent); border-radius: 0 8px 8px 0; }
pre { overflow: auto; padding: 14px; color: #f8fafc; background: #172832; border-radius: 8px; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: .92em; }
p code { padding: 2px 5px; color: #173b38; background: #e8f1ef; border-radius: 5px; }
table { width: 100%; margin: 18px 0; border-collapse: collapse; font-size: 13px; }
th { color: #fff; background: var(--accent); }
th, td { padding: 8px 9px; border: 1px solid #d8ded9; vertical-align: top; }
tr:nth-child(even) td { background: #f8faf8; }
@page { size: A4; margin: 16mm 14mm 18mm; }
@media print {
  body { background: #fff; }
  .report-shell { max-width: none; padding: 0; }
  .cover, .metrics, .toc, .report-section { box-shadow: none; }
}
"""
