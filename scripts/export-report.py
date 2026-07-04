#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.db.engine import close_db, init_db
from app.services.metadata_store import MetadataStore
from app.services.report_exporter import ReportExporter
from app.services.skill_workspace import SkillWorkspace
from app.settings import get_settings


async def main() -> int:
    parser = argparse.ArgumentParser(description="Export a Vedic session report to HTML and PDF.")
    parser.add_argument("session_id", help="Session id, e.g. skill_mr1dpnm3_fcqxm5vi")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Target directory. Defaults to backend/data/sessions/<session_id>/exports.",
    )
    args = parser.parse_args()

    settings = get_settings()
    await init_db(settings)
    workspace = SkillWorkspace(settings)
    exporter = ReportExporter(workspace)
    try:
        result = exporter.export_session(
            args.session_id,
            output_dir=Path(args.output_dir).expanduser().resolve() if args.output_dir else None,
        )
        await MetadataStore(workspace).sync_session_from_files(args.session_id)
    finally:
        await close_db()

    print(f"session={result.session_id}")
    print(f"sections={result.section_count}")
    print(f"html={result.html_path}")
    print(f"pdf={result.pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
