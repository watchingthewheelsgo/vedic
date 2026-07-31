# ADR 0001: Establish the VedicDust evidence pipeline

- Status: Accepted
- Date: 2026-07-31

## Context

Astronomical calculation, Jyotish derivation, interpretive policy,
rectification heuristics, and report prose require explicit ownership. A caller
must be able to determine which setting or source produced a conclusion, and a
model must not silently bridge gaps between calculated data and narrative.

There is no single universal Jyotish calculation or consultation SOP. Product
choices such as ayanamsa, node model, divisional-chart method, Dasha year
definition, and lineage must therefore be explicit and versioned.

## Decision

Build VedicDust as an evidence pipeline with five separate artifacts:

1. Canonical Birth Moment
2. Astronomy Snapshot
3. Chart Record
4. Rectification Record
5. Claim Graph

The deterministic engine owns the first three artifacts and all candidate
scoring. Skills may audit a Chart Record, conduct an interview from engine-provided
discriminators, and render an approved Claim Graph. Skills may not calculate
placements, invent Method Rules, or choose a birth time without a Rectification
Decision.

The first Calculation Profile is a declared product baseline named
`parashari-lahiri-1.0.0`. It is not represented as the only valid Jyotish
standard. Other lineages require separate profiles and may not be blended
silently.

## Consequences

- VedicDust is the sole Vedic production workflow.
- Every calculated artifact carries a schema version and Calculation Profile.
- Every derived judgement carries source references and counter-evidence.
- Rectification returns an interval and calibrated confidence, not false
  second-level precision.
- Report prose becomes replaceable because it is downstream of the Claim Graph.
- New algorithms cannot enter production without a pinned source, rule ID, and
  regression fixture.
