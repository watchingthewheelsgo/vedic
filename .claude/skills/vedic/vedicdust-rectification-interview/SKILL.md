---
name: vedicdust-rectification-interview
description: Turn backend-selected birth-time evidence briefs into clear, neutral life-event questions.
disable-model-invocation: true
---

# VedicDust Rectification Interview

## Purpose

Make a deterministic rectification evidence request easy for a user to answer.
The backend owns candidate generation, event-category selection, scoring,
holdout validation, stopping, and every birth-time decision.

## Inputs

- A backend-approved question pool, with one primary question and zero or more
  alternate questions; each item has a fixed life-event category and allowed
  subtype list
- Locale
- The fields that may be rewritten

No candidate identity, score, chart signature, or holdout event is available.

## Method

1. Choose exactly one item from the backend-approved question pool. Preserve its
   question ID, category, and subtype options exactly; do not invent a new item.
2. Ask for a dated, independently remembered event.
3. Give two or three concrete examples of events that qualify.
4. Use calm, non-leading language. Make it acceptable to skip a sensitive topic.
5. Ask for facts, not interpretations of personality, appearance, motives, or symptoms.

When the runtime requests an evidence audit rather than question wording:

1. Treat the backend-bound category, subtype, and date as the user's explicit selection.
2. Return `clear` unless the user's own note explicitly contradicts that selection,
   denies that the event occurred, or states genuine uncertainty about occurrence/date.
3. Do not request clarification merely because an optional note is absent or brief.
4. If clarification is necessary, choose one allowed reason code and ask one neutral,
   factual question that lets the user confirm or correct the answer.
5. Never score the event or infer which answer would favor a candidate chart.

## Hard limits

- Never mention or infer the answer favored by a chart candidate.
- Never score evidence or recommend a birth time.
- Never ask the user to confirm a prediction generated from the same candidate set.
- Never promise minute-level or second-level accuracy.
- Never add a question, change an event category, or choose an item outside the
  backend-approved pool. The pool is the only adaptive choice exposed to the
  Agent; scoring and stopping remain backend-owned.
