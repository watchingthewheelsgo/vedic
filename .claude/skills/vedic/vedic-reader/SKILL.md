---
name: vedic-reader
description: Generate evidence-seeking birth-time validation questions from a VedicDust Chart Record and backend-owned candidate plan.
disable-model-invocation: true
---

# VedicDust Birth-Time Validation

## Authoritative inputs

- `chart_record.json`
- `chart_audit.json`
- `birth_input_context.json`
- `sensitivity_scan.json`
- `chart_rectification_state.json`
- prior `rectification_question_set.json`, answer batch, and user feedback when present

## Output

Write only `reader_prevalidation.md` in the runtime response contract. The backend parses it into typed `rectification_question_set.json`, scores answers, updates `chart_rectification_state.json`, and recalculates a new Chart Record revision when a candidate is selected.

## Question method

1. Read `rectificationPlan` before asking anything.
2. Ask only about facts that discriminate at least two surviving candidates.
3. Prefer dated, externally checkable life events over personality language.
4. Keep each question neutral and falsifiable. Include why it is asked without revealing the preferred candidate.
5. Never turn a vague match into confirmation; preserve partly accurate, inaccurate, unknown, and contradictory answers.
6. Stop when the required anchor count is reached. Do not pad a round.

## Release discipline

- Exact or high-confidence input still receives a short holdout check.
- Coarse time or city-level place expands the candidate window within user-provided bounds.
- Precise verified POI coordinates lock the place axis; only time may be rectified.
- No answer may move the time or place outside the reported window/radius.
- The result is a bounded interval or an explicit underdetermined state, never fabricated second-level certainty.
