from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from app.schemas import SkillArtifact
from app.services.skill_workspace import SkillWorkspace

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


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
        self._render_pdf(
            session_id=session_id,
            sections=sections,
            metrics=metrics,
            theme=report_theme,
            pdf_path=pdf_path,
        )

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

    def _render_pdf(
        self,
        *,
        session_id: str,
        sections: list[ReportSection],
        metrics: dict[str, object] | None,
        theme: ThemeConfig,
        pdf_path: Path,
    ) -> None:
        self._register_pdf_fonts()
        styles = self._pdf_styles()
        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            rightMargin=16 * mm,
            leftMargin=16 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title=f"{theme.title} - {session_id}",
            author="VedaLight",
        )
        story: list[object] = [
            Spacer(1, 48),
            Paragraph(theme.subtitle.upper(), styles["CoverEyebrow"]),
            Spacer(1, 18),
            Paragraph(theme.title, styles["CoverTitle"]),
            Spacer(1, 24),
            Paragraph(f"Session: {xml_escape(session_id)}", styles["CoverMeta"]),
            Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["CoverMeta"]),
            PageBreak(),
            Paragraph("Contents", styles["H1"]),
        ]
        for index, section in enumerate(sections, start=1):
            story.append(Paragraph(f"{index:02d}. {xml_escape(section.title)}", styles["TocItem"]))
        if metrics:
            story.append(Spacer(1, 12))
            story.append(Paragraph(f"Core report status: {xml_escape(str(metrics.get('status') or 'recorded'))}", styles["Muted"]))
        story.append(PageBreak())

        for index, section in enumerate(sections, start=1):
            story.append(Paragraph(f"Section {index:02d}", styles["SectionLabel"]))
            story.append(Paragraph(section.title, styles["H1"]))
            story.append(Paragraph(xml_escape(section.path), styles["Muted"]))
            story.append(Spacer(1, 8))
            story.extend(self._markdown_to_pdf_flowables(section.markdown, styles))
            if index < len(sections):
                story.append(PageBreak())

        doc.build(story, onFirstPage=self._pdf_page_footer, onLaterPages=self._pdf_page_footer)

    def _register_pdf_fonts(self) -> None:
        if "STSong-Light" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    def _pdf_styles(self) -> dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        return {
            "CoverEyebrow": ParagraphStyle(
                "CoverEyebrow",
                parent=base["Normal"],
                fontName="STSong-Light",
                fontSize=12,
                leading=16,
                textColor=colors.HexColor("#9A7A4A"),
                alignment=TA_CENTER,
                spaceAfter=6,
            ),
            "CoverTitle": ParagraphStyle(
                "CoverTitle",
                parent=base["Title"],
                fontName="STSong-Light",
                fontSize=34,
                leading=42,
                textColor=colors.HexColor("#2C1F0F"),
                alignment=TA_CENTER,
            ),
            "CoverMeta": ParagraphStyle(
                "CoverMeta",
                parent=base["Normal"],
                fontName="STSong-Light",
                fontSize=10,
                leading=16,
                textColor=colors.HexColor("#5A4A35"),
                alignment=TA_CENTER,
            ),
            "H1": ParagraphStyle(
                "H1",
                parent=base["Heading1"],
                fontName="STSong-Light",
                fontSize=22,
                leading=28,
                textColor=colors.HexColor("#2C1F0F"),
                spaceBefore=8,
                spaceAfter=10,
            ),
            "H2": ParagraphStyle(
                "H2",
                parent=base["Heading2"],
                fontName="STSong-Light",
                fontSize=16,
                leading=22,
                textColor=colors.HexColor("#9A7A4A"),
                spaceBefore=12,
                spaceAfter=7,
            ),
            "H3": ParagraphStyle(
                "H3",
                parent=base["Heading3"],
                fontName="STSong-Light",
                fontSize=13,
                leading=18,
                textColor=colors.HexColor("#2C1F0F"),
                spaceBefore=10,
                spaceAfter=5,
            ),
            "Body": ParagraphStyle(
                "Body",
                parent=base["BodyText"],
                fontName="STSong-Light",
                fontSize=9.6,
                leading=15,
                textColor=colors.HexColor("#3A2A18"),
                alignment=TA_LEFT,
                spaceAfter=6,
            ),
            "Muted": ParagraphStyle(
                "Muted",
                parent=base["BodyText"],
                fontName="STSong-Light",
                fontSize=8.5,
                leading=12,
                textColor=colors.HexColor("#8A7A65"),
                spaceAfter=4,
            ),
            "Quote": ParagraphStyle(
                "Quote",
                parent=base["BodyText"],
                fontName="STSong-Light",
                fontSize=9,
                leading=14,
                leftIndent=8,
                borderColor=colors.HexColor("#C9A96E"),
                borderWidth=1,
                borderPadding=6,
                backColor=colors.HexColor("#FBF7EE"),
                textColor=colors.HexColor("#5A4A35"),
                spaceAfter=7,
            ),
            "Code": ParagraphStyle(
                "Code",
                parent=base["Code"],
                fontName="STSong-Light",
                fontSize=7.6,
                leading=10,
                leftIndent=6,
                rightIndent=6,
                backColor=colors.HexColor("#F0E8D8"),
                textColor=colors.HexColor("#2C1F0F"),
                spaceAfter=7,
            ),
            "TableCell": ParagraphStyle(
                "TableCell",
                parent=base["BodyText"],
                fontName="STSong-Light",
                fontSize=6.8,
                leading=8.4,
                textColor=colors.HexColor("#2C1F0F"),
            ),
            "TableHeader": ParagraphStyle(
                "TableHeader",
                parent=base["BodyText"],
                fontName="STSong-Light",
                fontSize=7,
                leading=8.8,
                textColor=colors.white,
            ),
            "TocItem": ParagraphStyle(
                "TocItem",
                parent=base["BodyText"],
                fontName="STSong-Light",
                fontSize=11,
                leading=17,
                textColor=colors.HexColor("#2C1F0F"),
                spaceAfter=4,
            ),
            "SectionLabel": ParagraphStyle(
                "SectionLabel",
                parent=base["BodyText"],
                fontName="STSong-Light",
                fontSize=8,
                leading=11,
                textColor=colors.HexColor("#9A7A4A"),
                spaceAfter=2,
            ),
        }

    def _markdown_to_pdf_flowables(
        self,
        markdown: str,
        styles: dict[str, ParagraphStyle],
    ) -> list[object]:
        flowables: list[object] = []
        lines = markdown.splitlines()
        index = 0
        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            if not stripped or stripped == "---":
                index += 1
                continue
            if stripped.startswith("```"):
                code_lines: list[str] = []
                index += 1
                while index < len(lines) and not lines[index].strip().startswith("```"):
                    code_lines.append(lines[index])
                    index += 1
                flowables.append(Paragraph(self._pdf_code_text("\n".join(code_lines)), styles["Code"]))
                index += 1
                continue
            if self._is_table_start(lines, index):
                table_lines: list[str] = []
                while index < len(lines) and lines[index].strip().startswith("|"):
                    table_lines.append(lines[index])
                    index += 1
                table = self._table_to_pdf(table_lines, styles)
                if table is not None:
                    flowables.append(table)
                    flowables.append(Spacer(1, 8))
                continue
            heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
            if heading:
                level = len(heading.group(1))
                style_name = "H1" if level == 1 else "H2" if level == 2 else "H3"
                flowables.append(Paragraph(self._pdf_inline(heading.group(2)), styles[style_name]))
                index += 1
                continue
            if stripped.startswith(">"):
                quote_lines: list[str] = []
                while index < len(lines) and lines[index].strip().startswith(">"):
                    quote_lines.append(lines[index].strip().lstrip(">").strip())
                    index += 1
                flowables.append(Paragraph(self._pdf_inline(" ".join(quote_lines)), styles["Quote"]))
                continue
            if re.match(r"^[-*]\s+", stripped):
                items: list[ListItem] = []
                while index < len(lines) and re.match(r"^[-*]\s+", lines[index].strip()):
                    text = re.sub(r"^[-*]\s+", "", lines[index].strip())
                    items.append(ListItem(Paragraph(self._pdf_inline(text), styles["Body"])))
                    index += 1
                flowables.append(ListFlowable(items, bulletType="bullet", start="-", leftIndent=14))
                continue
            paragraph: list[str] = [stripped]
            index += 1
            while index < len(lines) and lines[index].strip() and not self._starts_block(lines, index):
                paragraph.append(lines[index].strip())
                index += 1
            flowables.append(Paragraph(self._pdf_inline(" ".join(paragraph)), styles["Body"]))
        return flowables

    def _table_to_pdf(
        self,
        lines: list[str],
        styles: dict[str, ParagraphStyle],
    ) -> Table | None:
        rows = [
            [cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in lines
        ]
        if len(rows) < 2:
            return None
        head = rows[0]
        body = rows[2:]
        column_count = max(len(row) for row in [head, *body])
        if column_count == 0:
            return None
        normalized = [
            row + [""] * (column_count - len(row))
            for row in [head, *body]
        ]
        data = [
            [
                Paragraph(
                    self._pdf_inline(cell),
                    styles["TableHeader"] if row_index == 0 else styles["TableCell"],
                )
                for cell in row
            ]
            for row_index, row in enumerate(normalized)
        ]
        available_width = A4[0] - 32 * mm
        table = Table(
            data,
            repeatRows=1,
            colWidths=[available_width / column_count] * column_count,
            splitByRow=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#9A7A4A")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D6C6A5")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#FBF7EE")),
                ]
            )
        )
        return table

    def _pdf_inline(self, text: str) -> str:
        escaped = xml_escape(text)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
        escaped = re.sub(r"`([^`]+)`", '<font name="STSong-Light" color="#9A7A4A">\\1</font>', escaped)
        return escaped

    def _pdf_code_text(self, text: str) -> str:
        escaped = xml_escape(text)
        return escaped.replace("\n", "<br/>")

    def _pdf_page_footer(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("STSong-Light", 8)
        canvas.setFillColor(colors.HexColor("#8A7A65"))
        canvas.drawCentredString(A4[0] / 2, 9 * mm, f"VedaLight Report - {doc.page}")
        canvas.restoreState()

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
        # Gold / cream / dark theme aligned with the web app (Downloads/test.html).
        return """
:root {
  color: #2C1F0F;
  background: #F0E8D8;
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
  color: #FAF5EC;
  background:
    linear-gradient(135deg, rgb(15 12 9 / 94%), rgb(42 32 24 / 90%)),
    radial-gradient(circle at 22% 24%, #C9A96E, transparent 36%);
  border-radius: 14px;
  padding: 54px;
  page-break-after: always;
}
.eyebrow { margin: 0; color: #EDD9A3; font-size: 13px; letter-spacing: .14em; text-transform: uppercase; }
.cover h1 { margin: 0; max-width: 760px; font-size: 64px; line-height: 1.02; letter-spacing: 0; font-weight: 300; }
.cover h1 strong, .cover h1 b { color: #C9A96E; font-weight: 600; }
.cover-meta { display: grid; grid-template-columns: 110px 1fr; gap: 8px 18px; max-width: 640px; }
.cover-meta span { color: rgb(237 217 163 / 65%); font-size: 12px; text-transform: uppercase; }
.cover-meta strong { color: #fff; font-size: 14px; overflow-wrap: anywhere; }
.metrics, .toc, .report-section {
  margin-top: 22px;
  background: #FAF5EC;
  border: 1px solid rgba(201,169,110,0.3);
  border-radius: 12px;
  box-shadow: 0 12px 34px rgb(44 31 15 / 8%);
}
.metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; overflow: hidden; }
.metrics > div { padding: 18px; background: #FBF7EE; }
.metrics span { display: block; color: #8A7A65; font-size: 12px; font-weight: 700; }
.metrics strong { display: block; margin-top: 5px; color: #9A7A4A; font-size: 22px; }
.metrics .wave-row { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 8px; background: #FAF5EC; }
.wave-row span { padding: 7px 10px; color: #5A4A35; background: #F0E8D8; border-radius: 999px; }
.wave-row b { margin-left: 6px; color: #9A7A4A; }
.toc { padding: 24px; }
.toc h2 { margin: 0 0 14px; font-size: 24px; }
.toc div { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.toc a { color: #2C1F0F; text-decoration: none; padding: 10px 12px; border: 1px solid rgba(201,169,110,0.3); border-radius: 8px; }
.toc a span { color: #9A7A4A; font-weight: 800; margin-right: 9px; }
.report-section { padding: 30px; page-break-before: always; }
.section-header { display: flex; align-items: center; gap: 16px; padding-bottom: 18px; border-bottom: 2px solid var(--accent); }
.section-header > span { display: grid; place-items: center; width: 48px; height: 48px; color: #fff; background: var(--accent); border-radius: 10px; font-weight: 800; }
.section-header p { margin: 0; color: #8A7A65; font-size: 12px; font-weight: 700; }
.section-header h2 { margin: 2px 0 0; font-size: 28px; line-height: 1.2; }
.markdown-body { margin-top: 24px; }
.markdown-body h2, .markdown-body h3, .markdown-body h4, .markdown-body h5 { color: #2C1F0F; line-height: 1.25; }
.markdown-body h2 { margin-top: 34px; font-size: 26px; color: #9A7A4A; }
.markdown-body h3 { margin-top: 28px; font-size: 21px; }
.markdown-body h4, .markdown-body h5 { margin-top: 22px; font-size: 17px; }
.markdown-body p { margin: 12px 0; color: #5A4A35; }
blockquote { margin: 16px 0; padding: 12px 16px; color: #5A4A35; background: rgba(201,169,110,0.09); border-left: 4px solid var(--accent); border-radius: 0 8px 8px 0; }
pre { overflow: auto; padding: 14px; color: #F0E8D8; background: #1C1610; border-radius: 8px; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: .92em; }
p code { padding: 2px 5px; color: #9A7A4A; background: #F0E8D8; border-radius: 5px; }
table { width: 100%; margin: 18px 0; border-collapse: collapse; font-size: 13px; }
th { color: #fff; background: var(--accent); }
th, td { padding: 8px 9px; border: 1px solid rgba(201,169,110,0.3); vertical-align: top; }
tr:nth-child(even) td { background: #FBF7EE; }
@page { size: A4; margin: 16mm 14mm 18mm; }
@media print {
  body { background: #fff; }
  .report-shell { max-width: none; padding: 0; }
  .cover, .metrics, .toc, .report-section { box-shadow: none; }
}
"""
