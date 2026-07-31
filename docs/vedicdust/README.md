# VedicDust

VedicDust is the product-owned Vedic astrology method and data layer. The
production session runtime owns chart identity, revisions, deterministic
audits, the calculation-to-LLM boundary, and deterministic report rendering.
Legacy Markdown reports remain readable for historical sessions but are no
longer generated or consumed by the VedicDust report pipeline.

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
- Generated JSON Schemas live in `docs/vedicdust/schemas/`.

The deterministic engine is authoritative for calculation and candidate
scoring. Skills are authoritative only for their explicitly declared language
tasks.

## Runtime artifacts

- `reading_session.json`: stable workflow identity and active chart revision.
- `chart_record.json`: internal deterministic chart record.
- `chart_audit.json`: deterministic permission gate for rectification,
  judgement, and report rendering.
- `judgement_context.json`: backend-selected evidence bundles, active rules,
  varga eligibility, and restricted evidence for the active chart revision.
- `claim_graph.json`: evidence-linked judgements for the active chart revision.
- `consultation_dossier.json`: approved reading scope, section plan, timing
  windows, and unresolved questions.
- `agent_context.json`: compact retrieval context for later consultation.
- `consultation_report.md`: deterministic user-facing rendering of the approved
  Dossier and Claim Graph.
- `structured_data.md`: compatibility projection for the reader/calculator UI;
  never authoritative over the chart record.

Internal JSON artifacts are not returned in ordinary user-facing session
responses. The runtime loads them explicitly for calculation, audit, and LLM
context.
