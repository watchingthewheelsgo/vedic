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

- `chart_record.json` (`vedicdust-chart-record/1.0.0`)
- `chart_audit.json`
- `birth_input_context.json`
- `sensitivity_scan.json`
- `chart_rectification_state.json`
- `reading_session.json`

`chart_record.json` is the sole astrological fact owner. It contains the canonical moment, method profile, astronomy snapshot, D1 and supported vargas, typed facts, Vimshottari periods, quality checks, sensitivity boundaries, and rectification state.

## Calculation policy

- Swiss Ephemeris owns precise D1 astronomical longitudes.
- PyJHora supplies supported vargas and classical strength/timing calculations.
- The method profile fixes Lahiri sidereal zodiac, mean nodes, whole-sign Rashi houses, Parashari varga scheme, and Vimshottari Dasha.
- Every fact carries provenance, method profile, evidence class, confidence, and source IDs.
- D1 may be primary evidence after audit. Vargas are eligible only when their sensitivity policy allows it. D60 is final-confirmation-only.
- Any failed quality check blocks judgement.

## Prohibitions

- Do not produce a Markdown fact dump.
- Do not expose calculator implementation dictionaries as a model prompt.
- Do not let user testimony alter astronomical facts.
- Do not claim a rectified time more precise than the surviving candidate interval.
