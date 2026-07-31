---
name: vedicdust-consultation
description: Render an approved Jyotish Claim Graph as a clear, bounded consultation report.
disable-model-invocation: true
---

# Jyotish Consultation

## Purpose

Translate approved Claims into a readable consultation without changing their
meaning, certainty, scope, or evidence.

## Inputs

- `chart_record.json`
- `chart_audit.json` authorizing `judge`
- `judgement_context.json`
- `claim_graph.json`
- `prevalidation_result.json` and `chart_rectification_state.json`
- Requested locale and reader relationship

## Report order

1. Scope, input quality, and limits
2. Executive synthesis: three to five patterns that organize the reading
3. Chart foundation and core architecture
4. At most five priority domains selected from user concern and chart salience
5. Current, near-term, and strategic timing windows with approved timing Claims
6. Decision support and unresolved consultation questions
7. Technical evidence appendix

## Evidence language

- `high`: "The chart consistently supports..."
- `moderate`: "Several factors support..., with this limitation..."
- `low`: "This is a possible expression, not a firm conclusion..."
- `withheld`: explain why the chart record cannot determine the topic

Use localized plain language for the reader. Keep canonical IDs and Sanskrit or
English technical terms in the appendix. Define a technical term on first use.

## Procedure

1. Build `consultation_dossier.json` before any rendered prose.
2. Select three to five executive Claims. Do not use one Claim per planet,
   house, or varga.
3. Assign every included Claim to exactly one section; record omitted Claims
   and why. Leave `technical_evidence.claimIds` empty because the deterministic
   renderer supplies the evidence table.
4. Build timing windows only from approved timing Claims and exact Chart Record
   periods. State conditions and ranges, never guaranteed events.
5. Keep unresolved questions explicit so later consultations know what remains
   open.
6. Let the backend derive `consultation_report_manifest.json`,
   `consultation_report.md`, and `agent_context.json`. Do not hand-write them.
7. Do not read or reuse legacy p1-p5 reports, appendices, or Markdown audits.
   The Claim Graph is the complete judgement input.

Complete only when the dossier conforms to
`vedicdust-consultation-dossier/1.0.0` and every released Claim is accounted for.

## Hard limits

- Do not use "scientifically proven", "destined", "certain", or equivalent claims.
- Do not diagnose health, promise financial outcomes, or direct irreversible decisions.
- Do not hide uncertainty in the appendix.
- Do not expose internal candidate scores or private testimony unnecessarily.
