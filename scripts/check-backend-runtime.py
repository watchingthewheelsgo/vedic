#!/usr/bin/env python3
"""Validate the backend Vedic runtime without installing anything."""

from __future__ import annotations

import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    from app.runtime.preflight import validate_backend_runtime

    try:
        report = validate_backend_runtime(PROJECT_ROOT)
        with redirect_stdout(StringIO()):
            from app.calculator.engine import SIGNS, calculate_full_chart

            chart = calculate_full_chart(
                1869,
                10,
                2,
                7,
                12,
                21.6417,
                69.6293,
                "Asia/Kolkata",
            )
        sav_total = sum(chart["sav"].get(sign, 0) for sign in SIGNS)
        if sav_total != 337:
            raise RuntimeError(f"SAV validation failed: {sav_total} != 337")
    except Exception as exc:
        print(f"[err] Backend runtime is not ready: {exc}")
        print("[err] Run `npm run backend:setup` from the project root.")
        return 1

    print("[ok] Backend runtime is ready")
    print(f"[ok] Dependencies: {', '.join(sorted(report.dependencies.keys()))}")
    print(f"[ok] GeoNames: {report.geonames_path}")
    print(f"[ok] Ephemeris files: {', '.join(report.ephemeris_files)}")
    print(f"[ok] SAV total: {sav_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
