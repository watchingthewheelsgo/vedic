# Vedic Birth-Time Rectification

This document describes the active backend-owned rectification mechanism after
reported civil time and place have been canonicalized.

## Release principle

Rectification may narrow only the user's reported time window and permitted
place radius. It returns a bounded interval, equivalent intervals, or an
explicit underdetermined result. It never publishes an invented exact second.

The Reader Agent does not rank candidates. Confirming an event already supplied
by the user is not independent evidence and cannot change a chart score.

## Active flow

1. Canonicalize the reported local time with IANA historical timezone rules and
   resolve the place to WGS84 coordinates.
2. Calculate the base Chart Record and scan every minute of the complete allowed
   time window. Scan the place axis only when the location remains city-level or
   otherwise uncertain.
3. Coalesce contiguous equal fingerprints into bounded candidate intervals.
4. If one fingerprint is stable across the full window, retain the complete
   reported interval. The state is `not_required`; an optional Reader pass may
   ask 1-5 neutral reading-quality questions using only scan-stable facts.
5. If multiple material candidates remain, stop report synthesis and collect
   3-5 structured, dated life events. The UI asks for one event per round; after
   each accepted answer the backend recalculates the bounded candidate state and
   issues the next deterministic question. Consultation focus is never evidence.
6. Split eligible events without looking at candidate scores. Calibration keeps
   the broadest available category coverage; one date-precise event is reserved
   as a blind holdout. The Agent never receives holdout content, scores, or
   derived partitions.
7. Score each candidate from calibration events only. The current versioned
   policy records Dasha activation, relevant Varga domain activation, and stable
   Jupiter/Saturn double-transit support. Missing positive support is neutral,
   not fabricated contradiction evidence.
8. Select only when every candidate has the same calibration event set, at least
   two calibration events cover at least two mapped life domains, and the leader
   clears the declared absolute score and margin.
9. Evaluate the selected candidate or equivalence class against the reserved
   event. A failed or inconclusive holdout returns `underdetermined`.
10. Every passed candidate is recalculated once at its bounded representative
    time/place and becomes `corrected_chart_ready`, including when the selected
    interval contains the user's reported time. This canonical calculation does not start a second
    uncertainty search around the representative moment: the original candidate
    scan and refined boundaries remain the selection evidence. The final chart
    revision, audit, and report gate are then persisted as one active revision.

Every event mutation is serialized per session, checked against the chart
revision observed by the client, and recorded with an idempotency fingerprint.
A retry of an accepted answer returns the existing session instead of running
the calculator again. A stale answer is rejected and must be refreshed. The
same lock also protects the current interview while a skip or reset is being
prepared.

## Outcomes

- `collecting_evidence`: fewer than three recognized dated events.
- `underdetermined`: insufficient domain breadth, no clear calibration margin,
  or failed/inconclusive holdout.
- `multiple_equivalent`: several bounded candidates remain indistinguishable
  under all permitted evidence. No exact time is selected.
- `needs_recalculation`: a bounded interval passed calibration and holdout but has
  not yet been materialized as the active chart.
- `corrected_chart_ready`: the selected bounded interval passed and its chart was
  recalculated at the recorded representative moment.
- `input_resolution_required` / `calculation_failed`: civil-time/place or
  deterministic provider failure must be fixed before astrological questioning.

Only `corrected_chart_ready` with a passed holdout and an
open report gate may bypass Reader prevalidation. Stable `not_required` charts
still use the ordinary pre-reading quality check.

## Evidence contracts

- `birth_input_context.json`: immutable reported input and search constraints,
  separate reading focus and life-event ledger, plus an `activeCanonicalInput`
  that names the selected candidate interval and its representative calculation
  moment after correction.
- `sensitivity_scan.json`: full bounded scan, candidate intervals, scores,
  divisional sensitivity, provider errors, and report-readiness decision.
- `active_chart_sensitivity.json`: internal sensitivity contract produced from the
  canonical recalculation input after any selected bounded interval. Judgement uses this
  version while the original full-window scan remains the rectification audit.
- `chart_rectification_state.json`: active selection policy IDs, candidate state,
  hidden-holdout result, report gate, and materialized chart revision.
- `chart_record.json`: typed auditable chart, event evidence, candidates, and the
  final bounded decision consumed by judgement/report stages. Accepted event
  descriptions may also carry bounded semantic facts (`occurrence`, `agency`,
  `impact`, and `dateConfidence`) extracted by the evidence-intake Agent. These
  facts are provenance/context for downstream interpretation; they do not
  override the deterministic astrological score.
- `reader_prevalidation.md` / `prevalidation_result.json`: stable-chart reading
  quality checks only; they have no candidate-selection authority.

## Divisional sensitivity

The engine tracks `D1, D2, D3, D4, D5, D7, D9, D10, D12, D16, D20, D24,
D27, D30, D60` from the same canonical instant and calculation profile.

- D1 remains foundational.
- D2/D3/D4/D5/D7/D9/D10/D12 may split candidates when their declared
  rectification fields change.
- D16/D20/D24/D27/D30 are corroborative at narrower time windows.
- D60 is final-confirmation-only and cannot create first-pass candidates or
  independently select a birth time.

The backend uses computed transitions rather than assuming a fixed minutes-per-
division sensitivity. Optional sub-minute refinement searches only the selected
existing transition band, excludes D60-only changes, and returns an uncertainty
interval rather than an exact second.

## Current limits

- Event-house/karaka mappings and component weights are explicit versioned
  product hypotheses. The source-pinned workflow does not make those weights a
  universally accepted classical formula.
- Every `RectificationRecord` publishes its method maturity, validation status,
  policy IDs, and source IDs. Until independent professional blind-review
  fixtures exist, the contract remains `product_hypothesis` /
  `internal_regression_only`, and reports retain that limitation explicitly.
- The contradiction channel is intentionally unused until contrary rules have
  edition-pinned sources and professional review fixtures.
- Independent JHora desktop golden cases and professional end-to-end review
  fixtures are not yet populated, so release certification is incomplete.
- A Rectification Record cannot promote itself by changing maturity labels. Any
  `professionally_validated` result must reference a registered
  `professional_review` fixture whose retained artifact, hash, blind-review
  protocol, reviewer independence, and reviewed cases pass the fixture gate.
- One reserved event is a guard against direct fitting, not statistical proof.
  Sparse or same-domain histories correctly remain underdetermined.
- The product collects one structured dated event per interaction round. Each accepted
  answer recalculates the bounded candidates before the next question is selected.
  Adaptive follow-up should request genuinely new dated evidence or clarify date
  precision; it must never restate an existing event to manufacture another vote.
