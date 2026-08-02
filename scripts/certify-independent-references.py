#!/usr/bin/env python3
"""Certify the full external Jyotish reference corpus against VedicDust."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recalculate every registered JHora/Parashara's Light case and fail unless "
            "the corpus policy and all field comparisons pass."
        )
    )
    parser.add_argument(
        "--registry",
        default=os.getenv("VEDIC_INDEPENDENT_REFERENCE_REGISTRY"),
        help="Path to the normalized independent-reference registry.",
    )
    parser.add_argument(
        "--minimum-cases",
        type=int,
        default=None,
        help="Required corpus size. Defaults to the VedicDust certification policy.",
    )
    parser.add_argument(
        "--require-tag",
        action="append",
        default=None,
        help="Required corpus coverage tag. Repeat for multiple tags.",
    )
    parser.add_argument(
        "--output", help="Optional JSON report path; otherwise prints stdout."
    )
    return parser.parse_args()


def main() -> int:
    from app.vedicdust.independent_reference import (
        DEFAULT_CERTIFICATION_COVERAGE_TAGS,
        DEFAULT_CERTIFICATION_MINIMUM_CASES,
        certify_independent_reference_registry,
    )

    args = parse_args()
    if not args.registry:
        print(
            "[err] --registry or VEDIC_INDEPENDENT_REFERENCE_REGISTRY is required.",
            file=sys.stderr,
        )
        return 2
    minimum_cases = (
        args.minimum_cases
        if args.minimum_cases is not None
        else DEFAULT_CERTIFICATION_MINIMUM_CASES
    )
    required_tags = set(args.require_tag or DEFAULT_CERTIFICATION_COVERAGE_TAGS)
    try:
        report = certify_independent_reference_registry(
            Path(args.registry),
            minimum_cases=minimum_cases,
            required_coverage_tags=required_tags,
        )
    except Exception as exc:
        print(f"[err] certification could not run: {exc}", file=sys.stderr)
        return 2

    payload = report.model_dump_json(by_alias=True, indent=2) + "\n"
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        print(f"[info] certification report: {output}", file=sys.stderr)
    else:
        print(payload, end="")
    print(
        f"[{report.status}] independent corpus: {report.passed_cases}/{report.total_cases} "
        "cases passed",
        file=sys.stderr,
    )
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
