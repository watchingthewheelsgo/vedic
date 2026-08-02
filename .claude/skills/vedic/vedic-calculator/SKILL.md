---
name: vedic-calculator
description: Backend-owned VedicDust chart calculation contract for canonical birth data, Jyotish facts, vargas, strengths, timing periods, and sensitivity boundaries.
disable-model-invocation: true
---

# VedicDust Chart Calculator

This skill documents the deterministic calculation interface. The model never hand-calculates or rewrites chart facts.

## Input

- reported local birth date and time
- IANA timezone and historical UTC offset
- WGS84 latitude and longitude with place evidence
- time certainty, source, and bounded search window
- subject context needed for life-stage-safe reporting

## Canonical output

The backend writes:

- `chart_record.json` (`vedicdust-chart-record/1.3.0`)
- `chart_audit.json`
- `birth_input_context.json`
- `sensitivity_scan.json`
- `chart_rectification_state.json`
- `reading_session.json`

`chart_record.json` is the sole astrological fact owner. It contains the canonical moment, method profile, astronomy snapshot, D1 and supported vargas, typed facts, Vimshottari periods, quality checks, input-sensitivity assessment, sensitivity boundaries, and rectification state.

## Calculation policy

- Swiss Ephemeris owns precise D1 astronomical longitudes.
- PyJHora supplies supported vargas and classical strength/timing calculations.
- The method profile fixes Lahiri sidereal zodiac, mean nodes, whole-sign Rashi houses, Parashari varga scheme, and Vimshottari Dasha.
- Every fact carries provenance, method profile, evidence class, calculation confidence,
  input stability, sensitivity dependencies, and source IDs. The backend derives fact
  stability from the exact changed fields in the completed scan; the Agent must not
  replace that grade with whole-chart intuition. Effective judgement confidence is the
  lower of the calculation and input-stability axes.
- D1 may be primary evidence after audit. Vargas are eligible only when their sensitivity policy allows it. D60 is final-confirmation-only.
- Named Yoga facts are emitted only when every condition declared by the pinned
  rule is present. The current Gaja-Kesari implementation is structure-only and
  cannot be expanded by the Agent into fame, wealth, status, or timing claims.
- Vimshottari periods carry their own input stability plus start/end boundary
  envelopes recalculated at the declared birth-window endpoints. Timing claims
  must use the lower of Dasha calculation provenance and birth-window stability,
  and must expose endpoint-sampling limitations instead of presenting one
  provider date as exact.
- Any failed quality check blocks judgement.

## Prohibitions

- Do not produce a Markdown fact dump.
- Do not expose calculator implementation dictionaries as a model prompt.
- Do not let user testimony alter astronomical facts.
- Do not claim a rectified time more precise than the surviving candidate interval.
