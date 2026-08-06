---
name: vedicdust-rectification-confirmation
description: Generate cautious retrospective confirmation prompts from a finalized Vedic chart after deterministic birth-time rectification.
disable-model-invocation: true
---

# VedicDust Rectification Confirmation

## Purpose

This skill runs only after the deterministic rectification service has selected a bounded candidate and recalculated the chart. It creates at most two plain-language, retrospective prompts so the user can sanity-check the provisional conclusion before the full report begins.

This is a user-facing post-selection confirmation step, not another rectification algorithm. The prompts are derived from the active chart, so they are not independent proof of the selected time. The skill must never select a candidate, rank candidates, change the birth time, or turn an answer into new scoring evidence.

## Input boundary

The input contains only finalized chart facts and timing material. It intentionally does not contain the user's submitted life-event descriptions or the competing candidate charts. Do not infer or recreate those facts.

## Output contract

Return JSON only:

```json
{
  "examples": [
    {
      "category": "career|education|relationship|relocation|child|family|finance|property|spiritual",
      "startDate": "YYYY or YYYY-MM",
      "endDate": "YYYY or YYYY-MM",
      "prompt": "A short neutral question about a possible past change.",
      "rationale": "A short internal explanation based on the supplied timing material."
    }
  ]
}
```

Use zero to two examples only when the supplied material supports them. The backend validator may discard the output if it is unsafe or not independently dated.

## Writing rules

- Ask whether a broad past change may have happened; do not state that it definitely happened.
- Use a year or month range from the supplied material. Never claim an exact day, minute, or certainty.
- Keep each prompt short, concrete, and answerable from memory without writing an essay.
- Prefer observable changes such as a role change, move, study milestone, relationship transition, family change, property decision, or change in spiritual practice.
- Do not use astrology terminology, chart terminology, candidate terminology, or explain the calculation.
- Do not generate medical diagnoses, death, legal accusations, guaranteed outcomes, future predictions, or sensational claims.
- Do not reuse a submitted event or ask the user to agree with a chart-derived assertion.
- If the evidence does not support a safe prompt, return an empty list rather than inventing a life event.
