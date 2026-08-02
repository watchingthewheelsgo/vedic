---
name: vedic-rectifier
description: Explain an immutable backend-owned VedicDust birth-time rectification decision and its evidence limits.
disable-model-invocation: true
---

# VedicDust Rectification Audit

## Inputs

- active `chart_record.json`
- `chart_rectification_state.json`

## Method

- Treat both artifacts as immutable backend records.
- Explain the persisted bounded interval, equivalent candidates, or underdetermined result.
- Report the versioned selection, event-mapping, and holdout policy IDs when present.
- Distinguish the user-reported birth assertion from the representative canonical calculation moment.
- Preserve the recorded confidence and residual uncertainty exactly.
- Never score evidence, rank candidates, reinterpret Reader testimony, propose a new time,
  or request confirmation of a model-selected time.

Write `rectification_report.md` as a user-readable audit trail. The backend alone may
select a candidate, update the active Chart Record revision, or open the report gate.
