# VedicDust

VedicDust is the product-owned Vedic astrology method and data layer. The
production session runtime now owns chart identity, revisions, deterministic
audits, and the calculation-to-LLM boundary. Existing Markdown report files
remain compatibility projections while the typed Claim Graph renderer is
validated.

## Pipeline

```text
Birth Assertion
  -> Canonical Birth Moment
  -> Astronomy Snapshot
  -> Chart Record
  -> Chart Audit
  -> Rectification Record (when required)
  -> Claim Graph
  -> Consultation Report
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
- `structured_data.md`: compatibility projection for the current report UI;
  never authoritative over the chart record.

Internal JSON artifacts are not returned in ordinary user-facing session
responses. The runtime loads them explicitly for calculation, audit, and LLM
context.
