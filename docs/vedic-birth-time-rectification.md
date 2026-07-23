# Vedic Birth Time Rectification

This document describes the backend-owned rectification mechanism used after a
birth time and place have been converted into chart data.

## Goal

The system must not treat prevalidation as generic personality confirmation.
When the input can produce multiple materially different charts, prevalidation
must discriminate between explicit chart candidates, collect user feedback, and
either confirm the base chart, select a corrected candidate for recalculation, or
keep the report low-confidence.

## Artifacts

- `birth_input_context.json`: original reported time/place, resolved coordinates,
  timezone, allowed time window, place radius, rectification guardrails, and
  optional `lifeEvents`.
- `sensitivity_scan.json`: base chart signature, time/place variants, unstable
  fields, all 15 divisional chart confidence entries, report readiness, and
  initial candidate groups.
- `chart_rectification_state.json`: backend-owned multi-round state. This is the
  source of truth for candidate scores, active candidate, report gate, and the
  next round plan.
- `reader_prevalidation.md`: user-facing 3-5 validation anchors written by the
  reader.
- `prevalidation_result.json`: deterministic backend scoring and report gate.

## Candidate Loop

1. The calculator writes `birth_input_context.json` and `sensitivity_scan.json`.
2. `ChartRectificationService.initial_state()` builds
   `chart_rectification_state.json`.
3. If `reportReadiness.mode=rectification_required`, the state includes
   `rectificationPlan`:
   - `targetCandidateIds`
   - `discriminatingFields`
   - `focusAxes`
     - narrowed `timeWindow` / `placeWindow`
     - `divisionalSensitivity`
     - `advancedVargaPolicy`
     - `requiredAnchorCount`
     - stop conditions
4. The reader must generate anchors from `rectificationPlan`, not from free-form
   intuition.
5. User feedback updates candidate scores cumulatively across rounds.
6. If a candidate has clear support, the backend either:
   - confirms the base chart, or
   - selects a non-base candidate and recalculates the chart from its time/place
     members.
7. If no candidate is clear, the backend writes a narrower next
   `rectificationPlan` for the following reader round.

## Life Event Anchors

Birth time rectification should be grounded in dated life events, not only
generic traits. The intake form accepts optional major events such as marriage,
relocation, career change, childbirth, surgery, or major loss.

The calculator parses those events deterministically into
`birth_input_context.json.lifeEvents`:

- `eventId`
- `date` and `datePrecision`
- event `category`
- user-provided description
- rectification rules: relevant houses, vargas, karakas, and preferred unstable
  fields

`ChartRectificationService.initial_state()` copies this ledger into
`chart_rectification_state.json.lifeEventLedger` and adds
`rectificationPlan.lifeEventFocus`. When `lifeEventFocus` exists, high-risk
reader anchors must include:

- `> Candidate: ...`
- `> Field: ...`
- `> Event: ...`

The backend rejects reader output that omits the event line or references an
unknown event. This keeps the loop tied to concrete user history and prevents
the reader from treating broad personality hits as birth-time proof.

## Divisional Sensitivity Policy

The calculator now tracks the standard divisional chart set:

`D1, D2, D3, D4, D5, D7, D9, D10, D12, D16, D20, D24, D27, D30, D60`.

All of these are derived from the same birth time, latitude, longitude, timezone,
Swiss Ephemeris, and PyJHora divisional calculation chain. They are all time
sensitive, because divisional lagna changes faster as the factor rises. As a
rough average, one D1 lagna sign spans about 120 minutes, so a D60 lagna slice is
about 2 minutes. Actual ascensional speed varies by latitude and sign, so the
backend still uses concrete sensitivity samples instead of relying only on this
average.

The backend writes for every division:

- `confidence`
- `approxLagnaIntervalMinutes`
- `changedInScan`
- `usageTier`
- `recommendedUse`
- `useAsPrimaryEvidence`

The policy is intentionally conservative:

- D1 is the foundation.
- D2/D3/D4/D5 are supporting domain charts.
- D7/D9/D10/D12 are useful for rectification when they change across candidate
  times and can be tied to dated life events.
- D16/D20/D24/D27/D30 are corroboration-only until the birth-time window is
  narrow.
- D60 is final-confirmation-only. It must not drive first-pass report claims or
  candidate selection by itself.

Candidate grouping includes D2/D3/D4/D5/D7/D9/D10/D12 lagna changes, but does
not split candidates on D16+ or D60 alone. Those higher vargas remain visible in
`divisionalSensitivity` and `advancedVargaPolicy`, so the reader can use them as
restricted evidence without exploding the candidate set.

## Current Limits

- The backend narrows from existing candidate member times. It does not yet
  resample every midpoint/minute inside the narrowed window.
- Life event parsing currently maps events to houses/vargas/fields. It does not
  yet score exact historical dasha/transit hits against each candidate.
- The divisional policy prevents overuse of sensitive vargas, but it does not
  yet perform a full professional event-by-event dasha/transit scoring pass.
- Product orchestration still needs to automatically launch the next
  `vedic-reader` round when the state returns `needs_more_feedback` or
  `needs_candidate_bound_checks`.
- Place coordinate correction still needs stricter timezone/radius rechecking
  after a rectified coordinate is selected.
