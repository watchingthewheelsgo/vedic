from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.vedicdust.models import (
    CaseAudit,
    ClaimGraph,
    ConsultationReportManifest,
    VedicDustCase,
    RectificationAnswerBatch,
    RectificationQuestionSet,
    RuleCatalog,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "vedicdust" / "schemas"
SCHEMAS = {
    "vedicdust-case.schema.json": VedicDustCase,
    "vedicdust-case-audit.schema.json": CaseAudit,
    "vedicdust-question-set.schema.json": RectificationQuestionSet,
    "vedicdust-answer-batch.schema.json": RectificationAnswerBatch,
    "vedicdust-claim-graph.schema.json": ClaimGraph,
    "vedicdust-report-manifest.schema.json": ConsultationReportManifest,
    "vedicdust-rule-catalog.schema.json": RuleCatalog,
}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        payload = model.model_json_schema(by_alias=True, mode="serialization")
        (OUTPUT_DIR / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    prettier = ROOT / "node_modules" / ".bin" / "prettier"
    if not prettier.exists():
        raise RuntimeError(
            "local Prettier is required; run npm install before exporting schemas"
        )
    subprocess.run([str(prettier), "--write", str(OUTPUT_DIR)], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
