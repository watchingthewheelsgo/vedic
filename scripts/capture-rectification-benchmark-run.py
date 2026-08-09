from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.vedicdust.models import ChartRecord  # noqa: E402
from app.vedicdust.rectification_benchmark import (  # noqa: E402
    RectificationBenchmarkBlindInput,
    RectificationBenchmarkRunReceipt,
    rectification_blind_input_binding_failures,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Capture a revision-pinned receipt binding one source-blind input package "
            "to one terminal VedicDust Chart Record."
        )
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--blind-input", required=True, type=Path)
    parser.add_argument("--chart-record", required=True, type=Path)
    parser.add_argument("--run-operator-id", required=True)
    parser.add_argument("--run-started-at", required=True, type=_aware_datetime)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    blind_path = args.blind_input.expanduser().resolve()
    chart_path = args.chart_record.expanduser().resolve()
    blind = RectificationBenchmarkBlindInput.model_validate_json(
        blind_path.read_text(encoding="utf-8")
    )
    if blind.case_id != args.case_id:
        raise ValueError("blind input belongs to a different case")
    record = ChartRecord.model_validate_json(chart_path.read_text(encoding="utf-8"))
    rectification = record.rectification
    if rectification is None or rectification.reported_window is None:
        raise ValueError("Chart Record has no terminal rectification evidence")
    binding_failures = rectification_blind_input_binding_failures(blind, record)
    if binding_failures:
        raise ValueError(
            "blind input does not match Chart Record: " + "; ".join(binding_failures)
        )

    revision = _git("rev-parse", "HEAD")
    dirty = bool(
        _git(
            "status",
            "--porcelain",
            "--",
            "backend/app",
            "backend/astrology-runtime.lock",
            "backend/pyproject.toml",
            "backend/uv.lock",
            "scripts",
        )
    )
    receipt = RectificationBenchmarkRunReceipt(
        caseId=args.case_id,
        engineRevision=revision,
        engineSourceSha256=_engine_source_digest(),
        workingTreeClean=not dirty,
        runOperatorId=args.run_operator_id,
        runStartedAt=args.run_started_at,
        runCompletedAt=datetime.now(timezone.utc),
        blindInputSha256=_file_digest(blind_path),
        chartRecordSha256=_file_digest(chart_path),
        selectionPolicyId=rectification.selection_policy_id,
        eventMappingId=rectification.event_mapping_id,
        holdoutPolicyId=rectification.holdout_policy_id,
    )
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        receipt.model_dump_json(by_alias=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if dirty:
        sys.stderr.write(
            "warning: receipt records a dirty working tree and is not primary-benchmark eligible\n"
        )
    return 0


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _engine_source_digest() -> str:
    paths = sorted(
        [
            *BACKEND_ROOT.joinpath("app").rglob("*.py"),
            ROOT / "backend" / "astrology-runtime.lock",
            ROOT / "backend" / "pyproject.toml",
            ROOT / "backend" / "uv.lock",
        ],
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return "sha256:" + digest.hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
