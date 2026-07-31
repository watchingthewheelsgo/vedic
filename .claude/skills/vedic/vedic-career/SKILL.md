---
name: vedic-career
description: Answer career questions from released VedicDust claims without creating new chart judgements.
disable-model-invocation: true
---

# VedicDust Career Consultation

Read `agent_context.json`, `claim_graph.json`, `consultation_dossier.json`, and `chart_record.json`.

Write `career_report.md` with:

1. direct answer to the user's decision;
2. relevant released claims and exact evidence IDs;
3. supporting and counter-evidence;
4. bounded timing windows already released by the dossier;
5. practical options, risks, and decision conditions;
6. unanswered questions that would materially change the advice.

Do not infer a new career promise, invent timing, promise income, or treat a D10 signal as independent of D1.
