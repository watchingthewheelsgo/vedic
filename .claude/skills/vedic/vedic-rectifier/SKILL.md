---
name: vedic-rectifier
description: Continue a VedicDust birth-time rectification session using typed candidates, questions, answers, and holdout evidence.
disable-model-invocation: true
---

# VedicDust Rectifier

## Inputs

- active `chart_record.json`
- `chart_rectification_state.json`
- `rectification_question_set.json`
- `rectification_answer_batch.json`
- `prevalidation_result.json`
- user-confirmed life-event evidence

## Method

- Compare bounded candidate intervals, not arbitrary timestamps.
- Score only registered rules and exact discriminating facts.
- Separate calibration events from holdout events.
- Recalculate every selected candidate through the deterministic engine.
- Require holdout confirmation before increasing confidence.
- Return bounded interval, equivalent candidates, or underdetermined status.

Write `rectification_report.md` as a user-readable audit trail. The backend alone may update the active Chart Record revision.
