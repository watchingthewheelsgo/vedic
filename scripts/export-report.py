#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from app.services.report_exporter import ReportExporter
from app.services.skill_workspace import SkillWorkspace
from app.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a Vedic session report to HTML and PDF.")
    parser.add_argument("session_id", help="Session id, e.g. skill_mr1dpnm3_fcqxm5vi")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Target directory. Defaults to backend/data/sessions/<session_id>/exports.",
    )
    args = parser.parse_args()

    workspace = SkillWorkspace(get_settings())
    exporter = ReportExporter(workspace)
    result = exporter.export_session(
        args.session_id,
        output_dir=Path(args.output_dir).expanduser().resolve() if args.output_dir else None,
    )

    print(f"session={result.session_id}")
    print(f"sections={result.section_count}")
    print(f"html={result.html_path}")
    print(f"pdf={result.pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
