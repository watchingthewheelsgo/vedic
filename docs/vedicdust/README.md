# VedicDust

VedicDust is the product-owned Vedic astrology method and data layer. It runs
in parallel with the legacy workflow while its calculations and consultation
SOP are validated.

## Pipeline

```text
Birth Assertion
  -> Canonical Birth Moment
  -> Astronomy Snapshot
  -> VedicDust Case
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
