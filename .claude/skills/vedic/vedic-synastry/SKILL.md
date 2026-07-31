---
name: vedic-synastry
description: Interpret a VedicDust SynastryContext for relationship consultation without recalculating chart evidence.
---

# VedicDust Relationship Consultation

## Contract

Required inputs:

- `chart_record.json`: subject A's canonical chart record.
- `synastry_<label>_<date>/chart_record_B.json`: subject B's canonical chart record.
- `synastry_<label>_<date>/synastry_context.json`: backend-derived D1 overlays and directed Parashari graha drishti.

Write exactly one artifact:

- `synastry_<label>_<date>/reports/relationship_consultation.md`

The skill interprets released evidence. It must not calculate placements, overlays, aspects,
compatibility scores, or timing periods.

## Release Gate

Stop and explain the blocking limitation when:

- `synastry_context.status` is `blocked`;
- either chart revision differs from the corresponding subject reference;
- the two records use different method profiles;
- a requested conclusion requires a technique absent from `synastry_context`.

Do not silently substitute Western degree aspects, composite charts, Ashtakoota, Jaimini,
or a different ayanamsa.

## Interpretation SOP

1. Restate the relationship scope and the user's actual question.
2. Identify three to five high-signal bidirectional patterns from `contacts` and `overlays`.
3. Separate mutual reinforcement, friction, asymmetry, and missing evidence.
4. Cite each technical statement by `overlayId` or `contactId`.
5. Test the leading interpretation against counter-evidence from the opposite direction.
6. Discuss timing only when both chart records provide eligible timing evidence; otherwise state
   that timing is unresolved.
7. Convert the synthesis into observable relationship dynamics and practical decision support.

## Report Structure

Use this order:

1. `# Relationship Consultation`
2. `## Scope and Data Confidence`
3. `## Executive Synthesis`
4. `## How A Activates B`
5. `## How B Activates A`
6. `## Mutual Support and Friction`
7. `## Timing and Limits`
8. `## Practical Guidance`
9. `## Evidence Register`

Keep astrology terminology in the evidence register or explain it immediately in plain language.
Never assign a deterministic compatibility percentage or promise a relationship outcome.
