from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.vedicdust.models import (
    AgentContext,
    ChartAudit,
    ChartRecord,
    ClaimGraph,
    ConsultationDossier,
    ConsultationReportManifest,
    JudgementContext,
    ReadingSession,
    RuleCatalog,
    SynastryContext,
    ValidationFixtureRegistry,
)
from app.vedicdust.independent_reference import (
    IndependentReferenceCertificationReport,
    IndependentReferenceRegistry,
)
from app.vedicdust.professional_review import ProfessionalReviewArtifact


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "vedicdust" / "schemas"
SCHEMAS = {
    "vedicdust-chart-record.schema.json": ChartRecord,
    "vedicdust-reading-session.schema.json": ReadingSession,
    "vedicdust-chart-audit.schema.json": ChartAudit,
    "vedicdust-claim-graph.schema.json": ClaimGraph,
    "vedicdust-judgement-context.schema.json": JudgementContext,
    "vedicdust-consultation-dossier.schema.json": ConsultationDossier,
    "vedicdust-agent-context.schema.json": AgentContext,
    "vedicdust-report-manifest.schema.json": ConsultationReportManifest,
    "vedicdust-rule-catalog.schema.json": RuleCatalog,
    "vedicdust-validation-fixtures.schema.json": ValidationFixtureRegistry,
    "vedicdust-professional-review.schema.json": ProfessionalReviewArtifact,
    "vedicdust-independent-reference-registry.schema.json": IndependentReferenceRegistry,
    "vedicdust-independent-reference-certification.schema.json": (
        IndependentReferenceCertificationReport
    ),
    "vedicdust-synastry-context.schema.json": SynastryContext,
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
