#!/usr/bin/env python3
"""Apply Alembic migrations, bootstrapping databases created by older releases."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.engine import _ensure_runtime_columns, normalize_database_url  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.settings import get_settings  # noqa: E402


async def table_names() -> set[str]:
    settings = get_settings()
    engine = create_async_engine(
        normalize_database_url(settings.resolved_database_url())
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_ensure_runtime_columns)
            return await connection.run_sync(
                lambda sync: set(inspect(sync).get_table_names())
            )
    finally:
        await engine.dispose()


def main() -> int:
    tables = asyncio.run(table_names())
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    expected = set(Base.metadata.tables)
    if "alembic_version" in tables:
        command.upgrade(config, "head")
        return 0
    if tables:
        missing = sorted(expected - tables)
        if missing:
            raise SystemExit(
                "Existing database is only partially compatible with the initial migration; "
                f"missing tables: {', '.join(missing)}"
            )
        # Before Alembic was introduced, create_all owned this schema. Stamp only
        # when every current table exists; later revisions remain forward-only.
        command.stamp(config, "head")
        return 0
    command.upgrade(config, "head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
