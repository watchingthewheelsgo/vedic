from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.vedicdust.rectification_benchmark import (  # noqa: E402
    RectificationBenchmarkArtifact,
    evaluate_rectification_benchmark,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a source-blind VedicDust birth-time rectification benchmark."
    )
    parser.add_argument("artifact", type=Path, help="Benchmark artifact JSON path")
    parser.add_argument("--output", type=Path, help="Optional report JSON path")
    args = parser.parse_args()

    artifact_path = args.artifact.expanduser().resolve()
    artifact = RectificationBenchmarkArtifact.model_validate_json(
        artifact_path.read_text(encoding="utf-8")
    )
    report = evaluate_rectification_benchmark(artifact, artifact_path)
    rendered = report.model_dump_json(by_alias=True, indent=2) + "\n"
    if args.output:
        args.output.expanduser().resolve().write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if report.release_gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
