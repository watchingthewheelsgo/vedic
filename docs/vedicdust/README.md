# VedicDust

VedicDust is the product-owned Vedic astrology method and data layer. The
production session runtime owns chart identity, revisions, deterministic
audits, the calculation-to-LLM boundary, and deterministic report rendering.
Only artifacts declared by the current contracts participate in the runtime.

## Pipeline

```text
Birth Assertion
  -> Canonical Birth Moment
  -> Astronomy Snapshot
  -> Chart Record
  -> Chart Audit
  -> Rectification Record (when required)
  -> Judgement Context
  -> Claim Graph
  -> Consultation Dossier
  -> Consultation Report + Agent Context
```

## Authority

- `CONTEXT.md` defines domain language.
- `methodology.md` defines the consultation SOP.
- `backend/app/vedicdust/models.py` defines machine contracts.
- `backend/app/vedicdust/resources/sources.json` is the source registry.
- `backend/app/vedicdust/profiles.py` declares calculation profiles.
- `independent-reference.md` defines external desktop-software certification.
- `vedicdust-professional-review.schema.json` defines retained blind-review evidence.
- Generated JSON Schemas live in `docs/vedicdust/schemas/`.

The deterministic engine is authoritative for calculation and candidate
scoring. Skills are authoritative only for their explicitly declared language
tasks.

## Runtime artifacts

- `reading_session.json`: stable workflow identity and active chart revision.
- `chart_record.json`: canonical deterministic chart record and calculation view.
- `chart_audit.json`: deterministic permission gate for rectification,
  judgement, and report rendering.
- `judgement_context.json`: backend-selected evidence bundles, active rules,
  varga eligibility, restricted evidence, and bounded Judgement Units for the
  active chart revision.
- `claim_graph.json`: backend-published, evidence-linked judgements for the active chart revision.
- `consultation_dossier.json`: approved Claim arrangement, with identity, scope,
  confidence, audience, section presentation, omission language, unresolved
  questions, and timing windows materialized by the backend.
- `agent_context.json`: compact retrieval context for later consultation, including
  authoritative age, life-stage, reader-relationship, and birth-date framing.
- `consultation_report.md`: deterministic user-facing rendering of the approved
  Dossier and Claim Graph.
- `synastry_context.json`: deterministic D1 whole-sign overlays and directed
  Parashari graha drishti for a two-chart consultation.

Workflow-only JSON artifacts are hidden from ordinary report views. `chart_record.json`
remains available to the calculation-stage UI; the runtime loads all contracts explicitly
for audit and bounded LLM context.
