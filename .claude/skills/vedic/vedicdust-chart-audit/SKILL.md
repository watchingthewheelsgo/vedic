---
name: vedicdust-chart-audit
description: Audit a VedicDust chart record before rectification, judgement, or report rendering.
disable-model-invocation: true
---

# VedicDust Chart Audit

## Purpose

Determine what the workflow may safely do next. This skill audits evidence and
contracts; it does not calculate a chart or interpret a life.

## Inputs

- `chart_record.json`, conforming to `vedicdust-chart-record/1.0.0`
- `docs/vedicdust/methodology.md`
- `docs/vedicdust/schemas/vedicdust-chart-record.schema.json`

If the chart record is missing or fails schema validation, stop with a blocking audit.

## Procedure

1. Validate the JSON contract and schema version.
   Complete when every invalid or unknown field is recorded.
2. Audit Birth Assertion evidence, time window, place precision, IANA time-zone
   resolution, and subject/audience context.
   Complete when every unresolved input has a severity and required action.
3. Audit Calculation Profile completeness and source IDs.
   Complete when no hidden calculation default remains.
4. Audit quality checks and sensitivity boundaries.
   Complete when the chart record is either eligible for judgement, requires
   rectification, or is blocked.
5. Write `chart_audit.json` conforming to `vedicdust-chart-audit/1.0.0`.
   Complete when status, findings, and permitted next steps agree.

## Hard limits

- Never infer a missing time, coordinate, time zone, setting, or calculation.
- Never downgrade a failed deterministic check to a warning.
- Never authorize judgement while required rectification is unresolved.
- Do not write Markdown narrative; output the JSON artifact only.
