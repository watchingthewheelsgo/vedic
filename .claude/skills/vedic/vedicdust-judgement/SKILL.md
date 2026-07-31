---
name: vedicdust-judgement
description: Build an auditable Claim Graph from approved Jyotish facts and Method Rules.
disable-model-invocation: true
---

# Jyotish Judgement

## Purpose

Apply an approved rule pack to a qualified case. This skill produces structured
judgements, not report prose.

## Inputs

- `vedicdust_case.json` with status `ready_for_judgement`
- `case_audit.json` authorizing `judge`
- The exact Method Rule pack named by the Calculation Profile
- Source registry and rule-specific references

The production catalog is `backend/app/vedicdust/resources/rules.json`. A rule
absent from that catalog does not exist for this workflow.

## Judgement order

1. Establish D1 natal promise.
2. Establish capacity from dignity and declared strength measures.
3. Seek confirmation or contradiction only in eligible vargas.
4. Apply timing only where natal promise and capacity exist.
5. Record counter-evidence before assigning certainty.
6. Withhold topics that lack sufficient evidence.

## Procedure

For each requested topic:

1. Resolve applicable Method Rules; do not invent a rule.
2. Record supporting, contradicting, and timing fact IDs.
3. Require natal promise plus capacity for a strong structural Claim.
4. Require natal promise, capacity, and timing for a forecast Claim.
5. Assign `high`, `moderate`, `low`, or `withheld` from evidence completeness,
   not rhetorical confidence.
6. Write `claim_graph.json` conforming to `vedicdust-claim-graph/1.0.0`.

Complete only when every Claim is traceable and every omitted requested topic
has a reason.

## Hard limits

- User testimony may test expression but cannot create a chart promise.
- A varga cannot create a promise absent from D1.
- A Dasha cannot create an event absent from natal promise.
- Never mix rules from another Calculation Profile.
- Do not write advice, reassurance, diagnosis, or report sections.
