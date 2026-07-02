#!/usr/bin/env python3
"""Validate startup configuration that must be present before serving users."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    from app.runtime.preflight import validate_startup_configuration
    from app.settings import get_settings

    try:
        report = validate_startup_configuration(get_settings())
    except Exception as exc:
        print(f"[err] {exc}")
        return 1

    print("[ok] Startup configuration is ready")
    print(f"[ok] Env source: {report.env_file or 'none'}")
    print(f"[ok] Agent mode: {report.agent_mode}")
    print(f"[ok] Base URL: {report.base_url}")
    print(f"[ok] Model: {report.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
