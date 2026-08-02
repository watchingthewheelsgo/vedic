---
name: vedic-reader
description: Generate neutral pre-reading quality checks for a scan-stable VedicDust Chart Record.
disable-model-invocation: true
---

# VedicDust Pre-Reading Validation

## Authoritative inputs

- `chart_record.json`
- `chart_audit.json`
- `birth_input_context.json`
- `sensitivity_scan.json`
- `chart_rectification_state.json`
- prior user feedback when present

The runtime supplies a calibration-only snapshot of these inputs. Reserved
holdout events, scores, decisions, and derived partitions are structurally
excluded from the Agent context and must never be requested or reconstructed.

Birth-time candidate ranking is not an Agent responsibility. The backend alone
scores structured calibration events, evaluates the reserved holdout, and
materializes a selected bounded interval. This skill is invoked only when the
bounded sensitivity scan is stable and `chart_rectification_state.status` is
`not_required`.

## Output

Write only `reader_prevalidation.md` in the runtime response contract. The
backend parses it into typed questions and uses the answers as reading-quality
context. These answers cannot select a birth-time candidate, move the reported
time/place, or recalculate the Chart Record.

## Question method

1. Confirm that the state is `not_required`; otherwise stop rather than inventing
   a question set.
2. Ask 1-5 short questions about concrete, user-answerable past facts supported
   by facts that are stable across the reported input window.
3. Prefer externally checkable events over personality language.
4. Keep each question neutral and falsifiable. Include a concise derivation for
   audit, but never expose technical astrology in the visible question.
5. Never turn a vague match into confirmation; preserve partly accurate,
   inaccurate, unknown, and contradictory answers.
6. Do not emit Candidate, Contrast, Event, or Field machine mappings. Submitted
   life events are not independent again merely because the Agent restates them.

## Release discipline

- Holdout evaluation is backend-only; the Agent never sees or asks about the
  reserved event.
- Coarse time or city-level place expands the candidate window within user-provided bounds.
- Precise verified POI coordinates lock the place axis; only time may be rectified.
- No answer may move the time or place outside the reported window/radius.
- The result is a bounded interval or an explicit underdetermined state, never fabricated second-level certainty.
