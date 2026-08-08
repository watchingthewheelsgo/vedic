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

- One backend-selected question ID, life-event category, and allowed subtype list
- Locale
- The fields that may be rewritten

No candidate identity, score, chart signature, or holdout event is available.

## Method

1. Preserve the one question ID, category, and subtype options exactly.
2. Ask for a dated, independently remembered event.
3. Give two or three concrete examples of events that qualify.
4. Use calm, non-leading language. Make it acceptable to skip a sensitive topic.
5. Ask for facts, not interpretations of personality, appearance, motives, or symptoms.

## Hard limits

- Never mention or infer the answer favored by a chart candidate.
- Never score evidence or recommend a birth time.
- Never ask the user to confirm a prediction generated from the same candidate set.
- Never promise minute-level or second-level accuracy.
- Never select another pool item, add a question, or change an event category.
