---
name: vedicdust-rectification-confirmation
description: Reserved contract for the deterministic post-rectification confirmation checkpoint.
disable-model-invocation: true
---

# VedicDust Rectification Confirmation

## Purpose

This bundle documents the post-rectification checkpoint. The active runtime does not invoke a model here. After the deterministic service selects a bounded candidate and recalculates the chart, the user reviews the retained interval and its calculation reference time before the full report begins.

Chart-derived retrospective events are not independent evidence and must not be generated merely to make the result appear accurate. This checkpoint must never select a candidate, rank candidates, change the birth time, or create new scoring evidence.

## Input boundary

The active checkpoint receives the deterministic conclusion, calculation reference time, bounded candidate interval, aggregate evidence counts, and up to two submitted-evidence highlights. A calibration highlight explains candidate comparison; a holdout highlight explains the separately reserved check. The visible confirmation cards may recheck those submitted facts, but neither card is a new prediction or another vote used for selection. The checkpoint does not ask a model to infer additional life events.

## Output contract

The backend owns the conclusion schema. Its visible check contains only:

```json
{
  "correctedBirthTime": {"localDate": "YYYY-MM-DD", "localTime": "HH:MM"},
  "selectedInterval": {"start": "local datetime", "end": "local datetime"},
  "evidenceSummary": {"calibrationEventCount": 3, "holdoutEventCount": 1},
  "evidenceHighlights": [{"role": "calibration|holdout", "usedForSelection": true}],
  "confirmation": {"status": "pending", "responses": []}
}
```

No model-generated retrospective example is permitted in the active runtime. Submitted-evidence cards must be labeled as fact rechecks and must never be presented as independent chart hits.

## Writing rules

- Present the retained interval first and label the representative minute as a calculation reference.
- Ask the user to review the retained interval and, when available, confirm the submitted facts shown on the post-selection cards.
- Label confidence and unresolved ambiguity plainly.
- Do not present submitted events as an independent blind hit.
- Do not generate medical, bereavement, legal, or other life-event claims from timing periods.
- A negative confirmation reopens an underdetermined result; it does not silently choose another chart.
