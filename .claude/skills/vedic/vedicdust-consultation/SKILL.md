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
- `chart_audit.json` authorizing `render_report`
- `claim_graph.json`
- Requested locale and reader relationship

## Report order

1. Scope, input quality, and limits
2. Orientation: the few patterns that organize the rest of the reading
3. Requested life domains
4. Timing windows that have approved timing Claims
5. Practical observations and decision questions
6. Technical evidence appendix

## Evidence language

- `high`: "The chart consistently supports..."
- `moderate`: "Several factors support..., with this limitation..."
- `low`: "This is a possible expression, not a firm conclusion..."
- `withheld`: explain why the chart record cannot determine the topic

Use localized plain language for the reader. Keep canonical IDs and Sanskrit or
English technical terms in the appendix. Define a technical term on first use.

## Procedure

1. Build `consultation_report_manifest.json` before prose.
2. Assign every included Claim to one section; record omitted Claims and why.
3. Write each section as meaning, evidence, counterweight, limit, and practical
   observation. Omit empty elements rather than fabricating content.
4. Generate `consultation_report.md` from the manifest.
5. Verify every factual sentence maps to a Claim or subject context.

Complete only when the manifest conforms to
`vedicdust-report-manifest/1.0.0` and the report adds no unsupported conclusion.

## Hard limits

- Do not use "scientifically proven", "destined", "certain", or equivalent claims.
- Do not diagnose health, promise financial outcomes, or direct irreversible decisions.
- Do not hide uncertainty in the appendix.
- Do not expose internal candidate scores or private testimony unnecessarily.
