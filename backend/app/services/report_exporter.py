from __future__ import annotations

import html
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.schemas import SkillArtifact
from app.services.skill_workspace import SkillWorkspace


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
    markdown: str
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
            subtitle="Data-Driven Vedic Astrology",
            accent_palette=(
                "#C9A96E",
                "#9A7A4A",
                "#B58A45",
                "#8a5a22",
                "#7a5a2a",
                "#6d4c1d",
            ),
        )


@dataclass(frozen=True)
class ReportExportResult:
    session_id: str
    html_path: Path
    pdf_path: Path
    section_count: int


class ReportExporter:
    """Export session markdown artifacts into themed HTML."""

    def __init__(self, workspace: SkillWorkspace) -> None:
        self.workspace = workspace

    def export_session(
        self,
        session_id: str,
        *,
        output_dir: Path | None = None,
        theme: ThemeConfig | None = None,
    ) -> ReportExportResult:
        artifacts = self.workspace.read_artifacts(session_id)
        report_theme = theme or ThemeConfig.private_advisor()
        sections = self._collect_sections(artifacts, report_theme)
        if not sections:
            raise ValueError("No public report artifacts found for export")

        metrics = self._load_metrics(artifacts)
        target_dir = output_dir or (self.workspace.require_session_dir(session_id) / "exports")
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
        pdf_path = target_dir / "report.pdf"
        self._render_pdf_with_playwright(html_path=html_path, pdf_path=pdf_path)

        return ReportExportResult(
            session_id=session_id,
            html_path=html_path,
            pdf_path=pdf_path,
            section_count=len(sections),
        )

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
                    markdown=artifact.content,
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

    def _render_pdf_with_playwright(self, *, html_path: Path, pdf_path: Path) -> None:
        script_path = self.workspace.settings.project_root / "scripts" / "render-report-pdf.mjs"
        command = [
            "node",
            str(script_path),
            "--input",
            str(html_path),
            "--output",
            str(pdf_path),
        ]
        try:
            result = subprocess.run(
                command,
                cwd=self.workspace.settings.project_root,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Cannot export PDF because Node.js is not available. Install Node.js and run `npm install`."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("PDF export timed out while rendering the report with Playwright.") from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(
                "PDF export failed. Ensure project dependencies are installed with `npm install` "
                "and Playwright Chromium is available with `npx playwright install chromium`."
                + (f"\n{detail}" if detail else "")
            )

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
  color: #17201f;
  background: #f6f4ee;
  font-family: "Iowan Old Style", "Songti SC", "Noto Serif SC", "Source Han Serif SC", Georgia, serif;
  line-height: 1.66;
  font-size: 11pt;
  letter-spacing: 0;
}
* { box-sizing: border-box; }
html { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
body { margin: 0; background: #f6f4ee; }
.report-shell { max-width: 980px; margin: 0 auto; padding: 32px; }
.cover {
  min-height: 760px;
  display: grid;
  align-content: center;
  gap: 34px;
  color: #f9f7ef;
  background:
    linear-gradient(135deg, rgb(23 32 31 / 98%), rgb(36 55 52 / 96%)),
    linear-gradient(90deg, rgb(177 142 74 / 62%), transparent 42%);
  border: 1px solid rgb(185 148 79 / 42%);
  border-radius: 4px;
  padding: 58px 62px;
  break-after: page;
}
.eyebrow {
  width: fit-content;
  margin: 0;
  padding-bottom: 8px;
  border-bottom: 1px solid rgb(185 148 79 / 80%);
  color: #d7c28d;
  font-family: "Avenir Next", "Helvetica Neue", Arial, sans-serif;
  font-size: 10pt;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0;
}
.cover h1 {
  margin: 0;
  max-width: 680px;
  font-size: 54pt;
  line-height: 0.98;
  font-weight: 400;
  letter-spacing: 0;
}
.cover h1 strong, .cover h1 b { color: #d8bd78; font-weight: 650; }
.cover-meta {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr);
  gap: 8px 18px;
  max-width: 620px;
  margin-top: 14px;
  padding-top: 22px;
  border-top: 1px solid rgb(249 247 239 / 18%);
}
.cover-meta span {
  color: rgb(249 247 239 / 56%);
  font-family: "Avenir Next", "Helvetica Neue", Arial, sans-serif;
  font-size: 8.5pt;
  text-transform: uppercase;
}
.cover-meta strong { color: #fffdf8; font-size: 10pt; font-weight: 500; overflow-wrap: anywhere; }
.metrics, .toc, .report-section {
  margin-top: 24px;
  background: #fffdf8;
  border: 1px solid rgb(23 32 31 / 12%);
  border-radius: 4px;
}
.metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0; overflow: hidden; break-after: page; }
.metrics > div { padding: 17px 18px; border-right: 1px solid rgb(23 32 31 / 10%); }
.metrics span {
  display: block;
  color: #65716f;
  font-family: "Avenir Next", "Helvetica Neue", Arial, sans-serif;
  font-size: 8.5pt;
  font-weight: 700;
}
.metrics strong { display: block; margin-top: 5px; color: #1f3d3a; font-size: 18pt; font-weight: 500; }
.metrics .wave-row { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 6px; border-top: 1px solid rgb(23 32 31 / 10%); }
.wave-row span { padding: 5px 8px; color: #465552; background: #f1f4f1; border-radius: 999px; }
.wave-row b { margin-left: 5px; color: #1f3d3a; }
.toc { padding: 28px 30px; break-after: page; }
.toc h2 {
  margin: 0 0 18px;
  color: #1f3d3a;
  font-size: 25pt;
  font-weight: 430;
}
.toc div { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 14px; }
.toc a {
  color: #17201f;
  text-decoration: none;
  padding: 8px 0;
  border-bottom: 1px solid rgb(23 32 31 / 12%);
  font-size: 10pt;
}
.toc a span { display: inline-block; min-width: 28px; color: #b9944f; font-weight: 700; }
.report-section {
  padding: 0;
  border: 0;
  background: transparent;
  break-before: page;
}
.section-header {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
  padding: 0 0 15px;
  border-bottom: 1.5px solid #b9944f;
}
.section-header > span {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  color: #fffdf8;
  background: #1f3d3a;
  border-radius: 50%;
  font-family: "Avenir Next", "Helvetica Neue", Arial, sans-serif;
  font-size: 10pt;
  font-weight: 800;
}
.section-header p {
  margin: 0;
  color: #65716f;
  font-family: "Avenir Next", "Helvetica Neue", Arial, sans-serif;
  font-size: 8pt;
  font-weight: 700;
}
.section-header h2 { margin: 3px 0 0; color: #17201f; font-size: 25pt; line-height: 1.12; font-weight: 430; }
.markdown-body { margin-top: 18px; }
.markdown-body h2, .markdown-body h3, .markdown-body h4, .markdown-body h5 {
  color: #17201f;
  line-height: 1.25;
  break-after: avoid;
  letter-spacing: 0;
}
.markdown-body h2 {
  margin: 25px 0 10px;
  padding-top: 8px;
  color: #1f3d3a;
  border-top: 1px solid rgb(185 148 79 / 36%);
  font-size: 18pt;
  font-weight: 500;
}
.markdown-body h3 { margin: 20px 0 8px; font-size: 14.5pt; font-weight: 560; }
.markdown-body h4, .markdown-body h5 { margin: 16px 0 6px; font-size: 11.5pt; font-weight: 650; }
.markdown-body p {
  margin: 7px 0;
  color: #273331;
  font-size: 10pt;
  line-height: 1.72;
  orphans: 3;
  widows: 3;
}
blockquote {
  margin: 13px 0;
  padding: 10px 13px 10px 15px;
  color: #243936;
  background: #eff4f0;
  border-left: 3px solid #b9944f;
  break-inside: avoid;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin: 12px 0;
  padding: 10px 12px;
  color: #18231f;
  background: #f1f4f1;
  border: 1px solid rgb(23 32 31 / 10%);
  border-radius: 3px;
  font-size: 8pt;
  line-height: 1.45;
  break-inside: avoid;
}
code { font-family: "SFMono-Regular", Menlo, Consolas, monospace; font-size: 0.88em; }
p code { padding: 1px 4px; color: #1f3d3a; background: #eef3ef; border-radius: 3px; }
table {
  width: 100%;
  margin: 13px 0 15px;
  border-collapse: collapse;
  font-family: "Avenir Next", "Helvetica Neue", Arial, sans-serif;
  font-size: 7.8pt;
  line-height: 1.38;
  break-inside: auto;
}
thead { display: table-header-group; }
tr { break-inside: avoid; }
th {
  color: #fffdf8;
  background: #1f3d3a;
  font-weight: 700;
}
th, td { padding: 5px 6px; border: 1px solid rgb(23 32 31 / 16%); vertical-align: top; }
td { color: #273331; }
tr:nth-child(even) td { background: #f7f8f4; }
@page { size: A4; }
@media print {
  body { background: #fffdf8; }
  .report-shell { max-width: none; padding: 0; }
  .cover { min-height: 247mm; }
  .cover, .metrics, .toc, .report-section { box-shadow: none; }
}
"""
