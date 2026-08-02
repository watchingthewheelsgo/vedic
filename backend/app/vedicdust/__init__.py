"""VedicDust contracts, evidence models, and method profiles."""

from .models import (
    AgentContext,
    ChartAudit,
    ChartRecord,
    ClaimGraph,
    ConsultationDossier,
    ConsultationReportManifest,
    JudgementContext,
    ReadingSession,
)
from .chart_record_builder import ChartRecordBuildInput, build_chart_record
from .judgement import build_judgement_context
from .claims import build_claim_graph
from .profiles import parashari_lahiri_profile
from .reporting import (
    build_agent_context,
    build_report_manifest,
    materialize_consultation_dossier,
    render_consultation_report,
)

__all__ = [
    "AgentContext",
    "ChartAudit",
    "ChartRecord",
    "ClaimGraph",
    "ConsultationDossier",
    "ConsultationReportManifest",
    "JudgementContext",
    "ReadingSession",
    "ChartRecordBuildInput",
    "build_agent_context",
    "build_chart_record",
    "build_judgement_context",
    "build_claim_graph",
    "build_report_manifest",
    "materialize_consultation_dossier",
    "render_consultation_report",
    "parashari_lahiri_profile",
]
