---
name: vedicdust-rectification-dialogue
description: Turn engine-computed candidate differences into neutral birth-time rectification questions.
disable-model-invocation: true
---

# Jyotish Rectification Dialogue

## Purpose

Collect discriminating testimony without allowing the model to calculate,
score, or select a birth time.

## Inputs

- `vedicdust_case.json`
- `case_audit.json` authorizing `rectify`
- Candidate Intervals and engine-computed discriminating fact IDs
- Prior `rectification_answer_batch.json` artifacts, if any

Read the rectification section of `docs/vedicdust/methodology.md` before asking
questions.

## Procedure

1. Remove discriminators already answered or lacking at least two materially
   different Candidate Intervals.
   Complete when every remaining discriminator can change candidate support.
2. Rank by event date reliability, discriminatory power, and user burden.
   Complete when the selected set contains at most five questions.
3. Write neutral, concrete questions about observable events. Include
   `unknown` whenever memory may reasonably fail.
   Complete when no option reveals which candidate it supports.
4. Bind every option to candidate IDs exactly as supplied by the engine.
   Complete when every candidate mapping is machine-readable.
5. Write `rectification_question_set.json` conforming to
   `vedicdust-question-set/1.0.0`.

## Stop conditions

Return no new questions and request engine evaluation when there is no unused
discriminator, when prior answers satisfy the round completion condition, or
when further questions would only collect generic personality descriptions.

## Hard limits

- Do not search for a person's biography.
- Do not use appearance, illness, trauma, or fear as a leading shortcut.
- Do not convert free text directly into candidate scores.
- Do not claim exact-minute or exact-second convergence.
- Do not discard `unknown` answers.
