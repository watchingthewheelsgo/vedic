---
name: vedic-core
description: Orchestrate the native VedicDust judgement and consultation contracts after chart audit and birth-time validation.
disable-model-invocation: true
---

# VedicDust Core Orchestrator

This is an orchestration contract, not a prose-report skill.

## Required gate

The backend must confirm:

- `chart_audit.json` permits judgement;
- prevalidation permits the requested report scope;
- active Chart Record revision matches the rectification state;
- restricted facts and periods have been removed from eligible evidence.

## Native workflow

1. Backend builds `judgement_context.json` from the Chart Record and versioned Rule Catalog.
2. The backend judgement kernel compiles and writes `claim_graph.json`; no model may author its astrological semantics.
3. Deterministic validation rejects unknown facts, unregistered rules, unsupported evidence layers, unstable primary evidence, and unsafe certainty.
4. `vedicdust-consultation` writes `consultation_dossier.json` without adding new astrological claims.
5. Backend deterministically renders `consultation_report.md`, `consultation_report_manifest.json`, and `agent_context.json`.

## Evidence hierarchy

`D1 natal promise -> capacity -> eligible varga confirmation -> timing activation -> user relevance`

Keep evidence roles distinct. `contextFactIds` explains chart structure but does
not support a directional conclusion; only `supportingFactIds` may be described
as affirmative support. Never promote context-only Yoga or association facts.

Vargas confirm a D1 promise; they do not create one. Timing activates a supported promise; it does not manufacture one. User testimony explains relevance; it does not alter the chart.

## Outputs

No stage writes planetary audit chapters, house-by-house batches, or other intermediate prose. The public deliverable is one consultation report backed by typed, reusable evidence contracts.
